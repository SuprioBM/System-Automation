"""Discord adapter.

Two halves that run in different processes, sharing one bot identity:
  - REST send functions below: called synchronously from the RQ worker to
    post an approval request (with Approve/Request-Changes/Reject buttons)
    using the bot token directly -- no gateway connection needed to send.
  - `DiscordBot`: the long-running gateway client (run via
    `python -m app.services.discord_bot_runner`) that actually receives the
    button-click/message interactions and relays them to this backend's
    POST /discord/approval, authenticated with DISCORD_CALLBACK_SHARED_SECRET.
Both send and receive share the same bot token/guild, so a click on a
worker-sent message is always caught by the gateway bot regardless of which
process sent the original message.
"""
from __future__ import annotations

import json

import discord
import requests

from app.core.config import require, settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.retry import with_retries

logger = get_logger("discord_service")
DISCORD_API = "https://discord.com/api/v10"


def _bot_headers() -> dict:
    return {"Authorization": f"Bot {require('DISCORD_BOT_TOKEN')}"}


def _components(approval_id: str) -> list[dict]:
    return [{
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "Approve", "custom_id": f"devsync:approve:{approval_id}"},
            {"type": 2, "style": 1, "label": "Request Changes", "custom_id": f"devsync:changes:{approval_id}"},
            {"type": 2, "style": 4, "label": "Reject", "custom_id": f"devsync:reject:{approval_id}"},
        ],
    }]


@with_retries("discord", "send_message", exceptions=(requests.ConnectionError, requests.Timeout))
def _send_message(channel_id: int, content: str, components: list[dict] | None = None,
                   file_bytes: bytes | None = None, filename: str | None = None) -> str:
    payload = {"content": content[:2000]}
    if components:
        payload["components"] = components
    if file_bytes and filename:
        res = requests.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=_bot_headers(),
            data={"payload_json": _json(payload)},
            files={"files[0]": (filename, file_bytes)},
            timeout=30,
        )
    else:
        res = requests.post(f"{DISCORD_API}/channels/{channel_id}/messages", headers=_bot_headers(),
                             json=payload, timeout=15)
    if res.status_code >= 300:
        raise ExternalServiceError("discord", "send_message", res.text, status_code=res.status_code)
    return res.json()["id"]


def send_approval_message(channel_id: int, content: str, approval_id: str,
                           file_bytes: bytes | None = None, filename: str | None = None) -> str:
    return _send_message(channel_id, content, _components(approval_id), file_bytes, filename)


@with_retries("discord", "edit_message", exceptions=(requests.ConnectionError, requests.Timeout))
def edit_message(channel_id: int, message_id: str, content: str, components: list[dict] | None = None) -> None:
    payload = {"content": content[:2000], "components": components or []}
    res = requests.patch(f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}", headers=_bot_headers(),
                          json=payload, timeout=15)
    if res.status_code >= 300:
        raise ExternalServiceError("discord", "edit_message", res.text, status_code=res.status_code)


def _json(payload: dict) -> str:
    return json.dumps(payload)


def build_approval_content(*, workflow_id: str, artifact_type: str, what_changed: str, why: str,
                            validation_summary: str, link: str | None) -> str:
    lines = [
        f"**DevSync approval — {artifact_type}**",
        f"Workflow: `{workflow_id}`",
        "",
        f"**What changed:** {what_changed}",
        f"**Why:** {why}",
        f"**Validation:** {validation_summary}",
    ]
    if link:
        lines.append(f"**Artifact:** {link}")
    return "\n".join(lines)


# ── Failure / recovery notifications ─────────────────────────────────────

def workflow_action_components(workflow_id: str) -> list[dict]:
    return [{
        "type": 1,
        "components": [
            {"type": 2, "style": 3, "label": "🔄 Resume", "custom_id": f"devsync:wfresume:{workflow_id}"},
            {"type": 2, "style": 4, "label": "❌ Cancel", "custom_id": f"devsync:wfcancel:{workflow_id}"},
        ],
    }]


def build_failure_content(*, project_name: str, repository: str, workflow_id: str, failed_node: str,
                           error_summary: str, attempts: int, completed_nodes: list[str],
                           timestamp: str, again: bool = False) -> str:
    checklist = "\n".join(f"✓ {n}" for n in completed_nodes) + (f"\n→ {failed_node} ← failed" if failed_node else "")
    title = "🔴 DevSync Workflow Failed Again" if again else "🔴 DevSync Workflow Failed"
    return (
        f"**{title}**\n\n"
        f"Project: {project_name}\n"
        f"Repository: {repository}\n\n"
        f"Workflow:\n`{workflow_id}`\n\n"
        f"Failed Node:\n{failed_node}\n\n"
        f"Error:\n{error_summary[:500]}\n\n"
        f"Attempts:\n{attempts}\n\n"
        f"Checkpoint:\n{checklist}\n\n"
        f"Time:\n{timestamp}"
    )


def build_resuming_content(*, workflow_id: str, resume_from_node: str, last_checkpoint: str, triggered_by: str) -> str:
    return (
        f"**🔄 DevSync Workflow Resuming**\n\n"
        f"Workflow:\n`{workflow_id}`\n\n"
        f"Resuming from:\n{resume_from_node}\n\n"
        f"Checkpoint:\n{last_checkpoint}\n\n"
        f"Triggered by:\n{triggered_by}"
    )


def build_completed_content(*, workflow_id: str) -> str:
    return f"**🟢 DevSync Workflow Completed**\n\nWorkflow:\n`{workflow_id}`"


def build_cancelled_content(*, workflow_id: str, cancelled_by: str) -> str:
    return f"**⚪ DevSync Workflow Cancelled**\n\nWorkflow:\n`{workflow_id}`\n\nCancelled by:\n{cancelled_by}"


def send_failure_notification(content: str, workflow_id: str) -> str:
    return _send_message(settings.discord_error_channel_id, content, workflow_action_components(workflow_id))


# ── Gateway bot (receiving side) ────────────────────────────────────────

class DiscordBot:
    def __init__(self, token: str):
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.token = token
        self.feedback_sessions: dict[int, dict] = {}  # user_id -> {approval_id}

        @self.client.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.client.user}")

        @self.client.event
        async def on_interaction(interaction: discord.Interaction):
            try:
                await self._handle_interaction(interaction)
            except Exception as e:
                log_error(logger, "interaction handling failed", exc=e, service="discord",
                          operation="on_interaction")

        @self.client.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return
            session = self.feedback_sessions.pop(message.author.id, None)
            if not session:
                return
            await self._callback(session["approval_id"], "changes_requested", message.content)
            await message.channel.send(f"Feedback recorded for `{session['approval_id']}`.")

    async def _handle_interaction(self, interaction: discord.Interaction) -> None:
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("devsync:"):
            return
        _, action, target_id = custom_id.split(":", 2)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if action in ("wfresume", "wfcancel"):
            authorized = settings.discord_authorized_user_ids
            if authorized and str(interaction.user.id) not in authorized:
                await interaction.followup.send("You're not authorized to control DevSync workflows.", ephemeral=True)
                logger.warning(f"unauthorized workflow-action attempt by discord user {interaction.user.id}")
                return
            result = await self._workflow_action_callback(
                target_id, "resume" if action == "wfresume" else "cancel", interaction.user.id
            )
            await interaction.followup.send(result, ephemeral=True)
            return

        if action == "changes":
            self.feedback_sessions[interaction.user.id] = {"approval_id": target_id}
            await interaction.followup.send("Send your requested changes as a chat message now.", ephemeral=True)
            return

        status = {"approve": "approved", "reject": "rejected"}.get(action)
        if not status:
            return
        result = await self._callback(target_id, status, None)
        await interaction.followup.send(result, ephemeral=True)

    async def _workflow_action_callback(self, workflow_id: str, action: str, discord_user_id: int) -> str:
        import asyncio
        try:
            res = await asyncio.to_thread(
                requests.post,
                f"{settings.APP_BASE_URL}/discord/workflow-action",
                json={"workflow_id": workflow_id, "action": action, "discord_user_id": str(discord_user_id)},
                headers={"X-DevSync-Secret": require("DISCORD_CALLBACK_SHARED_SECRET")},
                timeout=30,
            )
            if res.status_code >= 300:
                return f"Backend rejected the {action}: {res.text[:200]}"
            return f"{action.capitalize()} accepted for `{workflow_id}`."
        except Exception as e:
            log_error(logger, "workflow-action callback failed", exc=e, service="devsync_backend",
                      operation="workflow_action")
            return "Failed to reach the backend -- see server logs."

    async def _callback(self, approval_id: str, status: str, feedback: str | None) -> str:
        import asyncio
        try:
            res = await asyncio.to_thread(
                requests.post,
                f"{settings.APP_BASE_URL}/discord/approval",
                json={"approval_id": approval_id, "status": status, "feedback": feedback},
                headers={"X-DevSync-Secret": require("DISCORD_CALLBACK_SHARED_SECRET")},
                timeout=30,
            )
            if res.status_code >= 300:
                return f"Backend rejected the decision: {res.text[:200]}"
            return f"Recorded: {status}"
        except Exception as e:
            log_error(logger, "backend callback failed", exc=e, service="devsync_backend", operation="decide_approval")
            return "Failed to reach the backend -- see server logs."

    def start(self) -> None:
        self.client.run(self.token)

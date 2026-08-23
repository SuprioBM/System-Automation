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


@with_retries("discord", "send_approval_message", exceptions=(requests.ConnectionError, requests.Timeout))
def send_approval_message(channel_id: int, content: str, approval_id: str,
                           file_bytes: bytes | None = None, filename: str | None = None) -> str:
    payload = {"content": content[:2000], "components": _components(approval_id)}
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
        raise ExternalServiceError("discord", "send_approval_message", res.text, status_code=res.status_code)
    return res.json()["id"]


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
        _, action, approval_id = custom_id.split(":", 2)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if action == "changes":
            self.feedback_sessions[interaction.user.id] = {"approval_id": approval_id}
            await interaction.followup.send("Send your requested changes as a chat message now.", ephemeral=True)
            return

        status = {"approve": "approved", "reject": "rejected"}.get(action)
        if not status:
            return
        result = await self._callback(approval_id, status, None)
        await interaction.followup.send(result, ephemeral=True)

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

"""Builds and sends/updates the Discord failure-notification for a workflow,
given its checkpoint state and the exception that finally exhausted
recovery. Keeps this Discord-formatting logic out of tasks.py's job
orchestration and out of discord_service's generic send/receive plumbing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger, log_error
from app.services import discord_service, registry_service

logger = get_logger("failure_recovery_service")


def completed_nodes(checkpoint_state: dict) -> list[str]:
    timestamps = checkpoint_state.get("timestamps") or {}
    return list(timestamps.keys())


def _project_name(checkpoint_state: dict) -> str:
    project_data = checkpoint_state.get("project_data") or {}
    return project_data.get("name") or checkpoint_state.get("repository", "unknown")


def notify_failure(workflow_id: str, error: BaseException, checkpoint_state: dict) -> None:
    """Send (or, if this workflow already has a failure message, update in
    place per spec §17) the Discord failure notification with Resume/Cancel
    buttons. Never raises -- a notification failure must not mask the
    original workflow failure it's reporting on."""
    try:
        run = registry_service.get_workflow_run(workflow_id) or {}
        failed_node = getattr(error, "devsync_failed_node", None) or run.get("current_node") or "unknown"
        attempts = getattr(error, "devsync_attempt_count", None) or run.get("attempt_count") or 1
        again = bool(run.get("failure_message_id"))

        content = discord_service.build_failure_content(
            project_name=_project_name(checkpoint_state),
            repository=checkpoint_state.get("repository") or run.get("repository") or "unknown",
            workflow_id=workflow_id,
            failed_node=failed_node,
            error_summary=str(error),
            attempts=attempts,
            completed_nodes=completed_nodes(checkpoint_state),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            again=again,
        )

        if again and run.get("failure_message_id"):
            discord_service.edit_message(
                settings.discord_error_channel_id, run["failure_message_id"], content,
                discord_service.workflow_action_components(workflow_id),
            )
            message_id = run["failure_message_id"]
        else:
            message_id = discord_service.send_failure_notification(content, workflow_id)

        registry_service.update_workflow_run(workflow_id, failure_message_id=message_id)
    except Exception as e:
        log_error(logger, "failed to send/update Discord failure notification", exc=e,
                  service="discord", operation="notify_failure", workflow_id=workflow_id)


def notify_resuming(workflow_id: str, resume_from_node: str, checkpoint_state: dict, triggered_by: str) -> None:
    try:
        run = registry_service.get_workflow_run(workflow_id) or {}
        if not run.get("failure_message_id"):
            return
        nodes = completed_nodes(checkpoint_state)
        last_checkpoint = nodes[-1] if nodes else "none"
        discord_service.edit_message(
            settings.discord_error_channel_id, run["failure_message_id"],
            discord_service.build_resuming_content(
                workflow_id=workflow_id, resume_from_node=resume_from_node,
                last_checkpoint=last_checkpoint, triggered_by=triggered_by,
            ),
        )
    except Exception as e:
        log_error(logger, "failed to update Discord message to resuming", exc=e,
                  service="discord", operation="notify_resuming", workflow_id=workflow_id)


def notify_recovered(workflow_id: str) -> None:
    try:
        run = registry_service.get_workflow_run(workflow_id) or {}
        if not run.get("failure_message_id"):
            return
        discord_service.edit_message(
            settings.discord_error_channel_id, run["failure_message_id"],
            discord_service.build_completed_content(workflow_id=workflow_id),
        )
    except Exception as e:
        log_error(logger, "failed to update Discord message to completed", exc=e,
                  service="discord", operation="notify_recovered", workflow_id=workflow_id)


def notify_cancelled(workflow_id: str, cancelled_by: str) -> None:
    try:
        run = registry_service.get_workflow_run(workflow_id) or {}
        if not run.get("failure_message_id"):
            return
        discord_service.edit_message(
            settings.discord_error_channel_id, run["failure_message_id"],
            discord_service.build_cancelled_content(workflow_id=workflow_id, cancelled_by=cancelled_by),
        )
    except Exception as e:
        log_error(logger, "failed to update Discord message to cancelled", exc=e,
                  service="discord", operation="notify_cancelled", workflow_id=workflow_id)

"""Pause/approval approver resolution and pending notifications.

A pause node can pin an optional `approverIds` list in its config. When set,
only those users (plus superusers) may submit values/decisions; when absent,
the workflow owner plus team owners/admins fall back (the current write
permission set). The same resolution feeds both the submit endpoint check and
the pending notification so the two can never disagree.
"""

import logging
from typing import TYPE_CHECKING, cast
from uuid import UUID

from app.core.i18n import t
from app.models.notification import (
    AutoNotificationType,
    Notification,
    NotificationLevel,
)
from app.models.user import TeamMember, User
from app.schemas.team import TeamMemberRole
from app.services.auto_notification import AutoNotificationService

if TYPE_CHECKING:
    from app.models.workflow import Workflow, WorkflowRun

logger = logging.getLogger(__name__)

APPROVER_IDS_KEY = "approverIds"


async def _active_user_ids(user_ids: list[UUID]) -> set[UUID]:
    """Return active user ids without trusting stale membership snapshots."""
    if not user_ids:
        return set()
    rows = cast(
        list[UUID | tuple[UUID]],
        await User.filter(id__in=user_ids, is_active=True).values_list("id", flat=True),
    )
    return {row[0] if isinstance(row, tuple) else row for row in rows}


async def resolve_pause_approver_ids(workflow: "Workflow", config: dict) -> list[UUID]:
    """Return currently active users authorized for this pause request.

    A non-empty configured list never falls back: stale, malformed, or removed
    configured users must not broaden access to the workflow owner/admin set.
    An absent or empty list intentionally uses that owner/admin fallback.
    """
    raw = config.get(APPROVER_IDS_KEY) if isinstance(config, dict) else None
    if raw:
        if not isinstance(raw, list):
            logger.warning("Invalid pause approver list %r", raw)
            return []
        configured: list[UUID] = []
        for item in raw:
            try:
                user_id = UUID(str(item))
            except (ValueError, TypeError):
                logger.warning("Skipping invalid approver id %r in pause config", item)
                continue
            if user_id not in configured:
                configured.append(user_id)
        if not configured:
            return []
        member_rows = cast(
            list[UUID | tuple[UUID]],
            await TeamMember.filter(
                team_id=workflow.team_id,
                user_id__in=configured,
            ).values_list("user_id", flat=True),
        )
        member_ids = {row[0] if isinstance(row, tuple) else row for row in member_rows}
        active_ids = await _active_user_ids(
            [user_id for user_id in configured if user_id in member_ids]
        )
        return [user_id for user_id in configured if user_id in active_ids]

    owner_id = getattr(workflow, "created_by_id", None)
    candidates = [owner_id] if owner_id else []
    rows = cast(
        list[UUID | tuple[UUID]],
        await TeamMember.filter(
            team_id=workflow.team_id,
            role__in=[TeamMemberRole.OWNER, TeamMemberRole.ADMIN],
        ).values_list("user_id", flat=True),
    )
    for row in rows:
        user_id = row[0] if isinstance(row, tuple) else row
        if user_id not in candidates:
            candidates.append(user_id)
    active_ids = await _active_user_ids(candidates)
    return [user_id for user_id in candidates if user_id in active_ids]


async def notify_pause_pending(
    run: "WorkflowRun",
    config: dict,
    node_name: str,
    pause_request_id: object | None = None,
    node_id: str | None = None,
    description: str | None = None,
) -> None:
    """Notify the approvers that the run is waiting for input.

    Best-effort: a notification failure must never block or fail the run.
    """
    try:
        await run.fetch_related("workflow")
        workflow = run.workflow
        if workflow is None:
            return
        approver_ids = await resolve_pause_approver_ids(workflow, config)
        if not approver_ids:
            return
        users = await User.filter(id__in=approver_ids, is_active=True)
        if not users:
            return
        resolved = (description or "").strip()
        is_approval = str(config.get("mode") or "variables") == "approval"
        title_key = (
            "notify_workflow_approval_pending_title"
            if is_approval
            else "notify_workflow_input_pending_title"
        )
        content_key = (
            "notify_workflow_approval_pending_content"
            if is_approval
            else "notify_workflow_input_pending_content"
        )
        for user in users:
            lang = user.locale or "en"
            user_content = t(
                content_key,
                lang=lang,
                workflow_name=workflow.name,
                node_name=node_name,
            )
            if resolved:
                user_content = f"{user_content}\n\n{resolved}"
            await AutoNotificationService.send_to_user(
                notification_type=AutoNotificationType.WORKFLOW_PAUSE_PENDING,
                user_id=user.id,
                title=t(title_key, lang=lang),
                content=user_content,
                # The run page requires type=workflow; /run defaults to agent mode.
                link_url=f"/run/{workflow.id}?type=workflow&run={run.id}",
                # High priority so the notification center surfaces it as a
                # prominent dialog for the approver.
                level=NotificationLevel.HIGH,
                data={
                    "run_id": str(run.id),
                    "workflow_id": str(workflow.id),
                    "node_id": node_id or "",
                    "pause_request_id": str(pause_request_id)
                    if pause_request_id is not None
                    else None,
                },
            )
    except Exception:
        logger.exception("Failed to notify pause approvers for run %s", run.id)


async def remove_pause_pending_notification_for(
    pause_request_id: object, user_id: object
) -> None:
    """Delete one recipient's pending-approval notification.

    Used by require-all approvals: each approver's own notification is
    removed as soon as they submit, while the others keep theirs until the
    request resolves.
    """
    try:
        rows = await Notification.filter(
            type=AutoNotificationType.WORKFLOW_PAUSE_PENDING.value,
            user_id=user_id,
        ).all()
        matching = [
            n.id
            for n in rows
            if (n.data or {}).get("pause_request_id") == str(pause_request_id)
        ]
        if matching:
            await Notification.filter(id__in=matching).delete()
    except Exception:
        logger.exception(
            "Failed to remove pause pending notification for request %s user %s",
            pause_request_id,
            user_id,
        )


async def remove_pause_pending_notifications(pause_request_id: object) -> None:
    """Delete the pending-approval notifications for a resolved pause request.

    The notification is a one-shot task reminder; once the request is
    submitted (or the run cancelled) it must stop showing an actionable
    approve/reject state in the notification center.
    """
    try:
        rows = await Notification.filter(
            type=AutoNotificationType.WORKFLOW_PAUSE_PENDING.value
        ).all()
        matching = [
            n.id
            for n in rows
            if (n.data or {}).get("pause_request_id") == str(pause_request_id)
        ]
        if matching:
            await Notification.filter(id__in=matching).delete()
    except Exception:
        logger.exception(
            "Failed to remove pause pending notifications for request %s",
            pause_request_id,
        )


async def validate_pause_approvers(team_id: UUID, definition: object) -> list[str]:
    """Return the invalid approver ids pinned by pause nodes in a definition.

    The editor only offers team members, but the saved definition is the
    contract: every `approverIds` entry must be an existing, active member of
    the workflow's team. Unparseable ids count as invalid so a broken config
    fails at save time instead of stranding a run at approval with no one able
    to act (superuser aside).
    """
    if not isinstance(definition, dict):
        return []
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return []

    raw_ids: set[UUID] = set()
    invalid_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "pause":
            continue
        data = node.get("data")
        if not isinstance(data, dict):
            continue
        config = data.get("pauseConfig") or data.get("config")
        if not isinstance(config, dict):
            continue
        raw = config.get(APPROVER_IDS_KEY)
        if raw is not None and not isinstance(raw, list):
            invalid_ids.append(str(raw))
            continue
        if raw is None:
            continue
        for item in raw:
            try:
                raw_ids.add(UUID(str(item)))
            except (ValueError, TypeError):
                # Unparseable ids are invalid by definition.
                invalid_ids.append(str(item))
    if not raw_ids:
        return invalid_ids

    members = await TeamMember.filter(
        team_id=team_id, user_id__in=raw_ids
    ).prefetch_related("user")
    valid: set[UUID] = set()
    for member in members:
        user = getattr(member, "user", None)
        if user is not None and getattr(user, "is_active", True):
            valid.add(user.id)

    invalid_ids.extend(str(uid) for uid in sorted(raw_ids) if uid not in valid)
    return invalid_ids

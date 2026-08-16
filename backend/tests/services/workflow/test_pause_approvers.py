from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services.workflow import pause_approvers
from app.services.workflow.pause_approvers import (
    resolve_pause_approver_ids,
    notify_pause_pending,
    validate_pause_approvers,
)


def _team_members(*user_ids):
    return SimpleNamespace(values_list=AsyncMock(return_value=list(user_ids)))


@pytest.mark.asyncio
async def test_resolve_uses_configured_approver_ids(monkeypatch):
    owner_id, member_id, bad = uuid4(), uuid4(), "not-a-uuid"
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember, "filter", Mock(return_value=_team_members())
    )

    ids = await resolve_pause_approver_ids(
        workflow, {"mode": "approval", "approverIds": [str(member_id), bad]}
    )

    assert ids == [member_id]
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_falls_back_to_owner_and_team_admins(monkeypatch):
    owner_id, admin_id = uuid4(), uuid4()
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    # The query itself enforces role__in; the mock returns only the admin row.
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(admin_id)),
    )

    ids = await resolve_pause_approver_ids(workflow, {"mode": "variables"})

    # owner first, then admin; plain members excluded by the query
    assert ids == [owner_id, admin_id]
    pause_approvers.TeamMember.filter.assert_called_once_with(
        team_id=workflow.team_id,
        role__in=[
            pause_approvers.TeamMemberRole.OWNER,
            pause_approvers.TeamMemberRole.ADMIN,
        ],
    )


@pytest.mark.asyncio
async def test_resolve_handles_missing_owner(monkeypatch):
    admin_id = uuid4()
    workflow = SimpleNamespace(created_by_id=None, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(admin_id)),
    )

    assert await resolve_pause_approver_ids(workflow, {}) == [admin_id]


@pytest.mark.asyncio
async def test_resolve_invalid_only_approvers_falls_back(monkeypatch):
    owner_id = uuid4()
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members()),
    )

    ids = await resolve_pause_approver_ids(
        workflow, {"approverIds": ["junk", "also-junk"]}
    )

    assert ids == [owner_id]


@pytest.mark.asyncio
async def test_notify_sends_user_notifications_with_link(monkeypatch):
    run_id, workflow_id, approver_id = uuid4(), uuid4(), uuid4()
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=None, team_id=uuid4()
    )
    run = SimpleNamespace(id=run_id, workflow=workflow)
    run.fetch_related = AsyncMock()
    approver = SimpleNamespace(id=approver_id, username="alice", locale="zh")
    send = AsyncMock()

    monkeypatch.setattr(
        pause_approvers.User, "filter", AsyncMock(return_value=[approver])
    )
    monkeypatch.setattr(pause_approvers.AutoNotificationService, "send_to_user", send)

    await notify_pause_pending(
        run,
        {"approverIds": [str(approver_id)]},
        "审批",
        pause_request_id=uuid4(),
        node_id="pause-1",
        description="Review the quote",
    )

    send.assert_awaited_once()
    kwargs = send.await_args.kwargs
    assert kwargs["user_id"] == approver_id
    assert kwargs["link_url"] == f"/run/{workflow_id}?run={run_id}"
    assert kwargs["level"] == pause_approvers.NotificationLevel.HIGH
    assert kwargs["data"]["pause_request_id"] is not None
    assert kwargs["data"]["node_id"] == "pause-1"
    assert "Review the quote" in kwargs["content"]
    assert "审批" in kwargs["content"]
    assert "Flow" in kwargs["content"]


@pytest.mark.asyncio
async def test_notify_skips_missing_workflow(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow=None)
    run.fetch_related = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(pause_approvers.AutoNotificationService, "send_to_user", send)

    await notify_pause_pending(run, {}, "Pause")

    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_never_raises_on_failure(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow=None)
    run.fetch_related = AsyncMock(side_effect=RuntimeError("db down"))

    # must not raise: notification is best-effort
    await notify_pause_pending(run, {}, "Pause")


@pytest.mark.asyncio
async def test_validate_approvers_accepts_active_team_members(monkeypatch):
    team_id, member_id = uuid4(), uuid4()
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {
                    "pauseConfig": {"mode": "approval", "approverIds": [str(member_id)]}
                },
            }
        ]
    }
    member = SimpleNamespace(
        user_id=member_id, user=SimpleNamespace(id=member_id, is_active=True)
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(
            return_value=SimpleNamespace(
                prefetch_related=AsyncMock(return_value=[member])
            )
        ),
    )

    assert await validate_pause_approvers(team_id, definition) == []
    pause_approvers.TeamMember.filter.assert_called_once_with(
        team_id=team_id, user_id__in={member_id}
    )


@pytest.mark.asyncio
async def test_validate_approvers_flags_unknown_inactive_and_bad_ids(monkeypatch):
    team_id, member_id = uuid4(), uuid4()
    inactive_id, unknown_id = uuid4(), uuid4()
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {
                    "pauseConfig": {
                        "mode": "approval",
                        "approverIds": [
                            str(member_id),
                            str(inactive_id),
                            str(unknown_id),
                            "not-a-uuid",
                        ],
                    }
                },
            }
        ]
    }
    member = SimpleNamespace(
        user_id=member_id, user=SimpleNamespace(id=member_id, is_active=True)
    )
    inactive = SimpleNamespace(
        user_id=inactive_id, user=SimpleNamespace(id=inactive_id, is_active=False)
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(
            return_value=SimpleNamespace(
                prefetch_related=AsyncMock(return_value=[member, inactive])
            )
        ),
    )

    invalid = await validate_pause_approvers(team_id, definition)

    assert str(unknown_id) in invalid
    assert str(inactive_id) in invalid
    assert "not-a-uuid" in invalid
    assert str(member_id) not in invalid


@pytest.mark.asyncio
async def test_validate_approvers_ignores_non_pause_nodes(monkeypatch):
    team_id = uuid4()
    definition = {
        "nodes": [
            {
                "id": "llm-1",
                "type": "llm",
                "data": {"config": {"approverIds": [str(uuid4())]}},
            }
        ]
    }
    filter_mock = Mock()
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", filter_mock)

    assert await validate_pause_approvers(team_id, definition) == []
    filter_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remove_pause_pending_notifications_matches_request(monkeypatch):
    target_id, other_id = uuid4(), uuid4()
    rows = [
        SimpleNamespace(id=uuid4(), data={"pause_request_id": str(target_id)}),
        SimpleNamespace(id=uuid4(), data={"pause_request_id": str(other_id)}),
        SimpleNamespace(id=uuid4(), data=None),
    ]
    delete = AsyncMock(return_value=1)
    captured: dict = {}

    def filter_side_effect(**kwargs):
        if "id__in" in kwargs:
            captured["ids"] = kwargs["id__in"]
            return SimpleNamespace(delete=delete)
        return SimpleNamespace(all=AsyncMock(return_value=rows))

    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=filter_side_effect),
    )

    await pause_approvers.remove_pause_pending_notifications(target_id)

    delete.assert_awaited_once()
    # only the request-matching notification is removed, others kept
    assert captured["ids"] == [rows[0].id]


@pytest.mark.asyncio
async def test_remove_pause_pending_notifications_never_raises(monkeypatch):
    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=RuntimeError("db down")),
    )

    # best-effort cleanup must not break the submit/cancel flow
    await pause_approvers.remove_pause_pending_notifications(uuid4())


@pytest.mark.asyncio
async def test_notify_uses_mode_specific_copy(monkeypatch):
    run_id, workflow_id, approver_id = uuid4(), uuid4(), uuid4()
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=None, team_id=uuid4()
    )
    run = SimpleNamespace(id=run_id, workflow=workflow)
    run.fetch_related = AsyncMock()
    approver = SimpleNamespace(id=approver_id, username="alice", locale="en")
    send = AsyncMock()
    monkeypatch.setattr(
        pause_approvers.User, "filter", AsyncMock(return_value=[approver])
    )
    monkeypatch.setattr(pause_approvers.AutoNotificationService, "send_to_user", send)

    # approval mode -> approval copy
    await notify_pause_pending(
        run,
        {"approverIds": [str(approver_id)], "mode": "approval"},
        "Approval",
        pause_request_id=uuid4(),
    )
    approval_kwargs = send.await_args.kwargs
    assert approval_kwargs["title"] == "Workflow approval requested"
    assert "waiting for approval" in approval_kwargs["content"]

    # variables mode -> input copy
    await notify_pause_pending(
        run,
        {"approverIds": [str(approver_id)], "mode": "variables"},
        "Input",
        pause_request_id=uuid4(),
    )
    input_kwargs = send.await_args.kwargs
    assert input_kwargs["title"] == "Workflow input requested"
    assert "waiting for input" in input_kwargs["content"]

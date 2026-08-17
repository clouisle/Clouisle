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


class _UserQuery:
    def __init__(self, active_ids=(), users=()):
        self.active_ids = list(active_ids)
        self.users = list(users)

    async def values_list(self, *_args, **_kwargs):
        return self.active_ids

    def __await__(self):
        async def collect():
            return self.users

        return collect().__await__()


@pytest.mark.asyncio
async def test_resolve_uses_current_active_configured_members(monkeypatch):
    owner_id, member_id, bad = uuid4(), uuid4(), "not-a-uuid"
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(member_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[member_id])),
    )

    ids = await resolve_pause_approver_ids(
        workflow, {"mode": "approval", "approverIds": [str(member_id), bad]}
    )

    assert ids == [member_id]
    pause_approvers.TeamMember.filter.assert_called_once_with(
        team_id=workflow.team_id, user_id__in=[member_id]
    )


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
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[owner_id, admin_id])),
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
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[admin_id])),
    )

    assert await resolve_pause_approver_ids(workflow, {}) == [admin_id]


@pytest.mark.asyncio
async def test_resolve_invalid_configured_approvers_fails_closed(monkeypatch):
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

    assert ids == []


@pytest.mark.asyncio
async def test_resolve_excludes_departed_or_deactivated_configured_members(monkeypatch):
    active_id, departed_id = uuid4(), uuid4()
    workflow = SimpleNamespace(created_by_id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(active_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[active_id])),
    )

    ids = await resolve_pause_approver_ids(
        workflow, {"approverIds": [str(active_id), str(departed_id)]}
    )

    assert ids == [active_id]


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
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(approver_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[approver_id], users=[approver])),
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
    assert kwargs["link_url"] == f"/run/{workflow_id}?type=workflow&run={run_id}"
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
async def test_validate_approvers_rejects_non_list_values(monkeypatch):
    definition = {
        "nodes": [
            {
                "type": "pause",
                "data": {"pauseConfig": {"approverIds": "not-a-list"}},
            }
        ]
    }
    filter_mock = Mock()
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", filter_mock)

    assert await validate_pause_approvers(uuid4(), definition) == ["not-a-list"]
    filter_mock.assert_not_called()


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
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(approver_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[approver_id], users=[approver])),
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


@pytest.mark.asyncio
async def test_remove_pause_pending_notification_for_deletes_matching(monkeypatch):
    """单审批人提交后只移除其本人那条通知（require-all 流程）。"""
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

    await pause_approvers.remove_pause_pending_notification_for(target_id, uuid4())

    delete.assert_awaited_once()
    assert captured["ids"] == [rows[0].id]


@pytest.mark.asyncio
async def test_resolve_non_dict_config_falls_back(monkeypatch):
    """config 不是 dict 时按无配置处理，走 owner/admin 兜底。"""
    owner_id = uuid4()
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members()),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[owner_id])),
    )

    assert await resolve_pause_approver_ids(workflow, "not-a-dict") == [owner_id]


@pytest.mark.asyncio
async def test_resolve_rejects_non_list_approvers(monkeypatch):
    """配置的 approverIds 不是列表时 fail-closed，绝不落到兜底。"""
    workflow = SimpleNamespace(created_by_id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    monkeypatch.setattr(pause_approvers.User, "filter", Mock())

    assert await resolve_pause_approver_ids(workflow, {"approverIds": "all"}) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_deduplicates_configured_approvers(monkeypatch):
    """配置里重复的 id 只保留一次，且只查询一次成员表。"""
    member_id = uuid4()
    workflow = SimpleNamespace(created_by_id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(member_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[member_id])),
    )

    ids = await resolve_pause_approver_ids(
        workflow, {"approverIds": [str(member_id), str(member_id)]}
    )

    assert ids == [member_id]
    pause_approvers.TeamMember.filter.assert_called_once_with(
        team_id=workflow.team_id, user_id__in=[member_id]
    )


@pytest.mark.asyncio
async def test_resolve_empty_when_all_configured_invalid(monkeypatch):
    """配置的 id 全部无法解析时返回空（不触达成员/用户查询）。"""
    workflow = SimpleNamespace(created_by_id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    monkeypatch.setattr(pause_approvers.User, "filter", Mock())

    assert (
        await resolve_pause_approver_ids(workflow, {"approverIds": ["nope", 42]}) == []
    )
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_fallback_deduplicates_owner_admin(monkeypatch):
    """owner 同时出现在团队 admin 列表时不重复返回。"""
    owner_id = uuid4()
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(owner_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[owner_id])),
    )

    assert await resolve_pause_approver_ids(workflow, {}) == [owner_id]


@pytest.mark.asyncio
async def test_resolve_fallback_handles_tuple_rows(monkeypatch):
    """values_list 返回 tuple 行时同样解析为 user_id。"""
    owner_id, admin_id = uuid4(), uuid4()
    workflow = SimpleNamespace(created_by_id=owner_id, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members((admin_id,))),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[owner_id, admin_id])),
    )

    ids = await resolve_pause_approver_ids(workflow, {})
    assert ids == [owner_id, admin_id]


@pytest.mark.asyncio
async def test_notify_send_failure_never_raises(monkeypatch):
    """send_to_user 抛错时通知不阻断运行。"""
    run_id, workflow_id, approver_id = uuid4(), uuid4(), uuid4()
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=None, team_id=uuid4()
    )
    run = SimpleNamespace(id=run_id, workflow=workflow)
    run.fetch_related = AsyncMock()

    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(approver_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(
            return_value=_UserQuery(
                active_ids=[approver_id],
                users=[SimpleNamespace(id=approver_id, username="alice", locale="zh")],
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.AutoNotificationService,
        "send_to_user",
        AsyncMock(side_effect=RuntimeError("notify down")),
    )

    # must not raise: notification is best-effort
    await notify_pause_pending(run, {"approverIds": [str(approver_id)]}, "Pause")


@pytest.mark.asyncio
async def test_validate_ignores_non_dict_definition(monkeypatch):
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), "not-a-definition") == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_validate_skips_node_with_non_dict_data(monkeypatch):
    definition = {
        "nodes": [
            {"id": "pause-1", "type": "pause", "data": "broken"},
        ]
    }
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), definition) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_validate_returns_invalid_when_all_ids_unparseable(monkeypatch):
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {"pauseConfig": {"approverIds": ["nope", 42]}},
            }
        ]
    }
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    invalid = await validate_pause_approvers(uuid4(), definition)
    assert invalid == ["nope", "42"]
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_validate_flags_member_without_user(monkeypatch):
    team_id, member_id = uuid4(), uuid4()
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {"pauseConfig": {"approverIds": [str(member_id)]}},
            }
        ]
    }
    member = SimpleNamespace(user_id=member_id, user=None)
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(
            return_value=SimpleNamespace(
                prefetch_related=AsyncMock(return_value=[member])
            )
        ),
    )

    invalid = await validate_pause_approvers(team_id, definition)
    assert invalid == [str(member_id)]


@pytest.mark.asyncio
async def test_resolve_fallback_empty_without_owner_or_admins(monkeypatch):
    """既无 owner 也无团队 admin 时兜底返回空（_active_user_ids 收到空列表）。"""
    workflow = SimpleNamespace(created_by_id=None, team_id=uuid4())
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members()),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[])),
    )

    assert await resolve_pause_approver_ids(workflow, {}) == []


@pytest.mark.asyncio
async def test_notify_skips_when_no_approvers_resolved(monkeypatch):
    """解析不到审批人时不发通知。"""
    run = SimpleNamespace(
        id=uuid4(),
        workflow=SimpleNamespace(id=uuid4(), name="Flow", team_id=uuid4()),
    )
    run.fetch_related = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members()),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[])),
    )
    monkeypatch.setattr(pause_approvers.AutoNotificationService, "send_to_user", send)

    await notify_pause_pending(run, {}, "Pause")

    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_skips_when_no_active_users(monkeypatch):
    """审批人在案但已停用时跳过通知。"""
    run_id, workflow_id, approver_id = uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        workflow=SimpleNamespace(id=workflow_id, name="Flow", team_id=uuid4()),
    )
    run.fetch_related = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=_team_members(approver_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        Mock(return_value=_UserQuery(active_ids=[approver_id], users=[])),
    )
    monkeypatch.setattr(pause_approvers.AutoNotificationService, "send_to_user", send)

    await notify_pause_pending(run, {"approverIds": [str(approver_id)]}, "Pause")

    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_pause_pending_notification_for_never_raises(monkeypatch):
    """单条移除的通知查询失败时不抛出。"""
    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=RuntimeError("db down")),
    )

    await pause_approvers.remove_pause_pending_notification_for(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_validate_pause_node_without_approver_ids(monkeypatch):
    """暂停节点未配置 approverIds 时直接跳过。"""
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {"pauseConfig": {"mode": "approval"}},
            }
        ]
    }
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), definition) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_validate_empty_approver_list(monkeypatch):
    """approverIds 为空列表时不进入成员校验。"""
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {"pauseConfig": {"approverIds": []}},
            }
        ]
    }
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), definition) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_remove_pause_pending_notification_for_delete_failure_never_raises(
    monkeypatch,
):
    """匹配到通知后删除失败也不抛出。"""
    target_id = uuid4()
    rows = [SimpleNamespace(id=uuid4(), data={"pause_request_id": str(target_id)})]
    delete = AsyncMock(side_effect=RuntimeError("db down"))

    def filter_side_effect(**kwargs):
        if "id__in" in kwargs:
            return SimpleNamespace(delete=delete)
        return SimpleNamespace(all=AsyncMock(return_value=rows))

    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=filter_side_effect),
    )

    await pause_approvers.remove_pause_pending_notification_for(target_id, uuid4())


@pytest.mark.asyncio
async def test_validate_reads_legacy_config_key(monkeypatch):
    """旧版节点只用 config 键时同样读取 approverIds。"""
    team_id, member_id = uuid4(), uuid4()
    definition = {
        "nodes": [
            {
                "id": "pause-1",
                "type": "pause",
                "data": {"config": {"approverIds": [str(member_id)]}},
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


@pytest.mark.asyncio
async def test_validate_ignores_non_list_nodes(monkeypatch):
    definition = {"nodes": "broken"}
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), definition) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_validate_skips_pause_node_with_non_dict_config(monkeypatch):
    definition = {
        "nodes": [{"id": "pause-1", "type": "pause", "data": {"pauseConfig": "broken"}}]
    }
    monkeypatch.setattr(pause_approvers.TeamMember, "filter", Mock())
    assert await validate_pause_approvers(uuid4(), definition) == []
    pause_approvers.TeamMember.filter.assert_not_called()


@pytest.mark.asyncio
async def test_remove_pause_pending_notifications_delete_failure_never_raises(
    monkeypatch,
):
    """匹配到多条通知后批量删除失败也不抛出。"""
    target_id = uuid4()
    rows = [SimpleNamespace(id=uuid4(), data={"pause_request_id": str(target_id)})]
    delete = AsyncMock(side_effect=RuntimeError("db down"))

    def filter_side_effect(**kwargs):
        if "id__in" in kwargs:
            return SimpleNamespace(delete=delete)
        return SimpleNamespace(all=AsyncMock(return_value=rows))

    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=filter_side_effect),
    )

    await pause_approvers.remove_pause_pending_notifications(target_id)


@pytest.mark.asyncio
async def test_remove_pause_pending_notification_for_keeps_unrelated(monkeypatch):
    """没有匹配本请求的通知时不删除任何东西。"""
    other_id = uuid4()
    rows = [SimpleNamespace(id=uuid4(), data={"pause_request_id": str(other_id)})]
    delete = AsyncMock()
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

    await pause_approvers.remove_pause_pending_notification_for(uuid4(), uuid4())

    delete.assert_not_awaited()
    assert "ids" not in captured


@pytest.mark.asyncio
async def test_remove_pause_pending_notifications_keeps_unrelated(monkeypatch):
    """批量移除时同样只删匹配请求的通知。"""
    other_id = uuid4()
    rows = [SimpleNamespace(id=uuid4(), data={"pause_request_id": str(other_id)})]
    delete = AsyncMock()

    def filter_side_effect(**kwargs):
        if "id__in" in kwargs:
            return SimpleNamespace(delete=delete)
        return SimpleNamespace(all=AsyncMock(return_value=rows))

    monkeypatch.setattr(
        pause_approvers.Notification,
        "filter",
        Mock(side_effect=filter_side_effect),
    )

    await pause_approvers.remove_pause_pending_notifications(uuid4())

    delete.assert_not_awaited()

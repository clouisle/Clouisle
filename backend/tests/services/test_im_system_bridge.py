from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.timezone import now_utc
from app.models.im import ImMessageType
from app.models.notification import Notification, NotificationLevel, NotificationScope
from app.services import im_system_bridge


class _RecordingLock:
    """记录加锁/释放，用于断言分布式锁没有泄漏。"""

    instances: list[_RecordingLock] = []

    def __init__(self, key: str, lease_seconds: int = 10) -> None:
        self.key = key
        self.lease_seconds = lease_seconds
        self.entered = False
        self.exited = False
        _RecordingLock.instances.append(self)

    async def __aenter__(self) -> bool:
        self.entered = True
        return True

    async def __aexit__(self, *exc_info: object) -> None:
        self.exited = True


class _FakeTransaction:
    async def __aenter__(self) -> _FakeTransaction:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _fake_transaction() -> _FakeTransaction:
    return _FakeTransaction()


def _notification(
    type_: str,
    scope: NotificationScope,
    *,
    user_id: UUID | None = None,
    team_id: UUID | None = None,
) -> Notification:
    notif = Notification(
        id=uuid4(),
        scope=scope,
        type=type_,
        title="Title",
        content="Body",
        level=NotificationLevel.LOW,
        created_at=now_utc(),
    )
    notif.user_id = user_id
    notif.team_id = team_id
    return notif


def _notification_query_mock(
    pages: list[list[Notification]],
) -> tuple[MagicMock, MagicMock]:
    """模拟 Notification.filter(...).order_by(...).limit(...).all() 的分页返回。"""
    all_mock = AsyncMock(side_effect=pages)
    limit_mock = MagicMock(return_value=AsyncMock(all=all_mock))
    order_by_mock = MagicMock(return_value=MagicMock(limit=limit_mock))
    filter_mock = MagicMock(return_value=MagicMock(order_by=order_by_mock))
    return filter_mock, limit_mock


@pytest.fixture(autouse=True)
def _reset_recording_locks() -> None:
    _RecordingLock.instances.clear()


@pytest.mark.asyncio
async def test_bridge_user_notification_to_im() -> None:
    user_id = uuid4()
    team_id = uuid4()
    notif = Notification(
        id=uuid4(),
        scope=NotificationScope.USER,
        type="workflow.pause_pending",
        title="Workflow Paused",
        content="Waiting for approval",
        level=NotificationLevel.HIGH,
        data={"run_id": "run-123"},
    )
    notif.user_id = user_id
    notif.team_id = team_id

    with patch(
        "app.services.im_service.send_system_message", new_callable=AsyncMock
    ) as mock_send:
        await im_system_bridge.bridge_notification_to_im(notif)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["team_id"] == team_id
        assert call_kwargs["recipient_user_id"] == user_id
        assert call_kwargs["msg_type"] == ImMessageType.CARD
        assert "Workflow Paused" in call_kwargs["content"]
        assert call_kwargs["payload"]["data"] == {"run_id": "run-123"}


@pytest.mark.asyncio
async def test_bridge_user_notification_without_team_prefers_default_team() -> None:
    user_id = uuid4()
    default_team_id = uuid4()
    notif = _notification("notice", NotificationScope.USER, user_id=user_id)
    membership = MagicMock(team_id=default_team_id)
    query = MagicMock()
    query.order_by = MagicMock(
        return_value=MagicMock(first=AsyncMock(return_value=membership))
    )

    with (
        patch(
            "app.models.user.TeamMember.filter",
            return_value=query,
        ) as mock_filter,
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        await im_system_bridge.bridge_notification_to_im(notif)

        # 只查默认团队，且排序显式指定，保证结果确定
        mock_filter.assert_called_once()
        assert mock_filter.call_args.kwargs["team__is_default"] is True
        mock_filter.return_value.order_by.assert_called_once_with("joined_at", "id")
        assert mock_send.call_args.kwargs["team_id"] == default_team_id


@pytest.mark.asyncio
async def test_bridge_user_notification_falls_back_to_oldest_membership() -> None:
    user_id = uuid4()
    fallback_team_id = uuid4()
    notif = _notification("notice", NotificationScope.USER, user_id=user_id)
    membership = MagicMock(team_id=fallback_team_id)
    queries: list[MagicMock] = []

    def fake_member_filter(**kwargs: object) -> MagicMock:
        query = MagicMock(
            first=AsyncMock(
                return_value=None if kwargs.get("team__is_default") else membership
            )
        )
        query.order_by = MagicMock(return_value=query)
        queries.append(query)
        return query

    with (
        patch(
            "app.models.user.TeamMember.filter", side_effect=fake_member_filter
        ) as mock_filter,
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        await im_system_bridge.bridge_notification_to_im(notif)

        assert mock_filter.call_count == 2
        assert mock_filter.call_args_list[0].kwargs["team__is_default"] is True
        assert "team__is_default" not in mock_filter.call_args_list[1].kwargs
        queries[1].order_by.assert_called_once_with("joined_at", "id")
        assert mock_send.call_args.kwargs["team_id"] == fallback_team_id


@pytest.mark.asyncio
async def test_sync_legacy_notifications_for_user_skips_already_imported() -> None:
    user_id = uuid4()
    team_id = uuid4()
    conv = MagicMock(id=uuid4(), latest_seq=1, save=AsyncMock())
    imported = _notification("notice", NotificationScope.GLOBAL)
    filter_mock, limit_mock = _notification_query_mock([[imported]])

    with (
        patch("app.services.im_redis.DistributedLock", _RecordingLock),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(
                values_list=AsyncMock(
                    return_value=[im_system_bridge._legacy_client_msg_id(imported.id)]
                )
            ),
        ),
        patch("app.models.notification.Notification.filter", filter_mock),
        patch(
            "app.models.notification.NotificationRead.filter",
            return_value=MagicMock(values_list=AsyncMock(return_value=[])),
        ),
        patch("app.models.im.ImMessage.create", new_callable=AsyncMock) as mock_create,
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_unread,
        patch(
            "app.services.im_system_bridge._raise_conversation_seq_counter",
            new_callable=AsyncMock,
        ) as mock_bump,
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, user_id)

        # 已导入的通知不会重复导入，也不会重复累加未读数
        mock_create.assert_not_called()
        mock_unread.assert_not_called()
        mock_bump.assert_not_called()
        # 分页扫描必须带 limit，不允许无界全表扫描
        limit_mock.assert_called_once_with(im_system_bridge.LEGACY_NOTIF_BATCH_SIZE)
        # 加锁后必须释放，不能泄漏分布式锁
        assert len(_RecordingLock.instances) == 1
        assert _RecordingLock.instances[0].entered is True
        assert _RecordingLock.instances[0].exited is True


@pytest.mark.asyncio
async def test_sync_legacy_notifications_for_user_imports_new_pages() -> None:
    user_id = uuid4()
    team_id = uuid4()
    conv = MagicMock(
        id=uuid4(),
        latest_seq=5,
        last_message_content="older",
        last_message_at=None,
        save=AsyncMock(),
    )
    already_imported = _notification("notice", NotificationScope.USER, user_id=user_id)
    read_pending = _notification(
        "approval.pending", NotificationScope.TEAM, team_id=team_id
    )
    unread_pending = _notification("notice", NotificationScope.GLOBAL)
    participant = MagicMock(last_read_seq=2, save=AsyncMock())

    filter_mock, limit_mock = _notification_query_mock(
        [[already_imported, read_pending], [unread_pending]]
    )
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="5")
    fake_redis.set = AsyncMock()

    with (
        patch.object(im_system_bridge, "LEGACY_NOTIF_BATCH_SIZE", 2),
        patch("app.services.im_redis.DistributedLock", _RecordingLock),
        patch("app.services.im_redis.get_redis", AsyncMock(return_value=fake_redis)),
        patch("app.services.im_system_bridge.in_transaction", _fake_transaction),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(
                values_list=AsyncMock(
                    return_value=[
                        im_system_bridge._legacy_client_msg_id(already_imported.id)
                    ]
                )
            ),
        ),
        patch("app.models.notification.Notification.filter", filter_mock),
        patch(
            "app.models.notification.NotificationRead.filter",
            return_value=MagicMock(
                values_list=AsyncMock(return_value=[read_pending.id])
            ),
        ),
        patch("app.models.im.ImMessage.create", new_callable=AsyncMock) as mock_create,
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=participant)),
        ),
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_unread,
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, user_id)

        # 分两页取回全部通知，只写入未导入的两条，seq 从会话 latest_seq 续写
        assert limit_mock.call_count == 2
        assert mock_create.call_count == 2
        first_call, second_call = mock_create.call_args_list
        assert first_call.kwargs["seq"] == 6
        assert first_call.kwargs["client_msg_id"] == (
            im_system_bridge._legacy_client_msg_id(read_pending.id)
        )
        assert first_call.kwargs["msg_type"] == ImMessageType.CARD
        assert second_call.kwargs["seq"] == 7
        assert second_call.kwargs["client_msg_id"] == (
            im_system_bridge._legacy_client_msg_id(unread_pending.id)
        )

        assert conv.latest_seq == 7
        # read_pending 已读，游标推进到它的 seq；只有 unread_pending 计入未读数
        assert participant.last_read_seq == 6
        participant.save.assert_awaited_once()
        mock_unread.assert_awaited_once_with(user_id, conv.id, 1)
        # Redis seq 计数器每批抬高一次，最终为新写入的 latest_seq
        seq_key = im_system_bridge.im_redis.CONV_SEQ_KEY_PREFIX.format(conv.id)
        assert [call.args for call in fake_redis.set.await_args_list] == [
            (seq_key, 6),
            (seq_key, 7),
        ]
        # sync 锁 + 每批一次的会话锁，全部释放
        assert len(_RecordingLock.instances) == 3
        assert all(lock.exited for lock in _RecordingLock.instances)


@pytest.mark.asyncio
async def test_bridge_user_notification_without_user_id_is_ignored() -> None:
    notif = _notification("notice", NotificationScope.USER)
    with (
        patch("app.models.user.TeamMember.filter") as member_filter,
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as send,
    ):
        await im_system_bridge.bridge_notification_to_im(notif)

    member_filter.assert_not_called()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_bridge_swallows_send_failures() -> None:
    notif = _notification(
        "notice", NotificationScope.USER, user_id=uuid4(), team_id=uuid4()
    )
    with patch(
        "app.services.im_service.send_system_message",
        new_callable=AsyncMock,
        side_effect=RuntimeError("redis down"),
    ):
        await im_system_bridge.bridge_notification_to_im(notif)


@pytest.mark.asyncio
async def test_raise_conversation_seq_counter_swallows_redis_errors() -> None:
    with patch(
        "app.services.im_redis.get_redis",
        new_callable=AsyncMock,
        side_effect=RuntimeError("redis down"),
    ):
        await im_system_bridge._raise_conversation_seq_counter(uuid4(), 5)


@pytest.mark.asyncio
async def test_resolve_notification_team_id_without_user() -> None:
    notif = MagicMock(user_id=None)
    assert await im_system_bridge._resolve_notification_team_id(notif) is None

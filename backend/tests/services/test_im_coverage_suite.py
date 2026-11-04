from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


import pytest
from tortoise.exceptions import IntegrityError

from app.core.timezone import now_utc
from app.models.im import (
    ImConversationType,
    ImMessageType,
)
from app.models.notification import Notification, NotificationLevel, NotificationScope
from app.schemas.response import BusinessError
from app.services import im_redis, im_service, im_system_bridge


@asynccontextmanager
async def fake_tx():
    yield


# ============================================================================
# 1. im_redis.py 深入覆盖
# ============================================================================


@pytest.mark.asyncio
async def test_distributed_lock_acquire_timeout_and_error() -> None:
    lock = im_redis.DistributedLock("test:lock", lease_seconds=2)

    fake_redis = AsyncMock()
    # 模拟第一次失败，第二次成功
    fake_redis.set = AsyncMock(side_effect=[False, True])
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        ok = await lock.acquire(timeout_seconds=0.2)
        assert ok is True

    # 模拟超时失败
    fake_redis.set = AsyncMock(return_value=False)
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        ok = await lock.acquire(timeout_seconds=0.08)
        assert ok is False

    # 模拟异常降级为 True
    fake_redis.set = AsyncMock(side_effect=Exception("Redis down"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        ok = await lock.acquire(timeout_seconds=0.05)
        assert ok is True

    # release 异常处理
    fake_redis.eval = AsyncMock(side_effect=Exception("Release failed"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await lock.release()  # 不抛异常


@pytest.mark.asyncio
async def test_im_redis_helpers_and_error_branches() -> None:
    conv_id = uuid4()
    user_id = uuid4()

    # get_conversation_lock & get_create_conversation_lock
    assert im_redis.get_conversation_lock(conv_id).key.startswith("im:lock:conv:")
    assert im_redis.get_create_conversation_lock(
        uuid4(), user_id, uuid4()
    ).key.startswith("im:lock:create_conv:")

    # generate_next_seq: seq == 1 且 DB 存在历史消息
    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.set = AsyncMock()
    mock_msg = MagicMock(seq=15)
    with (
        patch("app.services.im_redis.get_redis", return_value=fake_redis),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=AsyncMock(first=AsyncMock(return_value=mock_msg))
                )
            ),
        ),
    ):
        seq = await im_redis.generate_next_seq(conv_id)
        assert seq == 16
        fake_redis.set.assert_called_once()

    # generate_next_seq: Redis 异常走 DB 兜底
    fake_redis.incr = AsyncMock(side_effect=Exception("incr error"))
    with (
        patch("app.services.im_redis.get_redis", return_value=fake_redis),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=AsyncMock(first=AsyncMock(return_value=mock_msg))
                )
            ),
        ),
    ):
        seq = await im_redis.generate_next_seq(conv_id)
        assert seq == 16

    # acquire_dedup_lock 异常走 True
    fake_redis.set = AsyncMock(side_effect=Exception("set error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert await im_redis.acquire_dedup_lock("dedup-key") is True

    # cache_message_result / get_cached_message_result
    await im_redis.cache_message_result("", {})  # 空直接 return
    assert await im_redis.get_cached_message_result("") is None

    fake_redis.setex = AsyncMock(side_effect=Exception("cache error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.cache_message_result("key", {"a": 1})  # 不抛异常

    fake_redis.get = AsyncMock(return_value=b'{"id": "msg-1"}')
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        data = await im_redis.get_cached_message_result("key")
        assert data == {"id": "msg-1"}

    fake_redis.get = AsyncMock(side_effect=Exception("get error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert await im_redis.get_cached_message_result("key") is None

    # release_dedup_lock 空与异常
    await im_redis.release_dedup_lock("")
    fake_redis.delete = AsyncMock(side_effect=Exception("del error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.release_dedup_lock("key")

    # increment_user_unread 异常
    fake_redis.eval = AsyncMock(side_effect=Exception("eval error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.increment_user_unread(user_id, conv_id)

    # mark_conversation_read_in_cache 异常
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert await im_redis.mark_conversation_read_in_cache(user_id, conv_id) == 0

    # get_user_unread_counts 异常与全空
    fake_pipe = AsyncMock()
    fake_pipe.execute = AsyncMock(return_value=[None, None])
    fake_redis.pipeline = MagicMock(return_value=fake_pipe)
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        t, c = await im_redis.get_user_unread_counts(user_id)
        assert t is None
        assert c is None

    fake_redis.pipeline = MagicMock(side_effect=Exception("pipe error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        t, c = await im_redis.get_user_unread_counts(user_id)
        assert t is None
        assert c is None

    # rebuild_unread_cache 异常
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.rebuild_unread_cache(user_id, 0, {})

    # publish_im_event 正常与异常
    fake_redis.publish = AsyncMock()
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.publish_im_event(user_id, "test", {"msg": "ok"})
        fake_redis.publish.assert_called_once()

    fake_redis.publish = AsyncMock(side_effect=Exception("pub error"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.publish_im_event(user_id, "test", {})


# ============================================================================
# 2. im_service.py 深入覆盖
# ============================================================================


@pytest.mark.asyncio
async def test_get_or_create_direct_conversation_branches() -> None:
    team_id = uuid4()
    u1 = uuid4()
    u2 = uuid4()

    # 1. 已存在
    mock_conv = MagicMock(id=uuid4(), type=ImConversationType.DIRECT)
    with (
        patch("app.services.im_service.check_users_in_same_team", return_value=None),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_conv)),
        ),
        patch("app.services.im_service._ensure_participants", return_value=None),
    ):
        conv = await im_service.get_or_create_direct_conversation(team_id, u1, u2)
        assert conv.id == mock_conv.id

    # 2. 并发冲突 IntegrityError，二次查出已有
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch("app.services.im_service.check_users_in_same_team", return_value=None),
        patch(
            "app.models.im.ImConversation.filter",
            side_effect=[
                AsyncMock(first=AsyncMock(return_value=None)),  # 首次查空
                AsyncMock(first=AsyncMock(return_value=mock_conv)),  # 冲突后查出
            ],
        ),
        patch(
            "app.models.im.ImConversation.create",
            side_effect=IntegrityError("conflict"),
        ),
        patch("app.services.im_service._ensure_participants", return_value=None),
    ):
        conv = await im_service.get_or_create_direct_conversation(team_id, u1, u2)
        assert conv.id == mock_conv.id


@pytest.mark.asyncio
async def test_get_or_create_system_conversation_branches() -> None:
    team_id = uuid4()
    user_id = uuid4()
    mock_conv = MagicMock(id=uuid4(), type=ImConversationType.SYSTEM)

    # 1. 已存在
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_conv)),
        ),
        patch("app.services.im_service._ensure_participants", return_value=None),
    ):
        conv = await im_service.get_or_create_system_conversation(team_id, user_id)
        assert conv.id == mock_conv.id

    # 2. 冲突 IntegrityError 并二次恢复
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch(
            "app.models.im.ImConversation.filter",
            side_effect=[
                AsyncMock(first=AsyncMock(return_value=None)),
                AsyncMock(first=AsyncMock(return_value=mock_conv)),
            ],
        ),
        patch(
            "app.models.im.ImConversation.create",
            side_effect=IntegrityError("conflict"),
        ),
        patch("app.services.im_service._ensure_participants", return_value=None),
    ):
        conv = await im_service.get_or_create_system_conversation(team_id, user_id)
        assert conv.id == mock_conv.id


@pytest.mark.asyncio
async def test_send_direct_message_error_and_success_branches() -> None:
    conv_id = uuid4()
    sender_id = uuid4()
    other_id = uuid4()

    # 1. 会话不存在 404
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=None)),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service.send_direct_message(conv_id, sender_id, "hi")
        assert exc.value.status_code == 404

    # 2. 会话类型错误 400
    wrong_type_conv = MagicMock(
        id=conv_id,
        type=ImConversationType.SYSTEM,
        user1_id=sender_id,
        user2_id=other_id,
    )
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=wrong_type_conv)),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service.send_direct_message(conv_id, sender_id, "hi")
        assert exc.value.status_code == 400

    # 3. 正常发送成功与广播
    conv = MagicMock(
        id=conv_id,
        type=ImConversationType.DIRECT,
        user1_id=sender_id,
        user2_id=other_id,
        save=AsyncMock(),
    )
    mock_created_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=sender_id,
        seq=5,
        msg_type=ImMessageType.TEXT,
        content="hello",
        created_at=now_utc(),
    )

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.services.im_redis.get_cached_message_result", return_value=None),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch("app.services.im_redis.generate_next_seq", return_value=5),
        patch("app.models.im.ImMessage.create", return_value=mock_created_msg),
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_incr,
        patch(
            "app.services.im_redis.publish_im_event", new_callable=AsyncMock
        ) as mock_pub,
        patch("app.services.im_redis.cache_message_result", new_callable=AsyncMock),
    ):
        res = await im_service.send_direct_message(
            conv_id, sender_id, "hello", client_msg_id="uuid-123"
        )
        assert res.id == mock_created_msg.id
        mock_incr.assert_called_once_with(other_id, conv_id, 1)
        mock_pub.assert_called_once()


@pytest.mark.asyncio
async def test_send_system_message_flow() -> None:
    team_id = uuid4()
    recipient_id = uuid4()
    conv = MagicMock(id=uuid4(), save=AsyncMock())
    mock_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv.id,
        seq=1,
        msg_type=ImMessageType.SYSTEM_NOTICE,
        content="system notice",
        created_at=now_utc(),
    )

    with (
        patch(
            "app.services.im_service.get_or_create_system_conversation",
            return_value=conv,
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch("app.services.im_redis.generate_next_seq", return_value=1),
        patch("app.models.im.ImMessage.create", return_value=mock_msg),
        patch("app.services.im_redis.increment_user_unread", new_callable=AsyncMock),
        patch(
            "app.services.im_redis.publish_im_event", new_callable=AsyncMock
        ) as mock_pub,
    ):
        msg = await im_service.send_system_message(
            team_id, recipient_id, "system notice"
        )
        assert msg.id == mock_msg.id
        mock_pub.assert_called_once()


@pytest.mark.asyncio
async def test_get_messages_cursor_branches() -> None:
    conv_id = uuid4()
    user_id = uuid4()
    conv = MagicMock(
        id=conv_id, type=ImConversationType.DIRECT, user1_id=user_id, user2_id=uuid4()
    )

    mock_msgs = [MagicMock(seq=i) for i in range(1, 10)]

    fake_query = MagicMock()
    fake_query.filter = MagicMock(return_value=fake_query)
    fake_query.order_by = MagicMock(return_value=fake_query)
    fake_query.limit = MagicMock(return_value=fake_query)
    fake_query.all = AsyncMock(return_value=mock_msgs)

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.models.im.ImMessage.filter", return_value=fake_query),
    ):
        # 1. after_seq
        msgs, has_more = await im_service.get_messages(
            conv_id, user_id, after_seq=5, limit=5
        )
        assert len(msgs) == 5

        # 2. before_seq
        msgs, has_more = await im_service.get_messages(
            conv_id, user_id, before_seq=10, limit=5
        )
        assert len(msgs) == 5

        # 3. around_seq
        msgs, has_more = await im_service.get_messages(
            conv_id, user_id, around_seq=8, limit=10
        )
        assert len(msgs) == 9

        # 4. default
        msgs, has_more = await im_service.get_messages(conv_id, user_id, limit=5)
        assert len(msgs) == 5


@pytest.mark.asyncio
async def test_mark_conversation_read_branches() -> None:
    conv_id = uuid4()
    user_id = uuid4()
    conv = MagicMock(id=conv_id, latest_seq=10)
    part = MagicMock(last_read_seq=5, save=AsyncMock())

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=part)),
        ),
        patch("app.services.im_redis.mark_conversation_read_in_cache", return_value=5),
        patch(
            "app.services.im_redis.publish_im_event", new_callable=AsyncMock
        ) as mock_pub,
    ):
        cleared = await im_service.mark_conversation_read(
            conv_id, user_id, up_to_seq=10
        )
        assert cleared == 5
        assert part.last_read_seq == 10
        mock_pub.assert_called_once()


@pytest.mark.asyncio
async def test_get_global_unread_count_unmitigated_rebuild() -> None:
    user_id = uuid4()
    part = MagicMock(last_read_seq=2, conversation=MagicMock(id=uuid4(), latest_seq=5))

    with (
        patch(
            "app.services.im_redis.get_user_unread_counts", return_value=(None, None)
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[part]))
                )
            ),
        ),
        patch(
            "app.services.im_redis.rebuild_unread_cache", new_callable=AsyncMock
        ) as mock_rebuild,
    ):
        total = await im_service.get_global_unread_count(user_id)
        assert total == 3
        mock_rebuild.assert_called_once_with(user_id, 3, {str(part.conversation.id): 3})


@pytest.mark.asyncio
async def test_search_messages_flow() -> None:
    team_id = uuid4()
    user_id = uuid4()
    peer_id = uuid4()

    conv = MagicMock(
        id=uuid4(),
        team_id=team_id,
        type=ImConversationType.DIRECT,
        user1_id=user_id,
        user2_id=peer_id,
    )
    part = MagicMock(conversation=conv)
    mock_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv.id,
        seq=3,
        msg_type=ImMessageType.TEXT,
        content="hello target query",
        created_at=now_utc(),
    )
    mock_peer = MagicMock(
        id=peer_id, username="bob", full_name="Bob Builder", avatar_url=None
    )

    with (
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[part]))
                )
            ),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(
                                all=AsyncMock(return_value=[mock_msg])
                            )
                        )
                    )
                )
            ),
        ),
        patch(
            "app.models.user.User.filter",
            return_value=AsyncMock(all=AsyncMock(return_value=[mock_peer])),
        ),
    ):
        results = await im_service.search_messages(team_id, user_id, "target")
        assert len(results) == 1
        assert results[0]["content"] == "hello target query"
        assert results[0]["peer"]["username"] == "bob"


# ============================================================================
# 3. im_system_bridge.py 深入覆盖
# ============================================================================


@pytest.mark.asyncio
async def test_bridge_notification_team_scope() -> None:
    team_id = uuid4()
    u1, u2 = uuid4(), uuid4()
    notif = Notification(
        id=uuid4(),
        scope=NotificationScope.TEAM,
        type="system.notice",
        title="Notice",
        content="Team announcement",
        level=NotificationLevel.MEDIUM,
    )
    notif.team_id = team_id

    fake_query = MagicMock()
    fake_query.values_list = AsyncMock(return_value=[u1, u2])

    with (
        patch("app.models.user.TeamMember.filter", return_value=fake_query),
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        await im_system_bridge.bridge_notification_to_im(notif)
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_sync_legacy_notifications_for_user_full() -> None:
    team_id = uuid4()
    user_id = uuid4()
    conv = MagicMock(id=uuid4(), latest_seq=0, save=AsyncMock())
    part = MagicMock(last_read_seq=0, save=AsyncMock())

    n1 = Notification(
        id=uuid4(),
        scope=NotificationScope.GLOBAL,
        type="global.notice",
        title="Welcome",
        content="Welcome to platform",
        level=NotificationLevel.LOW,
        created_at=now_utc(),
    )
    n2 = Notification(
        id=uuid4(),
        scope=NotificationScope.USER,
        type="workflow.pause_pending",
        title="Approval",
        content="Please approve",
        level=NotificationLevel.HIGH,
        created_at=now_utc(),
    )
    n1.id = uuid4()
    n2.id = uuid4()

    # 模拟 n1 已读，n2 未读
    with (
        patch("app.services.im_system_bridge.in_transaction", fake_tx),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(exists=AsyncMock(return_value=False)),
        ),
        patch(
            "app.models.notification.Notification.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(all=AsyncMock(return_value=[n1, n2]))
                        )
                    )
                )
            ),
        ),
        patch(
            "app.models.notification.NotificationRead.filter",
            return_value=MagicMock(values_list=AsyncMock(return_value=[n1.id])),
        ),
        patch(
            "app.models.im.ImMessage.create", new_callable=AsyncMock
        ) as mock_msg_create,
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=part)),
        ),
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_incr,
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, user_id)
        assert mock_msg_create.call_count == 2
        assert conv.latest_seq == 2
        assert part.last_read_seq == 1  # n1 已读，游标停在 1
        mock_incr.assert_called_once_with(user_id, conv.id, 1)  # n2 未读，未读数加 1


@pytest.mark.asyncio
async def test_im_service_residual_branches() -> None:
    team_id = uuid4()
    u1, u2 = uuid4(), uuid4()

    # 1. _strip_markdown_summary 空输入
    assert im_service._strip_markdown_summary("") == ""

    # 2. get_or_create_direct_conversation 正常新建成功
    mock_new_conv = MagicMock(id=uuid4())
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch("app.services.im_service.check_users_in_same_team", return_value=None),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch("app.models.im.ImConversation.create", return_value=mock_new_conv),
        patch("app.models.im.ImConversationParticipant.create", new_callable=AsyncMock),
    ):
        c = await im_service.get_or_create_direct_conversation(team_id, u1, u2)
        assert c.id == mock_new_conv.id

    # 3. get_or_create_direct_conversation 冲突后第二次仍 None 抛 IntegrityError
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch("app.services.im_service.check_users_in_same_team", return_value=None),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch(
            "app.models.im.ImConversation.create",
            side_effect=IntegrityError("conflict"),
        ),
    ):
        with pytest.raises(IntegrityError):
            await im_service.get_or_create_direct_conversation(team_id, u1, u2)

    # 4. get_or_create_system_conversation 正常新建成功
    mock_sys_conv = MagicMock(id=uuid4())
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch("app.models.im.ImConversation.create", return_value=mock_sys_conv),
        patch("app.models.im.ImConversationParticipant.create", new_callable=AsyncMock),
    ):
        c = await im_service.get_or_create_system_conversation(team_id, u1)
        assert c.id == mock_sys_conv.id

    # 5. get_or_create_system_conversation 冲突后第二次仍 None 抛 IntegrityError
    with (
        patch("app.services.im_service.in_transaction", fake_tx),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch(
            "app.models.im.ImConversation.create",
            side_effect=IntegrityError("conflict"),
        ),
    ):
        with pytest.raises(IntegrityError):
            await im_service.get_or_create_system_conversation(team_id, u1)

    # 6. _ensure_participants: 部分缺失并成功创建，部分抛异常忽略
    part_query = MagicMock()
    part_query.values_list = AsyncMock(return_value=[u1])
    with (
        patch(
            "app.models.im.ImConversationParticipant.filter", return_value=part_query
        ),
        patch(
            "app.models.im.ImConversationParticipant.create",
            side_effect=Exception("create error"),
        ),
    ):
        await im_service._ensure_participants(uuid4(), [u1, u2])  # 不抛异常

    # 7. send_direct_message: 锁未抢到但自旋查库命中
    mock_msg = MagicMock(id=uuid4())
    mock_conv = MagicMock(
        id=uuid4(), type=ImConversationType.DIRECT, user1_id=u1, user2_id=u2
    )
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_conv)),
        ),
        patch("app.services.im_redis.get_cached_message_result", return_value=None),
        patch(
            "app.models.im.ImMessage.filter",
            side_effect=[
                AsyncMock(first=AsyncMock(return_value=None)),  # 首次空
                AsyncMock(
                    first=AsyncMock(return_value=mock_msg)
                ),  # 锁未获取到后二次命中
            ],
        ),
        patch("app.services.im_redis.acquire_dedup_lock", return_value=False),
    ):
        res = await im_service.send_direct_message(
            mock_conv.id, u1, "hi", client_msg_id="uuid"
        )
        assert res.id == mock_msg.id

    # 8. send_system_message: client_msg_id 已存在
    with (
        patch(
            "app.services.im_service.get_or_create_system_conversation",
            return_value=mock_conv,
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_msg)),
        ),
    ):
        res = await im_service.send_system_message(
            team_id, u1, "hi", client_msg_id="uuid"
        )
        assert res.id == mock_msg.id

    # 9. list_conversations 完整流程（含系统会话与单聊、peer 信息与未读数计算）
    sys_conv = MagicMock(
        id=uuid4(),
        team_id=team_id,
        type=ImConversationType.SYSTEM,
        latest_seq=5,
        last_message_content="test",
        last_message_at=now_utc(),
        created_at=now_utc(),
    )
    dir_conv = MagicMock(
        id=uuid4(),
        team_id=team_id,
        type=ImConversationType.DIRECT,
        user1_id=u1,
        user2_id=u2,
        latest_seq=10,
        last_message_content="hi",
        last_message_at=now_utc(),
        created_at=now_utc(),
    )
    p_sys = MagicMock(
        conversation=sys_conv, is_pinned=True, is_muted=False, last_read_seq=5
    )
    p_dir = MagicMock(
        conversation=dir_conv, is_pinned=False, is_muted=False, last_read_seq=8
    )
    mock_peer = MagicMock(
        id=u2, username="bob", full_name="Bob Builder", avatar_url=None
    )

    with (
        patch(
            "app.services.im_service.get_or_create_system_conversation",
            return_value=sys_conv,
        ),
        patch(
            "app.services.im_system_bridge.sync_legacy_notifications_for_user",
            new_callable=AsyncMock,
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[p_sys, p_dir]))
                )
            ),
        ),
        patch(
            "app.services.im_redis.get_user_unread_counts", return_value=(None, None)
        ),  # 模拟未命中缓存
        patch(
            "app.models.user.User.filter",
            return_value=AsyncMock(all=AsyncMock(return_value=[mock_peer])),
        ),
        patch("app.services.im_redis.rebuild_unread_cache", new_callable=AsyncMock),
    ):
        items = await im_service.list_conversations(team_id, u1)
        assert len(items) == 2
        assert items[0]["is_pinned"] is True
        assert items[1]["unread_count"] == 2
        assert items[1]["peer"]["username"] == "bob"

    # 10. get_messages 权限阻断
    sys_not_owned = MagicMock(id=uuid4(), type=ImConversationType.SYSTEM, user1_id=u2)
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=sys_not_owned)),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service.get_messages(sys_not_owned.id, u1)
        assert exc.value.status_code == 403

    # 11. mark_conversation_read 参与者不存在
    valid_conv = MagicMock(id=uuid4(), latest_seq=1)
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=valid_conv)),
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
    ):
        assert await im_service.mark_conversation_read(valid_conv.id, u1) == 0

    # 12. search_messages 无团队参与会话直接返回空
    with patch(
        "app.models.im.ImConversationParticipant.filter",
        return_value=MagicMock(
            prefetch_related=MagicMock(
                return_value=AsyncMock(all=AsyncMock(return_value=[]))
            )
        ),
    ):
        assert await im_service.search_messages(team_id, u1, "query") == []

    # 13. bridge_notification_to_im user scope 且未带 team_id
    notif_no_team = Notification(
        id=uuid4(),
        scope=NotificationScope.USER,
        type="system.notice",
        title="Title",
        content="Content",
        level=NotificationLevel.LOW,
    )
    notif_no_team.user_id = u1
    notif_no_team.team_id = None
    mock_tm = MagicMock(team_id=team_id)
    with (
        patch(
            "app.models.user.TeamMember.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_tm)),
        ),
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as mock_send,
    ):
        await im_system_bridge.bridge_notification_to_im(notif_no_team)
        mock_send.assert_called_once()

    # 14. sync_legacy_notifications_for_user 查无历史通知直接 return
    empty_sys_conv = MagicMock(id=uuid4(), type=ImConversationType.SYSTEM, user1_id=u1)
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=empty_sys_conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(exists=AsyncMock(return_value=False)),
        ),
        patch(
            "app.models.notification.Notification.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(all=AsyncMock(return_value=[]))
                        )
                    )
                )
            ),
        ),
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, u1)


@pytest.mark.asyncio
async def test_im_service_more_detailed_branches() -> None:
    team_id = uuid4()
    u1, u2 = uuid4(), uuid4()
    conv_id = uuid4()

    # 1. send_direct_message 当 sender 是 user2_id (receiver 为 user1_id)
    conv = MagicMock(
        id=conv_id,
        team_id=team_id,
        type=ImConversationType.DIRECT,
        user1_id=u1,
        user2_id=u2,
        latest_seq=1,
        save=AsyncMock(),
        created_at=now_utc(),
        last_message_at=now_utc(),
    )
    mock_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=u2,
        seq=2,
        msg_type=ImMessageType.TEXT,
        content="hello from u2",
        created_at=now_utc(),
    )
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.services.im_redis.get_cached_message_result", return_value=None),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=None)),
        ),
        patch("app.services.im_redis.generate_next_seq", return_value=2),
        patch("app.models.im.ImMessage.create", return_value=mock_msg),
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_incr,
        patch("app.services.im_redis.publish_im_event", new_callable=AsyncMock),
    ):
        msg = await im_service.send_direct_message(conv_id, u2, "hello from u2")
        assert msg.id == mock_msg.id
        mock_incr.assert_called_once_with(u1, conv_id, 1)  # receiver 为 u1

    # 2. send_direct_message 幂等命中 DB 已有
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.services.im_redis.get_cached_message_result", return_value=None),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_msg)),
        ),
    ):
        msg = await im_service.send_direct_message(
            conv_id, u2, "hello", client_msg_id="uuid-db"
        )
        assert msg.id == mock_msg.id

    # 3. get_messages 合法单聊 (用户为 user2) 与合法系统会话
    fake_query = MagicMock()
    fake_query.filter = MagicMock(return_value=fake_query)
    fake_query.order_by = MagicMock(return_value=fake_query)
    fake_query.limit = MagicMock(return_value=fake_query)
    fake_query.all = AsyncMock(return_value=[mock_msg])

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch("app.models.im.ImMessage.filter", return_value=fake_query),
    ):
        msgs, has_more = await im_service.get_messages(conv_id, u2)
        assert len(msgs) == 1

    sys_conv = MagicMock(id=uuid4(), type=ImConversationType.SYSTEM, user1_id=u1)
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=sys_conv)),
        ),
        patch("app.models.im.ImMessage.filter", return_value=fake_query),
    ):
        msgs, has_more = await im_service.get_messages(sys_conv.id, u1)
        assert len(msgs) == 1

    # 4. mark_conversation_read 当 target_seq <= last_read_seq (不更新游标)
    part = MagicMock(last_read_seq=10, save=AsyncMock())
    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=part)),
        ),
        patch("app.services.im_redis.mark_conversation_read_in_cache", return_value=0),
        patch("app.services.im_redis.publish_im_event", new_callable=AsyncMock),
    ):
        cleared = await im_service.mark_conversation_read(conv_id, u1, up_to_seq=5)
        assert cleared == 0
        part.save.assert_not_called()

    # 5. list_conversations 命中 Redis 缓存各会话未读数分支
    p_dir = MagicMock(
        conversation=conv, is_pinned=False, is_muted=False, last_read_seq=1
    )
    with (
        patch(
            "app.services.im_service.get_or_create_system_conversation",
            return_value=sys_conv,
        ),
        patch(
            "app.services.im_system_bridge.sync_legacy_notifications_for_user",
            new_callable=AsyncMock,
        ),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[p_dir]))
                )
            ),
        ),
        patch(
            "app.services.im_redis.get_user_unread_counts",
            return_value=(5, {str(conv_id): 5}),
        ),  # 命中缓存
        patch(
            "app.models.user.User.filter",
            return_value=AsyncMock(all=AsyncMock(return_value=[])),
        ),
    ):
        items = await im_service.list_conversations(team_id, u1)
        assert len(items) == 1
        assert items[0]["unread_count"] == 5

    # 6. sync_legacy_notifications_for_user 当所有通知已读 (unread_count == 0)
    n1 = Notification(
        id=uuid4(),
        scope=NotificationScope.GLOBAL,
        type="notice",
        title="Title",
        content="Content",
        level=NotificationLevel.LOW,
        created_at=now_utc(),
    )
    n1.id = uuid4()
    part_all_read = MagicMock(last_read_seq=0, save=AsyncMock())
    with (
        patch("app.services.im_system_bridge.in_transaction", fake_tx),
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(exists=AsyncMock(return_value=False)),
        ),
        patch(
            "app.models.notification.Notification.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(all=AsyncMock(return_value=[n1]))
                        )
                    )
                )
            ),
        ),
        patch(
            "app.models.notification.NotificationRead.filter",
            return_value=MagicMock(values_list=AsyncMock(return_value=[n1.id])),
        ),
        patch("app.models.im.ImMessage.create", new_callable=AsyncMock),
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=part_all_read)),
        ),
        patch(
            "app.services.im_redis.increment_user_unread", new_callable=AsyncMock
        ) as mock_incr_unread,
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, u1)
        mock_incr_unread.assert_not_called()  # 全部已读，不增加未读数
        assert part_all_read.last_read_seq == 1

    # 7. bridge_notification_to_im 异常安全捕获
    with patch(
        "app.services.im_service.send_system_message",
        side_effect=Exception("bridge error"),
    ):
        await im_system_bridge.bridge_notification_to_im(n1)  # 不抛异常


@pytest.mark.asyncio
async def test_im_exact_branch_gap_closure() -> None:
    team_id = uuid4()
    u1, u2 = uuid4(), uuid4()
    conv_id = uuid4()

    # 1. _sort_user_pair 分支覆盖 (u1 > u2)
    p1, p2 = (
        im_service._sort_user_pair(u2, u1)
        if str(u1) < str(u2)
        else im_service._sort_user_pair(u1, u2)
    )
    assert p1 != p2

    # 2. send_system_message 锁内二次检查 client_msg_id 已存在
    sys_conv = MagicMock(id=conv_id, save=AsyncMock())
    existing_sys_msg = MagicMock(id=uuid4())
    with (
        patch(
            "app.services.im_service.get_or_create_system_conversation",
            return_value=sys_conv,
        ),
        patch(
            "app.models.im.ImMessage.filter",
            side_effect=[
                AsyncMock(first=AsyncMock(return_value=None)),  # 锁外查空
                AsyncMock(first=AsyncMock(return_value=existing_sys_msg)),  # 锁内命中
            ],
        ),
    ):
        msg = await im_service.send_system_message(
            team_id, u1, "text", client_msg_id="dupe-sys"
        )
        assert msg.id == existing_sys_msg.id

    # 3. search_messages 搜索命中但没有消息
    conv_obj = MagicMock(id=conv_id, team_id=team_id, type=ImConversationType.SYSTEM)
    part_obj = MagicMock(conversation=conv_obj)
    with (
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[part_obj]))
                )
            ),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(all=AsyncMock(return_value=[]))
                        )
                    )
                )
            ),
        ),
    ):
        assert await im_service.search_messages(team_id, u1, "notfound") == []

    # 4. search_messages 搜索命中包含系统会话消息（peer 为 None）
    sys_msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        seq=1,
        content="matched text",
        msg_type=ImMessageType.SYSTEM_NOTICE,
        created_at=now_utc(),
    )
    with (
        patch(
            "app.models.im.ImConversationParticipant.filter",
            return_value=MagicMock(
                prefetch_related=MagicMock(
                    return_value=AsyncMock(all=AsyncMock(return_value=[part_obj]))
                )
            ),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(
                        limit=MagicMock(
                            return_value=AsyncMock(
                                all=AsyncMock(return_value=[sys_msg])
                            )
                        )
                    )
                )
            ),
        ),
    ):
        res = await im_service.search_messages(team_id, u1, "matched")
        assert len(res) == 1
        assert res[0]["conversation_type"] == "system"
        assert res[0]["peer"] is None

    # 5. sync_legacy_notifications_for_user 中 conv 为 None，或二次检查时已存在
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=None)),
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(
            team_id, u1
        )  # conv 为 None 直接返回

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=sys_conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            side_effect=[
                AsyncMock(exists=AsyncMock(return_value=False)),  # 锁外查空
                AsyncMock(
                    exists=AsyncMock(return_value=True)
                ),  # 锁内二次检查发现已存在
            ],
        ),
    ):
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, u1)

    # 6. bridge_notification_to_im title 已经在 content 中，以及 team scope 成员为空
    notif_title_in = Notification(
        id=uuid4(),
        scope=NotificationScope.USER,
        type="notice",
        title="Hello",
        content="Hello world",
        level=NotificationLevel.LOW,
    )
    notif_title_in.user_id = u1
    notif_title_in.team_id = team_id
    with patch(
        "app.services.im_service.send_system_message", new_callable=AsyncMock
    ) as mock_send:
        await im_system_bridge.bridge_notification_to_im(notif_title_in)
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["content"] == "Hello world"

    notif_team_empty = Notification(
        id=uuid4(),
        scope=NotificationScope.TEAM,
        type="notice",
        title="T",
        content="C",
        level=NotificationLevel.LOW,
    )
    notif_team_empty.team_id = team_id
    with (
        patch(
            "app.models.user.TeamMember.filter",
            return_value=MagicMock(values_list=AsyncMock(return_value=[])),
        ),
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as mock_send_team,
    ):
        await im_system_bridge.bridge_notification_to_im(notif_team_empty)
        mock_send_team.assert_not_called()

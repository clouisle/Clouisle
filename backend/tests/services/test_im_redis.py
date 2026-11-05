from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import im_redis


@pytest.mark.asyncio
async def test_acquire_and_release_dedup_lock() -> None:
    client_msg_id = "msg-123456"

    # 空 client_msg_id 返回 True
    assert await im_redis.acquire_dedup_lock("") is True

    fake_redis = AsyncMock()
    fake_redis.set = AsyncMock(return_value=True)
    fake_redis.delete = AsyncMock(return_value=1)

    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        # 成功获取锁
        acquired = await im_redis.acquire_dedup_lock(client_msg_id, ttl_seconds=30)
        assert acquired is True
        fake_redis.set.assert_called_once_with(
            f"im:dedup:{client_msg_id}", "1", ex=30, nx=True
        )

        # 锁已存在 (SETNX 返回 None/False)
        fake_redis.set = AsyncMock(return_value=None)
        acquired_again = await im_redis.acquire_dedup_lock(client_msg_id)
        assert acquired_again is False

        # 释放锁
        await im_redis.release_dedup_lock(client_msg_id)
        fake_redis.delete.assert_called_once_with(f"im:dedup:{client_msg_id}")


@pytest.mark.asyncio
async def test_generate_next_seq_normal() -> None:
    conv_id = uuid4()
    fake_redis = AsyncMock()
    fake_redis.incr = AsyncMock(return_value=42)

    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        seq = await im_redis.generate_next_seq(conv_id)
        assert seq == 42
        fake_redis.incr.assert_called_once_with(f"im:conv:{conv_id}:seq")


@pytest.mark.asyncio
async def test_increment_and_mark_read_in_cache() -> None:
    user_id = uuid4()
    conv_id = uuid4()

    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=2)

    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.increment_user_unread(user_id, conv_id, amount=2)
        fake_redis.eval.assert_called_once()

    # 标记已读扣减
    fake_redis.eval = AsyncMock(return_value=2)
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        deducted = await im_redis.mark_conversation_read_in_cache(user_id, conv_id)
        assert deducted == 2
        assert fake_redis.eval.call_count == 1


@pytest.mark.asyncio
async def test_get_and_rebuild_unread_cache() -> None:
    user_id = uuid4()
    conv_id = uuid4()
    fake_pipe = AsyncMock()
    fake_pipe.execute = AsyncMock(return_value=[b"5", {str(conv_id).encode(): b"5"}])

    fake_redis = AsyncMock()
    fake_redis.pipeline = lambda **kwargs: fake_pipe

    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        total, conv_map = await im_redis.get_user_unread_counts(user_id)
        assert total == 5
        assert conv_map == {str(conv_id): 5}

    # 重建缓存
    fake_pipe_rebuild = AsyncMock()
    fake_redis.pipeline = lambda **kwargs: fake_pipe_rebuild
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        await im_redis.rebuild_unread_cache(user_id, 3, {str(conv_id): 3})
        fake_pipe_rebuild.set.assert_called_once_with(
            f"im:user:{user_id}:total_unread", 3, ex=86400 * 7
        )
        fake_pipe_rebuild.delete.assert_called_once_with(
            f"im:user:{user_id}:conv_unread"
        )
        fake_pipe_rebuild.hset.assert_called_once()


@pytest.mark.asyncio
async def test_rebuild_unread_cache_version_cas() -> None:
    user_id = uuid4()
    conv_id = uuid4()
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)

    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert (
            await im_redis.rebuild_unread_cache(
                user_id, 2, {str(conv_id): 2}, expected_version=5
            )
            is True
        )
    assert fake_redis.eval.await_args.args[0] is im_redis._REBUILD_UNREAD_LUA
    assert fake_redis.eval.await_args.args[1] == 3

    fake_redis.eval = AsyncMock(return_value=0)
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert (
            await im_redis.rebuild_unread_cache(user_id, 2, {}, expected_version=6)
            is False
        )


@pytest.mark.asyncio
async def test_get_unread_version_reads_and_falls_back() -> None:
    user_id = uuid4()
    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=b"4")
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert await im_redis.get_unread_version(user_id) == 4

    fake_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("app.services.im_redis.get_redis", return_value=fake_redis):
        assert await im_redis.get_unread_version(user_id) == 0

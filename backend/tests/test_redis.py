from unittest.mock import AsyncMock, Mock

import pytest

from app.core import redis as redis_module


@pytest.fixture(autouse=True)
def reset_redis_pool(monkeypatch):
    monkeypatch.setattr(redis_module, "_redis_pool", None)


@pytest.mark.asyncio
async def test_get_redis_reuses_connection_and_close_resets_pool(monkeypatch):
    client = Mock()
    client.close = AsyncMock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(redis_module.redis, "Redis", factory)

    assert await redis_module.get_redis() is client
    assert await redis_module.get_redis() is client
    factory.assert_called_once_with(
        host=redis_module.settings.REDIS_HOST,
        port=redis_module.settings.REDIS_PORT,
        password=redis_module.settings.REDIS_PASSWORD,
        decode_responses=True,
    )

    await redis_module.close_redis()

    client.close.assert_awaited_once_with()
    assert redis_module._redis_pool is None


@pytest.mark.asyncio
async def test_token_blacklist_and_session_helpers_use_expected_keys(monkeypatch):
    client = Mock()
    client.setex = AsyncMock()
    client.exists = AsyncMock(return_value=1)
    client.get = AsyncMock(side_effect=["old-token", "current-token"])
    client.delete = AsyncMock()
    monkeypatch.setattr(redis_module, "get_redis", AsyncMock(return_value=client))

    await redis_module.add_token_to_blacklist("new-token", 60)
    assert await redis_module.is_token_blacklisted("new-token") is True
    await redis_module.set_user_session("user-1", "current-token", 120)
    await redis_module.invalidate_user_session("user-1", token_expires_in=30)
    assert await redis_module.get_user_session("user-1") == "current-token"
    await redis_module.clear_user_session("user-1")

    assert client.setex.await_args_list == [
        (("token:blacklist:new-token", 60, "1"), {}),
        (("user:session:user-1", 120, "current-token"), {}),
        (("token:blacklist:old-token", 30, "1"), {}),
    ]
    assert client.exists.await_args.args == ("token:blacklist:new-token",)
    assert client.delete.await_args_list == [
        (("user:session:user-1",), {}),
        (("user:session:user-1",), {}),
    ]


@pytest.mark.asyncio
async def test_missing_or_expired_entries_are_not_reported_as_active(monkeypatch):
    client = Mock()
    client.exists = AsyncMock(return_value=0)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock()
    monkeypatch.setattr(redis_module, "get_redis", AsyncMock(return_value=client))
    blacklist = AsyncMock()
    monkeypatch.setattr(redis_module, "add_token_to_blacklist", blacklist)

    assert await redis_module.is_token_blacklisted("missing") is False
    assert await redis_module.get_user_session("user-2") is None
    await redis_module.invalidate_user_session("user-2")

    blacklist.assert_not_awaited()
    client.delete.assert_awaited_once_with("user:session:user-2")


def test_redis_text_decodes_bytes_and_passes_strings():
    assert redis_module._redis_text(b"hello") == "hello"
    assert redis_module._redis_text("hello") == "hello"


@pytest.mark.asyncio
async def test_close_redis_is_noop_when_pool_not_initialized(monkeypatch):
    get_redis_mock = AsyncMock()
    monkeypatch.setattr(redis_module, "get_redis", get_redis_mock)

    await redis_module.close_redis()

    get_redis_mock.assert_not_awaited()
    assert redis_module._redis_pool is None

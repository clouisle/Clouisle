import asyncio
from types import SimpleNamespace

import pytest

from app.services import feishu_agent_locks


@pytest.mark.asyncio
async def test_sqlite_chat_lock_serializes_same_actor_and_releases_after_exit(
    monkeypatch,
):
    lock_name = "integration:chat:user"
    database = SimpleNamespace(capabilities=SimpleNamespace(dialect="sqlite"))
    monkeypatch.setattr(
        feishu_agent_locks,
        "connections",
        SimpleNamespace(get=lambda _name: database),
    )
    feishu_agent_locks._SQLITE_LOCKS.pop(lock_name, None)

    async with feishu_agent_locks.chat_lock("integration", "chat", "user"):
        lock = feishu_agent_locks._SQLITE_LOCKS[lock_name]
        assert lock.locked()
        second_context = feishu_agent_locks.chat_lock("integration", "chat", "user")
        competing = asyncio.create_task(second_context.__aenter__())
        await asyncio.sleep(0)
        assert not competing.done(), "a second worker must wait for this actor's lock"

    await competing
    await second_context.__aexit__(None, None, None)
    assert not lock.locked(), (
        "the actor lock must be released after leaving the context"
    )
    feishu_agent_locks._SQLITE_LOCKS.pop(lock_name, None)

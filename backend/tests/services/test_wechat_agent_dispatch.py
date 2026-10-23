"""Fair durable recovery, coalesced wakeups and stale ownership boundaries."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
import pytest_asyncio

from app.models.integration import Integration
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import WeChatAgentReceipt
from app.models.wechat_knowledge import WeChatKnowledgeBinding
from app.services import wechat_agent_dispatch as dispatch
from app.services.wechat_connection import utcnow
from app.tasks import wechat_agent
from tests.services.test_wechat_agent_runtime import db as db, world as world
from tests.services.delivery_fixtures import wechat_delivery_fields


@pytest_asyncio.fixture
async def recover(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        wechat_agent,
        "_run_async",
        lambda coro: asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=10),
    )

    async def execute():
        return await asyncio.to_thread(wechat_agent.recover_bindings_task.run)

    return execute


@pytest.mark.asyncio
async def test_binding_recovery_covers_more_than_one_hundred_without_idle_or_completed_only(
    world, recover, monkeypatch
):
    pending = []
    for index in range(150):
        binding = await WeChatKnowledgeBinding.create(
            user_id=world.user.id,
            wechat_user_id=f"fair-{index}",
            bot_id=f"fair-{index}",
            token="encrypted",
            base_url="https://ilinkai.weixin.qq.com",
            purpose="agent",
            agent_recovery_at=utcnow() - timedelta(seconds=200 - index),
        )
        await WeChatAgentReceipt.create(
            binding=binding,
            user_id=world.user.id,
            agent_id=world.agent.id,
            message_id=f"message-{index}",
            payload="encrypted",
        )
        pending.append(binding.id)
    completed_binding = await WeChatKnowledgeBinding.create(
        user_id=world.user.id,
        wechat_user_id="completed",
        bot_id="completed",
        token="encrypted",
        base_url="https://ilinkai.weixin.qq.com",
        purpose="agent",
    )
    await WeChatAgentReceipt.create(
        binding=completed_binding,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="completed",
        payload="encrypted",
        status="completed",
    )
    seen = set()

    async def enqueue(identifier):
        seen.add(UUID(str(identifier)))
        return True

    monkeypatch.setattr(dispatch, "enqueue_binding", enqueue)
    for _ in range(3):
        assert await recover() == {"queued": 64}
    assert seen == set(pending)
    assert world.binding.id not in seen
    assert completed_binding.id not in seen


@pytest.mark.asyncio
async def test_completed_receipt_outbox_recovers_and_feature_pause_preserves_work(
    world, recover, monkeypatch
):
    receipt = await WeChatAgentReceipt.create(
        binding=world.binding,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="outbox-only",
        payload="encrypted",
        status="completed",
    )
    delivery = await IntegrationDelivery.create(
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "pending answer"},
    )
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(dispatch, "enqueue_binding", enqueue)
    assert await recover() == {"queued": 1}
    enqueue.assert_awaited_once()
    await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
    assert await recover() == {"queued": 0}
    assert (await IntegrationDelivery.get(id=delivery.id)).status == "pending"
    await IntegrationDelivery.filter(id=delivery.id).update(status="sent")
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["agent_chat"]
    )
    assert await recover() == {"queued": 0}


class LeaseRedis:
    def __init__(self):
        self.value = None

    async def set(self, key, token, **kwargs):
        if self.value is not None:
            return False
        self.value = token
        return True

    async def get(self, key):
        return self.value

    async def eval(self, script, count, key, token):
        if self.value != token:
            return 0
        self.value = None
        return 1


@pytest.mark.asyncio
async def test_concurrent_wakeups_coalesce_and_stale_release_does_not_erase_new_owner(
    monkeypatch,
):
    redis = LeaseRedis()
    monkeypatch.setattr(dispatch, "get_redis", AsyncMock(return_value=redis))
    publish = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "apply_async", publish)
    results = await asyncio.gather(
        dispatch.enqueue_binding("binding"), dispatch.enqueue_binding("binding")
    )
    assert sorted(results) == [False, True]
    assert publish.call_count == 1
    old = redis.value
    redis.value = "new-owner"
    assert not await dispatch.owns_binding_dispatch("binding", old)
    await dispatch.release_binding_dispatch("binding", old)
    assert redis.value == "new-owner"


@pytest.mark.asyncio
async def test_publish_failure_releases_owner_and_allows_durable_recovery(monkeypatch):
    redis = LeaseRedis()
    monkeypatch.setattr(dispatch, "get_redis", AsyncMock(return_value=redis))
    publish = Mock(side_effect=[OSError("broker unavailable"), None])
    monkeypatch.setattr(wechat_agent.process_binding_task, "apply_async", publish)
    with pytest.raises(OSError, match="broker unavailable"):
        await dispatch.enqueue_binding("binding")
    assert redis.value is None
    assert await dispatch.enqueue_binding("binding")


def test_stale_queued_processing_task_never_enters_runtime(monkeypatch):
    from app.services import wechat_agent_runtime

    monkeypatch.setattr(wechat_agent, "_run_async", asyncio.run)
    monkeypatch.setattr(
        dispatch, "owns_binding_dispatch", AsyncMock(return_value=False)
    )
    process = AsyncMock()
    monkeypatch.setattr(wechat_agent_runtime, "process_binding", process)
    assert wechat_agent.process_binding_task.run("binding", "expired") == {
        "stale": True
    }
    process.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_publish_failure_preserves_receipt_and_retries(
    world, recover, monkeypatch
):
    receipt = await WeChatAgentReceipt.create(
        binding=world.binding,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="publish-failure",
        payload="encrypted",
    )
    enqueue = AsyncMock(side_effect=[OSError("broker unavailable"), False, True])
    monkeypatch.setattr(dispatch, "enqueue_binding", enqueue)
    assert await recover() == {"queued": 0}
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert await recover() == {"queued": 0}
    assert await recover() == {"queued": 1}


def test_owned_processing_task_releases_only_its_wakeup_after_runtime(monkeypatch):
    from contextlib import asynccontextmanager
    from app.services import wechat_agent_runtime, wechat_locks

    @asynccontextmanager
    async def lock(name):
        yield

    monkeypatch.setattr(wechat_agent, "_run_async", asyncio.run)
    monkeypatch.setattr(dispatch, "owns_binding_dispatch", AsyncMock(return_value=True))
    release = AsyncMock()
    monkeypatch.setattr(dispatch, "release_binding_dispatch", release)
    monkeypatch.setattr(wechat_locks, "collection_lock", lock)
    monkeypatch.setattr(
        wechat_agent_runtime,
        "process_binding",
        AsyncMock(return_value={"pending": False, "processed": 1}),
    )
    assert wechat_agent.process_binding_task.run("binding", "owner") == {
        "pending": False,
        "processed": 1,
    }
    release.assert_awaited_once_with("binding", "owner")

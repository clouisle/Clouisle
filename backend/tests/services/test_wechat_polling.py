"""Real ORM ownership, fairness and bounded poll batches; external I/O only faked."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.integration import Integration
from app.models.user import User
from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatPollBatch
from app.services import wechat_polling as polling
from app.services import wechat_receiver as receiver
from app.services.wechat_connection import utcnow
from app.tasks.wechat_poll import poll_batch_task


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        await Integration.create(
            name="wechat",
            provider_type="wechat",
            display_name="WeChat",
            enabled_capabilities=["agent_chat"],
        )
        user = await User.create(
            username="poll-owner", email="poll@example.test", hashed_password="unused"
        )
        monkeypatch.setattr(polling.settings, "WECHAT_POLL_BATCH_SIZE", 4)
        monkeypatch.setattr(polling.settings, "WECHAT_POLL_CONCURRENCY", 2)
        monkeypatch.setattr(polling.settings, "WECHAT_POLL_MAX_BATCHES", 2)
        yield user


async def bindings(user, count):
    rows = [
        WeChatKnowledgeBinding(
            user_id=user.id,
            wechat_user_id=f"wechat-{i}",
            bot_id=f"bot-{i}",
            token="test-only",
            base_url="https://ilinkai.weixin.qq.com",
            purpose="agent",
            poll_next_at=utcnow() - timedelta(seconds=10),
        )
        for i in range(count)
    ]
    await WeChatKnowledgeBinding.bulk_create(rows)
    return rows


@pytest.mark.asyncio
async def test_dispatch_bounds_queued_batches_and_restores_publish_failure(
    world, monkeypatch
):
    await bindings(world, 20)
    published = Mock()
    monkeypatch.setattr(poll_batch_task, "apply_async", published)
    assert await polling.dispatch_bindings() == {"batches": 2}
    assert published.call_count == 2
    assert await WeChatKnowledgeBinding.filter(poll_claim__not_isnull=True).count() == 8
    assert await polling.dispatch_bindings() == {"batches": 0}
    assert published.call_count == 2
    first = await WeChatPollBatch.get(id=1)
    await polling._release_batch(first.id, first.claim)
    published.side_effect = OSError("broker down")
    with pytest.raises(OSError, match="broker down"):
        await polling.dispatch_bindings()
    assert (await WeChatPollBatch.get(id=1)).claim is None
    assert await WeChatKnowledgeBinding.filter(poll_claim__not_isnull=True).count() == 4


@pytest.mark.asyncio
async def test_expired_claim_is_replaced_and_old_queued_delivery_cannot_start(
    world, monkeypatch
):
    await bindings(world, 8)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    old = slot.claim
    await WeChatPollBatch.filter(id=slot.id).update(
        expires_at=utcnow() - timedelta(seconds=1)
    )
    await WeChatKnowledgeBinding.filter(poll_claim=old).update(
        poll_next_at=utcnow() - timedelta(seconds=1)
    )
    assert await polling.dispatch_bindings() == {"batches": 1}
    assert (await WeChatPollBatch.get(id=1)).claim != old
    assert await polling.poll_batch(1, str(old)) == {"bindings": 0, "polled": 0}
    assert (await WeChatPollBatch.get(id=1)).claim is not None


@pytest.mark.asyncio
async def test_batch_bounded_concurrency_shared_transport_and_duplicate_delivery(
    world, monkeypatch
):
    await bindings(world, 8)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    active = peak = 0
    clients = []
    entered = asyncio.Event()
    proceed = asyncio.Event()

    async def poll(binding, *, http):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        clients.append(http)
        entered.set()
        await proceed.wait()
        active -= 1
        return {"polled": True}

    monkeypatch.setattr(receiver, "poll_binding", poll)
    task = asyncio.create_task(polling.poll_batch(slot.id, str(slot.claim)))
    await entered.wait()
    assert await polling.poll_batch(slot.id, str(slot.claim)) == {
        "bindings": 0,
        "polled": 0,
    }
    assert (await WeChatPollBatch.get(id=slot.id)).started is True
    proceed.set()
    assert await task == {"bindings": 4, "polled": 4}
    assert peak == 2
    assert len({id(client) for client in clients}) == 1
    assert clients[0].is_closed
    assert (await WeChatPollBatch.get(id=slot.id)).claim is None


@pytest.mark.asyncio
async def test_generation_disable_and_disconnect_prevent_upstream_requests(
    world, monkeypatch
):
    rows = await bindings(world, 4)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    await WeChatKnowledgeBinding.filter(id=rows[0].id).update(generation=uuid4())
    await WeChatKnowledgeBinding.filter(id=rows[1].id).update(status="disconnected")
    await WeChatKnowledgeBinding.filter(id=rows[2].id).update(purpose="none")
    await WeChatKnowledgeBinding.filter(id=rows[3].id).update(token="")
    poll = AsyncMock()
    monkeypatch.setattr(receiver, "poll_binding", poll)
    assert await polling.poll_batch(slot.id, str(slot.claim)) == {
        "bindings": 4,
        "polled": 0,
    }
    poll.assert_not_awaited()
    await WeChatKnowledgeBinding.all().update(
        status="connected",
        purpose="agent",
        token="test-only",
        poll_next_at=utcnow() - timedelta(seconds=1),
    )
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
    assert await polling.poll_batch(slot.id, str(slot.claim)) == {
        "bindings": 0,
        "polled": 0,
    }
    poll.assert_not_awaited()
    assert await polling.dispatch_bindings() == {"batches": 0}


@pytest.mark.asyncio
async def test_slow_batch_is_cancelled_and_all_claims_are_released(world, monkeypatch):
    await bindings(world, 4)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    monkeypatch.setattr(polling, "BATCH_TIMEOUT_SECONDS", 0.02)
    active = 0

    async def slow(binding, *, http):
        nonlocal active
        active += 1
        try:
            await asyncio.sleep(10)
        finally:
            active -= 1

    monkeypatch.setattr(receiver, "poll_binding", slow)
    with pytest.raises(TimeoutError):
        await polling.poll_batch(slot.id, str(slot.claim))
    assert active == 0
    assert (await WeChatPollBatch.get(id=slot.id)).claim is None
    assert not await WeChatKnowledgeBinding.filter(poll_claim__not_isnull=True).exists()


@pytest.mark.asyncio
async def test_oldest_due_bindings_progress_across_more_than_one_batch(
    world, monkeypatch
):
    rows = await bindings(world, 40)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    visited = set()

    async def poll(binding, *, http):
        visited.add(binding.id)
        return {"polled": True}

    monkeypatch.setattr(receiver, "poll_binding", poll)
    for _ in range(5):
        assert await polling.dispatch_bindings() == {"batches": 2}
        for slot in await WeChatPollBatch.all():
            await polling.poll_batch(slot.id, str(slot.claim))
    assert visited == {row.id for row in rows}


@pytest.mark.asyncio
async def test_one_failed_binding_does_not_abort_other_bindings(world, monkeypatch):
    await bindings(world, 4)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    first = slot.bindings[0]["id"]

    async def poll(binding, *, http):
        if str(binding.id) == first:
            raise OSError("one transport failed")
        return {"polled": True}

    monkeypatch.setattr(receiver, "poll_binding", poll)
    assert await polling.poll_batch(slot.id, str(slot.claim)) == {
        "bindings": 4,
        "polled": 3,
    }
    assert (await WeChatPollBatch.get(id=slot.id)).claim is None


@pytest.mark.asyncio
async def test_ambiguous_publish_cleanup_cannot_revoke_running_claim(
    world, monkeypatch
):
    await bindings(world, 4)
    monkeypatch.setattr(poll_batch_task, "apply_async", Mock())
    await polling.dispatch_bindings()
    slot = await WeChatPollBatch.get(id=1)
    assert await polling._start_batch(slot.id, slot.claim) == slot.bindings
    await polling._release_batch(slot.id, slot.claim, unpublished=True)
    saved = await WeChatPollBatch.get(id=slot.id)
    assert saved.claim == slot.claim and saved.started
    assert await WeChatKnowledgeBinding.filter(poll_claim=slot.claim).count() == 4
    await polling._release_batch(slot.id, slot.claim)

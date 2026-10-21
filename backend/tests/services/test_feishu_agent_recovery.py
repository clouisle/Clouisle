"""The Celery recovery entrypoint advances durable receipts and unsent replies."""

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.feishu_agent import FeishuAgentDelivery, FeishuAgentReceipt
from app.tasks import feishu_agent
from tests.services.test_feishu_agent_runtime import (
    db as db,
    receipt_for,
    world as world,
)


@pytest_asyncio.fixture
async def recover_task(monkeypatch):
    loop = asyncio.get_running_loop()

    def run_async(coroutine):
        # The task is synchronous; keep ORM work on the fixture's owning loop.
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=5)

    monkeypatch.setattr(feishu_agent, "_run_async", run_async)

    async def execute():
        result = await asyncio.to_thread(
            feishu_agent.recover_pending_task.apply, throw=True
        )
        return result.get()

    return execute


@pytest.mark.asyncio
async def test_recovery_task_submits_persisted_message_once(world, recover_task):
    receipt = await receipt_for(world, message_id="om_recovery_pending")

    summary = await recover_task()

    saved = await FeishuAgentReceipt.get(id=receipt.id)
    run = await AgentRun.get(id=saved.run_id)
    assert summary == {"integrations": 1, "processed": 1}
    assert saved.status == "submitted"
    assert run.agent_id == world.agent.id
    assert run.user_id == world.user.id
    assert run.status == AgentRunStatus.QUEUED

    await recover_task()
    assert await AgentRun.all().count() == 1
    assert (await FeishuAgentReceipt.get(id=receipt.id)).run_id == run.id


@pytest.mark.asyncio
async def test_recovery_task_delivers_outbox_after_receipt_completed(
    world, recover_task
):
    receipt = await receipt_for(world, message_id="om_recovery_outbox")
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    delivery = await FeishuAgentDelivery.create(
        receipt=receipt,
        event_key="final",
        sequence=0,
        uuid=str(uuid4()),
        text="Recovered answer",
    )

    assert await recover_task() == {"integrations": 1, "processed": 0}

    assert (await FeishuAgentDelivery.get(id=delivery.id)).status == "sent"
    assert world.transport.sent == [
        (receipt.message_id, "Recovered answer", delivery.uuid)
    ]
    assert await recover_task() == {"integrations": 0, "processed": 0}
    assert world.transport.sent == [
        (receipt.message_id, "Recovered answer", delivery.uuid)
    ]

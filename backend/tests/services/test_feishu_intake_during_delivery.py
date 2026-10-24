"""Provider reply latency cannot block receipt acceptance in the same chat."""

import asyncio

import pytest

from app.models.feishu_agent import FeishuAgentReceipt
from app.services import feishu_agent_runtime as runtime
from tests.services.test_feishu_agent_runtime import (
    db as db,
    world as world,
    receipt_for,
    text_event,
)


@pytest.mark.asyncio
async def test_next_message_commits_while_previous_provider_reply_is_blocked(
    world, monkeypatch
):
    first = await receipt_for(world, message_id="om_slow_reply")
    sending = asyncio.Event()
    release = asyncio.Event()

    async def slow_reply(message_id, text, *, uuid):
        sending.set()
        await release.wait()

    async def client(integration):
        from types import SimpleNamespace

        return SimpleNamespace(reply_text=slow_reply)

    monkeypatch.setattr(runtime, "_client_for", client)
    processing = asyncio.create_task(runtime.process_message(str(first.id)))
    try:
        await asyncio.wait_for(sending.wait(), timeout=1)
        identifier = await asyncio.wait_for(
            runtime.accept_message(
                text_event("next message", message_id="om_during_reply")
            ),
            timeout=1,
        )
        receipt = await FeishuAgentReceipt.get(id=identifier)
        assert receipt.user_id == world.user.id
        assert receipt.agent_id == world.agent.id
        assert receipt.status == "pending"
        assert not processing.done()
    finally:
        release.set()
        await processing

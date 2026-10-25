"""Persisted feature selection gates intake, execution and outbound side effects."""

from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import wechat_knowledge as endpoints
from app.integrations.credentials import decrypt_secret
from app.models.agent_run import AgentRun
from app.models.integration import Integration
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import WeChatAgentReceipt
from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatKnowledgeReceipt
from app.schemas.response import BusinessError
from app.services import wechat_agent_io as io
from app.services import wechat_agent_runtime as runtime
from app.services import wechat_connection as connection
from app.services import wechat_ingestion as ingestion
from app.services import wechat_receiver as receiver
from app.services.integration_features import enabled_features
from tests.services.test_wechat_agent_io import (
    io_db as io_db,
    make_receipt,
    receipt_message,
)
from tests.services.test_wechat_agent_runtime import (
    db as db,
    world as world,
    receipt_for,
)
from tests.services.test_wechat_knowledge import collection_db as collection_db, message
from tests.services.delivery_fixtures import wechat_delivery_fields


@pytest.mark.asyncio
async def test_missing_or_disabled_feature_rejects_authorization_without_upstream_call(
    collection_db, monkeypatch
):
    user, _, _, _, _, _ = collection_db
    upstream = AsyncMock()
    monkeypatch.setattr(connection.WeChatClient, "get_qrcode", upstream)
    await Integration.filter(provider_type="wechat").delete()
    assert await enabled_features("wechat") == set()
    with pytest.raises(BusinessError) as denied:
        await connection.start_login(user)
    assert denied.value.msg_key == "integration_feature_disabled"
    upstream.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_purpose_cannot_select_target_but_existing_binding_remains_readable(
    collection_db,
):
    user, _, kb, _, binding, _ = collection_db
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["agent_chat"]
    )
    with pytest.raises(BusinessError) as denied:
        await endpoints.update_purpose(
            binding.id,
            endpoints.PurposeInput(
                purpose="knowledge_collection", knowledge_base_id=kb.id
            ),
            user,
        )
    assert denied.value.msg_key == "integration_feature_disabled"
    assert (await endpoints.features(user))["data"] == {
        "agent_chat": True,
        "knowledge_collection": False,
    }
    assert (await endpoints.bindings(user))["data"][0]["id"] == str(binding.id)
    disabled = await endpoints.update_purpose(
        binding.id, endpoints.PurposeInput(purpose="none"), user
    )
    assert disabled["data"]["purpose"] == "none"
    assert disabled["data"]["collection"]["knowledge_base_id"] == str(kb.id)


@pytest.mark.asyncio
async def test_disabled_intake_keeps_cursor_and_can_accept_same_batch_after_reenable(
    collection_db, monkeypatch
):
    _, _, kb, _, binding, _ = collection_db
    await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
    redis = AsyncMock()
    monkeypatch.setattr(receiver, "get_redis", redis)
    assert await receiver.poll_binding(binding) == {
        "polled": False,
        "reason": "feature_disabled",
    }
    redis.assert_not_awaited()
    batch = {"msgs": [message()], "get_updates_buf": "next-cursor"}
    assert (await receiver.accept_updates(binding, batch)).accepted == 0
    assert not await WeChatKnowledgeReceipt.all().exists()
    assert (await WeChatKnowledgeBinding.get(id=binding.id)).cursor == binding.cursor
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["knowledge_collection"]
    )
    result = await receiver.accept_updates(binding, batch)
    assert result.agent_receipt_ids == []
    ids = result.knowledge_receipt_ids
    receipt = await WeChatKnowledgeReceipt.get(id=ids[0])
    assert receipt.knowledge_base_id == kb.id
    assert receipt.message_id == str(message()["message_id"])
    assert (
        decrypt_secret((await WeChatKnowledgeBinding.get(id=binding.id)).cursor)
        == "next-cursor"
    )


@pytest.mark.asyncio
async def test_disabled_agent_work_resumes_once_after_reenable(world):
    receipt = await receipt_for(world)
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["knowledge_collection"]
    )
    await runtime.process_binding(str(world.binding.id))
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert not await AgentRun.all().exists()
    assert not world.io.normalized
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["agent_chat"]
    )
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))
    assert (
        await WeChatAgentReceipt.get(id=receipt.id)
    ).run_id == world.submission.run.id
    assert await AgentRun.all().count() == 1


@pytest.mark.asyncio
async def test_feature_disabled_during_input_preparation_cannot_submit_run(
    world, monkeypatch
):
    receipt = await receipt_for(world)
    original = world.io.normalize_input

    async def disable_after_normalize(*args):
        prepared = await original(*args)
        await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
        return prepared

    monkeypatch.setattr(io, "normalize_input", disable_after_normalize)
    await runtime.process_binding(str(world.binding.id))
    assert not await AgentRun.all().exists()
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_disabled_delivery_stays_pending_and_sends_once_after_reenable(
    io_db, monkeypatch
):
    user, _, agent, binding, _, _ = io_db
    receipt = await make_receipt(binding, user, agent, receipt_message([]))
    delivery = await IntegrationDelivery.create(
        **wechat_delivery_fields(receipt),
        event_key="final",
        sequence=0,
        payload={"kind": "text", "text": "Canonical answer"},
    )
    sent = []

    class Transport:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send_text(self, recipient, text, token, **kwargs):
            sent.append((recipient, text, kwargs["client_id"]))

    monkeypatch.setattr(io, "WeChatClient", Transport)
    await Integration.filter(provider_type="wechat").update(enabled_capabilities=[])
    await io.deliver_pending(binding, user)
    assert not sent
    assert (await IntegrationDelivery.get(id=delivery.id)).status == "pending"
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["agent_chat"]
    )
    await io.deliver_pending(binding, user)
    await io.deliver_pending(binding, user)
    assert sent == [("wechat-user", "Canonical answer", str(delivery.id))]
    assert (await IntegrationDelivery.get(id=delivery.id)).status == "sent"


@pytest.mark.asyncio
async def test_disabled_collection_preserves_pending_receipt_without_processing(
    collection_db, monkeypatch
):
    _, _, _, _, binding, _ = collection_db
    accepted = await receiver.accept_updates(binding, {"msgs": [message()]})
    receipt = await WeChatKnowledgeReceipt.get(id=accepted.knowledge_receipt_ids[0])
    work = AsyncMock()
    monkeypatch.setattr(ingestion, "process_item", work)
    await Integration.filter(provider_type="wechat").update(
        enabled_capabilities=["agent_chat"]
    )
    assert await ingestion._process_receipt(str(receipt.id)) == {"status": "pending"}
    await receipt.refresh_from_db()
    assert receipt.status == "pending"
    assert receipt.reply_status == "pending"
    assert receipt.lease_owner is None
    work.assert_not_awaited()

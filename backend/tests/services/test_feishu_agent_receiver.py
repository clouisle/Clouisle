"""SDK WebSocket acknowledgements and durable private-message acceptance."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.models.agent import Agent, AgentStatus, AgentVisibility
from app.models.feishu_agent import FeishuAgentPreference, FeishuAgentReceipt
from app.models.feishu_user import FeishuUser
from app.models.integration import Integration
from app.models.user import Team, TeamMember, User
from app.services import feishu_agent_events as events
from app.services import feishu_agent_receiver as receiver


@pytest_asyncio.fixture
async def channel(monkeypatch):
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        user = await User.create(
            username="feishu-owner",
            email="owner@example.test",
            hashed_password="unused",
            is_active=True,
            approval_status="approved",
        )
        team = await Team.create(name="Feishu team")
        await TeamMember.create(team=team, user=user, role="owner")
        agent = await Agent.create(
            name="Support",
            team=team,
            created_by=user,
            status=AgentStatus.PUBLISHED,
            visibility=AgentVisibility.TEAM,
        )
        integration = await Integration.create(
            name="feishu",
            provider_type="feishu",
            display_name="Feishu",
            enabled_capabilities=["agent_chat"],
            config={
                "app_id": "cli_long",
                "agent_chat_connection_mode": "long_connection",
            },
            credentials={"app_secret": encrypt_secret("long-secret")},
        )
        await FeishuUser.create(user=user, feishu_user_id="user_1")
        await FeishuAgentPreference.create(
            integration=integration, user=user, agent=agent, is_enabled=True
        )
        monkeypatch.setattr(events, "_enqueue_receipt", lambda receipt_id: None)
        yield SimpleNamespace(
            user=user,
            agent=agent,
            integration=integration,
            config=await receiver._load_config(),
        )


def envelope(*, app_id="cli_long", message_id="om_long", sender="user_1"):
    return {
        "schema": "2.0",
        "header": {
            "app_id": app_id,
            "event_type": "im.message.receive_v1",
            "event_id": str(uuid4()),
        },
        "event": {
            "sender": {"sender_type": "user", "sender_id": {"user_id": sender}},
            "message": {
                "chat_id": "oc_long",
                "chat_type": "p2p",
                "message_id": message_id,
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
            },
        },
    }


async def sdk_ack(payload, config):
    """Use the installed SDK's actual frame decoder, dispatcher and ACK encoder."""
    handler = receiver.build_event_handler(config, asyncio.get_running_loop())

    def dispatch():
        from lark_oapi.ws.client import Client
        from lark_oapi.ws.const import (
            HEADER_MESSAGE_ID,
            HEADER_TRACE_ID,
            HEADER_SUM,
            HEADER_SEQ,
            HEADER_TYPE,
        )
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame

        async def handle():
            client = Client(config.app_id, "not-used", event_handler=handler)
            sent = []

            async def write(data):
                reply = Frame()
                reply.ParseFromString(data)
                sent.append(json.loads(reply.payload))

            client._write_message = write
            frame = Frame(
                SeqID=1,
                LogID=1,
                service=1,
                method=1,
                payload=json.dumps(payload).encode(),
            )
            for key, value in [
                (HEADER_MESSAGE_ID, "frame-1"),
                (HEADER_TRACE_ID, "trace-1"),
                (HEADER_SUM, "1"),
                (HEADER_SEQ, "0"),
                (HEADER_TYPE, "event"),
            ]:
                header = frame.headers.add()
                header.key, header.value = key, value
            await client._handle_data_frame(frame)
            client._cache._cron.cancel()
            await asyncio.gather(client._cache._cron, return_exceptions=True)
            return sent[0]["code"]

        with asyncio.Runner() as runner:
            return runner.run(handle())

    return await asyncio.to_thread(dispatch)


@pytest.mark.asyncio
async def test_sdk_ack_commits_one_owned_receipt_across_redelivery(channel):
    payload = envelope()
    assert await sdk_ack(payload, channel.config) == 200
    receipt = await FeishuAgentReceipt.get(message_id="om_long")
    assert receipt.user_id == channel.user.id
    assert receipt.agent_id == channel.agent.id
    assert receipt.text == "hello"
    assert receipt.status == "pending"
    assert await sdk_ack(payload, channel.config) == 200
    assert await FeishuAgentReceipt.filter(message_id="om_long").count() == 1
    # Both transports use the same provider idempotency key.
    assert await events.receive_message(payload["event"], app_id="cli_long") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["app", "mode", "disabled", "capability", "credentials", "unbound", "private"],
)
async def test_untrusted_or_no_longer_authorized_message_creates_no_receipt(
    channel, change
):
    payload = envelope()
    if change == "app":
        payload["header"]["app_id"] = "cli_foreign"
    elif change == "mode":
        await Integration.filter(id=channel.integration.id).update(
            config={
                **channel.integration.config,
                "agent_chat_connection_mode": "callback",
            }
        )
    elif change == "disabled":
        await Integration.filter(id=channel.integration.id).update(is_enabled=False)
    elif change == "capability":
        await Integration.filter(id=channel.integration.id).update(
            enabled_capabilities=[]
        )
    elif change == "credentials":
        await Integration.filter(id=channel.integration.id).update(
            credentials={"app_secret": encrypt_secret("changed")}
        )
    elif change == "unbound":
        payload["event"]["sender"]["sender_id"]["user_id"] = "unknown"
    else:
        stranger = await User.create(
            username="stranger", email="stranger@example.test", hashed_password="unused"
        )
        await Agent.filter(id=channel.agent.id).update(
            visibility=AgentVisibility.PRIVATE, created_by_id=stranger.id
        )
    assert await sdk_ack(payload, channel.config) == (
        500 if change == "credentials" else 200
    )
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_broker_failure_keeps_committed_receipt_recoverable(channel, monkeypatch):
    def fail_publish(receipt_id):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(events, "_enqueue_receipt", fail_publish)
    assert await sdk_ack(envelope(), channel.config) == 200
    assert (await FeishuAgentReceipt.get(message_id="om_long")).status == "pending"
    assert await sdk_ack(envelope(), channel.config) == 200
    assert await FeishuAgentReceipt.all().count() == 1


@pytest.mark.asyncio
async def test_failed_commit_produces_retryable_sdk_ack(channel, monkeypatch):
    original = FeishuAgentReceipt.create
    monkeypatch.setattr(
        FeishuAgentReceipt,
        "create",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    assert await sdk_ack(envelope(), channel.config) == 500
    assert not await FeishuAgentReceipt.all().exists()
    monkeypatch.setattr(FeishuAgentReceipt, "create", original)
    assert await sdk_ack(envelope(), channel.config) == 200
    assert (
        await FeishuAgentReceipt.get(message_id="om_long")
    ).user_id == channel.user.id


@pytest.mark.asyncio
async def test_intake_timeout_never_acknowledges_an_uncommitted_message(
    channel, monkeypatch
):
    original = FeishuAgentReceipt.create
    cancelled = asyncio.Event()

    async def stalled_commit(**kwargs):
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(receiver, "EVENT_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(FeishuAgentReceipt, "create", stalled_commit)
    assert await sdk_ack(envelope(), channel.config) == 500
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert not await FeishuAgentReceipt.all().exists()
    monkeypatch.setattr(FeishuAgentReceipt, "create", original)
    monkeypatch.setattr(receiver, "EVENT_TIMEOUT_SECONDS", 3)
    assert await sdk_ack(envelope(), channel.config) == 200
    assert (
        await FeishuAgentReceipt.get(message_id="om_long")
    ).user_id == channel.user.id

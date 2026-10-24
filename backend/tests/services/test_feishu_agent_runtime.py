"""Feishu Agent runtime boundaries against an isolated real ORM.

The Tortoise ORM is real (SQLite in memory). The two external boundaries are
stubbed: the shared durable submission service (run creation) and the Feishu
transport client (``reply_text``). Everything the runtime itself owns —
receipts, sessions, deliveries, identity routing, command precedence, answer
accumulation, crash-safe dispatch and deduplication — runs against the
database.
"""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.models.agent import Agent, AgentStatus, AgentVisibility
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.feishu_agent import (
    FeishuAgentPreference,
    FeishuAgentReceipt,
    FeishuAgentSession,
)
from app.models.feishu_user import FeishuUser
from app.models.integration import Integration
from app.models.integration_delivery import IntegrationDelivery
from app.models.user import Team, TeamMember, User
from app.models.user_sso_connection import UserSSOConnection
from app.services import feishu_agent_runtime as runtime
from app.services.wechat_connection import utcnow

APP_ID = "cli_test"
CHAT_ID = "oc_chat_1"
TENANT_USER_ID = "u_tenant_1"


class FakeSubmission:
    """Stand-in for the shared durable submission boundary."""

    def __init__(self):
        self.calls = []
        self.run = None
        self.error = None

    async def __call__(self, agent_id, chat_in, user, **kwargs):
        self.calls.append((agent_id, chat_in, kwargs))
        if self.error is not None:
            raise self.error
        from app.models.agent import Conversation

        conversation_id = (
            chat_in.conversation_id
            or (await Conversation.create(agent_id=agent_id, user_id=user.id)).id
        )
        run = await AgentRun.create(
            id=uuid4(),
            agent_id=agent_id,
            conversation_id=conversation_id,
            user_id=user.id,
            mode=AgentRunMode.SEND,
            status=AgentRunStatus.QUEUED,
            submitted_at=utcnow(),
        )
        self.run = run
        return SimpleNamespace(
            run=run,
            run_id=run.id,
            payload={"run_id": str(run.id)},
            prepared=chat_in,
        )


class FakeTransport:
    """Stand-in for FeishuClient.reply_text."""

    def __init__(self):
        self.sent = []
        self.error = None

    async def __call__(self, message_id, text, *, uuid):
        self.sent.append((message_id, text, uuid))
        if self.error is not None:
            raise self.error

    async def reply_markdown(self, message_id, text, *, uuid):
        self.sent.append((message_id, text, uuid))
        if self.error is not None:
            raise self.error


class FakeAssetTransport(FakeTransport):
    """Feishu transport with native media upload and reply recording."""

    def __init__(self):
        super().__init__()
        self.uploads = []
        self.media = []
        self.upload_error = None
        self.reply_error = None

    async def upload_image(self, content, *, filename, content_type):
        self.uploads.append(("image", content, filename, content_type))
        if self.upload_error is not None:
            raise self.upload_error
        return "img_key"

    async def upload_file(self, content, *, filename, content_type, file_type="stream"):
        self.uploads.append((file_type, content, filename, content_type))
        if self.upload_error is not None:
            raise self.upload_error
        return "file_key"

    async def reply_media(self, message_id, *, msg_type, key, uuid):
        self.media.append((message_id, msg_type, key, uuid))
        if self.reply_error is not None:
            raise self.reply_error


def text_event(
    text="hello",
    *,
    message_id="om_1",
    chat_id=CHAT_ID,
    chat_type="p2p",
    message_type="text",
    sender_type="user",
    sender=TENANT_USER_ID,
    app_id=APP_ID,
):
    sender_id = {"user_id": sender}
    if sender is None:
        sender_id = {}
    return {
        "app_id": app_id,
        "sender": {"sender_type": sender_type, "sender_id": sender_id},
        "message": {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "message_type": message_type,
            "content": json.dumps({"text": text}),
        },
    }


async def make_agent(team, user, name="Test agent"):
    return await Agent.create(
        id=uuid4(),
        name=name,
        team=team,
        created_by=user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
        enable_attachments=False,
    )


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest_asyncio.fixture
async def world(db, monkeypatch):
    user = await User.create(
        id=uuid4(),
        username="owner",
        email="owner@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    team = await Team.create(id=uuid4(), name="Agent team")
    await TeamMember.create(id=uuid4(), team=team, user=user, role="owner")
    agent = await make_agent(team, user)
    integration = await Integration.create(
        name="feishu",
        provider_type="feishu",
        display_name="Feishu",
        is_enabled=True,
        enabled_capabilities=["agent_chat"],
        config={"app_id": APP_ID},
        credentials={"app_secret": encrypt_secret("not-real")},
    )
    await FeishuUser.create(user=user, feishu_user_id=TENANT_USER_ID)
    await FeishuAgentPreference.create(
        integration=integration, user=user, agent=agent, is_enabled=True
    )
    submission = FakeSubmission()
    transport = FakeTransport()
    monkeypatch.setattr("app.services.agent_submission.submit_chat_run", submission)
    monkeypatch.setattr("app.services.agent_submission.dispatch_run", _noop_dispatch)
    monkeypatch.setattr(runtime, "_client_for", _client_for(transport))
    return SimpleNamespace(
        user=user,
        team=team,
        agent=agent,
        integration=integration,
        submission=submission,
        transport=transport,
    )


def _client_for(transport):
    async def _factory(integration):
        client = SimpleNamespace(reply_text=transport)
        if hasattr(transport, "reply_markdown"):
            client.reply_markdown = transport.reply_markdown
        for name in ("upload_image", "upload_file", "reply_media"):
            if hasattr(transport, name):
                setattr(client, name, getattr(transport, name))
        return client

    return _factory


async def _noop_dispatch(payload, run):
    return None


async def session_for(world, agent_id=None):
    """The session row for one Agent in this chat (per-Agent rows by design)."""
    agent_id = agent_id or world.agent.id
    return await FeishuAgentSession.get(
        integration_id=world.integration.id,
        chat_id=CHAT_ID,
        user_id=world.user.id,
        agent_id=agent_id,
    )


async def receipt_for(world, text="hello", message_id=None, **kwargs):
    message_id = message_id or f"om_{uuid4().hex}"
    receipt_id = await runtime.accept_message(
        text_event(text, message_id=message_id, **kwargs)
    )
    assert receipt_id is not None
    return await FeishuAgentReceipt.get(id=receipt_id)


def delivery_fields(receipt):
    """Identity fields a durable outbound row copies from its receipt."""
    return {
        "provider_type": "feishu",
        "integration_id": receipt.integration_id,
        "receipt_id": receipt.id,
        "user_id": receipt.user_id,
        "agent_id": receipt.agent_id,
        "run_id": receipt.run_id,
        "chat_id": receipt.chat_id,
        "message_id": receipt.message_id,
    }


# --- inbound validation and identity -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "post"])
async def test_attachment_message_reaches_run_with_private_asset(
    world, monkeypatch, kind
):
    from unittest.mock import AsyncMock
    from app.services import feishu_agent_input as inputs
    from app.models.asset import Asset

    await Agent.filter(id=world.agent.id).update(enable_attachments=True)
    event = text_event(message_type=kind, message_id=f"om_attachment_{kind}")
    content = {"file_key": "file_secret", "file_name": "report.txt"}
    if kind == "post":
        content = {
            "zh_cn": {
                "title": "总结",
                "content": [
                    [
                        {"tag": "text", "text": "分析一下"},
                        {
                            "tag": "file",
                            "file_key": "file_secret",
                            "file_name": "report.txt",
                        },
                    ]
                ],
            }
        }
    event["message"]["content"] = json.dumps(content)
    receipt_id = await runtime.accept_message(event)
    assert receipt_id is not None
    assert await runtime.accept_message(event) is None
    download = AsyncMock(return_value=(b"report content", "", "text/plain"))
    transport_factory = runtime._client_for

    async def client_for(integration):
        client = await transport_factory(integration)
        client.download_message_resource = download
        return client

    monkeypatch.setattr(runtime, "_client_for", client_for)
    monkeypatch.setattr(inputs, "_store_upload", AsyncMock())
    await runtime.process_pending()
    receipt = await FeishuAgentReceipt.get(id=receipt_id)
    assert receipt.status == "submitted"
    request = world.submission.calls[0][1]
    assert request.file_urls[0].filename == "report.txt"
    asset = await Asset.get(id=request.file_urls[0].asset_id)
    assert asset.created_by_id == world.user.id
    assert asset.team_id is None
    assert request.message == ("总结\n分析一下" if kind == "post" else "")
    await runtime.process_pending()
    assert download.await_count == 1
    assert len(world.submission.calls) == 1


@pytest.mark.asyncio
async def test_disabled_attachments_receive_explanation(world):
    event = text_event(message_type="file")
    event["message"]["content"] = json.dumps(
        {"file_key": "file_key", "file_name": "report.txt"}
    )
    receipt_id = await runtime.accept_message(event)
    await runtime.process_pending()
    receipt = await FeishuAgentReceipt.get(id=receipt_id)
    assert receipt.status == "error"
    assert receipt.error == "feishu_agent_attachments_disabled"
    assert not world.submission.calls
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "sent"


@pytest.mark.asyncio
async def test_accept_persists_durable_receipt(world):
    receipt = await receipt_for(world)

    assert receipt.integration_id == world.integration.id
    assert receipt.user_id == world.user.id
    assert receipt.chat_id == CHAT_ID
    assert receipt.text == "hello"
    assert receipt.status == "pending"


@pytest.mark.asyncio
async def test_replayed_message_creates_no_second_receipt(world):
    await receipt_for(world, message_id="om_dup")
    assert await runtime.accept_message(text_event(message_id="om_dup")) is None
    assert await FeishuAgentReceipt.filter(message_id="om_dup").count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        text_event(sender_type="app"),
        text_event(chat_type="group"),
        text_event(message_type="image"),
        text_event(sender=None),
        text_event(app_id="cli_other"),
        text_event(text="   "),
    ],
)
async def test_unacceptable_events_are_ignored(world, event):
    assert await runtime.accept_message(event) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_disabled_integration_is_ignored(world):
    await Integration.filter(id=world.integration.id).update(is_enabled=False)
    assert await runtime.accept_message(text_event()) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_unconfigured_channel_is_ignored(world):
    await Integration.filter(id=world.integration.id).update(config={})
    assert await runtime.accept_message(text_event()) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_inactive_and_unapproved_users_are_ignored(world):
    await User.filter(id=world.user.id).update(is_active=False)
    assert await runtime.accept_message(text_event()) is None
    await User.filter(id=world.user.id).update(
        is_active=True, approval_status="pending"
    )
    assert await runtime.accept_message(text_event(message_id="om_pending")) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_sso_subject_resolves_without_directory_mapping(world):
    """A union_id sender resolves through the SSO connection of this channel."""
    await FeishuUser.filter(feishu_user_id=TENANT_USER_ID).delete()
    await UserSSOConnection.create(
        user=world.user,
        integration=world.integration,
        provider_user_id="on_union_1",
    )
    event = text_event(message_id="om_sso")
    event["sender"]["sender_id"] = {"union_id": "on_union_1"}
    receipt_id = await runtime.accept_message(event)

    assert receipt_id is not None
    receipt = await FeishuAgentReceipt.get(id=receipt_id)
    assert receipt.user_id == world.user.id


@pytest.mark.asyncio
async def test_tenant_id_never_probes_the_sso_namespace(world):
    """A tenant user_id must not match an SSO subject row."""
    await FeishuUser.filter(feishu_user_id=TENANT_USER_ID).delete()
    await UserSSOConnection.create(
        user=world.user,
        integration=world.integration,
        provider_user_id=TENANT_USER_ID,
    )
    assert await runtime.accept_message(text_event()) is None


@pytest.mark.asyncio
async def test_unknown_sender_is_ignored(world):
    assert await runtime.accept_message(text_event(sender="u_stranger")) is None
    assert not await FeishuAgentReceipt.all().exists()


# --- submission and sessions -------------------------------------------------


@pytest.mark.asyncio
async def test_receipt_submits_run_and_maps_before_dispatch(world):
    receipt = await receipt_for(world)

    result = await runtime.process_message(str(receipt.id))

    assert result == {"processed": 1, "status": "submitted"}
    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.run_id == world.submission.run.id
    assert world.submission.calls, "submission boundary was not used"
    session = await session_for(world)
    assert session.active_run_id == refreshed.run_id
    assert session.conversation_id is not None
    assert session.agent_id == world.agent.id


@pytest.mark.asyncio
async def test_second_message_while_running_starts_no_second_run(world):
    await receipt_for(world, message_id="om_first")
    await runtime.process_pending()
    run = world.submission.run

    second = await receipt_for(world, text="second", message_id="om_second")
    await runtime.process_pending()

    assert len(world.submission.calls) == 1
    assert await AgentRun.all().count() == 1
    busy = await IntegrationDelivery.filter(
        receipt_id=second.id, event_key="busy"
    ).first()
    assert busy is not None
    assert busy.text
    assert (await FeishuAgentReceipt.get(id=second.id)).status == "pending"
    assert run.status == AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_unknown_receipt_id_is_not_found(world):
    assert await runtime.process_message(str(uuid4())) == {
        "processed": 0,
        "status": "not_found",
    }


@pytest.mark.asyncio
async def test_unpublished_agent_blocks_processing(world):
    """Selection never grants permission to execute a draft Agent."""
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)
    assert await runtime.accept_message(text_event()) is None

    # A receipt accepted while the Agent was published is still explained when
    # the Agent is withdrawn before processing.
    receipt = await FeishuAgentReceipt.create(
        integration_id=world.integration.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        chat_id=CHAT_ID,
        chat_type="p2p",
        message_id="om_withdrawn",
        sender_id=TENANT_USER_ID,
        text="hello",
    )

    await runtime.process_message(str(receipt.id))

    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "feishu_agent_agent_unavailable"
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_other_available_agent_does_not_override_personal_choice(world):
    """Availability never silently changes the user's selected Agent."""
    other = await make_agent(world.team, world.user, name="Other agent")
    receipt = await receipt_for(world)

    await runtime.process_message(str(receipt.id))

    assert world.submission.calls[0][0] == world.agent.id
    assert other.id != world.submission.calls[0][0]


# --- commands ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_command_lists_only_accessible_agents(world):
    outsider = await User.create(
        username="outsider", email="out@example.test", hashed_password="unused"
    )
    hidden = await make_agent(world.team, outsider, name="Hidden agent")
    await Agent.filter(id=hidden.id).update(visibility=AgentVisibility.PRIVATE)
    command = await receipt_for(world, text="/agents", message_id="om_agents")

    await runtime.process_message(str(command.id))

    delivery = await IntegrationDelivery.get(receipt_id=command.id, event_key="command")
    assert world.agent.name in delivery.text
    assert hidden.name not in delivery.text
    assert (await FeishuAgentReceipt.get(id=command.id)).status == "completed"
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_use_command_switches_agent_for_later_messages(world):
    second = await make_agent(world.team, world.user, name="Second agent")
    use = await receipt_for(world, text=f"/use {second.id}", message_id="om_use")
    # The callback acknowledges independently queued Celery tasks. A following
    # event must bind to the selection immediately, even if /use has not run yet.
    message = await receipt_for(world, text="hello", message_id="om_after_use")
    assert use.agent_id == world.agent.id
    assert message.agent_id == second.id

    # Simulate the later message task winning the broker race; the durable chat
    # drain still applies /use before submitting the ordinary message.
    await runtime.process_message(str(message.id))
    assert (await FeishuAgentReceipt.get(id=use.id)).status == "completed"
    assert world.submission.calls[-1][0] == second.id

    following = await receipt_for(world, text="again", message_id="om_after_use_2")
    await runtime.process_message(str(following.id))


@pytest.mark.asyncio
async def test_use_switches_future_messages_while_old_agent_run_continues(world):
    second = await make_agent(world.team, world.user, name="Second agent")
    await receipt_for(world, message_id="om_old_run")
    await runtime.process_pending()
    old_run = world.submission.run
    await AgentRun.filter(id=old_run.id).update(status=AgentRunStatus.RUNNING)

    switch = await receipt_for(
        world, text=f"/use {second.id}", message_id="om_switch_running"
    )
    await runtime.process_message(str(switch.id))
    next_message = await receipt_for(world, text="next", message_id="om_new_agent")

    assert next_message.agent_id == second.id
    assert (await AgentRun.get(id=old_run.id)).status == AgentRunStatus.RUNNING
    assert (await session_for(world)).active_run_id == old_run.id
    assert (await session_for(world, second.id)).agent_id == second.id


@pytest.mark.asyncio
async def test_use_command_rejects_unknown_agent(world):
    use = await receipt_for(world, text="/use 99", message_id="om_use_bad")

    await runtime.process_message(str(use.id))

    delivery = await IntegrationDelivery.get(receipt_id=use.id, event_key="command")
    assert delivery.text
    assert (await FeishuAgentReceipt.get(id=use.id)).status == "completed"
    assert not world.submission.calls
    # The invalid selection must not rebind the chat to another Agent.
    session = await session_for(world)
    assert session.agent_id == world.agent.id
    assert session.conversation_id is None


@pytest.mark.asyncio
async def test_new_command_resets_only_when_idle(world):
    await receipt_for(world, message_id="om_first")
    await runtime.process_pending()
    run = world.submission.run

    busy = await receipt_for(world, text="/new", message_id="om_new_busy")
    await runtime.process_pending()
    session = await session_for(world)
    assert session.conversation_id is not None

    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await FeishuAgentReceipt.filter(id=busy.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()

    session = await session_for(world)
    assert session.conversation_id is None
    assert session.active_run_id is None
    assert (await FeishuAgentReceipt.get(id=busy.id)).status == "completed"


@pytest.mark.asyncio
async def test_stop_command_stops_run_and_cancels_queued_receipts(world):
    await receipt_for(world, message_id="om_running")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)

    queued = await receipt_for(world, text="queued", message_id="om_queued")
    stop = await receipt_for(world, text="/stop", message_id="om_stop")
    await runtime.process_pending()

    assert (await FeishuAgentReceipt.get(id=queued.id)).status == "error"
    assert (await FeishuAgentReceipt.get(id=stop.id)).status == "completed"
    refreshed = await AgentRun.get(id=run.id)
    assert refreshed.status in (AgentRunStatus.STOPPING, AgentRunStatus.STOPPED)


@pytest.mark.asyncio
async def test_status_and_help_commands_do_not_start_runs(world):
    help_receipt = await receipt_for(world, text="/help", message_id="om_help")
    status_receipt = await receipt_for(world, text="/状态", message_id="om_status")

    await runtime.process_pending()

    assert not world.submission.calls
    for receipt in (help_receipt, status_receipt):
        assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"
        assert await IntegrationDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_natural_language_is_not_a_command(world):
    receipt = await receipt_for(world, text="停止", message_id="om_natural")

    await runtime.process_message(str(receipt.id))

    assert world.submission.calls, "bare Chinese words must stay user content"
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "submitted"


# --- waiting answers ---------------------------------------------------------


async def _waiting_run(world, questions):
    receipt = await receipt_for(world, message_id="om_ask")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-1",
        pending_tool_name="ask_user",
        pending_tool_input={"questions": questions},
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()
    return receipt, run


@pytest.mark.asyncio
async def test_waiting_run_announces_question_and_ignores_older_message(world):
    receipt, run = await _waiting_run(
        world,
        [
            {
                "id": "q1",
                "question": "Which one?",
                "required": True,
                "options": ["A", "B"],
            }
        ],
    )

    question = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="ask:call-1"
    )
    assert question.text
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING

    older = await FeishuAgentReceipt.create(
        integration_id=world.integration.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        chat_id=CHAT_ID,
        chat_type="p2p",
        message_id="om_older",
        sender_id=TENANT_USER_ID,
        text="A",
        created_at=utcnow() - timedelta(minutes=5),
    )
    # The run's own receipt can be revisited while this earlier accepted text
    # must remain ineligible to answer a question sent after it.
    await runtime.process_message(str(older.id))
    session = await session_for(world)
    assert session.pending_answers == {}
    assert (await FeishuAgentReceipt.get(id=older.id)).status == "pending"


@pytest.mark.asyncio
async def test_invalid_choice_is_rejected_and_not_replayed(world):
    await _waiting_run(
        world,
        [
            {
                "id": "q1",
                "question": "Which one?",
                "required": True,
                "options": ["A", "B"],
            }
        ],
    )
    invalid = await receipt_for(world, text="C", message_id="om_bad_choice")

    await runtime.process_pending()

    session = await session_for(world)
    assert session.pending_answers == {}
    rejection = await IntegrationDelivery.filter(
        receipt_id=invalid.id, event_key="answer_error"
    ).first()
    assert rejection is not None
    assert (await FeishuAgentReceipt.get(id=invalid.id)).status == "completed"
    await runtime.process_pending()
    assert (await session_for(world)).pending_answers == {}


@pytest.mark.asyncio
async def test_answer_resumes_waiting_run_without_a_new_run(world):
    receipt, run = await _waiting_run(
        world,
        [{"id": "q1", "question": "Why?", "required": True}],
    )
    answer = await receipt_for(world, text="because", message_id="om_answer")
    submitted = []

    async def fake_submit(run_id, **kwargs):
        submitted.append(kwargs)
        return SimpleNamespace(id=run.id, status=AgentRunStatus.QUEUED)

    import app.services.agent_run_store as store

    real_submit = store.submit_user_answers
    store.submit_user_answers = fake_submit
    try:
        await runtime.process_pending()
    finally:
        store.submit_user_answers = real_submit

    assert submitted and submitted[0]["answers"] == {"q1": "because"}
    assert submitted[0]["skipped"] is False
    assert (await FeishuAgentReceipt.get(id=answer.id)).status == "completed"
    session = await session_for(world)
    assert session.pending_answers == {}
    assert await AgentRun.all().count() == 1
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


# --- terminal output ---------------------------------------------------------


@pytest.mark.asyncio
async def test_terminal_run_delivers_canonical_text(world):
    receipt = await receipt_for(world, message_id="om_final")
    await runtime.process_pending()
    run = world.submission.run
    from app.models.agent import Message, MessageRole

    await Message.create(
        id=uuid4(),
        conversation_id=run.conversation_id,
        role=MessageRole.ASSISTANT,
        content="the answer",
    )
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=(await Message.all().order_by("-created_at").first()).id,
        finished_at=utcnow(),
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()

    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.text == "the answer"
    assert delivery.kind == "markdown"
    assert delivery.provider_uuid and len(delivery.provider_uuid) <= 50
    final = next(sent for sent in world.transport.sent if sent[1] == delivery.text)
    assert final[0] == receipt.message_id
    assert final[2] == delivery.provider_uuid


@pytest.mark.asyncio
async def test_failed_run_sends_generic_notice_only(world):
    await User.filter(id=world.user.id).update(locale="zh")
    receipt = await receipt_for(world, message_id="om_failed")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.FAILED,
        error_message="provider secret detail",
        finished_at=utcnow(),
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()

    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert "provider secret detail" not in delivery.text
    assert delivery.text.strip()


@pytest.mark.asyncio
async def test_disabled_feature_preserves_terminal_run_until_reenabled(world):
    receipt = await receipt_for(world, message_id="om_off")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await Integration.filter(id=world.integration.id).update(enabled_capabilities=[])
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()

    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"
    assert refreshed.error is None
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()
    await Integration.filter(id=world.integration.id).update(
        enabled_capabilities=["agent_chat"]
    )
    await runtime.process_pending()
    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error is None
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "sent"


@pytest.mark.asyncio
async def test_empty_canonical_output_sends_explicit_notice(world):
    receipt = await receipt_for(world, message_id="om_empty")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.text.strip()


@pytest.mark.asyncio
async def test_concurrent_finalization_queues_the_answer_once(world):
    receipt = await receipt_for(world, message_id="om_once")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    stale = await FeishuAgentReceipt.get(id=receipt.id)

    await runtime.process_pending()
    # Simulate a racing recovery pass still holding the pre-finalization row.
    await runtime._finalize_receipt(stale, await session_for(world), run)

    assert (
        await IntegrationDelivery.filter(
            receipt_id=receipt.id, event_key="final"
        ).count()
        == 1
    )


# --- generated artifacts -----------------------------------------------------


async def _generated_asset(
    world,
    *,
    conversation_id=None,
    ref="abcd",
    content_type="image/png",
    size=4,
):
    from app.models.asset import Asset, AssetScopeRef, AssetScopeType

    asset = await Asset.create(
        id=uuid4(),
        storage_key=f"generated-images/{uuid4().hex}.bin",
        original_filename="artifact.bin",
        display_filename="artifact.bin",
        content_type=content_type,
        size=size,
        checksum="0" * 64,
        source="generated_media",
        team_id=world.team.id,
        created_by_id=world.user.id,
    )
    if conversation_id is not None:
        await AssetScopeRef.create(
            id=uuid4(),
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation_id,
            asset=asset,
            ref=ref,
        )
    return asset


def _image_display(ref="abcd", *, success=True):
    return {
        "kind": "media.image",
        "success": success,
        "images": [{"image": {"asset_ref": ref}}],
    }


async def _terminal_run(
    world, *, display=None, canonical_text="answer", conversation_id=None
):
    from app.models.agent import Message, MessageRole

    receipt = await receipt_for(world, message_id=f"om_artifact_{uuid4().hex}")
    await runtime.process_pending()
    run = world.submission.run
    round_id = uuid4()
    if display is not None:
        await Message.create(
            id=uuid4(),
            conversation_id=run.conversation_id,
            role=MessageRole.TOOL,
            content=json.dumps(display),
            round_id=round_id,
            round_role="tool_result",
            round_index=0,
        )
    canonical = await Message.create(
        id=uuid4(),
        conversation_id=conversation_id or run.conversation_id,
        role=MessageRole.ASSISTANT,
        content=canonical_text,
        round_id=round_id,
        round_role="assistant_final",
    )
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=canonical.id,
        finished_at=utcnow(),
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    return receipt, run


async def _use_media_transport(world, monkeypatch):
    transport = FakeAssetTransport()
    monkeypatch.setattr(runtime, "_client_for", _client_for(transport))

    async def read_bytes(asset):
        return b"artifact-bytes"

    monkeypatch.setattr("app.services.channel_artifacts.read_asset_bytes", read_bytes)
    return transport


@pytest.mark.asyncio
async def test_terminal_run_delivers_generated_image_as_native_media(
    world, monkeypatch
):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_image")
    await runtime.process_pending()
    run = world.submission.run
    asset = await _generated_asset(world, conversation_id=run.conversation_id)
    from app.models.agent import Message, MessageRole

    round_id = uuid4()
    await Message.create(
        id=uuid4(),
        conversation_id=run.conversation_id,
        role=MessageRole.TOOL,
        content=json.dumps(_image_display("abcd")),
        round_id=round_id,
        round_role="tool_result",
        round_index=0,
    )
    canonical = await Message.create(
        id=uuid4(),
        conversation_id=run.conversation_id,
        role=MessageRole.ASSISTANT,
        content="",
        round_id=None,
        round_role="assistant_final",
    )
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=canonical.id,
        finished_at=utcnow(),
        active_round_id=round_id,
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset", sequence=0
    )
    assert delivery.kind == "asset"
    assert delivery.asset_id == asset.id
    assert delivery.media_type == "image"
    assert delivery.media_key == "img_key"
    assert delivery.status == "sent"
    assert transport.uploads == [
        ("image", b"artifact-bytes", "artifact.bin", "image/png")
    ]
    assert transport.media == [
        (receipt.message_id, "image", "img_key", delivery.provider_uuid)
    ]
    # An artifact-only answer does not also emit the empty-output notice.
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()


@pytest.mark.asyncio
async def test_artifact_scoped_to_another_conversation_is_not_delivered(
    world, monkeypatch
):
    transport = await _use_media_transport(world, monkeypatch)
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    from app.models.agent import Conversation

    other = await Conversation.create(agent_id=world.agent.id, user_id=world.user.id)
    await _generated_asset(world, conversation_id=other.id)

    await runtime.process_pending()

    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final-asset"
    ).exists()
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_foreign_canonical_message_is_not_delivered(world, monkeypatch):
    await _use_media_transport(world, monkeypatch)
    from app.models.agent import Conversation

    other = await Conversation.create(agent_id=world.agent.id, user_id=world.user.id)
    receipt, _ = await _terminal_run(
        world, canonical_text="foreign answer", conversation_id=other.id
    )

    await runtime.process_pending()

    text = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert text.text != "foreign answer"
    assert text.text.strip()


@pytest.mark.asyncio
async def test_upload_failure_is_terminal_error_not_ambiguous(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    transport.upload_error = TimeoutError("upload timeout")
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(world, conversation_id=run.conversation_id)

    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_upload_failed"
    assert transport.media == []


@pytest.mark.asyncio
async def test_artifact_reply_timeout_is_unknown_and_not_resent(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    transport.reply_error = TimeoutError("reply timeout")
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(world, conversation_id=run.conversation_id)

    await runtime.process_pending()
    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "unknown"
    assert len(transport.media) == 1
    await runtime.process_pending()
    assert len(transport.media) == 1


@pytest.mark.asyncio
async def test_artifact_is_reauthorized_before_upload(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_recheck")
    await runtime.process_pending()
    run = world.submission.run
    asset = await _generated_asset(world, conversation_id=run.conversation_id)
    from app.models.asset import AssetScopeRef

    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    await IntegrationDelivery.create(
        provider_type="feishu",
        integration_id=receipt.integration_id,
        receipt_id=receipt.id,
        user_id=receipt.user_id,
        agent_id=receipt.agent_id,
        run_id=receipt.run_id,
        chat_id=receipt.chat_id,
        message_id=receipt.message_id,
        event_key="final-asset",
        sequence=0,
        provider_uuid=str(uuid4()),
        text=asset.display_filename,
        kind="asset",
        asset_id=asset.id,
        filename=asset.display_filename,
        content_type=asset.content_type,
        size=asset.size,
    )
    # The artifact was queued while authorized, then lost its scope.
    await AssetScopeRef.filter(asset_id=asset.id).delete()

    await runtime.deliver_pending_for_integration(world.integration.id)

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_unavailable"
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_mp4_artifact_uses_native_video_and_other_files_use_file(
    world, monkeypatch
):
    transport = await _use_media_transport(world, monkeypatch)
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(
        world, conversation_id=run.conversation_id, content_type="video/mp4"
    )
    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.media_type == "media"
    assert transport.uploads[0][0] == "mp4"
    assert transport.media[0][1] == "media"

    transport.uploads.clear()
    transport.media.clear()
    receipt2, run2 = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(
        world, conversation_id=run2.conversation_id, content_type="application/pdf"
    )
    await runtime.process_pending()

    delivery2 = await IntegrationDelivery.get(
        receipt_id=receipt2.id, event_key="final-asset"
    )
    assert delivery2.media_type == "file"
    assert transport.uploads[0][0] == "pdf"
    assert transport.media[0][1] == "file"


@pytest.mark.asyncio
async def test_rejected_upload_size_is_permanent_error(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    transport.upload_error = ValueError("Invalid Feishu image size")
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(world, conversation_id=run.conversation_id)

    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_unsupported"
    assert transport.media == []


@pytest.mark.asyncio
async def test_provider_upload_rejection_is_not_reported_as_unsupported_format(
    world, monkeypatch, caplog
):
    from app.integrations.feishu import FeishuAPIError

    transport = await _use_media_transport(world, monkeypatch)
    transport.upload_error = FeishuAPIError(
        "Feishu API error 234001: Invalid request param.",
        code=234001,
        status_code=400,
    )
    receipt, run = await _terminal_run(world, display=_image_display("abcd"))
    await _generated_asset(
        world,
        conversation_id=run.conversation_id,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    with caplog.at_level("WARNING", logger=runtime.logger.name):
        await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_upload_failed"
    assert "234001" in delivery.error_detail
    assert "Invalid request param" in delivery.error_detail
    assert transport.media == []
    assert "234001" in caplog.text
    assert str(run.id) in caplog.text


@pytest.mark.asyncio
async def test_unsuccessful_tool_display_yields_no_asset(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt, run = await _terminal_run(
        world, display=_image_display("abcd", success=False)
    )
    await _generated_asset(world, conversation_id=run.conversation_id)

    await runtime.process_pending()

    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final-asset"
    ).exists()
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_asset_media_type_classification():
    assert runtime._asset_media_type("image/png") == "image"
    assert runtime._asset_media_type("image/heic; charset=binary") == "image"
    assert runtime._asset_media_type("video/mp4") == "media"
    assert runtime._asset_media_type("video/webm") == "file"
    assert runtime._asset_media_type("") == "file"


# --- delivery ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_ambiguous_send_is_not_resent(world):
    receipt = await receipt_for(world, message_id="om_ambiguous")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    world.transport.error = TimeoutError("outcome unknown")
    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unknown"
    assert sum(sent[1] == delivery.text for sent in world.transport.sent) == 1
    # A later pass must not resend an ambiguous row.
    await runtime.process_pending()
    assert sum(sent[1] == delivery.text for sent in world.transport.sent) == 1


@pytest.mark.asyncio
async def test_expired_send_lease_is_resolved_as_unknown(world):
    receipt = await receipt_for(world, message_id="om_lease")
    await runtime.process_pending()
    run = world.submission.run
    from app.models.agent import Message, MessageRole

    canonical = await Message.create(
        id=uuid4(),
        conversation_id=run.conversation_id,
        role=MessageRole.ASSISTANT,
        content="lease answer",
    )
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=canonical.id,
        finished_at=utcnow(),
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_pending()
    await IntegrationDelivery.filter(receipt_id=receipt.id).update(
        status="sending", updated_at=utcnow() - timedelta(seconds=3600)
    )

    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unknown"
    assert sum(sent[1] == delivery.text for sent in world.transport.sent) == 1


@pytest.mark.asyncio
async def test_recover_pending_counts_integrations_with_work(world):
    await receipt_for(world, message_id="om_recover")
    await runtime.process_pending()

    summary = await runtime.recover_pending()

    assert summary["integrations"] >= 1
    await FeishuAgentReceipt.all().delete()
    assert (await runtime.recover_pending())["integrations"] == 0


# --- uncovered helper and recovery outcomes ---------------------------------


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({}, ""),
        ({"message": []}, ""),
        ({"message": {"content": "not json"}}, ""),
        ({"message": {"content": "[]"}}, ""),
        ({"message": {"content": {"text": "  hello  "}}}, "hello"),
        ({"message": {"content": {"text": 7}}}, ""),
    ],
)
def test_event_text_requires_valid_text_payload(event, expected):
    assert runtime._event_text(event) == expected


def test_text_chunks_preserve_multibyte_boundaries_and_empty_values():
    assert runtime._split_text_chunks("") == []
    assert runtime._split_text_chunks("abc", limit=3) == ["abc"]
    chunks = runtime._split_text_chunks("ab🙂cd", limit=4)
    assert chunks == ["ab", "🙂", "cd"]
    assert "".join(chunks) == "ab🙂cd"


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"sender": {"sender_type": "app", "sender_id": {"user_id": "u"}}}, []),
        ({"sender": {"sender_type": "user", "sender_id": None}}, []),
        (
            {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"user_id": "u", "union_id": "s", "open_id": "s"},
                }
            },
            [("user_id", "u"), ("subject", "s")],
        ),
    ],
)
def test_sender_candidates_ignore_non_users_and_deduplicate(event, expected):
    assert runtime._sender_ids(event) == expected


@pytest.mark.asyncio
async def test_accept_ignores_invalid_envelope_and_missing_sender(world):
    assert await runtime.accept_message([]) is None
    assert await runtime.accept_message(text_event(sender=None)) is None
    event = text_event()
    event["message"]["content"] = "{}"
    assert await runtime.accept_message(event) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_session_helpers_handle_missing_and_terminal_mismatch(world):
    assert (
        await runtime._session_for(world.integration.id, CHAT_ID, world.user.id, None)
        is None
    )
    assert await runtime._active_run(None) is None
    session = await FeishuAgentSession.create(
        integration_id=world.integration.id,
        chat_id=CHAT_ID,
        user_id=world.user.id,
        agent_id=world.agent.id,
    )
    await runtime._clear_active_run(session, None)
    assert session.active_run_id is None


@pytest.mark.asyncio
async def test_answer_cutoff_is_missing_without_owner_delivery(world):
    from app.models.agent import Conversation

    conversation = await Conversation.create(
        agent_id=world.agent.id, user_id=world.user.id
    )
    run = await AgentRun.create(
        id=uuid4(),
        agent_id=world.agent.id,
        conversation_id=conversation.id,
        user_id=world.user.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-1",
    )
    receipt = await receipt_for(world)
    await FeishuAgentReceipt.filter(id=receipt.id).update(run_id=run.id)
    receipt = await FeishuAgentReceipt.get(id=receipt.id)
    assert await runtime._answer_cutoff(run) is None


@pytest.mark.asyncio
async def test_apply_use_without_argument_consumes_with_command_reply(world):
    receipt = await receipt_for(world, text="/use")
    session = await session_for(world)
    applied, same_session = await runtime._apply_command(
        receipt, session, world.agent, None, "use", "", world.integration, world.user
    )
    assert applied and same_session.id == session.id
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"
    assert await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="command"
    ).exists()


@pytest.mark.asyncio
async def test_use_resolution_rejects_non_index_and_unlisted_uuid(world):
    assert (
        await runtime._resolve_use_argument("not-an-id", world.integration, world.user)
        is None
    )
    assert (
        await runtime._resolve_use_argument(str(uuid4()), world.integration, world.user)
        is None
    )
    assert (
        await runtime._resolve_use_argument("0", world.integration, world.user) is None
    )


@pytest.mark.asyncio
async def test_dispatch_or_defer_skips_nonqueued_and_recent_receipt(world):
    receipt = await receipt_for(world)
    await runtime.process_pending()
    run = world.submission.run
    calls = []

    async def dispatch(payload, dispatched_run):
        calls.append(dispatched_run.id)

    from app.services import agent_submission

    old = agent_submission.dispatch_run
    agent_submission.dispatch_run = dispatch
    try:
        run.status = AgentRunStatus.RUNNING
        await runtime._dispatch_or_defer(receipt, run)
        assert calls == []
        run.status = AgentRunStatus.QUEUED
        await runtime._dispatch_or_defer(receipt, run)
        assert calls == []
        receipt.updated_at = utcnow() - timedelta(seconds=11)
        await runtime._dispatch_or_defer(receipt, run)
        assert calls == [run.id]
    finally:
        agent_submission.dispatch_run = old


@pytest.mark.asyncio
async def test_delivery_authorization_rejects_unbound_noncommand(world):
    receipt = await receipt_for(world)
    await FeishuAgentReceipt.filter(id=receipt.id).update(agent_id=None)
    receipt = await FeishuAgentReceipt.get(id=receipt.id)
    assert not await runtime._delivery_authorized(receipt)


@pytest.mark.asyncio
async def test_client_requires_app_credentials(db):
    integration = SimpleNamespace(config={}, credentials={})
    with pytest.raises(Exception) as error:
        await runtime._client_for(integration)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_channel_disabled"


@pytest.mark.asyncio
async def test_drain_chat_empty_queue_reports_zero(world):
    result = await runtime._drain_chat(
        (world.integration.id, "empty-chat", world.user.id)
    )
    assert result == {"processed": 0}


@pytest.mark.asyncio
async def test_apply_use_current_agent_keeps_existing_session(world):
    receipt = await receipt_for(world, text=f"/use {world.agent.id}")
    session = await session_for(world)
    applied, resulting = await runtime._apply_command(
        receipt,
        session,
        world.agent,
        None,
        "use",
        str(world.agent.id),
        world.integration,
        world.user,
    )
    assert applied and resulting.id == session.id
    response = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="command")
    assert world.agent.name in response.text
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_send_one_records_rejected_parameters(world):
    receipt = await receipt_for(world, message_id="om_rejected")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")
    world.transport.error = ValueError("invalid recipient parameters")

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    failed = await IntegrationDelivery.get(id=delivery.id)
    assert failed.status == "error"
    assert failed.error == "feishu_agent_run_failed"
    assert world.transport.sent == [
        (receipt.message_id, "reply", delivery.provider_uuid)
    ]


@pytest.mark.asyncio
async def test_send_one_defers_when_personal_feature_is_disabled(world):
    receipt = await receipt_for(world, message_id="om_personal_disabled")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")
    await FeishuAgentPreference.filter(
        integration_id=world.integration.id, user_id=world.user.id
    ).update(is_enabled=False)

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    assert (await IntegrationDelivery.get(id=delivery.id)).status == "pending"
    assert not world.transport.sent


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"sender": None},
        {"sender": {"sender_type": "app"}},
    ],
)
def test_sender_candidates_ignore_absent_sender_structures(event):
    assert runtime._sender_ids(event) == []


@pytest.mark.asyncio
async def test_resolve_integration_requires_matching_enabled_capability(world):
    assert await runtime._resolve_integration("") is None
    await Integration.filter(id=world.integration.id).update(enabled_capabilities=[])
    assert await runtime._resolve_integration(APP_ID) is None
    await Integration.filter(id=world.integration.id).update(
        enabled_capabilities=["agent_chat"], config={"app_id": "different"}
    )
    assert await runtime._resolve_integration(APP_ID) is None


@pytest.mark.asyncio
async def test_dispatch_failure_is_recorded_for_recovery(world, monkeypatch):
    receipt = await receipt_for(world)
    await runtime.process_pending()
    run = world.submission.run
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    async def fail_dispatch(payload, submitted_run):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr("app.services.agent_submission.dispatch_run", fail_dispatch)
    await runtime._dispatch_or_defer(await FeishuAgentReceipt.get(id=receipt.id), run)

    updated = await FeishuAgentReceipt.get(id=receipt.id)
    assert updated.status == "submitted"
    assert updated.error == "feishu_agent_run_failed"


@pytest.mark.asyncio
async def test_receipt_bound_to_revoked_agent_is_explained_not_rerouted(world):
    receipt = await receipt_for(world, message_id="om_revoked")
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    await runtime.process_pending()

    failed = await FeishuAgentReceipt.get(id=receipt.id)
    assert failed.status == "error"
    assert failed.error == "feishu_agent_agent_unavailable"
    assert not world.submission.calls
    assert not await IntegrationDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_final_delivery_is_unavailable_after_user_revocation(world):
    receipt = await receipt_for(world, message_id="om_revoked_user")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    await User.filter(id=world.user.id).update(is_active=False)

    await runtime._finalize_receipt(receipt, None, await AgentRun.get(id=run.id))

    failed = await FeishuAgentReceipt.get(id=receipt.id)
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert failed.status == "completed"
    assert failed.error == "feishu_agent_channel_disabled"
    assert delivery.status == "unavailable"
    assert delivery.error == "feishu_agent_channel_disabled"
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, status="pending"
    ).exists()


@pytest.mark.asyncio
async def test_accept_different_message_ids_as_distinct_provider_events(world):
    first = await receipt_for(world, message_id="om_distinct_1")
    second_id = await runtime.accept_message(text_event(message_id="om_distinct_2"))

    assert second_id is not None
    second = await FeishuAgentReceipt.get(id=second_id)
    assert first.message_id != second.message_id
    assert await FeishuAgentReceipt.filter(user_id=world.user.id).count() == 2


@pytest.mark.asyncio
async def test_accept_ignores_unhandled_message_type(world):
    event = text_event(message_type="image", message_id="om_image")

    assert await runtime.accept_message(event) is None
    assert not await FeishuAgentReceipt.filter(message_id="om_image").exists()


@pytest.mark.asyncio
async def test_finalize_skips_delivery_when_agent_authorization_revoked(world):
    receipt = await receipt_for(world, message_id="om_revoked_agent_output")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    await runtime._finalize_receipt(receipt, None, await AgentRun.get(id=run.id))

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unavailable"
    assert delivery.error == "feishu_agent_channel_disabled"
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, status="pending"
    ).exists()


@pytest.mark.asyncio
async def test_send_one_records_transport_failure_without_retry(world):
    receipt = await receipt_for(world, message_id="om_send_failure")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")
    world.transport.error = RuntimeError("provider rejected request")

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    recorded = await IntegrationDelivery.get(id=delivery.id)
    assert recorded.status == "error"
    assert recorded.error == "feishu_agent_run_failed"
    assert len(world.transport.sent) == 1


@pytest.mark.asyncio
async def test_process_submitted_missing_run_records_failure(world):
    receipt = await receipt_for(world, message_id="om_missing_run")
    await runtime.process_pending()
    await FeishuAgentSession.filter(
        integration_id=receipt.integration_id,
        chat_id=receipt.chat_id,
        user_id=receipt.user_id,
        agent_id=receipt.agent_id,
    ).update(active_run_id=None)
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        status="submitted", run_id=None
    )

    await runtime.process_message(str(receipt.id))

    failed = await FeishuAgentReceipt.get(id=receipt.id)
    assert failed.status == "error"
    assert failed.error == "feishu_agent_run_failed"


@pytest.mark.asyncio
async def test_delivery_without_receipt_is_unavailable(world, monkeypatch):
    receipt = await receipt_for(world, message_id="om_orphan")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)

    class MissingReceiptQuery:
        async def first(self):
            return None

    monkeypatch.setattr(
        FeishuAgentReceipt,
        "filter",
        lambda **kwargs: MissingReceiptQuery(),
    )
    await runtime._send_one(delivery)

    assert not world.transport.sent


@pytest.mark.asyncio
async def test_failed_question_submission_consumes_answer(world, monkeypatch):
    receipt, run = await _waiting_run(
        world, [{"id": "q1", "question": "Why?", "required": True}]
    )
    answer = await receipt_for(world, text="because", message_id="om_answer_failed")

    async def failed_submit(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_run_store.submit_user_answers", failed_submit
    )
    await runtime.process_pending()

    consumed = await FeishuAgentReceipt.get(id=answer.id)
    assert consumed.status == "completed"
    assert consumed.error == "feishu_agent_run_failed"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "submitted"


def test_question_text_formats_multiple_questions_and_options():
    assert (
        runtime._question_text(
            {"question": "  Pick one? ", "options": ["A", "B"]}, 2, 3
        )
        == "[2/3]\nPick one?\nA / B"
    )
    assert runtime._question_text({"question": "Solo?"}, 1, 1) == "Solo?"


@pytest.mark.asyncio
async def test_announce_questions_reports_partial_answers(world):
    receipt = await receipt_for(world)
    from app.models.agent import Conversation

    conversation = await Conversation.create(agent=world.agent, user=world.user)
    run = await AgentRun.create(
        id=uuid4(),
        agent=world.agent,
        conversation=conversation,
        user=world.user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-partial",
        pending_tool_input={
            "questions": [
                {"id": "q1", "question": "First?"},
                {"id": "q2", "question": "Second?"},
            ]
        },
    )

    await runtime._announce_questions(receipt, run, answered={"q1": "done"})

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="ask:call-partial"
    )
    assert "Second?" in delivery.text
    assert "First?" not in delivery.text
    assert "Answered 1 of 2 questions" in delivery.text


@pytest.mark.asyncio
async def test_clear_active_run_keeps_different_pointer(world):
    session = await FeishuAgentSession.create(
        integration=world.integration,
        chat_id=CHAT_ID,
        user=world.user,
        agent=world.agent,
    )
    from app.models.agent import Conversation

    conversation = await Conversation.create(agent=world.agent, user=world.user)
    run = await AgentRun.create(
        id=uuid4(),
        agent=world.agent,
        conversation=conversation,
        user=world.user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
    )
    other_run = await AgentRun.create(
        id=uuid4(),
        agent=world.agent,
        conversation=conversation,
        user=world.user,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.RUNNING,
    )
    pointer = other_run.id
    session.active_run_id = pointer
    await session.save(update_fields=["active_run_id"])

    await runtime._clear_active_run(session, run)

    assert (await FeishuAgentSession.get(id=session.id)).active_run_id == pointer


@pytest.mark.asyncio
async def test_agent_list_explains_when_no_agents_are_selectable(world):
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    text = await runtime._agents_text(
        await runtime._selectable_agents(world.integration, world.user)
    )

    assert text
    assert world.agent.name not in text

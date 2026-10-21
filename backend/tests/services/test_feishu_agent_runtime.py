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
    FeishuAgentDelivery,
    FeishuAgentPreference,
    FeishuAgentReceipt,
    FeishuAgentSession,
)
from app.models.feishu_user import FeishuUser
from app.models.integration import Integration
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
        return SimpleNamespace(reply_text=transport)

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


# --- inbound validation and identity -----------------------------------------


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
    busy = await FeishuAgentDelivery.filter(
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

    delivery = await FeishuAgentDelivery.get(receipt_id=command.id, event_key="command")
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

    delivery = await FeishuAgentDelivery.get(receipt_id=use.id, event_key="command")
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
        assert await FeishuAgentDelivery.filter(receipt_id=receipt.id).exists()


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

    question = await FeishuAgentDelivery.get(
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
    rejection = await FeishuAgentDelivery.filter(
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
    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.text == "the answer"
    assert delivery.uuid and len(delivery.uuid) <= 50
    final = next(sent for sent in world.transport.sent if sent[1] == delivery.text)
    assert final[0] == receipt.message_id
    assert final[2] == delivery.uuid


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
    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
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
    assert not await FeishuAgentDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()
    await Integration.filter(id=world.integration.id).update(
        enabled_capabilities=["agent_chat"]
    )
    await runtime.process_pending()
    refreshed = await FeishuAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error is None
    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
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

    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
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
        await FeishuAgentDelivery.filter(
            receipt_id=receipt.id, event_key="final"
        ).count()
        == 1
    )


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

    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
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
    await FeishuAgentDelivery.filter(receipt_id=receipt.id).update(
        status="sending", updated_at=utcnow() - timedelta(seconds=3600)
    )

    await runtime.process_pending()

    delivery = await FeishuAgentDelivery.get(receipt_id=receipt.id, event_key="final")
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

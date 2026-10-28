"""WeChat Agent runtime boundaries against an isolated real ORM.

The Tortoise ORM is real (SQLite in memory) and the durable run pipeline is
stubbed at its two boundaries: the shared submission service (run creation)
and the WeChat IO service (transport + asset normalization).  Everything the
runtime itself owns — receipts, sessions, deliveries, command precedence,
answer accumulation, crash-safe dispatch — runs against the database.
"""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.models.agent import Agent, AgentStatus, AgentVisibility
from app.models.agent_run import AgentRun, AgentRunStatus, AgentRunMode
from app.models.user import Team, TeamMember, User
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentConfig,
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import WeChatKnowledgeBinding
from app.services import wechat_agent_runtime as runtime
from app.services.wechat_agent_io import deliver_pending as deliver_agent_pending
from app.services.wechat_connection import utcnow


class FakeSubmission:
    """Stand-in for the shared submission service boundary."""

    def __init__(self):
        self.calls = []
        self.run = None
        self.error = None

    async def __call__(self, agent_id, chat_in, user, **kwargs):
        self.calls.append((agent_id, chat_in, kwargs))
        if self.error is not None:
            raise self.error
        run = await AgentRun.create(
            id=uuid4(),
            agent_id=agent_id,
            conversation_id=chat_in.conversation_id,
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


class FakeIO:
    """Stand-in for the WeChat IO boundary."""

    def __init__(self):
        self.normalized = []
        self.outputs = {}
        self.normalize_error = None
        self.delivered = []

    async def normalize_input(self, receipt, session, agent, user, client):
        self.normalized.append((receipt, session, agent, user, client))
        if self.normalize_error is not None:
            raise self.normalize_error
        from app.schemas.agent import ChatRequest

        return ChatRequest(
            message="hello",
            conversation_id=session.conversation_id,
        )

    async def build_output(self, run, receipt, session, user):
        return self.outputs.get(str(run.id), [])

    async def deliver_pending(self, binding, user):
        self.delivered.append((binding.id, user.id))


def message_payload(text="hello", context_token="ctx-1"):
    return {
        "message_id": "mid",
        "from_user_id": "wechat-user",
        "message_type": 1,
        "message_state": 2,
        "context_token": context_token,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
    }


async def make_agent(team, user):
    agent = await Agent.create(
        id=uuid4(),
        name="Test agent",
        team=team,
        created_by=user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
        enable_attachments=False,
    )
    return agent


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        from app.models.integration import Integration

        await Integration.create(
            name="wechat",
            provider_type="wechat",
            display_name="WeChat iLink",
            enabled_capabilities=["agent_chat", "knowledge_collection"],
        )
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
    binding = await WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id="wechat-user",
        bot_id="bot",
        token=encrypt_secret("not-real"),
        base_url="https://ilinkai.weixin.qq.com",
        purpose="agent",
    )
    config = await WeChatAgentConfig.create(binding=binding, agent=agent, variables={})
    submission = FakeSubmission()
    io = FakeIO()
    monkeypatch.setattr("app.services.agent_submission.submit_chat_run", submission)
    monkeypatch.setattr(runtime, "WeChatAgentConfig", WeChatAgentConfig)
    monkeypatch.setattr(
        "app.services.wechat_agent_io.normalize_input", io.normalize_input
    )
    monkeypatch.setattr("app.services.wechat_agent_io.build_output", io.build_output)
    monkeypatch.setattr(
        "app.services.wechat_agent_io.deliver_pending", io.deliver_pending
    )
    monkeypatch.setattr("app.services.agent_submission.dispatch_run", _noop_dispatch)
    return SimpleNamespace(
        user=user,
        team=team,
        agent=agent,
        binding=binding,
        config=config,
        submission=submission,
        io=io,
    )


async def _noop_dispatch(payload, run):
    return None


async def receipt_for(world, text="hello", identifier="mid"):
    return await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        variables={},
        message_id=identifier,
        payload=encrypt_secret(json.dumps(message_payload(text))),
    )


@pytest.mark.asyncio
async def test_one_response_combines_text_and_file_and_replay_is_deduplicated(
    world, monkeypatch
):
    from app.services.wechat_receiver import accept_updates
    from app.services import wechat_agent_io as io

    text = {**message_payload("总结一下"), "message_id": "caption"}
    file = {
        **message_payload(),
        "message_id": "document",
        "item_list": [{"type": 4, "file_item": {"file_name": "report.docx"}}],
    }
    response = {"msgs": [text, file], "get_updates_buf": "batch-one"}
    accepted = await accept_updates(world.binding, response)
    assert len(accepted.agent_receipt_ids) == 2
    rows = await WeChatAgentReceipt.all().order_by("created_at")
    assert [row.status for row in rows] == ["pending", "merged"]
    payload = json.loads(decrypt_secret(rows[0].payload))
    assert payload["batch_messages"] == [text, file]

    async def normalize(receipt, session, agent, user, client):
        from app.schemas.agent import ChatRequest

        data = json.loads(decrypt_secret(receipt.payload))
        assert [item["type"] for item in data["item_list"]] == [1, 4]
        return ChatRequest(message="总结一下", conversation_id=session.conversation_id)

    monkeypatch.setattr(io, "normalize_input", normalize)
    await runtime.process_binding(str(world.binding.id))
    assert await AgentRun.all().count() == 1
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "summary"}]
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))
    assert await IntegrationDelivery.filter(event_key="received").count() == 1
    assert await IntegrationDelivery.filter(event_key="final").count() == 1
    fresh = await WeChatKnowledgeBinding.get(id=world.binding.id)
    replay = await accept_updates(fresh, response)
    assert replay.agent_receipt_ids == []
    assert await WeChatAgentReceipt.all().count() == 2


@pytest.mark.asyncio
async def test_response_commands_and_separate_responses_do_not_merge(world):
    from app.services.wechat_receiver import accept_updates

    messages = [
        {**message_payload(text), "message_id": str(index)}
        for index, text in enumerate(["first", "/status", "second", "third"])
    ]
    await accept_updates(world.binding, {"msgs": messages, "get_updates_buf": "one"})
    rows = await WeChatAgentReceipt.all().order_by("created_at")
    assert [row.status for row in rows] == ["pending", "pending", "pending", "merged"]
    assert "batch_messages" not in json.loads(decrypt_secret(rows[0].payload))
    fresh = await WeChatKnowledgeBinding.get(id=world.binding.id)
    await accept_updates(
        fresh,
        {
            "msgs": [{**message_payload("fourth"), "message_id": "four"}],
            "get_updates_buf": "two",
        },
    )
    fourth = await WeChatAgentReceipt.get(message_id="four")
    assert fourth.status == "pending"
    assert "batch_messages" not in json.loads(decrypt_secret(fourth.payload))


@pytest.mark.asyncio
async def test_receipt_submits_run_and_maps_before_dispatch(world):
    receipt = await receipt_for(world)
    result = await runtime.process_binding(str(world.binding.id))

    assert result["processed"] == 1
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"
    assert refreshed.run_id == world.submission.run.id
    assert world.submission.calls, "submission boundary was not used"
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.active_run_id == refreshed.run_id
    assert decrypt_secret(session.context_token) == "ctx-1"
    assert session.conversation_id is not None


@pytest.mark.asyncio
async def test_first_message_runs_without_another_message_or_recovery(
    world, monkeypatch
):
    """The first publish must not be throttled as a retry of the fresh run."""

    async def execute(payload, run):
        receipt = await WeChatAgentReceipt.get(run_id=run.id)
        session = await WeChatAgentSession.get(binding_id=world.binding.id)
        assert receipt.status == "submitted"
        assert session.active_run_id == run.id
        await AgentRun.filter(id=run.id).update(
            status=AgentRunStatus.COMPLETED, finished_at=utcnow()
        )
        world.io.outputs[str(run.id)] = [{"kind": "text", "text": "first answer"}]

    monkeypatch.setattr("app.services.agent_submission.dispatch_run", execute)
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=(await WeChatAgentReceipt.get(id=receipt.id)).run_id)
    assert run.status == AgentRunStatus.COMPLETED
    await runtime.process_binding(str(world.binding.id))
    reply = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert reply.payload["text"] == "first answer"
    assert (
        await WeChatAgentSession.get(binding_id=world.binding.id)
    ).active_run_id is None


@pytest.mark.asyncio
async def test_partial_outbox_failure_keeps_terminal_receipt_recoverable(
    world, monkeypatch
):
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [
        {"kind": "text", "text": "first chunk"},
        {"kind": "text", "text": "second chunk"},
    ]
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    create_delivery = runtime._create_delivery

    async def fail_second(receipt, **kwargs):
        if kwargs["event_key"] == "final" and kwargs["sequence"] == 1:
            raise RuntimeError("outbox insert failed")
        await create_delivery(receipt, **kwargs)

    monkeypatch.setattr(runtime, "_create_delivery", fail_second)
    await runtime.process_binding(str(world.binding.id))
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "submitted"
    assert (
        await WeChatAgentSession.get(binding_id=world.binding.id)
    ).active_run_id == run.id
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()

    monkeypatch.setattr(runtime, "_create_delivery", create_delivery)
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))
    replies = await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).order_by("sequence")
    assert [reply.payload["text"] for reply in replies] == [
        "first chunk",
        "second chunk",
    ]
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"
    assert (
        await WeChatAgentSession.get(binding_id=world.binding.id)
    ).active_run_id is None


@pytest.mark.asyncio
async def test_duplicate_receipt_message_id_submits_once(world):
    await receipt_for(world, identifier="dup")
    payload = message_payload()
    duplicate = await WeChatAgentReceipt.get_or_create(
        binding_id=world.binding.id,
        message_id="dup",
        defaults={
            "user_id": world.user.id,
            "agent_id": world.agent.id,
            "payload": encrypt_secret(json.dumps(payload)),
        },
    )
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))

    runs = await AgentRun.all()
    assert len(runs) == 1
    assert len(world.submission.calls) == 1
    refreshed = await WeChatAgentReceipt.get(id=duplicate[0].id)
    assert refreshed.run_id == runs[0].id


@pytest.mark.asyncio
async def test_second_message_while_running_waits_without_new_run(world):
    await receipt_for(world, identifier="first")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run

    second = await receipt_for(world, text="second", identifier="second")
    result = await runtime.process_binding(str(world.binding.id))

    # The run is queued, so the submitted receipt is polled again in the same
    # pass; the second message still does not start a competing run.
    assert result["processed"] == 2
    assert len(world.submission.calls) == 1
    assert await AgentRun.all().count() == 1
    busy = await IntegrationDelivery.filter(receipt_id=second.id).first()
    assert busy is not None
    assert busy.payload["kind"] == "text"
    assert run.status == AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_terminal_run_delivers_canonical_text(world):
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "the answer"}]

    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["text"] == "the answer"
    assert world.io.delivered


@pytest.mark.asyncio
async def test_failure_notice_uses_recipient_locale(world):
    """The worker's process language must not decide the notice's language.

    The failure branch emits text before the full authorization path, so it
    reads the recipient locale itself instead of relying on whichever language
    an unrelated earlier receipt left in the worker context.
    """
    from app.core.i18n import set_language
    from app.models.user import User as UserModel

    await UserModel.filter(id=world.user.id).update(locale="zh")
    set_language("en")
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.FAILED,
        error_message="provider detail",
        finished_at=utcnow(),
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    # An unrelated earlier task left the worker context in a different
    # language; the finalization pass must resolve it from the recipient.
    set_language("en")
    await runtime.process_binding(str(world.binding.id))

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["text"] == "Agent 任务未完成，请打开对话查看详情。"
    assert "Clouisle" not in delivery.payload["text"]
    assert "provider detail" not in delivery.payload["text"]


@pytest.mark.asyncio
async def test_failed_run_sends_generic_message_only(world):
    receipt = await receipt_for(world, identifier="failed-generic")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run

    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.FAILED,
        error_message="provider secret detail",
        finished_at=utcnow(),
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert "provider secret detail" not in delivery.payload["text"]


@pytest.mark.asyncio
async def test_waiting_question_ignores_older_message_and_accumulates(world):
    receipt = await receipt_for(world, identifier="ask")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run

    older = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="older",
        payload=encrypt_secret(json.dumps(message_payload("old answer"))),
        created_at=utcnow() - timedelta(minutes=5),
    )
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-1",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {
                    "id": "q1",
                    "question": "Which one?",
                    "required": True,
                    "options": ["A", "B"],
                },
                {"id": "q2", "question": "Why?", "required": True},
            ]
        },
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    question = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="ask:call-1"
    )
    assert question.payload["text"]
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}

    # A message created before the question must not be consumed as an answer.
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}
    assert (await WeChatAgentReceipt.get(id=older.id)).status == "pending"

    # An invalid choice for the current question is rejected explicitly and
    # leaves the accumulated answers untouched.
    invalid = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="answer-2",
        payload=encrypt_secret(json.dumps(message_payload("C"))),
    )
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}
    rejection = await IntegrationDelivery.filter(
        receipt_id=invalid.id, event_key="answer_error"
    ).first()
    assert rejection is not None
    assert (await WeChatAgentReceipt.get(id=invalid.id)).status == "completed"
    # A recovery pass must not silently consume the invalid message as an answer.
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}

    # A message created after the question is accepted as the first answer.
    answer = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="answer-1",
        payload=encrypt_secret(json.dumps(message_payload("A"))),
    )
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {"q1": "A"}
    # The answer message is consumed, so recovery must not replay it.
    assert (await WeChatAgentReceipt.get(id=answer.id)).status == "completed"
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {"q1": "A"}

    # The second required answer completes the set and resumes the run.
    final = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="answer-3",
        payload=encrypt_secret(json.dumps(message_payload("because"))),
    )
    submitted = []

    async def fake_submit(run_id, **kwargs):
        submitted.append(kwargs)
        return SimpleNamespace(id=run.id, status=AgentRunStatus.QUEUED)

    import app.services.agent_run_store as store

    real_submit = store.submit_user_answers
    store.submit_user_answers = fake_submit
    try:
        await runtime.process_binding(str(world.binding.id))
    finally:
        store.submit_user_answers = real_submit
    assert submitted and submitted[0]["answers"] == {"q1": "A", "q2": "because"}
    assert submitted[0]["skipped"] is False
    assert (await WeChatAgentReceipt.get(id=final.id)).status == "completed"
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}


@pytest.mark.asyncio
async def test_skip_command_submits_skipped_answers(world):
    await receipt_for(world, identifier="skipme")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-9",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
    )

    skip_receipt = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="skip-msg",
        payload=encrypt_secret(json.dumps(message_payload("/skip"))),
    )
    captured = {}

    async def fake_submit(run_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=run.id, status=AgentRunStatus.QUEUED)

    import app.services.agent_run_store as store

    real_submit = store.submit_user_answers
    store.submit_user_answers = fake_submit
    try:
        await runtime.process_binding(str(world.binding.id))
    finally:
        store.submit_user_answers = real_submit

    assert captured.get("skipped") is True
    assert captured.get("answers") == {}
    assert (await WeChatAgentReceipt.get(id=skip_receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_stop_cancels_queued_receipts_and_stops_run(world):
    await receipt_for(world, identifier="running")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)

    queued = await receipt_for(world, text="queued", identifier="queued")
    stop = await receipt_for(world, text="/stop", identifier="stop-1")
    await runtime.process_binding(str(world.binding.id))

    assert (await WeChatAgentReceipt.get(id=queued.id)).status == "error"
    assert (await WeChatAgentReceipt.get(id=stop.id)).status == "completed"
    refreshed = await AgentRun.get(id=run.id)
    assert refreshed.status in (AgentRunStatus.STOPPING, AgentRunStatus.STOPPED)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.active_run_id in (None, run.id)


@pytest.mark.asyncio
async def test_new_command_resets_session_only_when_terminal(world):
    await receipt_for(world, identifier="first")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    session = await WeChatAgentSession.get(binding_id=world.binding.id)

    # While the run is still active the conversation is preserved.
    busy = await receipt_for(world, text="/new", identifier="new-1")
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.conversation_id is not None
    assert (await WeChatAgentReceipt.get(id=busy.id)).status == "pending"

    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=busy.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.conversation_id is None
    assert session.active_run_id is None
    assert (await WeChatAgentReceipt.get(id=busy.id)).status == "completed"


@pytest.mark.asyncio
async def test_disconnected_binding_marks_output_unavailable(world):
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "answer"}]

    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
        status="disconnected", token="", disconnected_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error == "wechat_agent_binding_disconnected"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unavailable"


@pytest.mark.asyncio
async def test_missing_context_token_blocks_delivery(world):
    receipt = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="no-ctx",
        payload=encrypt_secret(json.dumps(message_payload(context_token=""))),
    )
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "answer"}]
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.error == "wechat_agent_context_missing"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unavailable"
    assert delivery.payload["kind"] == "text"


@pytest.mark.asyncio
async def test_submitted_receipt_finalizes_from_its_own_terminal_run(world):
    """A cleared session pointer must not hide a finished run.

    The session releases ``active_run_id`` the moment a run is terminal, so a
    receipt that is still ``submitted`` has to resolve its own ``run_id``;
    otherwise its answer is never queued and the receipt never completes.
    """
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "the answer"}]
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    # The pointer is already gone by the time the next pass finalizes.
    await WeChatAgentSession.filter(binding_id=world.binding.id).update(
        active_run_id=None
    )

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["text"] == "the answer"


@pytest.mark.asyncio
async def test_concurrent_finalization_queues_the_answer_once(world):
    """Two recovery passes may observe the same terminal run.

    Finalization claims the receipt first, so the slower pass cannot append a
    duplicate ``final`` row that would send the same answer twice.
    """
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "only once"}]
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    stale = await WeChatAgentReceipt.get(id=receipt.id)

    await runtime.process_binding(str(world.binding.id))
    # Simulate the racing pass still holding the pre-finalization snapshot.
    await runtime._finalize_receipt(
        stale, await WeChatAgentSession.get(binding_id=world.binding.id), run
    )

    assert (
        await IntegrationDelivery.filter(
            receipt_id=receipt.id, event_key="final"
        ).count()
        == 1
    )


@pytest.mark.asyncio
async def test_empty_output_sends_explicit_notice(world):
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    world.io.outputs[str(run.id)] = []
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["kind"] == "text"
    assert delivery.payload["text"]


@pytest.mark.asyncio
async def test_unsupported_input_is_explained_not_dropped(world):
    from app.schemas.response import BusinessError

    receipt = await receipt_for(world)
    world.io.normalize_error = BusinessError(
        code=400, msg_key="wechat_agent_media_unsupported", status_code=400
    )
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_media_unsupported"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["kind"] == "text"
    assert delivery.payload["text"]


@pytest.mark.asyncio
async def test_disconnected_binding_never_submits(world):
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
        status="disconnected", token="", disconnected_at=utcnow()
    )
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))

    assert not world.submission.calls
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_binding_disconnected"


@pytest.mark.asyncio
async def test_media_while_waiting_is_consumed_with_explanation(world):
    receipt = await receipt_for(world, identifier="ask-media")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-media",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Which one?", "required": True}]
        },
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    media = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="media-answer",
        payload=encrypt_secret(
            json.dumps(
                {
                    "message_id": "media-answer",
                    "context_token": "ctx-1",
                    "item_list": [{"type": 2, "image_item": {"media": {}}}],
                }
            )
        ),
    )
    await runtime.process_binding(str(world.binding.id))

    media_row = await WeChatAgentReceipt.get(id=media.id)
    assert media_row.status == "completed"
    assert media_row.error == "wechat_agent_media_unsupported"
    notice = await IntegrationDelivery.filter(
        receipt_id=media.id, event_key="answer_error"
    ).first()
    assert notice is not None
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}
    # A recovery pass must not retry the media message.
    await runtime.process_binding(str(world.binding.id))
    assert (await WeChatAgentReceipt.get(id=media.id)).status == "completed"


@pytest.mark.asyncio
async def test_media_transport_failure_is_explained_not_left_pending(world):
    from app.integrations.wechat import WeChatAPIError

    receipt = await receipt_for(world)
    world.io.normalize_error = WeChatAPIError("media_download")
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_media_failed"
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.payload["kind"] == "text"
    assert delivery.payload["text"]


@pytest.mark.asyncio
async def test_purpose_switched_away_from_agent_blocks_new_work(world):
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(purpose="none")
    await WeChatAgentConfig.filter(binding_id=world.binding.id).delete()
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))

    assert not world.submission.calls
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.error == "wechat_agent_config_missing"


@pytest.mark.asyncio
async def test_bounded_batch_leaves_remaining_receipts_pending(world):
    for index in range(runtime.MAX_BATCH + 3):
        await receipt_for(world, text=f"m{index}", identifier=f"m{index}")
    result = await runtime.process_binding(str(world.binding.id))

    assert result["processed"] == runtime.MAX_BATCH
    assert result["pending"] is True
    # Only the first message starts a run; the messages that arrived while it
    # is active stay pending so they can be processed after it finishes.
    assert (
        await WeChatAgentReceipt.filter(
            binding_id=world.binding.id, status="submitted"
        ).count()
        == 1
    )
    remaining = await WeChatAgentReceipt.filter(
        binding_id=world.binding.id, status="pending"
    ).count()
    assert remaining == runtime.MAX_BATCH + 3 - 1


@pytest.mark.asyncio
async def test_help_and_status_commands_do_not_start_runs(world):
    help_receipt = await receipt_for(world, text="/help", identifier="help-1")
    status_receipt = await receipt_for(world, text="/状态", identifier="status-1")
    await runtime.process_binding(str(world.binding.id))

    assert not world.submission.calls
    assert (await WeChatAgentReceipt.get(id=help_receipt.id)).status == "completed"
    assert (await WeChatAgentReceipt.get(id=status_receipt.id)).status == "completed"
    assert await IntegrationDelivery.filter(receipt_id=status_receipt.id).exists()


@pytest.mark.asyncio
async def test_natural_language_is_not_treated_as_command(world):
    receipt = await receipt_for(world, text="停止", identifier="natural")
    await runtime.process_binding(str(world.binding.id))

    assert world.submission.calls, "bare Chinese words must stay user content"
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous", [False, True])
async def test_receipt_ack_precedes_preparation_and_is_not_resent(
    world, monkeypatch, ambiguous
):
    import app.services.wechat_agent_io as io

    receipt = await receipt_for(world)
    sent = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send_text(self, to, text, token, *, client_id):
            sent.append((to, text, token, client_id))
            if ambiguous:
                raise TimeoutError("send outcome unknown")

    async def normalize(receipt, session, agent, user, client):
        assert len(sent) == 1
        assert not await AgentRun.all().exists()
        return await world.io.normalize_input(receipt, session, agent, user, client)

    monkeypatch.setattr(io, "WeChatClient", Client)
    monkeypatch.setattr(io, "deliver_pending", deliver_agent_pending)
    monkeypatch.setattr(io, "normalize_input", normalize)
    # A failed submission leaves the receipt pending, so recovery revisits the
    # same acknowledgement before trying to submit again.
    world.submission.error = RuntimeError("submission unavailable")
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))

    ack = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="received")
    assert ack.status == ("unknown" if ambiguous else "sent")
    assert len(sent) == 1
    assert sent[0][0] == world.binding.wechat_user_id
    assert sent[0][2] == "ctx-1"
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"


@pytest.mark.asyncio
async def test_busy_and_command_messages_do_not_get_receipt_ack(world):
    await receipt_for(world, identifier="first")
    await runtime.process_binding(str(world.binding.id))
    queued = await receipt_for(world, identifier="queued")
    command = await receipt_for(world, text="/status", identifier="status")
    await runtime.process_binding(str(world.binding.id))
    assert await IntegrationDelivery.filter(
        receipt_id=queued.id, event_key="busy"
    ).exists()
    assert not await IntegrationDelivery.filter(
        receipt_id__in=[queued.id, command.id], event_key="received"
    ).exists()

    await AgentRun.filter(id=world.submission.run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await runtime.process_binding(str(world.binding.id))
    assert (await WeChatAgentReceipt.get(id=queued.id)).status == "submitted"
    assert not await IntegrationDelivery.filter(
        receipt_id=queued.id, event_key="received"
    ).exists()


async def _wait_for_tool_approval(world, monkeypatch, *, preview_text="confirm"):
    """Submit one message, park its run on a tool approval, and announce it."""
    from app.schemas.tool_approval import ExecutionEntrypoint

    owner = await receipt_for(world, identifier="approval-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    execution_id = uuid4()
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-approval",
        pending_tool_name="create_issue",
        pending_tool_input={
            "interaction_kind": "tool_approval",
            "execution_id": str(execution_id),
        },
    )

    async def preview(parked, user, origin, origin_id):
        assert parked.id == run.id
        assert origin == ExecutionEntrypoint.WECHAT_CHANNEL
        assert origin_id == world.binding.id
        return str(execution_id), preview_text

    monkeypatch.setattr(runtime, "approval_preview", preview)
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))
    return owner, run, execution_id


async def _command_receipt(world, text, identifier):
    return await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id=identifier,
        payload=encrypt_secret(json.dumps(message_payload(text))),
    )


@pytest.mark.asyncio
async def test_submission_uses_the_wechat_channel_origin(world):
    from app.schemas.tool_approval import ExecutionEntrypoint

    await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))

    _, _, kwargs = world.submission.calls[0]
    assert kwargs["tool_entrypoint"] == ExecutionEntrypoint.WECHAT_CHANNEL
    assert kwargs["tool_entrypoint_id"] == str(world.binding.id)


@pytest.mark.asyncio
async def test_waiting_tool_approval_announces_the_preview_once(world, monkeypatch):
    owner, _, execution_id = await _wait_for_tool_approval(
        world, monkeypatch, preview_text="Tool confirmation required"
    )

    event_key = f"approval:{execution_id}"
    first = await IntegrationDelivery.get(receipt_id=owner.id, event_key=event_key)
    assert first.payload["text"] == "Tool confirmation required"

    # A recovery pass must not append a second announcement.
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))
    assert (
        await IntegrationDelivery.filter(
            receipt_id=owner.id, event_key=event_key
        ).count()
        == 1
    )
    assert (await WeChatAgentReceipt.get(id=owner.id)).status == "submitted"


@pytest.mark.asyncio
async def test_long_approval_preview_is_split_on_the_same_event(world, monkeypatch):
    owner, _, execution_id = await _wait_for_tool_approval(
        world, monkeypatch, preview_text="x" * 7000
    )

    rows = await IntegrationDelivery.filter(
        receipt_id=owner.id, event_key=f"approval:{execution_id}"
    ).order_by("sequence")
    assert [row.sequence for row in rows] == [0, 1]
    assert "".join(row.payload["text"] for row in rows) != ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verb", "decision", "outcome_key"),
    [
        ("/approve", "approve", "channel_approval_approved"),
        ("/reject", "reject", "channel_approval_rejected"),
    ],
)
async def test_approval_command_decides_and_replies(
    world, monkeypatch, verb, decision, outcome_key
):
    from app.core.i18n import t
    from app.schemas.tool_approval import ExecutionEntrypoint

    _, run, execution_id = await _wait_for_tool_approval(world, monkeypatch)
    calls = []

    async def decide(parked, user, origin, origin_id, token, vote, receipt_id):
        calls.append((parked.id, user.id, origin, origin_id, token, vote, receipt_id))

    monkeypatch.setattr(runtime, "decide_channel_approval", decide)
    command = await _command_receipt(
        world, f"{verb} {execution_id}", f"{decision}-command"
    )
    await runtime.process_binding(str(world.binding.id))

    assert calls == [
        (
            run.id,
            world.user.id,
            ExecutionEntrypoint.WECHAT_CHANNEL,
            world.binding.id,
            str(execution_id),
            decision,
            command.id,
        )
    ]
    consumed = await WeChatAgentReceipt.get(id=command.id)
    assert consumed.status == "completed"
    assert consumed.error is None
    reply = await IntegrationDelivery.get(
        receipt_id=command.id, event_key="approval_result"
    )
    assert reply.payload["text"] == t(outcome_key)

    # A completed decision command is never replayed as a decision.
    await runtime.process_binding(str(world.binding.id))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_refused_approval_command_is_consumed_with_explanation(
    world, monkeypatch
):
    from app.core.i18n import t
    from app.schemas.response import BusinessError

    _, _, _ = await _wait_for_tool_approval(world, monkeypatch)
    calls = []

    async def decide(*args, **kwargs):
        calls.append(args)
        raise BusinessError(
            code=403, msg_key="channel_approval_invalid", status_code=403
        )

    monkeypatch.setattr(runtime, "decide_channel_approval", decide)
    command = await _command_receipt(world, f"/approve {uuid4()}", "bad-token")
    await runtime.process_binding(str(world.binding.id))

    assert len(calls) == 1
    consumed = await WeChatAgentReceipt.get(id=command.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_invalid"
    reply = await IntegrationDelivery.get(
        receipt_id=command.id, event_key="approval_result"
    )
    assert reply.payload["text"] == t("channel_approval_invalid")

    # A recovery pass must not retry the refused command.
    await runtime.process_binding(str(world.binding.id))
    assert len(calls) == 1
    assert (await WeChatAgentReceipt.get(id=command.id)).status == "completed"


@pytest.mark.asyncio
async def test_approval_command_queued_before_the_preview_cannot_decide(
    world, monkeypatch
):
    from app.core.i18n import t

    owner = await receipt_for(world, identifier="approval-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    execution_id = uuid4()
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-approval",
        pending_tool_name="create_issue",
        pending_tool_input={
            "interaction_kind": "tool_approval",
            "execution_id": str(execution_id),
        },
    )

    async def preview(parked, user, origin, origin_id):
        return str(execution_id), "confirm"

    monkeypatch.setattr(runtime, "approval_preview", preview)
    decided = []

    async def decide(*args, **kwargs):
        decided.append(args)

    monkeypatch.setattr(runtime, "decide_channel_approval", decide)
    # This command was observed before the confirmation existed.
    stale = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="stale-command",
        payload=encrypt_secret(json.dumps(message_payload(f"/approve {execution_id}"))),
        created_at=utcnow() - timedelta(minutes=5),
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    assert not decided
    assert await IntegrationDelivery.filter(
        receipt_id=owner.id, event_key=f"approval:{execution_id}"
    ).exists()
    consumed = await WeChatAgentReceipt.get(id=stale.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_invalid"
    reply = await IntegrationDelivery.get(
        receipt_id=stale.id, event_key="approval_result"
    )
    assert reply.payload["text"] == t("channel_approval_invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["yes please", None])
async def test_non_command_while_approval_waiting_is_explained(
    world, monkeypatch, text
):
    from app.core.i18n import t

    _, run, _ = await _wait_for_tool_approval(world, monkeypatch)
    decided = []

    async def decide(*args, **kwargs):
        decided.append(args)

    monkeypatch.setattr(runtime, "decide_channel_approval", decide)
    payload = (
        message_payload(text)
        if text is not None
        else {
            "message_id": "media-waiting",
            "context_token": "ctx-1",
            "item_list": [{"type": 2, "image_item": {"media": {}}}],
        }
    )
    message = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        message_id="plain-waiting",
        payload=encrypt_secret(json.dumps(payload)),
    )
    await runtime.process_binding(str(world.binding.id))

    assert not decided
    consumed = await WeChatAgentReceipt.get(id=message.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_waiting"
    notice = await IntegrationDelivery.get(
        receipt_id=message.id, event_key="approval_waiting"
    )
    assert notice.payload["text"] == t("channel_approval_waiting")
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}
    assert await AgentRun.all().count() == 1
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING

    # The explanation is not repeated on a recovery pass.
    await runtime.process_binding(str(world.binding.id))
    assert (
        await IntegrationDelivery.filter(
            receipt_id=message.id, event_key="approval_waiting"
        ).count()
        == 1
    )


@pytest.mark.asyncio
async def test_skip_is_not_accepted_for_a_tool_approval(world, monkeypatch):
    import app.services.agent_run_store as store

    _, run, _ = await _wait_for_tool_approval(world, monkeypatch)
    skipped = []

    async def fake_submit(*args, **kwargs):
        skipped.append(kwargs)
        return SimpleNamespace(id=run.id, status=AgentRunStatus.QUEUED)

    monkeypatch.setattr(store, "submit_user_answers", fake_submit)
    message = await _command_receipt(world, "/skip", "skip-approval")
    await runtime.process_binding(str(world.binding.id))

    assert not skipped
    consumed = await WeChatAgentReceipt.get(id=message.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_waiting"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_unknown_waiting_interaction_is_not_answerable(world):
    from app.core.i18n import t

    owner = await receipt_for(world, identifier="unknown-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-unknown",
        pending_tool_name="some_tool",
        pending_tool_input={"questions": []},
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))
    await runtime.process_binding(str(world.binding.id))

    notice = await IntegrationDelivery.get(
        receipt_id=owner.id, event_key="waiting_unsupported"
    )
    assert notice.payload["text"] == t("channel_approval_unsupported")
    assert (
        await IntegrationDelivery.filter(
            receipt_id=owner.id, event_key="waiting_unsupported"
        ).count()
        == 1
    )
    assert (await WeChatAgentReceipt.get(id=owner.id)).status == "submitted"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_approval_command_is_not_an_ask_user_answer(world):
    from app.core.i18n import t

    owner = await receipt_for(world, identifier="ask-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-ask",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Which one?", "required": True}]
        },
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    command = await _command_receipt(world, f"/approve {uuid4()}", "ask-command")
    await runtime.process_binding(str(world.binding.id))

    consumed = await WeChatAgentReceipt.get(id=command.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_invalid"
    reply = await IntegrationDelivery.get(
        receipt_id=command.id, event_key="approval_result"
    )
    assert reply.payload["text"] == t("channel_approval_invalid")
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_answers == {}


@pytest.mark.asyncio
async def test_decided_approval_is_dispatched_when_the_worker_already_parked(
    world, monkeypatch
):
    import app.services.agent_run_store as store

    owner = await receipt_for(world, identifier="approval-recovery")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-recovery",
        pending_tool_name="create_issue",
        pending_tool_input={
            "interaction_kind": "tool_approval",
            "execution_id": str(uuid4()),
        },
    )
    resumed = SimpleNamespace(
        id=run.id, status=AgentRunStatus.QUEUED, worker_payload={"run_id": str(run.id)}
    )

    async def terminal(run_id):
        assert run_id == run.id
        return resumed

    monkeypatch.setattr(store, "queue_agent_run_resume_if_approval_terminal", terminal)
    dispatched = []

    async def dispatch(payload, queued):
        dispatched.append((payload, queued))

    monkeypatch.setattr("app.services.agent_submission.dispatch_run", dispatch)

    async def preview(*args, **kwargs):
        raise AssertionError("a decided approval must not be announced")

    monkeypatch.setattr(runtime, "approval_preview", preview)
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    assert dispatched == [({"run_id": str(run.id)}, resumed)]


@pytest.mark.asyncio
async def test_announcement_failure_keeps_the_receipt_recoverable(world, monkeypatch):
    owner = await receipt_for(world, identifier="announce-failure")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    execution_id = uuid4()
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-announce",
        pending_tool_name="create_issue",
        pending_tool_input={
            "interaction_kind": "tool_approval",
            "execution_id": str(execution_id),
        },
    )

    async def preview(parked, user, origin, origin_id):
        return str(execution_id), "confirm"

    monkeypatch.setattr(runtime, "approval_preview", preview)
    create_delivery = runtime._create_delivery

    async def fail_announcement(receipt, **kwargs):
        if kwargs["event_key"].startswith("approval:"):
            raise RuntimeError("outbox unavailable")
        await create_delivery(receipt, **kwargs)

    monkeypatch.setattr(runtime, "_create_delivery", fail_announcement)
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    assert (await WeChatAgentReceipt.get(id=owner.id)).status == "submitted"
    assert not await IntegrationDelivery.filter(
        receipt_id=owner.id, event_key=f"approval:{execution_id}"
    ).exists()

    monkeypatch.setattr(runtime, "_create_delivery", create_delivery)
    await runtime.process_binding(str(world.binding.id))
    assert await IntegrationDelivery.filter(
        receipt_id=owner.id, event_key=f"approval:{execution_id}"
    ).exists()


@pytest.mark.asyncio
async def test_approval_command_stays_its_own_message(world):
    """A decision command must never be folded into neighbouring chat text."""
    from app.services.wechat_receiver import accept_updates

    response = {
        "msgs": [
            {**message_payload("hello"), "message_id": "chat-one"},
            {**message_payload(f"/approve {uuid4()}"), "message_id": "approve-one"},
        ],
        "get_updates_buf": "approval-batch",
    }
    await accept_updates(world.binding, response)

    rows = await WeChatAgentReceipt.all().order_by("created_at")
    assert [row.status for row in rows] == ["pending", "pending"]
    for row in rows:
        assert "batch_messages" not in json.loads(decrypt_secret(row.payload))


@pytest.mark.asyncio
async def test_waiting_notice_requires_the_session_to_own_the_run(world, monkeypatch):
    owner = await receipt_for(world, identifier="session-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    execution_id = uuid4()
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-session",
        pending_tool_name="create_issue",
        pending_tool_input={
            "interaction_kind": "tool_approval",
            "execution_id": str(execution_id),
        },
    )
    previewed = []

    async def preview(*args, **kwargs):
        previewed.append(args)
        return str(execution_id), "confirm"

    monkeypatch.setattr(runtime, "approval_preview", preview)
    # The session no longer owns the run's conversation: nothing is announced.
    await WeChatAgentSession.filter(binding_id=world.binding.id).update(
        conversation_id=None
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    await runtime.process_binding(str(world.binding.id))

    assert not previewed
    assert not await IntegrationDelivery.filter(
        receipt_id=owner.id, event_key=f"approval:{execution_id}"
    ).exists()


@pytest.mark.asyncio
async def test_decision_requires_the_session_to_own_the_run(world, monkeypatch):
    _, run, execution_id = await _wait_for_tool_approval(world, monkeypatch)
    calls = []

    async def decide(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(runtime, "decide_channel_approval", decide)
    await WeChatAgentSession.filter(binding_id=world.binding.id).update(
        conversation_id=None
    )
    command = await _command_receipt(world, f"/approve {execution_id}", "wrong-session")
    await runtime.process_binding(str(world.binding.id))

    assert not calls
    consumed = await WeChatAgentReceipt.get(id=command.id)
    assert consumed.status == "completed"
    assert consumed.error == "channel_approval_invalid"

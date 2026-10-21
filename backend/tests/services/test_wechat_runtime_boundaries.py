"""Behavior boundaries for WeChat Agent runtime validation and run transitions."""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.i18n import set_language
from app.integrations.credentials import encrypt_secret
from app.models.agent_run import (
    AgentRun,
    AgentRunInput,
    AgentRunInputKind,
    AgentRunInputStatus,
    AgentRunMode,
    AgentRunStatus,
)
from app.models.wechat_agent import (
    WeChatAgentConfig,
    WeChatAgentDelivery,
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.user import User
from app.models.wechat_knowledge import WeChatKnowledgeBinding
from app.models.agent import Conversation
from app.services import wechat_agent_runtime as runtime
from app.schemas.response import BusinessError
from app.services.wechat_connection import utcnow
from tests.services.test_wechat_agent_runtime import message_payload, receipt_for
from tests.services.test_wechat_agent_runtime import db as db, world as world


@pytest.mark.asyncio
async def test_missing_binding_returns_no_work(world):
    assert await runtime.process_binding(str(uuid4())) == {
        "pending": False,
        "processed": 0,
    }
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_missing_agent_configuration_errors_receipt(world):
    await WeChatAgentConfig.filter(binding_id=world.binding.id).delete()
    receipt = await receipt_for(world)

    result = await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert result["processed"] == 1
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_config_missing"
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_receipt_for_another_user_is_rejected_before_normalization(world):
    other = await User.create(
        id=uuid4(),
        username="other",
        email="other@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    receipt = await WeChatAgentReceipt.create(
        binding_id=world.binding.id,
        user_id=other.id,
        agent_id=world.agent.id,
        variables={},
        message_id="foreign-user",
        payload=encrypt_secret(json.dumps(message_payload())),
    )

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_binding_disconnected"
    assert not world.io.normalized
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_unauthorized_agent_is_rejected_before_normalization(world, monkeypatch):
    async def deny_agent(agent_id, user):
        raise BusinessError(code=403, msg_key="agent_access_denied", status_code=403)

    monkeypatch.setattr(runtime, "authorized_agent", deny_agent)
    receipt = await receipt_for(world)

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "agent_access_denied"
    assert not world.io.normalized
    assert not world.submission.calls


@pytest.mark.asyncio
async def test_waiting_run_persists_question_delivery(world):
    owner = await receipt_for(world, identifier="waiting-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-waiting",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "choice", "question": "Choose?", "required": True}]
        },
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(updated_at=utcnow())
    await runtime.process_binding(str(world.binding.id))

    question = await WeChatAgentDelivery.get(
        receipt_id=owner.id, event_key="ask:call-waiting"
    )
    assert question.status == "pending"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_missing_submitted_run_is_terminal_error(world):
    receipt = await receipt_for(world, identifier="orphan-run")
    receipt.status = "submitted"
    receipt.run_id = None
    await receipt.save(update_fields=["status", "run_id", "updated_at"])

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_run_failed"


@pytest.mark.asyncio
async def test_stopped_command_marks_receipt_completed_and_cancels_queued_run(world):
    await receipt_for(world, identifier="start-run")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    stop = await receipt_for(world, text="/stop", identifier="stop-run")

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=stop.id)
    session = await WeChatAgentSession.get(id=session.id)
    stopped_run = await AgentRun.get(id=run.id)
    assert refreshed.status == "completed"
    assert stopped_run.status == AgentRunStatus.STOPPED
    assert session.active_run_id is None


@pytest.mark.asyncio
async def test_long_waiting_question_preserves_utf8_across_delivery_rows(world):
    owner = await receipt_for(world, identifier="long-question")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    question_text = "请选择" * 1500
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="long-call",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "question", "question": question_text, "required": True}
            ]
        },
    )
    await runtime.process_binding(str(world.binding.id))
    rows = await WeChatAgentDelivery.filter(
        receipt_id=owner.id, event_key="ask:long-call"
    ).order_by("sequence")
    text = "".join(row.payload["text"] for row in rows)
    assert question_text in text
    assert len(rows) > 1
    assert all(len(row.payload["text"].encode("utf-8")) <= 3500 for row in rows)
    assert [row.sequence for row in rows] == list(range(len(rows)))


@pytest.mark.asyncio
async def test_answer_race_consumes_message_without_restarting_finished_run(
    world, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.services import agent_run_store

    await receipt_for(world, identifier="answer-owner")
    await runtime.process_binding(str(world.binding.id))
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="question-call",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q", "question": "Why?", "required": True}]
        },
    )
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    answer = await receipt_for(world, identifier="answer", text="Because")
    monkeypatch.setattr(
        agent_run_store, "submit_user_answers", AsyncMock(return_value=None)
    )
    resumed = await runtime._consume_answers(answer, session, run, text="Because")
    assert resumed is False
    await answer.refresh_from_db()
    assert answer.status == "completed" and answer.error == "wechat_agent_run_failed"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_error_key_uses_business_message_key_and_falls_back(world):
    """A BusinessError keeps its i18n key; anything else is the generic one."""
    assert runtime._error_key(
        BusinessError(msg_key="wechat_agent_media_unsupported")
    ) == ("wechat_agent_media_unsupported")
    assert runtime._error_key(BusinessError(msg_key=None)) == "wechat_agent_run_failed"
    assert runtime._error_key(RuntimeError("boom")) == "wechat_agent_run_failed"


@pytest.mark.asyncio
async def test_answer_completion_resumes_run_and_reports_true(world):
    """A complete answer set submits, resets the session and re-dispatches."""

    import app.services.agent_run_store as store

    receipt = await receipt_for(world, identifier="complete-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-1",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Which?", "required": True}]
        },
    )
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    session.pending_answers = {}
    await session.save(update_fields=["pending_answers"])
    resumed_run = SimpleNamespace(id=run.id, worker_payload={"run_id": str(run.id)})
    submitted = []

    async def fake_submit(run_id, **kwargs):
        submitted.append(kwargs)
        return resumed_run

    real_submit = store.submit_user_answers
    store.submit_user_answers = fake_submit
    try:
        assert await runtime._consume_answers(receipt, session, run, text="A") is True
    finally:
        store.submit_user_answers = real_submit

    assert submitted and submitted[0]["answers"] == {"q1": "A"}
    assert submitted[0]["skipped"] is False
    reloaded = await WeChatAgentSession.get(id=session.id)
    assert reloaded.pending_answers == {}
    assert reloaded.pending_tool_call_id is None
    assert reloaded.active_run_id == run.id
    await receipt.refresh_from_db()
    assert receipt.status == "completed"
    assert receipt.error is None


@pytest.mark.asyncio
async def test_already_answered_question_asks_the_next_unanswered_one(world):
    """When a question is answered the loop must advance, not re-ask it."""

    import app.services.agent_run_store as store

    receipt = await receipt_for(world, identifier="second-question")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-2",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "q1", "question": "Which?", "required": True},
                {"id": "q2", "question": "Why?", "required": True},
            ]
        },
    )
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    # q1 was already answered in a previous pass, so this message answers q2.
    session.pending_answers = {"q1": "A"}
    await session.save(update_fields=["pending_answers"])
    resumed_run = SimpleNamespace(id=run.id, worker_payload={"run_id": str(run.id)})
    captured = []

    async def fake_submit(run_id, **kwargs):
        captured.append(kwargs)
        return resumed_run

    real_submit = store.submit_user_answers
    real_validate = store.validate_user_answers
    store.submit_user_answers = fake_submit
    store.validate_user_answers = lambda pending, answers, **kw: None
    try:
        assert (
            await runtime._consume_answers(receipt, session, run, text="because")
            is True
        )
    finally:
        store.submit_user_answers = real_submit
        store.validate_user_answers = real_validate

    assert captured and captured[0]["answers"] == {"q1": "A", "q2": "because"}
    reloaded = await WeChatAgentSession.get(id=session.id)
    assert reloaded.pending_answers == {}
    assert reloaded.pending_tool_call_id is None


@pytest.mark.asyncio
async def test_optional_question_left_blank_is_resumed_without_notice(world):
    """A blank optional answer skips the notice and still completes the set."""

    import app.services.agent_run_store as store

    receipt = await receipt_for(world, identifier="optional-blank")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-3",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": False}]
        },
    )
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    session.pending_answers = {"q1": "   "}
    await session.save(update_fields=["pending_answers"])
    resumed_run = SimpleNamespace(id=run.id, worker_payload={"run_id": str(run.id)})

    async def fake_submit(run_id, **kwargs):
        return resumed_run

    real_submit = store.submit_user_answers
    store.submit_user_answers = fake_submit
    try:
        assert await runtime._consume_answers(receipt, session, run, text="   ") is True
    finally:
        store.submit_user_answers = real_submit

    assert not await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="answer_error"
    ).exists()
    assert (await WeChatAgentSession.get(id=session.id)).pending_tool_call_id is None


@pytest.mark.asyncio
async def test_waiting_run_without_owner_receipt_waits_for_announcement(world):
    """No owner receipt means a waiting message is not used as an answer."""
    receipt = await receipt_for(world, identifier="no-owner-yet")
    conversation = await Conversation.create(
        id=uuid4(), agent=world.agent, user=world.user
    )
    session = await WeChatAgentSession.create(
        binding_id=world.binding.id,
        agent_id=world.agent.id,
        conversation=conversation,
    )
    run = await AgentRun.create(
        id=uuid4(),
        agent_id=world.agent.id,
        conversation=conversation,
        user_id=world.user.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-4",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
        submitted_at=utcnow(),
    )
    await WeChatAgentSession.filter(id=session.id).update(active_run_id=run.id)

    await runtime.process_binding(str(world.binding.id))

    session = await WeChatAgentSession.get(id=session.id)
    assert session.pending_answers == {}
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    assert not await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="ask:cc-4"
    ).exists()
    assert not await AgentRunInput.filter(run_id=run.id).exists()


@pytest.mark.asyncio
async def test_announcement_with_earlier_answers_reports_partial_progress(world):
    """Re-announcing after one answer prefixes the partial notice and skips it."""
    receipt = await receipt_for(world, identifier="partial-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-5",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "q1", "question": "Which?", "required": False},
                {"id": "q2", "question": "Why?", "required": True},
            ]
        },
    )
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    session.pending_answers = {"q1": "A"}
    await session.save(update_fields=["pending_answers"])

    await runtime._announce_questions(
        receipt, await AgentRun.get(id=run.id), answered={"q1": "A"}
    )

    rows = await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="ask:cc-5"
    ).order_by("sequence")
    assert rows, "the unanswered question must still be announced"
    text = "".join(row.payload["text"] for row in rows)
    assert "Which?" not in text
    assert "Why?" in text
    assert "[1/2]" not in text


@pytest.mark.asyncio
async def test_cutoff_without_any_receipt_for_the_run_is_none(world):
    """A run referenced by no receipt has no cutoff at all."""
    conversation = await Conversation.create(
        id=uuid4(), agent=world.agent, user=world.user
    )
    run = await AgentRun.create(
        id=uuid4(),
        agent_id=world.agent.id,
        conversation=conversation,
        user_id=world.user.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-6",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
        submitted_at=utcnow(),
    )
    assert await runtime._answer_cutoff(run) is None


@pytest.mark.asyncio
async def test_stop_command_on_waiting_run_records_terminal_notice(world):
    """A waiting run is stopped through the waiting transition path."""
    import app.services.agent_run_store as store

    receipt = await receipt_for(world, identifier="stop-waiting-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-7",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
    )
    session = await WeChatAgentSession.get(binding_id=world.binding.id)

    async def fake_stop_waiting(run_id):
        await AgentRun.filter(id=run_id).update(status=AgentRunStatus.STOPPED)
        return await AgentRun.get(id=run_id)

    real_stop = store.stop_waiting_run
    store.stop_waiting_run = fake_stop_waiting
    try:
        await runtime._stop_current(session, await AgentRun.get(id=run.id))
    finally:
        store.stop_waiting_run = real_stop

    stopped = await AgentRun.get(id=run.id)
    assert stopped.status == AgentRunStatus.STOPPED
    reloaded = await WeChatAgentSession.get(id=session.id)
    assert reloaded.active_run_id is None
    assert reloaded.pending_tool_call_id is None
    # The receipt that owns the run is left submitted: its own run is now
    # terminal, so the next pass finalizes it instead of replaying it.
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "submitted"
    await runtime.process_binding(str(world.binding.id))
    finalized = await WeChatAgentReceipt.get(id=receipt.id)
    assert finalized.status == "completed"
    assert finalized.error == "wechat_agent_stopped"


@pytest.mark.asyncio
async def test_stop_command_on_stopping_run_enqueues_stop_input(world, monkeypatch):
    """An already-stopping run receives a queued STOP input, not a new transition."""
    import app.services.agent_run_store as store

    from unittest.mock import AsyncMock

    wake_worker = AsyncMock()
    monkeypatch.setattr(store, "_wake_run_worker", wake_worker)
    await receipt_for(world, identifier="stop-stopping-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.STOPPING)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)

    real_transition = store.transition_run_if_status

    async def fail_transition(*args, **kwargs):
        raise AssertionError("a stopping run must not be transitioned again")

    store.transition_run_if_status = fail_transition
    try:
        await runtime._stop_current(session, await AgentRun.get(id=run.id))
    finally:
        store.transition_run_if_status = real_transition

    inputs = await AgentRunInput.filter(run_id=run.id)
    wake_worker.assert_awaited_once_with(run.id)
    assert [item.kind for item in inputs] == [AgentRunInputKind.STOP]
    assert [item.status for item in inputs] == [AgentRunInputStatus.QUEUED]
    reloaded = await WeChatAgentSession.get(id=session.id)
    # A cooperative stop keeps the pointer until the run is really terminal.
    assert reloaded.active_run_id == run.id
    assert reloaded.pending_tool_call_id is None


@pytest.mark.asyncio
async def test_skip_command_without_resume_leaves_message_pending(world, monkeypatch):
    """A failed skip retry remains pending and is not consumed as an answer."""
    import app.services.agent_run_store as store

    owner = await receipt_for(world, identifier="skip-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-8",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
    )
    await WeChatAgentSession.filter(binding_id=world.binding.id).update(
        active_run_id=run.id, pending_tool_call_id="cc-8"
    )
    run = await AgentRun.get(id=run.id)
    await runtime._announce_questions(owner, run, answered={})
    receipt = await receipt_for(world, text="/skip", identifier="skip-lost")
    calls = []

    async def no_resume(run_id, **kwargs):
        calls.append((run_id, kwargs))
        return None

    monkeypatch.setattr(store, "submit_user_answers", no_resume)
    result = await runtime.process_binding(str(world.binding.id))

    assert len(calls) == 1
    assert calls[0][1] == {"tool_call_id": "cc-8", "answers": {}, "skipped": True}
    assert result["pending"] is True
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "pending"
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    assert session.pending_tool_call_id == "cc-8"
    assert session.pending_answers == {}
    assert not await AgentRunInput.filter(run_id=run.id).exists()


@pytest.mark.asyncio
async def test_help_command_replies_localized_and_completes(world):
    """/help answers with the localized help text and consumes the message."""
    receipt = await receipt_for(world, text="/help", identifier="help-text")
    session = await WeChatAgentSession.get_or_none(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    if session is None:
        session = await WeChatAgentSession.create(
            binding_id=world.binding.id, agent_id=world.agent.id
        )
    set_language("en")

    applied = await runtime._apply_command(receipt, session, None, "help")

    assert applied is True
    rows = await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="command"
    ).order_by("sequence")
    assert rows and rows[0].payload["text"].strip()
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error is None


@pytest.mark.asyncio
async def test_unknown_command_marker_is_not_consumed(world):
    """An unrecognized command falls through to normal message submission."""
    receipt = await receipt_for(world, identifier="unknown-command")
    session = await WeChatAgentSession.get_or_none(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    if session is None:
        session = await WeChatAgentSession.create(
            binding_id=world.binding.id, agent_id=world.agent.id
        )

    applied = await runtime._apply_command(receipt, session, None, "nonsense")

    assert applied is False
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "pending"
    assert not await WeChatAgentDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_skip_command_for_idle_run_is_not_consumed(world):
    """/skip without a waiting run stays pending and produces no delivery."""
    receipt = await receipt_for(world, text="/skip", identifier="skip-idle")
    session = await WeChatAgentSession.get_or_none(
        binding_id=world.binding.id, agent_id=world.agent.id
    )
    if session is None:
        session = await WeChatAgentSession.create(
            binding_id=world.binding.id, agent_id=world.agent.id
        )

    applied = await runtime._apply_command(receipt, session, None, "skip")

    assert applied is False
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "pending"
    assert not await WeChatAgentDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_resume_run_without_payload_raises_runtime_error(world):
    """A missing worker payload is a programmer error, never a silent retry."""

    receipt = await receipt_for(world, identifier="resume-no-payload")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-9",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
        worker_payload=None,
    )
    run = await AgentRun.get(id=run.id)

    with pytest.raises(RuntimeError):
        await runtime._resume_run(run)

    # The recovery pass logs the raise and keeps the receipt recoverable.
    await runtime.process_binding(str(world.binding.id))
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "submitted"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_resume_run_dispatches_stored_payload(world):
    """The resumed run is re-published with the payload stored on the run."""

    dispatched = []

    async def capture(payload, run):
        dispatched.append((payload, run.id))

    await receipt_for(world, identifier="resume-payload")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-10",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
        worker_payload={"run_id": str(run.id)},
    )
    run = await AgentRun.get(id=run.id)

    from app.services import agent_submission

    real_dispatch = agent_submission.dispatch_run
    agent_submission.dispatch_run = capture
    try:
        await runtime._resume_run(run)
    finally:
        agent_submission.dispatch_run = real_dispatch

    assert dispatched == [({"run_id": str(run.id)}, run.id)]


@pytest.mark.asyncio
async def test_dispatch_failure_marks_submission_error_and_keeps_receipt(world):
    """A broker failure records an error on the submitted receipt, not a loss."""
    dispatched = []

    async def failing(payload, run):
        dispatched.append(run.id)
        raise RuntimeError("broker down")

    receipt = await receipt_for(world, identifier="dispatch-fails")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    # The run stays queued: a crash before publishing is exactly the case the
    # submit path's own deferral and the recovery backoff cover.
    assert run.status == AgentRunStatus.QUEUED
    await AgentRun.filter(id=run.id).update(worker_payload={"run_id": str(run.id)})
    run = await AgentRun.get(id=run.id)
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=60)
    )
    receipt = await WeChatAgentReceipt.get(id=receipt.id)

    from app.services import agent_submission

    real_dispatch = agent_submission.dispatch_run
    agent_submission.dispatch_run = failing
    try:
        await runtime._dispatch_or_defer(receipt, run)
    finally:
        agent_submission.dispatch_run = real_dispatch

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"
    assert refreshed.error == "wechat_agent_run_failed"
    assert refreshed.run_id == run.id
    assert dispatched == [run.id]


@pytest.mark.asyncio
async def test_dispatch_of_stale_receipt_reaches_the_broker(world):
    """Once the backoff window has passed the queued run is re-published."""
    dispatched = []

    async def capture(payload, run):
        dispatched.append((payload, run.id))

    receipt = await receipt_for(world, identifier="dispatch-retry")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(worker_payload={"run_id": str(run.id)})
    run = await AgentRun.get(id=run.id)
    # A recovery pass long after submission is allowed to publish again.
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=60)
    )
    receipt = await WeChatAgentReceipt.get(id=receipt.id)

    from app.services import agent_submission

    real_dispatch = agent_submission.dispatch_run
    agent_submission.dispatch_run = capture
    try:
        await runtime._dispatch_or_defer(receipt, run)
    finally:
        agent_submission.dispatch_run = real_dispatch

    assert dispatched == [({"run_id": str(run.id)}, run.id)]
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.error is None


@pytest.mark.asyncio
async def test_dispatch_is_throttled_within_backoff_window(world):
    """A freshly updated receipt is not re-published inside the backoff."""
    calls = []

    async def capture(payload, run):
        calls.append(run.id)

    receipt = await receipt_for(world, identifier="dispatch-backoff")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    assert run.status == AgentRunStatus.QUEUED
    await AgentRun.filter(id=run.id).update(worker_payload={"run_id": str(run.id)})
    run = await AgentRun.get(id=run.id)

    from app.services import agent_submission

    real_dispatch = agent_submission.dispatch_run
    agent_submission.dispatch_run = capture
    try:
        await runtime._dispatch_or_defer(receipt, run)
    finally:
        agent_submission.dispatch_run = real_dispatch

    assert calls == []


@pytest.mark.asyncio
async def test_dispatch_of_non_queued_run_is_skipped(world):
    """A run that already left the queue must never be re-published."""
    calls = []

    async def capture(payload, run):
        calls.append(run.id)

    receipt = await receipt_for(world, identifier="dispatch-not-queued")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)
    run = await AgentRun.get(id=run.id)

    from app.services import agent_submission

    real_dispatch = agent_submission.dispatch_run
    agent_submission.dispatch_run = capture
    try:
        await runtime._dispatch_or_defer(receipt, run)
    finally:
        agent_submission.dispatch_run = real_dispatch

    assert calls == []


@pytest.mark.asyncio
async def test_submission_rejects_race_lost_claim_as_busy(world):
    """A concurrent claim of the same receipt fails the submission as busy."""
    receipt = await receipt_for(world, identifier="claim-race")
    # A peer already claimed the receipt, so the row-count guard in the
    # submission transaction must abort as busy instead of re-submitting.
    await WeChatAgentReceipt.filter(id=receipt.id).update(status="submitted")
    conversation = await Conversation.create(
        id=uuid4(), agent=world.agent, user=world.user
    )
    session = await WeChatAgentSession.create(
        binding_id=world.binding.id,
        agent_id=world.agent.id,
        conversation=conversation,
    )
    from app.schemas.agent import ChatRequest

    prepared = ChatRequest(message="hello", conversation_id=session.conversation_id)

    with pytest.raises(BusinessError) as caught:
        await runtime._submit_receipt(
            receipt,
            session,
            world.agent,
            world.user,
            world.binding,
            prepared=prepared,
        )
    assert caught.value.msg_key == "wechat_agent_busy"
    assert caught.value.status_code == 409
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_submission_revalidates_disconnect_under_lock(world, monkeypatch):
    """A disconnect landing after normalization aborts the submission."""
    receipt = await receipt_for(world, identifier="disconnect-race")
    original_normalize = world.io.normalize_input

    async def disconnect_during_normalize(inner_receipt, session, agent, user, client):
        await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
            status="disconnected", token="", disconnected_at=utcnow()
        )
        return await original_normalize(inner_receipt, session, agent, user, client)

    monkeypatch.setattr(
        "app.services.wechat_agent_io.normalize_input", disconnect_during_normalize
    )
    await runtime.process_binding(str(world.binding.id))

    await runtime.process_binding(str(world.binding.id))
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert not world.submission.calls
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_binding_disconnected"
    # The acknowledgement was already delivered, but the run was never created.
    assert await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="received"
    ).exists()
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_all_questions_answered_announces_notice_only(world):
    """A fully answered question set announces only the partial notice."""
    receipt = await receipt_for(world, identifier="all-done")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="cc-13",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
    )
    run = await AgentRun.get(id=run.id)

    await runtime._announce_questions(receipt, run, answered={"q1": "A"})

    rows = await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="ask:cc-13"
    ).order_by("sequence")
    assert rows, "the partial-progress notice itself must be delivered"
    text = "".join(row.payload["text"] for row in rows)
    assert "Why?" not in text
    assert len(rows) == 1 and rows[0].sequence == 0


@pytest.mark.asyncio
async def test_question_index_prefix_marks_multi_question_sets(world):
    """The [n/total] prefix is only used when more than one question is asked."""
    from app.services.wechat_agent_runtime import _question_text

    single = _question_text({"id": "q1", "question": "Why?"}, 1, 1)
    assert single == "Why?"

    multi = _question_text(
        {"id": "q1", "question": "Why?", "options": ["A", "B"]}, 2, 3
    )
    assert multi.startswith("[2/3]")
    assert "A / B" in multi


@pytest.mark.asyncio
async def test_stopped_run_finalization_is_silent_but_completes(world):
    """A stopped run completes its receipt without re-announcing the stop."""
    receipt = await receipt_for(world, identifier="stopped-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.STOPPED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    session = await WeChatAgentSession.get(binding_id=world.binding.id)

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error == "wechat_agent_stopped"
    assert not await WeChatAgentDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()
    assert (await WeChatAgentSession.get(id=session.id)).active_run_id is None


@pytest.mark.asyncio
async def test_interrupted_run_reports_generic_failure(world):
    """An interrupted run uses the same generic failure notice as a failure."""
    receipt = await receipt_for(world, identifier="interrupted-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.INTERRUPTED,
        error_message="worker vanished",
        finished_at=utcnow(),
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_run_failed"
    delivery = await WeChatAgentDelivery.get(receipt_id=receipt.id, event_key="final")
    assert "worker vanished" not in delivery.payload["text"]
    assert delivery.payload["text"].strip()


@pytest.mark.asyncio
async def test_finalize_without_authorization_marks_unavailable_reply(
    world, monkeypatch
):
    """A revoked agent turns the final reply into an unavailable delivery."""

    async def deny_agent(agent_id, user):
        raise BusinessError(code=403, msg_key="agent_access_denied", status_code=403)

    receipt = await receipt_for(world, identifier="revoked-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    world.io.outputs[str(run.id)] = [{"kind": "text", "text": "secret answer"}]
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    monkeypatch.setattr(runtime, "authorized_agent", deny_agent)
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "completed"
    assert refreshed.error == "agent_access_denied"
    delivery = await WeChatAgentDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.status == "unavailable"
    assert delivery.error == "agent_access_denied"
    assert delivery.payload["text"].strip()
    assert "secret answer" not in delivery.payload["text"]


@pytest.mark.asyncio
async def test_submitted_receipt_without_run_is_terminal_error(world):
    """A submitted receipt whose run row disappeared is a terminal error."""
    receipt = await receipt_for(world, identifier="gone-run")
    await runtime.process_binding(str(world.binding.id))
    run_id = world.submission.run.id
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    await AgentRun.filter(id=run_id).delete()
    # ON DELETE SET NULL clears the receipt and session pointers; the submitted
    # receipt is resolved as a terminal error on the next recovery pass.
    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_run_failed"
    assert (await WeChatAgentSession.get(id=session.id)).active_run_id is None


@pytest.mark.asyncio
async def test_blank_optional_answer_prompts_for_later_required_question(world):
    await receipt_for(world, identifier="optional-question-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="required-call",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "q1", "question": "Optional?", "required": False},
                {"id": "q2", "question": "Explain?", "required": True},
            ]
        },
    )
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)

    answer = await receipt_for(world, text="   ", identifier="blank-optional")
    await runtime._consume_answers(answer, session, run, text="   ")

    saved_session = await WeChatAgentSession.get(id=session.id)
    saved_receipt = await WeChatAgentReceipt.get(id=answer.id)
    assert saved_session.pending_answers == {"q1": ""}
    assert saved_receipt.status == "completed"
    assert saved_receipt.error == "wechat_agent_answer_required"
    delivery = await WeChatAgentDelivery.get(
        receipt_id=answer.id, event_key="answer_error"
    )
    assert "Explain?" in delivery.payload["text"]
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_finalize_empty_completed_run_sends_explicit_no_output(world):
    receipt = await receipt_for(world, identifier="empty-output")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED, finished_at=utcnow()
    )
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    await runtime.process_binding(str(world.binding.id))

    saved = await WeChatAgentReceipt.get(id=receipt.id)
    delivery = await WeChatAgentDelivery.get(receipt_id=receipt.id, event_key="final")
    assert saved.status == "completed" and saved.error is None
    assert delivery.payload["text"].strip()
    assert (await WeChatAgentSession.get(id=session.id)).active_run_id is None


@pytest.mark.asyncio
async def test_missing_binding_user_skips_delivery_but_counts_receipt(
    world, monkeypatch
):
    """A missing binding owner prevents delivery but receipt errors are counted."""
    from unittest.mock import AsyncMock

    receipt = await receipt_for(world)
    binding_id = world.binding.id
    missing_user_query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(User, "filter", lambda **_kwargs: missing_user_query)

    result = await runtime.process_binding(str(binding_id))

    assert result["processed"] == 1
    assert result["pending"] is False
    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "error"
    assert refreshed.error == "wechat_agent_binding_disconnected"
    assert world.io.delivered == []


@pytest.mark.asyncio
async def test_non_pending_receipt_ignores_missing_agent_config(world):
    """A submitted receipt with no agent config is left untouched, not errored."""
    receipt = await receipt_for(world)
    await runtime.process_binding(str(world.binding.id))
    submitted_at = (await WeChatAgentReceipt.get(id=receipt.id)).updated_at
    await WeChatAgentConfig.filter(binding_id=world.binding.id).delete()

    await runtime.process_binding(str(world.binding.id))

    refreshed = await WeChatAgentReceipt.get(id=receipt.id)
    assert refreshed.status == "submitted"
    assert refreshed.updated_at == submitted_at


@pytest.mark.asyncio
async def test_stop_command_without_active_run_clears_session_and_reports(world):
    receipt = await receipt_for(world, text="/stop", identifier="idle-stop")
    await runtime.process_binding(str(world.binding.id))

    saved = await WeChatAgentReceipt.get(id=receipt.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    delivery = await WeChatAgentDelivery.get(receipt_id=receipt.id, event_key="command")
    assert saved.status == "completed" and saved.error is None
    assert session.active_run_id is None and session.pending_answers == {}
    assert "stop" in delivery.payload["text"].lower()
    assert not await AgentRun.all().exists()


@pytest.mark.asyncio
async def test_required_answer_validation_saves_and_consumes_incomplete_answer(
    world, monkeypatch
):
    owner = await receipt_for(world, identifier="required-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="required-call",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "optional", "question": "Extra?", "required": False},
                {"id": "required", "question": "Explain?", "required": True},
            ]
        },
    )
    owner = await WeChatAgentReceipt.get(id=owner.id)
    run = await AgentRun.get(id=run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    answer = await receipt_for(world, text="", identifier="empty-required")
    await WeChatAgentReceipt.filter(id=answer.id).update(
        created_at=utcnow() + timedelta(seconds=1)
    )
    await runtime._announce_questions(owner, run, answered={})
    resumed = await runtime._consume_answers(answer, session, run, text="")

    assert resumed is False
    saved_session = await WeChatAgentSession.get(id=session.id)
    saved_answer = await WeChatAgentReceipt.get(id=answer.id)
    assert saved_session.pending_answers == {"optional": ""}
    assert saved_answer.status == "completed"
    assert saved_answer.error == "wechat_agent_answer_required"
    notice = await WeChatAgentDelivery.get(
        receipt_id=answer.id, event_key="answer_error"
    )
    assert "Explain?" in notice.payload["text"]


@pytest.mark.asyncio
async def test_answer_waits_until_question_announcement_is_persisted(world):
    owner = await receipt_for(world, identifier="announcement-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="late-announcement",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q", "question": "Why?", "required": True}]
        },
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(run_id=None, status="completed")
    answer = await receipt_for(world, text="Because", identifier="without-owner")
    await WeChatAgentReceipt.filter(id=answer.id).update(
        created_at=utcnow() + timedelta(seconds=1)
    )

    processed = await runtime._process_pending(
        answer,
        world.binding,
        await WeChatAgentSession.get(binding_id=world.binding.id),
        run,
    )

    assert processed is None
    assert (await WeChatAgentReceipt.get(id=answer.id)).status == "pending"


def test_agent_task_returns_pending_when_binding_lock_is_held(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from app.services import wechat_locks
    from app.tasks import wechat_agent

    @asynccontextmanager
    async def busy_lock(_name):
        raise wechat_locks.CollectionBusy
        yield

    monkeypatch.setattr(wechat_locks, "collection_lock", busy_lock)
    monkeypatch.setattr(
        wechat_agent, "_run_async", lambda coroutine: asyncio.run(coroutine)
    )

    result = wechat_agent.process_binding_task.run("binding-id")

    assert result == {"pending": True}


@pytest.mark.asyncio
async def test_runtime_ignores_completed_receipt_and_session_without_agent_id(world):
    receipt = await receipt_for(world, identifier="completed-no-op")
    receipt.status = "completed"
    await receipt.save(update_fields=["status"])

    await runtime._process_receipt(receipt, world.binding)

    assert await runtime._session_for(world.binding.id, None) is None
    assert (await WeChatAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_stale_receipt_is_rejected_after_binding_disconnect_time(world):
    from app.services.wechat_agent_runtime import _authorized_context

    receipt = await receipt_for(world, identifier="pre-disconnect-message")
    await WeChatKnowledgeBinding.filter(id=world.binding.id).update(
        disconnected_at=utcnow() + timedelta(seconds=1)
    )

    with pytest.raises(BusinessError) as denied:
        await _authorized_context(await WeChatAgentReceipt.get(id=receipt.id))

    assert denied.value.msg_key == "wechat_agent_binding_disconnected"


def test_runtime_chunking_does_not_append_empty_tail_after_exact_boundary(world):
    assert runtime._split_text_chunks("abcdef", limit=3) == ["abc", "def"]


@pytest.mark.asyncio
async def test_stop_race_that_finishes_run_does_not_enqueue_redundant_stop(
    world, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.services import agent_run_store

    await receipt_for(world, identifier="stop-race-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    session = await WeChatAgentSession.get(binding_id=world.binding.id)
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)
    terminal = await AgentRun.get(id=run.id)
    terminal.status = AgentRunStatus.STOPPED
    transition = AsyncMock(return_value=terminal)
    enqueue = AsyncMock()
    monkeypatch.setattr(agent_run_store, "transition_run_if_status", transition)
    monkeypatch.setattr(agent_run_store, "enqueue_input", enqueue)

    await runtime._stop_current(session, await AgentRun.get(id=run.id))

    transition.assert_awaited_once()
    enqueue.assert_not_awaited()
    assert (await WeChatAgentSession.get(id=session.id)).active_run_id is None


@pytest.mark.asyncio
async def test_waiting_run_with_empty_questions_leaves_answer_pending(world):
    owner = await receipt_for(world, identifier="empty-question-owner")
    await runtime.process_binding(str(world.binding.id))
    run = await AgentRun.get(id=world.submission.run.id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="empty-questions",
        pending_tool_name="ask_user",
        pending_tool_input={"questions": []},
    )
    await WeChatAgentReceipt.filter(id=owner.id).update(status="completed")
    answer = await receipt_for(
        world, text="unmatched answer", identifier="empty-question-answer"
    )
    await WeChatAgentReceipt.filter(id=answer.id).update(
        created_at=utcnow() + timedelta(seconds=1)
    )

    await runtime._process_pending(
        await WeChatAgentReceipt.get(id=answer.id),
        world.binding,
        await WeChatAgentSession.get(binding_id=world.binding.id),
        await AgentRun.get(id=run.id),
    )

    assert (await WeChatAgentReceipt.get(id=answer.id)).status == "pending"
    assert not await WeChatAgentDelivery.filter(
        receipt_id=owner.id, event_key="ask:empty-questions"
    ).exists()

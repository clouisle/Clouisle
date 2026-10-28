"""Feishu Agent runtime branch gaps against the isolated real ORM.

These tests reuse the shared ``world`` fixture from the runtime boundary suite
(real Tortoise on SQLite, stubbed submission and Feishu transport) and target
durable behaviors that the boundary suite does not reach yet:

* a bound Agent whose team was deleted, and a session Agent that was revoked,
* commands whose argument is missing, invalid, or already selected,
* ``/new`` on a busy run, and the ``/stop`` transitions for every run state,
* re-validation under the submit lock, including a switched Agent and a
  capability that was dropped while the transaction was open,
* a claim lost to a concurrent task, a channel that lost its feature, and a
  client without credentials,
* the answer cutoff that has to be persisted on the run's own receipt, and an
  answer that is still incomplete after a required question remains open,
* delivery re-authorization after the recipient was deactivated or lost
  approval, and asset uploads whose run, user, Agent or bytes are missing,
* ``deliver_pending_for_integration`` for a chat-less integration and an
  integration that lost the feature mid-drain.
"""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.agent import Agent, AgentStatus, AgentVisibility, Conversation
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.feishu_agent import (
    FeishuAgentPreference,
    FeishuAgentReceipt,
    FeishuAgentSession,
)
from app.models.integration import Integration
from app.models.integration_delivery import IntegrationDelivery
from app.models.user import User
from app.core.i18n import t
from app.services import feishu_agent_runtime as runtime
from app.services.wechat_connection import utcnow
from tests.services.test_feishu_agent_runtime import (
    CHAT_ID,
    _generated_asset,
    _image_display,
    _use_media_transport,
    _waiting_run,
    db as db,
    receipt_for,
    session_for,
    text_event,
    world as world,
)


async def _second_agent(world, name="Second agent"):
    """A second published Agent the same user may select."""
    return await Agent.create(
        id=uuid4(),
        name=name,
        team=world.team,
        created_by=world.user,
        status=AgentStatus.PUBLISHED,
        visibility=AgentVisibility.TEAM,
        enable_attachments=False,
    )


async def _make_run(world, **overrides):
    conversation = await Conversation.create(agent=world.agent, user=world.user)
    values = dict(
        id=uuid4(),
        agent_id=world.agent.id,
        conversation_id=conversation.id,
        user_id=world.user.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.QUEUED,
    )
    values.update(overrides)
    return await AgentRun.create(**values)


async def _display_asset_run(world, monkeypatch, message_id):
    """A completed run with one tool-displayed image asset queued for Feishu."""
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id=message_id)
    await runtime.process_pending()
    run = world.submission.run
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
        content="here is the image",
        round_id=round_id,
        round_role="assistant_final",
    )
    await _generated_asset(world, conversation_id=run.conversation_id)
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=canonical.id,
        active_round_id=round_id,
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    return transport, receipt, run


# --- inbound acceptance ------------------------------------------------------


@pytest.mark.asyncio
async def test_message_without_ids_is_ignored(world):
    event = text_event(message_id="", chat_id="")
    assert await runtime.accept_message(event) is None
    assert not await FeishuAgentReceipt.all().exists()


@pytest.mark.asyncio
async def test_command_message_is_accepted_without_any_bound_agent(world):
    """A revoked Agent must not block a plain command such as /help."""
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    receipt_id = await runtime.accept_message(
        text_event(text="/help", message_id="om_help_no_agent")
    )

    receipt = await FeishuAgentReceipt.get(id=receipt_id)
    assert receipt.status == "pending"
    assert receipt.agent_id is None

    await runtime.process_pending()

    answered = await FeishuAgentReceipt.get(id=receipt.id)
    assert answered.status == "completed"
    # /help is answered directly; no Agent is ever bound to this receipt.
    assert answered.agent_id is None
    assert await IntegrationDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_deleted_team_blocks_the_bound_agent(world):
    """A deleted team must make the receipt unusable, not silently rerouted."""
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    receipt_id = await runtime.accept_message(text_event(message_id="om_deleted_team"))

    assert receipt_id is None


@pytest.mark.asyncio
async def test_use_command_creates_the_selected_agent_session_and_receipt(world):
    second = await _second_agent(world)
    # The bound Agent becomes unusable, so the /use target carries the receipt.
    await Agent.filter(id=world.agent.id).update(status=AgentStatus.DRAFT)

    receipt_id = await runtime.accept_message(
        text_event(text=f"/use {second.id}", message_id="om_use_second")
    )

    receipt = await FeishuAgentReceipt.get(id=receipt_id)
    assert receipt.agent_id == second.id
    preference = await FeishuAgentPreference.get(
        integration_id=world.integration.id, user_id=world.user.id
    )
    assert preference.agent_id == second.id
    session = await FeishuAgentSession.get(
        integration_id=world.integration.id,
        chat_id=CHAT_ID,
        user_id=world.user.id,
        agent_id=second.id,
    )
    assert session.active_run_id is None


# --- commands ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_use_index_selects_the_first_listed_agent(world):
    await _second_agent(world)

    receipt = await receipt_for(world, text="/use 1", message_id="om_use_index")
    await runtime.process_pending()

    preference = await FeishuAgentPreference.get(
        integration_id=world.integration.id, user_id=world.user.id
    )
    ordered = await runtime._selectable_agents(world.integration, world.user)
    assert preference.agent_id == ordered[0].id
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_new_command_is_refused_while_a_run_is_active(world):
    receipt = await receipt_for(world, text="hello", message_id="om_new_busy")
    await runtime.process_pending()
    run = world.submission.run
    assert run is not None
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)
    session = await session_for(world)

    applied, resulting = await runtime._apply_command(
        receipt,
        session,
        world.agent,
        await AgentRun.get(id=run.id),
        "new",
        "",
        world.integration,
        world.user,
    )

    assert applied is False
    assert resulting.id == session.id
    busy = await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="busy"
    ).first()
    assert busy is not None
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "submitted"


@pytest.mark.asyncio
async def test_new_command_resets_even_without_a_session_row(world):
    receipt = await receipt_for(world, text="/new", message_id="om_new_no_session")

    applied, resulting = await runtime._apply_command(
        receipt, None, world.agent, None, "new", "", world.integration, world.user
    )

    assert applied is True
    assert resulting is None
    reply = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="command")
    assert reply.text.strip()
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_unknown_command_falls_through_to_the_message_path(world):
    receipt = await receipt_for(
        world, text="/agents extra", message_id="om_unknown_cmd"
    )
    session = await session_for(world)

    applied, resulting = await runtime._apply_command(
        receipt,
        session,
        world.agent,
        None,
        "definitely-not",
        "",
        world.integration,
        world.user,
    )

    assert applied is False
    assert resulting.id == session.id
    assert not await IntegrationDelivery.filter(receipt_id=receipt.id).exists()
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "pending"


@pytest.mark.asyncio
async def test_use_command_switches_to_a_new_agent_from_the_processing_path(world):
    second = await _second_agent(world)
    receipt = await receipt_for(
        world, text=f"/use {second.id}", message_id="om_use_switch"
    )
    session = await session_for(world)

    applied, resulting = await runtime._apply_command(
        receipt,
        session,
        world.agent,
        None,
        "use",
        str(second.id),
        world.integration,
        world.user,
    )

    assert applied is True
    assert resulting is session
    await FeishuAgentSession.get(
        integration_id=world.integration.id,
        chat_id=CHAT_ID,
        user_id=world.user.id,
        agent_id=second.id,
    )
    preference = await FeishuAgentPreference.get(
        integration_id=world.integration.id, user_id=world.user.id
    )
    assert preference.agent_id == second.id
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


# --- stop transitions --------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_command_handles_every_run_state(world, monkeypatch):
    import app.services.agent_run_store as store

    session = await FeishuAgentSession.get_or_create(
        integration_id=world.integration.id,
        chat_id=CHAT_ID,
        user_id=world.user.id,
        agent_id=world.agent.id,
    )
    session = session[0]
    events = []

    async def stop_waiting(run_id):
        events.append(("waiting", run_id))
        return None

    async def stop_queued(run_id):
        events.append(("queued", run_id))
        return None

    async def transition(run, current, target):
        events.append(("transition", current, target))
        # The real store mutates the run object on a successful transition.
        run.status = target
        return run

    async def enqueue(**kwargs):
        events.append(("input", kwargs["kind"]))
        return None

    monkeypatch.setattr(store, "stop_waiting_run", stop_waiting)
    monkeypatch.setattr(store, "stop_queued_run", stop_queued)
    monkeypatch.setattr(store, "transition_run_if_status", transition)
    monkeypatch.setattr(store, "enqueue_input", enqueue)

    # A waiting run asks the worker to stop waiting; a None return keeps the
    # original run object.
    waiting = await _make_run(world, status=AgentRunStatus.WAITING)
    await runtime._stop_current(session, waiting)
    assert events == [("waiting", waiting.id)]

    # A queued run is cancelled instead of dispatched.
    events.clear()
    queued = await _make_run(world, status=AgentRunStatus.QUEUED)
    await runtime._stop_current(session, queued)
    assert events == [("queued", queued.id)]

    # A running run moves to STOPPING and enqueues a cooperative stop input.
    events.clear()
    running = await _make_run(world, status=AgentRunStatus.RUNNING)
    await runtime._stop_current(session, running)
    assert events == [
        ("transition", AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
        ("input", "stop"),
    ]

    # A run already STOPPING only needs the stop input.
    events.clear()
    stopping = await _make_run(world, status=AgentRunStatus.STOPPING)
    await runtime._stop_current(session, stopping)
    assert events == [("input", "stop")]


@pytest.mark.asyncio
async def test_stop_current_without_session_or_run_is_a_noop(world):
    await runtime._stop_current(None, None)
    assert not await FeishuAgentReceipt.filter(status="error").exists()


@pytest.mark.asyncio
async def test_stop_current_cancels_pending_receipts_of_the_chat(world):
    receipt = await receipt_for(world, text="hello", message_id="om_stop_cancel")
    await runtime.process_pending()
    run = world.submission.run
    session = await session_for(world)
    # A message that was accepted but not yet submitted is still pending.
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="pending")

    await runtime._stop_current(session, await AgentRun.get(id=run.id))

    cancelled = await FeishuAgentReceipt.get(id=receipt.id)
    assert cancelled.status == "error"
    assert cancelled.error == "feishu_agent_stopped"
    assert session.pending_answers == {}
    assert session.pending_tool_call_id is None


# --- resume and answers ------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_run_requires_a_worker_payload(world):
    run = await _make_run(world, status=AgentRunStatus.WAITING)
    with pytest.raises(RuntimeError, match="payload is missing"):
        await runtime._resume_run(run)


@pytest.mark.asyncio
async def test_resume_run_redispatches_the_stored_payload(world, monkeypatch):
    run = await _make_run(
        world, status=AgentRunStatus.WAITING, worker_payload={"run_id": "r"}
    )
    dispatched = []

    async def dispatch(payload, dispatched_run):
        dispatched.append((payload, dispatched_run.id))

    monkeypatch.setattr("app.services.agent_submission.dispatch_run", dispatch)
    await runtime._resume_run(run)

    assert dispatched == [({"run_id": "r"}, run.id)]


@pytest.mark.asyncio
async def test_incomplete_answer_set_is_reported_without_resuming(world):
    receipt, run = await _waiting_run(
        world,
        [
            {"id": "q1", "question": "First?", "required": True},
            {"id": "q2", "question": "Second?", "required": True},
        ],
    )
    answer = await receipt_for(world, text="only first", message_id="om_partial")
    session = await session_for(world)
    # Refresh: the stored questions were written after the run was created.
    run = await AgentRun.get(id=run.id)

    applied = await runtime._consume_answers(answer, session, run, text="only first")

    assert applied is False
    refreshed = await FeishuAgentReceipt.get(id=answer.id)
    assert refreshed.status == "completed"
    assert refreshed.error == "feishu_agent_answer_required"
    saved = await session_for(world)
    assert saved.pending_answers == {"q1": "only first"}
    assert saved.pending_tool_call_id is None
    notice = await IntegrationDelivery.filter(
        receipt_id=answer.id, event_key="answer_error"
    ).first()
    assert notice is not None
    assert "Second?" in notice.text
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_optional_question_does_not_block_the_answer(world):
    receipt, run = await _waiting_run(
        world,
        [
            {"id": "q1", "question": "Only?", "required": False},
        ],
    )
    answer = await receipt_for(world, text="anything", message_id="om_optional")
    session = await session_for(world)
    run = await AgentRun.get(id=run.id)

    applied = await runtime._consume_answers(answer, session, run, text="anything")

    # An optional question is answered and resumes the run immediately.
    assert applied is True
    assert (await FeishuAgentReceipt.get(id=answer.id)).status == "completed"
    assert (await session_for(world)).pending_answers == {}


@pytest.mark.asyncio
async def test_attachment_answer_is_rejected_for_a_waiting_run(world):
    receipt, run = await _waiting_run(
        world, [{"id": "q1", "question": "Which?", "required": True}]
    )
    # A file-only message is accepted, but it can never answer a question.
    event = text_event(text="", message_type="file", message_id="om_answer_file")
    event["message"]["content"] = json.dumps(
        {"file_key": "file_1", "file_name": "a.txt"}
    )
    answer_id = await runtime.accept_message(event)
    assert answer_id is not None
    answer = await FeishuAgentReceipt.get(id=answer_id)

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=answer.id)
    assert stored.status == "completed"
    assert stored.error == "feishu_agent_answer_text_required"
    notice = await IntegrationDelivery.filter(
        receipt_id=answer.id, event_key="answer_error"
    ).first()
    assert notice is not None
    assert (await session_for(world)).pending_answers == {}


@pytest.mark.asyncio
async def test_question_cutoff_is_persisted_on_the_owning_receipt(world, monkeypatch):
    """The question delivery must exist before any message can answer it."""
    receipt = await receipt_for(world, message_id="om_cutoff_owner")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-cutoff",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [{"id": "q1", "question": "Why?", "required": True}]
        },
    )
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="submitted")
    answer = await receipt_for(world, text="because", message_id="om_cutoff_answer")
    await FeishuAgentReceipt.filter(id=answer.id).update(
        created_at=utcnow() + timedelta(seconds=1)
    )

    async def submit(run_id, **kwargs):
        return SimpleNamespace(id=run.id, status=AgentRunStatus.QUEUED)

    monkeypatch.setattr("app.services.agent_run_store.submit_user_answers", submit)
    await runtime.process_pending()

    # The question is announced on the receipt that owns the run, and the
    # newer message is then accepted as its answer.
    announced = await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="ask:call-cutoff"
    ).first()
    assert announced is not None
    assert (await FeishuAgentReceipt.get(id=answer.id)).status == "completed"


@pytest.mark.asyncio
async def test_message_older_than_the_question_is_not_an_answer(world):
    receipt, run = await _waiting_run(
        world, [{"id": "q1", "question": "Why?", "required": True}]
    )
    stale = await receipt_for(world, text="too old", message_id="om_stale_answer")
    await FeishuAgentReceipt.filter(id=stale.id).update(
        created_at=utcnow() - timedelta(minutes=10)
    )

    await runtime.process_pending()

    assert (await FeishuAgentReceipt.get(id=stale.id)).status == "pending"
    assert (await session_for(world)).pending_answers == {}


# --- submission lock and claim ----------------------------------------------


@pytest.mark.asyncio
async def test_submission_is_refused_when_the_agent_switched_under_the_lock(
    world, monkeypatch
):
    receipt = await receipt_for(world, message_id="om_switch_race")
    session = await session_for(world)
    second = await _second_agent(world)

    class RacingSessionQuery:
        """A locked session row that a concurrent /use already rebound."""

        def __init__(self, row):
            self.row = row

        def using_db(self, _db):
            return self

        def select_for_update(self):
            return self

        async def first(self):
            # The row now belongs to a different Agent than the caller holds.
            return SimpleNamespace(id=self.row.id, agent_id=second.id)

    monkeypatch.setattr(
        FeishuAgentSession,
        "filter",
        lambda **kwargs: RacingSessionQuery(session),
    )

    with pytest.raises(Exception) as error:
        await runtime._submit_receipt(receipt, session, world.agent, world.user)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_agent_unavailable"


@pytest.mark.asyncio
async def test_submission_is_refused_when_the_session_row_disappears(
    world, monkeypatch
):
    receipt = await receipt_for(world, message_id="om_session_gone")
    session = await session_for(world)

    class MissingSessionQuery:
        def using_db(self, _db):
            return self

        def select_for_update(self):
            return self

        async def first(self):
            return None

    monkeypatch.setattr(
        FeishuAgentSession, "filter", lambda **kwargs: MissingSessionQuery()
    )

    with pytest.raises(Exception) as error:
        await runtime._submit_receipt(receipt, session, world.agent, world.user)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_agent_unavailable"


@pytest.mark.asyncio
async def test_submission_is_refused_when_the_feature_is_dropped_under_the_lock(
    world, monkeypatch
):
    receipt = await receipt_for(world, message_id="om_feature_race")
    session = await session_for(world)

    class FeaturelessIntegrationQuery:
        def using_db(self, _db):
            return self

        async def first(self):
            return SimpleNamespace(
                id=world.integration.id,
                is_enabled=True,
                enabled_capabilities=[],
                config={"app_id": "cli_test"},
            )

    monkeypatch.setattr(
        Integration, "filter", lambda **kwargs: FeaturelessIntegrationQuery()
    )

    with pytest.raises(Exception) as error:
        await runtime._submit_receipt(receipt, session, world.agent, world.user)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_channel_disabled"


@pytest.mark.asyncio
async def test_lost_claim_is_reported_as_busy(world, monkeypatch):
    receipt = await receipt_for(world, message_id="om_lost_claim")
    session = await session_for(world)
    await runtime.process_pending()
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        status="pending", run_id=None, error=None
    )

    class ClaimlessReceiptQuery:
        """The receipt row was claimed by another task before this one."""

        def using_db(self, _db):
            return self

        async def update(self, **values):
            if values.get("status") == "submitted":
                return 0
            return 1

    monkeypatch.setattr(
        FeishuAgentReceipt, "filter", lambda **kwargs: ClaimlessReceiptQuery()
    )

    with pytest.raises(Exception) as error:
        await runtime._submit_receipt(receipt, session, world.agent, world.user)
    assert getattr(error.value, "msg_key", None) == "feishu_agent_busy"


@pytest.mark.asyncio
async def test_attachment_too_many_files_blocks_submission(world):
    await Agent.filter(id=world.agent.id).update(enable_attachments=True)
    receipt = await receipt_for(world, message_id="om_too_many_files")
    attachments = [
        {"kind": "file", "key": f"file_{index}", "name": "a.txt"} for index in range(7)
    ]
    await FeishuAgentReceipt.filter(id=receipt.id).update(attachments=attachments)

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_too_many_files"


@pytest.mark.asyncio
async def test_disabled_attachments_block_submission(world):
    receipt = await receipt_for(world, message_id="om_attachments_off")
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        attachments=[{"kind": "file", "key": "file_1", "name": "a.txt"}]
    )

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_attachments_disabled"


@pytest.mark.asyncio
async def test_submission_failure_with_attachments_explains_media(world):
    await Agent.filter(id=world.agent.id).update(enable_attachments=True)
    receipt = await receipt_for(world, message_id="om_media_failed")
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        attachments=[{"kind": "file", "key": "file_1", "name": "a.txt"}]
    )
    world.submission.error = RuntimeError("download exploded")

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_media_failed"
    notice = await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).first()
    assert notice is not None


@pytest.mark.asyncio
async def test_submission_failure_without_attachments_keeps_the_error(world):
    receipt = await receipt_for(world, message_id="om_plain_failed")
    world.submission.error = RuntimeError("broker down")

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "pending"
    assert stored.error == "feishu_agent_run_failed"


# --- finalization ------------------------------------------------------------


@pytest.mark.asyncio
async def test_stopped_run_is_consumed_without_any_reply(world):
    receipt = await receipt_for(world, message_id="om_stopped_run")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.STOPPED)
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    await runtime._finalize_receipt(receipt, None, await AgentRun.get(id=run.id))

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "completed"
    assert stored.error == "feishu_agent_stopped"
    # Only the intake progress notice was ever sent; a stopped run never
    # implies a reply.
    assert [sent[1] for sent in world.transport.sent] != [t("feishu_agent_stopped")]
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()


@pytest.mark.asyncio
async def test_interrupted_run_sends_the_generic_failure_notice(world):
    receipt = await receipt_for(world, message_id="om_interrupted")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.INTERRUPTED)
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )

    await runtime._finalize_receipt(receipt, None, await AgentRun.get(id=run.id))

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_run_failed"
    notice = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert notice.text.strip()
    await runtime.deliver_pending_for_integration(world.integration.id)
    assert (await IntegrationDelivery.get(id=notice.id)).status == "sent"


@pytest.mark.asyncio
async def test_repeated_finalization_queues_the_answer_once(world):
    receipt = await receipt_for(world, message_id="om_double_final")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        updated_at=utcnow() - timedelta(seconds=30)
    )
    terminal = await AgentRun.get(id=run.id)

    await runtime._finalize_receipt(receipt, None, terminal)
    await runtime._finalize_receipt(receipt, None, terminal)

    rows = await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).all()
    assert len(rows) == 1
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


@pytest.mark.asyncio
async def test_finalize_skips_assets_when_the_agent_row_is_gone(world, monkeypatch):
    transport, receipt, run = await _display_asset_run(
        world, monkeypatch, "om_no_agent_assets"
    )
    await Agent.filter(id=world.agent.id).delete()

    await runtime.process_pending()

    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final-asset"
    ).exists()
    assert transport.uploads == []


# --- delivery authorization --------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_authorization_needs_an_enabled_integration(world):
    receipt = await receipt_for(world)
    await Integration.filter(id=world.integration.id).update(is_enabled=False)
    assert not await runtime._delivery_authorized(receipt)
    await Integration.filter(id=world.integration.id).update(is_enabled=True)
    assert await runtime._delivery_authorized(receipt)


@pytest.mark.asyncio
async def test_delivery_authorization_rejects_a_pending_recipient(world):
    receipt = await receipt_for(world)
    await User.filter(id=world.user.id).update(approval_status="pending")
    assert not await runtime._delivery_authorized(receipt)


@pytest.mark.asyncio
async def test_delivery_authorization_allows_help_without_an_agent(world):
    receipt = await receipt_for(world, text="/help", message_id="om_help_auth")
    await FeishuAgentReceipt.filter(id=receipt.id).update(agent_id=None)
    receipt = await FeishuAgentReceipt.get(id=receipt.id)
    assert await runtime._delivery_authorized(receipt)

    await FeishuAgentReceipt.filter(id=receipt.id).update(
        text="plain words", error="feishu_agent_agent_none"
    )
    receipt = await FeishuAgentReceipt.get(id=receipt.id)
    assert await runtime._delivery_authorized(receipt)


# --- asset delivery ----------------------------------------------------------


async def _queued_asset_delivery(world, receipt, run, asset, **overrides):
    values = dict(
        provider_type="feishu",
        integration_id=receipt.integration_id,
        receipt_id=receipt.id,
        user_id=receipt.user_id,
        agent_id=receipt.agent_id,
        run_id=run.id,
        chat_id=receipt.chat_id,
        message_id=receipt.message_id,
        event_key="final-asset",
        sequence=0,
        provider_uuid=str(uuid4()),
        text=asset.display_filename,
        kind="asset",
        asset_id=asset.id,
    )
    values.update(overrides)
    return await IntegrationDelivery.create(**values)


@pytest.mark.asyncio
async def test_asset_without_a_run_cannot_be_delivered(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_asset_no_run")
    asset = await _generated_asset(world)
    delivery = await IntegrationDelivery.create(
        provider_type="feishu",
        integration_id=receipt.integration_id,
        receipt_id=receipt.id,
        user_id=receipt.user_id,
        agent_id=receipt.agent_id,
        run_id=None,
        chat_id=receipt.chat_id,
        message_id=receipt.message_id,
        event_key="final-asset",
        sequence=0,
        provider_uuid=str(uuid4()),
        text=asset.display_filename,
        kind="asset",
        asset_id=asset.id,
        status="pending",
    )

    await runtime._send_one(delivery)

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_asset_unavailable"
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_asset_without_a_user_or_agent_cannot_be_delivered(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_asset_no_user")
    await runtime.process_pending()
    run = world.submission.run
    asset = await _generated_asset(world, conversation_id=run.conversation_id)
    delivery = await _queued_asset_delivery(world, receipt, run, asset)
    # The Agent disappears before the send.
    await Agent.filter(id=receipt.agent_id).delete()

    await runtime._send_one(delivery)

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_asset_unavailable"
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_unreadable_asset_is_a_permanent_error(world, monkeypatch):
    transport, receipt, run = await _display_asset_run(
        world, monkeypatch, "om_asset_unreadable"
    )

    async def broken_read(asset):
        raise OSError("disk gone")

    monkeypatch.setattr("app.services.channel_artifacts.read_asset_bytes", broken_read)
    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_unreadable"
    assert delivery.error_detail
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_empty_asset_bytes_are_a_permanent_error(world, monkeypatch):
    transport, receipt, run = await _display_asset_run(
        world, monkeypatch, "om_asset_empty"
    )

    async def empty_read(asset):
        return b""

    monkeypatch.setattr("app.services.channel_artifacts.read_asset_bytes", empty_read)
    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_unreadable"


@pytest.mark.asyncio
async def test_cached_media_key_is_reused_without_reupload(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_asset_cached")
    await runtime.process_pending()
    run = world.submission.run
    asset = await _generated_asset(world, conversation_id=run.conversation_id)
    delivery = await _queued_asset_delivery(
        world, receipt, run, asset, media_type="image", media_key="cached-image-key"
    )

    await runtime._send_one(delivery)

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "sent"
    assert transport.uploads == []
    assert transport.media == [
        (receipt.message_id, "image", "cached-image-key", stored.provider_uuid)
    ]


@pytest.mark.asyncio
async def test_generic_upload_failure_is_a_permanent_error(world, monkeypatch):
    transport, receipt, run = await _display_asset_run(
        world, monkeypatch, "om_asset_generic_failure"
    )
    transport.upload_error = OSError("storage offline")

    await runtime.process_pending()

    delivery = await IntegrationDelivery.get(
        receipt_id=receipt.id, event_key="final-asset"
    )
    assert delivery.status == "error"
    assert delivery.error == "feishu_agent_asset_upload_failed"
    assert delivery.error_detail
    assert transport.media == []


# --- outbound sending --------------------------------------------------------


@pytest.mark.asyncio
async def test_send_one_defers_when_personal_access_is_revoked_midflight(world):
    receipt = await receipt_for(world, message_id="om_personal_midflight")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")

    import app.services.feishu_agent_preferences as preferences

    calls = {"count": 0}
    real = preferences.personal_enabled

    async def flipping(integration_id, user_id):
        calls["count"] += 1
        if calls["count"] > 1:
            return False
        return await real(integration_id, user_id)

    preferences.personal_enabled = flipping
    try:
        await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))
    finally:
        preferences.personal_enabled = real

    assert (await IntegrationDelivery.get(id=delivery.id)).status == "pending"
    assert not world.transport.sent


@pytest.mark.asyncio
async def test_send_one_marks_missing_integration_unavailable(world, monkeypatch):
    receipt = await receipt_for(world, message_id="om_integration_gone")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")

    class MissingIntegrationQuery:
        async def first(self):
            return None

    monkeypatch.setattr(
        Integration, "filter", lambda **kwargs: MissingIntegrationQuery()
    )
    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "unavailable"
    assert stored.error == "feishu_agent_channel_disabled"


@pytest.mark.asyncio
async def test_send_one_records_ambiguous_timeout_after_transmission(world):
    receipt = await receipt_for(world, message_id="om_ambiguous_cause")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")

    # A timeout after transmission is ambiguous: the reply may already have
    # reached the chat, so it must never be blind-resent.
    world.transport.error = TimeoutError("transmission timed out")

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "unknown"
    assert stored.error_detail
    assert len(world.transport.sent) == 1


@pytest.mark.asyncio
async def test_send_one_records_non_timeout_api_error(world):
    receipt = await receipt_for(world, message_id="om_api_error")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")

    from app.integrations.feishu import FeishuAPIError

    world.transport.error = FeishuAPIError("Feishu rejected the reply")

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_run_failed"
    assert stored.error_detail


@pytest.mark.asyncio
async def test_send_one_marks_a_successful_send(world):
    receipt = await receipt_for(world, message_id="om_sent_ok")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id)
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")

    await runtime._send_one(await IntegrationDelivery.get(id=delivery.id))

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "sent"
    assert stored.error is None
    assert world.transport.sent == [
        (receipt.message_id, "reply", delivery.provider_uuid)
    ]


# --- delivery sweep ----------------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_sweep_needs_receipts_for_the_integration(world):
    receipt = await receipt_for(world, message_id="om_sweep_no_rows")
    await FeishuAgentReceipt.filter(id=receipt.id).delete()
    await runtime.deliver_pending_for_integration(world.integration.id)


@pytest.mark.asyncio
async def test_delivery_sweep_stops_when_the_feature_is_gone(world):
    await receipt_for(world, message_id="om_sweep_feature_gone")
    await runtime.process_pending()
    await Integration.filter(id=world.integration.id).update(enabled_capabilities=[])

    await runtime.deliver_pending_for_integration(world.integration.id)

    assert not await IntegrationDelivery.filter(status="sending").exists()


@pytest.mark.asyncio
async def test_delivery_sweep_skips_a_row_that_lost_its_claim(world):
    receipt = await receipt_for(world, message_id="om_sweep_claimed")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="first"
    )
    await runtime._create_delivery(
        receipt, event_key="command", sequence=1, text="second"
    )
    # A row that lost its claim must not be sent twice.
    await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="command", sequence=1
    ).update(status="sending", updated_at=utcnow())

    await runtime.deliver_pending_for_integration(world.integration.id)

    rows = (
        await IntegrationDelivery.filter(receipt_id=receipt.id, event_key="command")
        .order_by("sequence")
        .all()
    )
    assert [row.status for row in rows] == ["sent", "sending"]


@pytest.mark.asyncio
async def test_delivery_sweep_resolves_a_crashed_claim_as_unknown(world):
    receipt = await receipt_for(world, message_id="om_sweep_crashed")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    await IntegrationDelivery.filter(receipt_id=receipt.id).update(
        status="sending", updated_at=utcnow() - timedelta(seconds=3600)
    )

    await runtime.deliver_pending_for_integration(world.integration.id)

    stored = await IntegrationDelivery.get(receipt_id=receipt.id)
    assert stored.status == "unknown"
    assert not world.transport.sent


@pytest.mark.asyncio
async def test_delivery_sweep_handles_a_row_without_a_recipient(world):
    receipt = await receipt_for(world, message_id="om_sweep_no_user")
    await runtime._create_delivery(
        receipt, event_key="command", sequence=0, text="reply"
    )
    # A delivery whose recipient row is gone still resolves, and the process
    # language falls back to English instead of raising.
    await IntegrationDelivery.filter(receipt_id=receipt.id).update(user_id=None)

    await runtime.deliver_pending_for_integration(world.integration.id)

    stored = await IntegrationDelivery.get(receipt_id=receipt.id)
    assert stored.status == "sent"
    assert world.transport.sent


# --- recovery bookkeeping ----------------------------------------------------


@pytest.mark.asyncio
async def test_recover_pending_discovers_integrations_from_unsent_deliveries(world):
    receipt = await receipt_for(world, message_id="om_recover_delivery")
    await runtime.process_pending()
    # The receipt is finished; only the delivery row keeps work outstanding.
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    await IntegrationDelivery.filter(receipt_id=receipt.id).update(status="pending")

    summary = await runtime.recover_pending()

    assert summary["integrations"] == 1


@pytest.mark.asyncio
async def test_process_pending_drains_deliveries_of_finished_receipts(world):
    receipt = await receipt_for(world, message_id="om_process_delivery")
    await runtime.process_pending()
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    await IntegrationDelivery.filter(receipt_id=receipt.id).update(status="pending")

    summary = await runtime.process_pending()

    assert summary["processed"] == 0
    assert not await IntegrationDelivery.filter(status="pending").exists()


@pytest.mark.asyncio
async def test_drain_keeps_a_receipt_that_keeps_failing(world, monkeypatch):
    receipt = await receipt_for(world, message_id="om_drain_keeps")
    calls = {"count": 0}

    async def exploding(receipt_row):
        calls["count"] += 1
        raise RuntimeError("temporary failure")

    monkeypatch.setattr(runtime, "_process_receipt", exploding)

    summary = await runtime._drain_chat(
        (receipt.integration_id, receipt.chat_id, receipt.user_id)
    )

    assert summary["processed"] == 1
    assert calls["count"] == 1
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "pending"

"""Feishu Agent runtime isolation, invalid input, and failure state handling.

These tests reuse the real-ORM ``world`` fixture from the runtime boundary
suite. They cover durable outcomes the existing suites do not reach yet:

* a bound Agent whose team was soft-deleted is refused, not rerouted,
* unsupported message types and unrecognized slash commands change nothing,
* a waiting run without a stored question never consumes a message, and an
  announced question becomes the answer cutoff for later messages,
* answering questions that were already collected still resumes the run,
* a lost stop race and stop on a terminal run never enqueue a second stop,
* a lost submit claim leaves the receipt recoverable instead of failing it,
* a vanished recipient fails closed with an explained receipt,
* finalization without the Agent row still delivers the no-output notice,
* completed receipts are idempotent through drag/drain and direct processing,
* the enabled channel builds a real client, capability removal mid-flight
  returns a delivery to pending, and a purged run makes an asset unavailable.
"""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.i18n import t
from app.integrations.credentials import encrypt_secret
from app.integrations.feishu import FeishuClient
from app.models.agent import Conversation
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.feishu_agent import FeishuAgentReceipt, FeishuAgentSession
from app.models.integration import Integration
from app.models.integration_delivery import IntegrationDelivery
from app.models.user import Team
from app.services import feishu_agent_runtime as runtime
from app.services.wechat_connection import utcnow
from tests.services.test_feishu_agent_runtime import (
    CHAT_ID,
    TENANT_USER_ID,
    _generated_asset,
    _use_media_transport,
    db as db,
    receipt_for,
    session_for,
    text_event,
    world as world,
)


class _MissingRowQuery:
    """A query whose row vanished between the caller's check and this read."""

    async def first(self):
        return None


async def _waiting_run(world, session, questions, *, token="call-1"):
    conversation = await Conversation.create(agent=world.agent, user=world.user)
    run = await AgentRun.create(
        id=uuid4(),
        agent_id=world.agent.id,
        conversation_id=conversation.id,
        user_id=world.user.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        pending_tool_call_id=token,
        pending_tool_name="ask_user",
        pending_tool_input={"questions": questions},
        worker_payload={"run_id": str(uuid4())},
    )
    await FeishuAgentSession.filter(id=session.id).update(active_run_id=run.id)
    return run


async def _owner_receipt(world, run, message_id="om_owner"):
    return await FeishuAgentReceipt.create(
        integration_id=world.integration.id,
        user_id=world.user.id,
        agent_id=world.agent.id,
        chat_id=CHAT_ID,
        chat_type="p2p",
        message_id=message_id,
        sender_id=TENANT_USER_ID,
        text="run owner",
        run_id=run.id,
        status="completed",
    )


async def _sending_delivery(world, receipt, text="reply"):
    await runtime._create_delivery(receipt, event_key="command", sequence=0, text=text)
    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="command")
    await IntegrationDelivery.filter(id=delivery.id).update(status="sending")
    return await IntegrationDelivery.get(id=delivery.id)


# --- delegated identity and authorization ------------------------------------


@pytest.mark.asyncio
async def test_soft_deleted_team_refuses_the_bound_agent(world):
    """A deleted team invalidates the Agent; the message is never rerouted."""
    await Team.filter(id=world.team.id).update(is_deleted=True)

    accepted = await runtime.accept_message(text_event(message_id="om_deleted_team"))

    assert accepted is None
    assert not await FeishuAgentReceipt.filter(message_id="om_deleted_team").exists()


@pytest.mark.asyncio
async def test_unsupported_message_type_is_rejected_before_identity_lookup(world):
    event = text_event(message_type="audio", message_id="om_audio")

    assert await runtime.accept_message(event) is None
    assert not await FeishuAgentReceipt.filter(message_id="om_audio").exists()


# --- invalid input -----------------------------------------------------------


@pytest.mark.asyncio
async def test_unrecognized_slash_command_is_ordinary_chat_text(world):
    receipt = await receipt_for(
        world, text="/not-a-command", message_id="om_unknown_command"
    )

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "submitted"
    assert len(world.submission.calls) == 1
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="command"
    ).exists()


@pytest.mark.asyncio
async def test_waiting_run_without_receipts_never_consumes_the_message(world):
    """No receipt owns the run, so no message can be attributed to a question."""
    receipt = await receipt_for(world, message_id="om_unbound_wait")
    session = await session_for(world)
    run = await _waiting_run(
        world,
        session,
        [{"id": "q1", "question": "Which?", "required": True}],
    )

    await runtime.process_message(str(receipt.id))

    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "pending"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING
    assert not world.submission.calls
    assert not await IntegrationDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_question_announced_on_owner_makes_newer_message_the_answer(
    world, monkeypatch
):
    """The owner receipt persists the question; a later message answers it."""
    receipt = await receipt_for(
        world, text="the answer", message_id="om_pending_answer"
    )
    session = await session_for(world)
    run = await _waiting_run(
        world,
        session,
        [{"id": "q1", "question": "Which?", "required": True}],
    )
    owner = await _owner_receipt(world, run)
    # The message arrived after the question was persisted, even though this
    # worker processes the announcement.
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        created_at=utcnow() + timedelta(seconds=5)
    )
    submitted = []

    async def fake_submit(run_id, **kwargs):
        submitted.append(kwargs)
        await AgentRun.filter(id=run_id).update(status=AgentRunStatus.QUEUED)
        return await AgentRun.get(id=run_id)

    monkeypatch.setattr("app.services.agent_run_store.submit_user_answers", fake_submit)

    await runtime.process_message(str(receipt.id))

    question = await IntegrationDelivery.get(
        receipt_id=owner.id, event_key=f"ask:{run.pending_tool_call_id}"
    )
    assert question.text
    assert submitted[0]["answers"] == {"q1": "the answer"}
    assert submitted[0]["skipped"] is False
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.QUEUED
    assert world.submission.calls == []


@pytest.mark.asyncio
async def test_waiting_run_without_questions_stays_unanswered(world):
    """A crash-left empty question set cannot consume a user message."""
    receipt = await receipt_for(world, message_id="om_empty_questions")
    session = await session_for(world)
    run = await _waiting_run(world, session, [])
    await _owner_receipt(world, run, message_id="om_empty_owner")

    await runtime.process_message(str(receipt.id))

    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "pending"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.WAITING


@pytest.mark.asyncio
async def test_already_collected_answers_are_not_asked_again(world, monkeypatch):
    """A retry message resumes with the stored answers instead of replacing them."""
    receipt = await receipt_for(world, text="retry", message_id="om_retry_answer")
    session = await session_for(world)
    run = await _waiting_run(
        world,
        session,
        [{"id": "q1", "question": "Which?", "required": True}],
    )
    await FeishuAgentSession.filter(id=session.id).update(pending_answers={"q1": "A"})
    session = await FeishuAgentSession.get(id=session.id)
    submitted = []

    async def fake_submit(run_id, **kwargs):
        submitted.append(kwargs)
        await AgentRun.filter(id=run_id).update(status=AgentRunStatus.QUEUED)
        return await AgentRun.get(id=run_id)

    monkeypatch.setattr("app.services.agent_run_store.submit_user_answers", fake_submit)

    applied = await runtime._consume_answers(receipt, session, run, text="retry")

    assert applied is True
    assert submitted[0]["answers"] == {"q1": "A"}
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"
    assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.QUEUED
    refreshed = await FeishuAgentSession.get(id=session.id)
    assert refreshed.pending_answers == {}
    assert refreshed.pending_tool_call_id is None


@pytest.mark.asyncio
async def test_malformed_question_set_is_consumed_without_a_prompt(world):
    """Corrupt stored questions must not produce a misleading required prompt."""
    receipt = await receipt_for(world, text="A", message_id="om_malformed_question")
    session = await session_for(world)
    run = await _waiting_run(
        world,
        session,
        [{"id": "q1", "required": False}],
    )

    applied = await runtime._consume_answers(receipt, session, run, text="A")

    assert applied is False
    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "completed"
    assert stored.error == "feishu_agent_answer_required"
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="answer_error"
    ).exists()
    refreshed = await FeishuAgentSession.get(id=session.id)
    assert refreshed.pending_answers == {"q1": "A"}


# --- stop state handling -----------------------------------------------------


@pytest.mark.asyncio
async def test_stop_on_a_terminal_run_only_clears_session_state(world, monkeypatch):
    import app.services.agent_run_store as store

    events = []

    async def record(*args, **kwargs):
        events.append((args, kwargs))

    monkeypatch.setattr(store, "stop_waiting_run", record)
    monkeypatch.setattr(store, "stop_queued_run", record)
    monkeypatch.setattr(store, "transition_run_if_status", record)
    monkeypatch.setattr(store, "enqueue_input", record)

    session = (
        await FeishuAgentSession.get_or_create(
            integration_id=world.integration.id,
            chat_id=CHAT_ID,
            user_id=world.user.id,
            agent_id=world.agent.id,
        )
    )[0]
    run = await _waiting_run(world, session, [])
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    run = await AgentRun.get(id=run.id)
    session = await FeishuAgentSession.get(id=session.id)

    await runtime._stop_current(session, run)

    assert events == []
    assert (await FeishuAgentSession.get(id=session.id)).active_run_id is None


@pytest.mark.asyncio
async def test_lost_stop_transition_does_not_enqueue_a_second_stop(world, monkeypatch):
    """Another worker already moved the run; this request must not duplicate it."""
    import app.services.agent_run_store as store

    events = []

    async def lost_transition(run, current, target):
        events.append(("transition", current, target))
        return None

    async def enqueue(**kwargs):
        events.append(("input", kwargs["kind"]))
        return None

    monkeypatch.setattr(store, "transition_run_if_status", lost_transition)
    monkeypatch.setattr(store, "enqueue_input", enqueue)

    session = (
        await FeishuAgentSession.get_or_create(
            integration_id=world.integration.id,
            chat_id=CHAT_ID,
            user_id=world.user.id,
            agent_id=world.agent.id,
        )
    )[0]
    run = await _waiting_run(world, session, [])
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.RUNNING)
    run = await AgentRun.get(id=run.id)
    session = await FeishuAgentSession.get(id=session.id)

    await runtime._stop_current(session, run)

    assert events == [("transition", AgentRunStatus.RUNNING, AgentRunStatus.STOPPING)]
    assert (await FeishuAgentSession.get(id=session.id)).active_run_id == run.id


# --- submission and processing failures --------------------------------------


@pytest.mark.asyncio
async def test_lost_submit_claim_keeps_receipt_recoverable(world, monkeypatch):
    """A 409 means another worker won the claim; do not fail the receipt."""
    receipt = await receipt_for(world, message_id="om_lost_claim")

    async def busy(*args, **kwargs):
        raise runtime.channel_error("feishu_agent_busy", 409)

    monkeypatch.setattr(runtime, "_submit_receipt", busy)

    await runtime.process_pending()

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "pending"
    assert stored.error is None
    assert not await IntegrationDelivery.filter(
        receipt_id=receipt.id, event_key="final"
    ).exists()


@pytest.mark.asyncio
async def test_vanished_recipient_fails_closed_with_an_explained_receipt(
    world, monkeypatch
):
    receipt = await receipt_for(world, message_id="om_missing_user")
    monkeypatch.setattr(
        runtime,
        "User",
        SimpleNamespace(filter=lambda **kwargs: _MissingRowQuery()),
    )

    await runtime._process_receipt(receipt)

    stored = await FeishuAgentReceipt.get(id=receipt.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_channel_disabled"


@pytest.mark.asyncio
async def test_completed_receipt_is_not_processed_again(world):
    receipt = await receipt_for(world, message_id="om_completed_noop")
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    receipt = await FeishuAgentReceipt.get(id=receipt.id)

    await runtime._process_receipt(receipt)

    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"
    assert not world.submission.calls
    assert not await IntegrationDelivery.filter(receipt_id=receipt.id).exists()


@pytest.mark.asyncio
async def test_drain_skips_a_receipt_resolved_after_the_snapshot(world, monkeypatch):
    receipt = await receipt_for(world, message_id="om_drain_stale")
    await FeishuAgentReceipt.filter(id=receipt.id).update(status="completed")
    stale = await FeishuAgentReceipt.get(id=receipt.id)

    async def snapshot(chat_key):
        return [stale]

    monkeypatch.setattr(runtime, "_chat_receipts", snapshot)

    summary = await runtime._drain_chat(
        (stale.integration_id, stale.chat_id, stale.user_id)
    )

    assert summary == {"processed": 0}
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


# --- terminal output ---------------------------------------------------------


@pytest.mark.asyncio
async def test_finalization_without_the_agent_still_explains_no_output(
    world, monkeypatch
):
    receipt = await receipt_for(world, message_id="om_no_agent_output")
    await runtime.process_pending()
    run = world.submission.run
    await AgentRun.filter(id=run.id).update(status=AgentRunStatus.COMPLETED)
    run = await AgentRun.get(id=run.id)
    session = await session_for(world)
    receipt = await FeishuAgentReceipt.get(id=receipt.id)

    async def authorized(row):
        return True

    monkeypatch.setattr(runtime, "_delivery_authorized", authorized)
    monkeypatch.setattr(
        runtime.Agent,
        "filter",
        lambda **kwargs: _MissingRowQuery(),
    )

    await runtime._finalize_receipt(receipt, session, run)

    delivery = await IntegrationDelivery.get(receipt_id=receipt.id, event_key="final")
    assert delivery.kind == "markdown"
    assert delivery.text == t("feishu_agent_no_output")
    assert (await FeishuAgentReceipt.get(id=receipt.id)).status == "completed"


# --- outbound channel state --------------------------------------------------


@pytest.mark.asyncio
async def test_client_for_builds_a_client_from_stored_credentials(db):
    integration = await Integration.create(
        name="feishu-enabled",
        provider_type="feishu",
        display_name="Feishu",
        is_enabled=True,
        enabled_capabilities=["agent_chat"],
        config={"app_id": "cli_configured"},
        credentials={"app_secret": encrypt_secret("real-secret")},
    )

    client = await runtime._client_for(integration)

    assert isinstance(client, FeishuClient)
    assert client.app_id == "cli_configured"
    assert client.app_secret == "real-secret"


@pytest.mark.asyncio
async def test_send_one_returns_the_row_to_pending_when_capability_is_gone(
    world,
):
    receipt = await receipt_for(world, message_id="om_capability_gone")
    delivery = await _sending_delivery(world, receipt)
    await Integration.filter(id=world.integration.id).update(enabled_capabilities=[])

    await runtime._send_one(delivery)

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "pending"
    assert not world.transport.sent


@pytest.mark.asyncio
async def test_send_one_defers_when_capability_disappears_after_claim(
    world, monkeypatch
):
    """The capability is re-read under the send path; a dropped one defers."""
    receipt = await receipt_for(world, message_id="om_capability_midflight")
    delivery = await _sending_delivery(world, receipt)
    calls = iter([{"agent_chat"}, set()])

    monkeypatch.setattr(runtime, "active_features", lambda integration: next(calls))

    await runtime._send_one(delivery)

    assert (await IntegrationDelivery.get(id=delivery.id)).status == "pending"
    assert not world.transport.sent


@pytest.mark.asyncio
async def test_asset_delivery_without_its_run_is_unavailable(world, monkeypatch):
    transport = await _use_media_transport(world, monkeypatch)
    receipt = await receipt_for(world, message_id="om_asset_purged_run")
    await runtime.process_pending()
    run = world.submission.run
    asset = await _generated_asset(world, conversation_id=run.conversation_id)
    delivery = await IntegrationDelivery.create(
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
        status="sending",
    )
    # The run row is purged after the outbox row was written.
    monkeypatch.setattr(
        runtime.AgentRun,
        "filter",
        lambda **kwargs: _MissingRowQuery(),
    )

    await runtime._send_one(delivery)

    stored = await IntegrationDelivery.get(id=delivery.id)
    assert stored.status == "error"
    assert stored.error == "feishu_agent_asset_unavailable"
    assert transport.uploads == []

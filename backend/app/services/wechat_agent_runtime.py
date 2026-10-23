"""Durable single-Agent runtime for one personal WeChat binding.

The receiver persists an immutable receipt per upstream message; this service
turns receipts into runs on the existing durable AgentRun pipeline and back
into WeChat replies.  All state lives in PostgreSQL:

* ``WeChatAgentReceipt`` maps one upstream message to one ``AgentRun``,
* ``WeChatAgentSession`` owns the conversation, the active run, the reply
  context token and the accumulated answers for a waiting ``ask_user`` call,
* ``IntegrationDelivery`` is the durable outbound queue.

Guarantees:

- a receipt is submitted at most once: the run creation, the receipt claim and
  the session pointer all commit in one transaction before the broker publish,
- a crash before publishing leaves a ``QUEUED`` run that recovery re-dispatches
  with a bounded backoff, never a receipt without a run,
- a waiting ``ask_user`` run consumes only messages created after the question
  delivery was persisted, so an already-queued message is never silently used
  as an answer,
- output is delivered only while the actor is still authorized; a revoked or
  disconnected connection records an explained ``unavailable`` delivery instead
  of pretending the reply was sent.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from tortoise.transactions import in_transaction

from app.core.i18n import set_language, t
from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.integrations.wechat import WeChatClient
from app.models.agent import Agent, Conversation
from app.models.agent_run import (
    AgentRun,
    AgentRunInputKind,
    AgentRunMode,
    AgentRunStatus,
)
from app.models.integration import Integration
from app.models.user import User
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentConfig,
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.models.wechat_knowledge import WeChatKnowledgeBinding
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError
from app.services.wechat_connection import collection_error, utcnow
from app.services.wechat_purpose import authorized_agent
from app.services.integration_features import enabled_features, require_feature

logger = logging.getLogger(__name__)

# One iteration claims a bounded batch so no binding transaction stays open
# across model calls or network sends.
MAX_BATCH = 10
# A submitted-but-unclaimed run is re-dispatched at most this often, which
# keeps a crash loop from flooding the agent queue.
REDISPATCH_BACKOFF = timedelta(seconds=10)
TERMINAL_RUN_STATUSES = (
    AgentRunStatus.COMPLETED,
    AgentRunStatus.STOPPED,
    AgentRunStatus.FAILED,
    AgentRunStatus.INTERRUPTED,
)
COMMANDS = {
    "/new": "new",
    "/新对话": "new",
    "/stop": "stop",
    "/停止": "stop",
    "/status": "status",
    "/状态": "status",
    "/help": "help",
    "/帮助": "help",
    "/skip": "skip",
    "/跳过": "skip",
    "/agents": "agents",
    "/智能体": "agents",
    "/use": "use",
    "/使用": "use",
}


def _error_key(exc: BaseException) -> str:
    if isinstance(exc, BusinessError) and exc.msg_key:
        return exc.msg_key
    return "wechat_agent_run_failed"


def _text_of(payload: dict) -> str:
    """Extract the plain user text from a decrypted upstream message."""
    parts = payload.get("item_list") or []
    texts = [
        str((part.get("text_item") or {}).get("text") or "").strip()
        for part in parts
        if part.get("type") == 1
    ]
    return "\n\n".join(value for value in texts if value)


def _split_text_chunks(text: str, *, limit: int = 3500) -> list[str]:
    """Split on UTF-8 boundaries so a chunk is never sent half-encoded."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    current = ""
    current_size = 0
    for character in text:
        size = len(character.encode("utf-8"))
        if current_size + size > limit:
            chunks.append(current)
            current, current_size = "", 0
        current += character
        current_size += size
    if current:
        chunks.append(current)
    return chunks


async def _authorized_context(
    receipt: WeChatAgentReceipt,
) -> tuple[WeChatKnowledgeBinding, User, Agent]:
    """Re-authorize every execution and every delivery attempt."""
    await require_feature("wechat", "agent_chat")
    binding = await WeChatKnowledgeBinding.filter(id=receipt.binding_id).first()
    user = await User.filter(id=receipt.user_id).first()
    if not binding or not user or binding.user_id != receipt.user_id:
        raise collection_error("wechat_agent_binding_disconnected", 403)
    if binding.status != "connected" or not binding.token:
        raise collection_error("wechat_agent_binding_disconnected", 403)
    if binding.disconnected_at and receipt.created_at <= binding.disconnected_at:
        raise collection_error("wechat_agent_binding_disconnected", 403)
    agent = await authorized_agent(receipt.agent_id, user)
    return binding, user, agent


async def _session_for(binding_id: UUID, agent_id: UUID | None):
    if not agent_id:
        return None
    return await WeChatAgentSession.filter(
        binding_id=binding_id, agent_id=agent_id
    ).first()


async def _active_run(session) -> AgentRun | None:
    if not session or not session.active_run_id:
        return None
    return await AgentRun.get_or_none(id=session.active_run_id)


async def _clear_active_run(session, run: AgentRun | None) -> None:
    """Clear the session pointer only once the run is really terminal."""
    if run is None or run.status not in TERMINAL_RUN_STATUSES:
        return
    if session.active_run_id == run.id:
        await WeChatAgentSession.filter(id=session.id).update(active_run_id=None)
        session.active_run_id = None


async def _create_delivery(
    receipt: WeChatAgentReceipt,
    *,
    event_key: str,
    sequence: int,
    payload: dict[str, Any],
    status: str = "pending",
    error: str | None = None,
) -> None:
    integration = await Integration.get_or_none(provider_type="wechat")
    kind = str(payload.get("kind") or "text")
    asset_id = payload.get("asset_id")
    await IntegrationDelivery.get_or_create(
        provider_type="wechat",
        receipt_id=receipt.id,
        event_key=event_key,
        sequence=sequence,
        defaults={
            "integration_id": integration.id if integration is not None else None,
            "user_id": receipt.user_id,
            "agent_id": receipt.agent_id,
            "run_id": receipt.run_id,
            "chat_id": str(receipt.binding_id),
            "message_id": receipt.message_id,
            "kind": kind,
            "text": str(payload.get("text") or ""),
            "payload": payload,
            "asset_id": UUID(asset_id) if asset_id else None,
            "filename": payload.get("filename"),
            "content_type": payload.get("content_type"),
            "size": payload.get("size"),
            "status": status,
            "error": error,
        },
    )


def _question_text(question: dict, index: int, total: int) -> str:
    lines = []
    if total > 1:
        lines.append(f"[{index}/{total}]")
    lines.append(str(question.get("question") or "").strip())
    options = question.get("options")
    if options:
        lines.append(" / ".join(str(option) for option in options))
    return "\n".join(line for line in lines if line).strip()


async def _announce_questions(
    receipt: WeChatAgentReceipt,
    run: AgentRun,
    *,
    answered: dict[str, Any],
) -> None:
    """Persist the question delivery; its created_at is the answer cutoff."""
    questions = (run.pending_tool_input or {}).get("questions") or []
    event_key = f"ask:{run.pending_tool_call_id}"
    if await IntegrationDelivery.filter(
        provider_type="wechat", receipt_id=receipt.id, event_key=event_key
    ).exists():
        return
    total = len(questions)
    lines = []
    for index, question in enumerate(questions, start=1):
        if str(question.get("id") or "") in answered:
            continue
        lines.append(_question_text(question, index, total))
    done = sum(1 for question in questions if str(question.get("id")) in answered)
    text = "\n\n".join(line for line in lines if line)
    if done:
        notice = t("wechat_agent_questions_partial", done=done, total=total)
        text = f"{notice}\n\n{text}" if text else notice
    for sequence, chunk in enumerate(_split_text_chunks(text)):
        await _create_delivery(
            receipt,
            event_key=event_key,
            sequence=sequence,
            payload={"kind": "text", "text": chunk},
        )


async def _answer_cutoff(run: AgentRun):
    """Only messages created after the question delivery may answer it."""
    receipt_ids = await WeChatAgentReceipt.filter(run_id=run.id).values_list(
        "id", flat=True
    )
    if not receipt_ids:
        return None
    delivery = (
        await IntegrationDelivery.filter(
            provider_type="wechat",
            receipt_id__in=list(receipt_ids),
            event_key=f"ask:{run.pending_tool_call_id}",
        )
        .order_by("sequence")
        .first()
    )
    return delivery.created_at if delivery else None


def _command_of(text: str) -> str | None:
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    if parts and parts[0] in ("/use", "/使用"):
        return "use"
    return COMMANDS.get(stripped)


async def _stop_current(session, run: AgentRun | None) -> None:
    """Stop the current run and cancel its queued ordinary receipts."""
    from app.services.agent_run_store import (
        enqueue_input,
        stop_queued_run,
        stop_waiting_run,
        transition_run_if_status,
    )

    if run is not None:
        if run.status == AgentRunStatus.WAITING:
            run = await stop_waiting_run(run.id) or run
        elif run.status == AgentRunStatus.QUEUED:
            run = await stop_queued_run(run.id) or run
        elif run.status in (AgentRunStatus.RUNNING, AgentRunStatus.STOPPING):
            if run.status == AgentRunStatus.RUNNING:
                run = (
                    await transition_run_if_status(
                        run, AgentRunStatus.RUNNING, AgentRunStatus.STOPPING
                    )
                    or run
                )
            if run.status == AgentRunStatus.STOPPING:
                await enqueue_input(run_id=run.id, kind=AgentRunInputKind.STOP)
    await WeChatAgentReceipt.filter(
        binding_id=session.binding_id,
        agent_id=session.agent_id,
        status="pending",
    ).update(status="error", error="wechat_agent_stopped", updated_at=utcnow())
    # A cooperative stop keeps the run pointer until the run is really
    # terminal, so a racing message cannot start a second run.
    await _clear_active_run(session, run)
    session.pending_answers = {}
    session.pending_tool_call_id = None
    await session.save(
        update_fields=["pending_answers", "pending_tool_call_id", "updated_at"]
    )


async def _reset_session(session) -> None:
    """Apply a new-conversation reset once the previous run is terminal."""
    await WeChatAgentSession.filter(id=session.id).update(
        conversation_id=None,
        active_run_id=None,
        pending_answers={},
        pending_tool_call_id=None,
        updated_at=utcnow(),
    )
    session.conversation_id = None
    session.active_run_id = None
    session.pending_answers = {}
    session.pending_tool_call_id = None


async def _ensure_conversation(session, agent: Agent, user: User) -> None:
    if session.conversation_id:
        return
    conversation = await Conversation.create(agent=agent, user=user)
    await WeChatAgentSession.filter(id=session.id).update(
        conversation_id=conversation.id
    )
    session.conversation_id = conversation.id


async def _reply_text(
    receipt: WeChatAgentReceipt, text: str, *, key: str = "command"
) -> None:
    for sequence, chunk in enumerate(_split_text_chunks(text)):
        await _create_delivery(
            receipt,
            event_key=key,
            sequence=sequence,
            payload={"kind": "text", "text": chunk},
        )


async def _agent_selection_command(receipt: WeChatAgentReceipt, command: str) -> None:
    """Commit a routing choice and its reply together; never rebind a receipt."""
    from app.services.wechat_purpose import (
        available_agents,
        check_switch_idle,
        resolve_variables,
    )
    from app.services.audit_log import AuditLogService

    user = await User.get(id=receipt.user_id)
    agents = await available_agents(user)
    if command == "agents":
        lines = [t("wechat_agent_agents_header")]
        lines.extend(
            f"{index}. {agent.name} · {agent.team.name}"
            for index, agent in enumerate(agents, start=1)
        )
        lines.append(t("wechat_agent_agents_footer"))
        await _reply_text(
            receipt, "\n".join(lines) if agents else t("wechat_agent_no_agents")
        )
        await _consume(receipt)
        return

    text = _text_of(json.loads(decrypt_secret(receipt.payload)))
    parts = text.split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else ""
    selected = None
    if argument.isascii() and argument.isdigit():
        index = int(argument)
        if 1 <= index <= len(agents):
            selected = agents[index - 1]
    else:
        selected = next((agent for agent in agents if str(agent.id) == argument), None)
    if selected is None:
        await _reply_text(
            receipt,
            t("wechat_agent_use_invalid" if argument else "wechat_agent_use_missing"),
        )
        await _consume(receipt)
        return

    changed = False
    async with in_transaction() as db:
        binding = (
            await WeChatKnowledgeBinding.filter(id=receipt.binding_id)
            .using_db(db)
            .select_for_update()
            .get()
        )
        current = await WeChatAgentReceipt.filter(id=receipt.id).using_db(db).first()
        if current is None or current.status != "pending":
            return
        # Recheck ownership, authorization and availability after taking the
        # same row lock used by web configuration and inbound snapshots.
        _, user, _ = await _authorized_context(receipt)
        selected = await authorized_agent(selected.id, user)
        if binding.purpose != "agent":
            raise collection_error("wechat_agent_config_missing")
        config = (
            await WeChatAgentConfig.filter(binding_id=binding.id).using_db(db).first()
        )
        if config and config.agent_id == selected.id:
            reply = t("wechat_agent_use_current", agent=selected.name)
        else:
            try:
                await check_switch_idle(binding.id, exclude_receipt_id=receipt.id)
                variables = resolve_variables(selected, {})
            except BusinessError as exc:
                reply = t(
                    "wechat_agent_use_variables"
                    if exc.msg_key == "wechat_agent_variables_invalid"
                    else exc.msg_key
                )
            else:
                await WeChatAgentConfig.update_or_create(
                    binding_id=binding.id,
                    defaults={
                        "agent_id": selected.id,
                        "variables": variables,
                        "stt_model_id": None,
                    },
                    using_db=db,
                )
                binding.generation = uuid4()
                await binding.save(
                    using_db=db, update_fields=["generation", "updated_at"]
                )
                reply = t("wechat_agent_use_selected", agent=selected.name)
                changed = True
        await _reply_text(receipt, reply)
        await _consume(receipt)
    if changed:
        await AuditLogService.log(
            user=user,
            action="update_wechat_binding",
            resource_type="wechat_binding",
            resource_id=receipt.binding_id,
            resource_name=None,
            operation="update",
            status="success",
            metadata={
                "purpose": "agent",
                "agent_id": str(selected.id),
                "source": "wechat_command",
            },
        )


async def _apply_command(
    receipt: WeChatAgentReceipt, session, run: AgentRun | None, command: str
) -> bool:
    """Deterministic command handling; commands preempt queued messages."""
    if command in ("agents", "use"):
        await _agent_selection_command(receipt, command)
        return True
    if command == "help":
        await _reply_text(receipt, t("wechat_agent_help"))
    elif command == "status":
        if run is None:
            status = t("run_status_idle")
        else:
            status = t(f"run_status_{run.status.value}")
        await _reply_text(receipt, t("wechat_agent_status", status=status))
    elif command == "skip":
        if run is None or run.status != AgentRunStatus.WAITING:
            return False
        from app.services.agent_run_store import submit_user_answers

        resumed = await submit_user_answers(
            run.id,
            tool_call_id=run.pending_tool_call_id,
            answers={},
            skipped=True,
        )
        if resumed is not None:
            session.pending_answers = {}
            session.pending_tool_call_id = None
            await session.save(
                update_fields=[
                    "pending_answers",
                    "pending_tool_call_id",
                    "updated_at",
                ]
            )
            await WeChatAgentReceipt.filter(id=receipt.id).update(
                status="completed", error=None, updated_at=utcnow()
            )
            await _resume_run(resumed)
            return True
        return False
    elif command == "stop":
        await _stop_current(session, run)
        await _reply_text(receipt, t("wechat_agent_stopped"))
    elif command == "new":
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            await _reply_text(receipt, t("wechat_agent_busy"), key="busy")
            return False
        await _reset_session(session)
        await _reply_text(receipt, t("wechat_agent_new_conversation"))
    else:
        return False
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        status="completed", error=None, updated_at=utcnow()
    )
    return True


async def _resume_run(run: AgentRun) -> None:
    """Re-dispatch a resumed waiting run with its stored payload."""
    from app.services.agent_submission import dispatch_run

    payload = run.worker_payload
    if not isinstance(payload, dict):
        raise RuntimeError("run resume payload is missing")
    await dispatch_run(payload, run)


async def _submit_receipt(
    receipt: WeChatAgentReceipt,
    session,
    agent: Agent,
    user: User,
    binding: WeChatKnowledgeBinding,
    *,
    prepared: ChatRequest,
) -> None:
    """Create the run, claim the receipt, then publish.

    The binding row is locked for the whole transaction so a concurrent purpose
    switch cannot interleave, and the receipt claim, the run row and the
    session pointer commit together.  The broker publish happens only after
    that commit.
    """
    from app.services.agent_submission import submit_chat_run

    async with in_transaction() as db:
        locked = (
            await WeChatKnowledgeBinding.filter(id=binding.id)
            .using_db(db)
            .select_for_update()
            .first()
        )
        # Re-validate under the lock: the caller authorized the receipt before
        # normalizing its attachments, and a disconnect or purpose switch may
        # have landed in between.
        if (
            not locked
            or locked.status != "connected"
            or not locked.token
            or locked.user_id != receipt.user_id
            or (locked.disconnected_at and receipt.created_at <= locked.disconnected_at)
        ):
            raise collection_error("wechat_agent_binding_disconnected", 403)
        agent = await authorized_agent(receipt.agent_id, user)
        await require_feature("wechat", "agent_chat")
        submission = await submit_chat_run(
            agent.id,
            prepared,
            user,
            mode=AgentRunMode.SEND,
            conversation_id=session.conversation_id,
            defer_dispatch=True,
        )
        claimed = (
            await WeChatAgentReceipt.filter(id=receipt.id, status="pending")
            .using_db(db)
            .update(
                status="submitted",
                run_id=submission.run_id,
                prepared=submission.prepared.model_dump(mode="json"),
                error=None,
                updated_at=utcnow(),
            )
        )
        if not claimed:
            raise collection_error("wechat_agent_busy", 409)
        batch_ids = (
            json.loads(decrypt_secret(receipt.payload)).get("batch_receipt_ids") or []
        )
        if batch_ids:
            await (
                WeChatAgentReceipt.filter(
                    id__in=batch_ids,
                    binding_id=receipt.binding_id,
                    agent_id=receipt.agent_id,
                    status="merged",
                )
                .using_db(db)
                .update(run_id=submission.run_id)
            )
        await (
            WeChatAgentSession.filter(id=session.id)
            .using_db(db)
            .update(active_run_id=submission.run_id)
        )
        session.active_run_id = submission.run_id
    await _dispatch_or_defer(receipt, submission.run, initial=True)


async def _dispatch_or_defer(
    receipt: WeChatAgentReceipt, run: AgentRun, *, initial: bool = False
) -> None:
    """Publish after the receipt mapping committed; recovery repeats safely."""
    from app.services.agent_submission import dispatch_run

    if run.status != AgentRunStatus.QUEUED:
        return
    if (
        not initial
        and receipt.updated_at
        and utcnow() - receipt.updated_at < REDISPATCH_BACKOFF
    ):
        return
    try:
        await dispatch_run(run.worker_payload, run)
        await WeChatAgentReceipt.filter(id=receipt.id).update(updated_at=utcnow())
    except Exception:
        logger.warning("WeChat agent dispatch failed for run %s", run.id)
        await WeChatAgentReceipt.filter(id=receipt.id, status="submitted").update(
            error="wechat_agent_run_failed", updated_at=utcnow()
        )


async def _consume_answers(
    receipt: WeChatAgentReceipt,
    session,
    run: AgentRun,
    *,
    text: str,
) -> bool:
    """Feed one new user message into the waiting question set."""
    from app.services.agent_run_store import submit_user_answers, validate_user_answers

    questions = (run.pending_tool_input or {}).get("questions") or []
    pending_answers = dict(session.pending_answers or {})
    for question in questions:
        question_id = str(question.get("id") or "")
        if question_id in pending_answers:
            continue
        options = question.get("options")
        if options and text.strip() not in [str(option) for option in options]:
            await _reply_text(
                receipt,
                t(
                    "wechat_agent_answer_invalid_choice",
                    options=" / ".join(str(option) for option in options),
                ),
                key="answer_error",
            )
            # The message was consumed: recovery must not replay it as the
            # answer to a different question.
            await _consume(receipt, error="wechat_agent_answer_invalid_choice")
            return False
        pending_answers[question_id] = text.strip()
        break
    try:
        validate_user_answers(run.pending_tool_input, pending_answers)
    except ValueError:
        required = next(
            (
                question
                for question in questions
                if str(question.get("id")) not in pending_answers
                and question.get("required", True)
            ),
            None,
        )
        if required is not None:
            await _reply_text(
                receipt,
                t(
                    "wechat_agent_answer_required",
                    question=str(required.get("question") or "").strip(),
                ),
                key="answer_error",
            )
        session.pending_answers = pending_answers
        await session.save(update_fields=["pending_answers", "updated_at"])
        await _consume(receipt, error="wechat_agent_answer_required")
        return False
    resumed = await submit_user_answers(
        run.id,
        tool_call_id=run.pending_tool_call_id,
        answers=pending_answers,
        skipped=False,
    )
    if resumed is None:
        await _consume(receipt, error="wechat_agent_run_failed")
        return False
    session.pending_answers = {}
    session.pending_tool_call_id = None
    await session.save(
        update_fields=["pending_answers", "pending_tool_call_id", "updated_at"]
    )
    await _consume(receipt)
    await _resume_run(resumed)
    return True


async def _consume(receipt: WeChatAgentReceipt, *, error: str | None = None) -> None:
    """Mark one inbound message consumed so recovery never replays it."""
    await WeChatAgentReceipt.filter(id=receipt.id).update(
        status="completed", error=error, updated_at=utcnow()
    )


async def _finalize_receipt(
    receipt: WeChatAgentReceipt, session, run: AgentRun
) -> None:
    """Commit receipt completion and its outbox atomically, or retry both."""
    async with in_transaction():
        await _finalize_receipt_output(receipt, session, run)


async def _finalize_receipt_output(
    receipt: WeChatAgentReceipt, session, run: AgentRun
) -> None:
    """Map a terminal run to its outbound delivery rows inside the transaction."""
    from app.models.user import User
    from app.services.wechat_agent_io import build_output

    # Resolve the recipient locale before any localized text is produced. The
    # failure and unavailable branches emit text without the full
    # authorization path, so the process-context language may still belong to
    # an unrelated earlier receipt.
    recipient = await User.filter(id=receipt.user_id).first()
    set_language(getattr(recipient, "locale", None) or "en")

    if run.status == AgentRunStatus.STOPPED:
        # The stop command already told the user; never imply a reply was sent.
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="completed", error="wechat_agent_stopped", updated_at=utcnow()
        )
        await _clear_active_run(session, run)
        return
    if run.status in (AgentRunStatus.FAILED, AgentRunStatus.INTERRUPTED):
        # A lost or failed worker produced no trustworthy canonical output, so
        # only the generic localized failure is sent, never a partial result.
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="error", error="wechat_agent_run_failed", updated_at=utcnow()
        )
        await _reply_text(receipt, t("wechat_agent_run_failed"), key="final")
        await _clear_active_run(session, run)
        return
    try:
        _, user, _ = await _authorized_context(receipt)
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            return
        key = exc.msg_key or "wechat_agent_binding_disconnected"
        # The run finished, but the reply must never look like it was sent.
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="completed", error=key, updated_at=utcnow()
        )
        await _create_delivery(
            receipt,
            event_key="final",
            sequence=0,
            payload={"kind": "text", "text": t(key)},
            status="unavailable",
            error=key,
        )
        await _clear_active_run(session, run)
        return
    if not session.context_token:
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="completed",
            error="wechat_agent_context_missing",
            updated_at=utcnow(),
        )
        await _create_delivery(
            receipt,
            event_key="final",
            sequence=0,
            payload={
                "kind": "text",
                "text": t("wechat_agent_context_missing"),
            },
            status="unavailable",
            error="wechat_agent_context_missing",
        )
        await _clear_active_run(session, run)
        return
    payloads = await build_output(run, receipt, session, user)
    # Claim finalization once: two recovery passes can observe the same
    # terminal run, and without this claim both would append the same outbox
    # rows. A duplicate event key would also re-send the answer.
    claimed = await WeChatAgentReceipt.filter(id=receipt.id, status="submitted").update(
        status="completed", error=None, updated_at=utcnow()
    )
    if not claimed:
        await _clear_active_run(session, run)
        return
    if not payloads:
        # A completed run with no visible content still owes the user an
        # explicit answer instead of an empty outbox.
        await _reply_text(receipt, t("wechat_agent_no_output"), key="final")
    for sequence, payload in enumerate(payloads):
        await _create_delivery(
            receipt, event_key="final", sequence=sequence, payload=payload
        )
    await _clear_active_run(session, run)


async def _process_submitted(
    receipt: WeChatAgentReceipt, session, run: AgentRun
) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        await _finalize_receipt(receipt, session, run)
        return
    if run.status == AgentRunStatus.WAITING:
        # Announce (idempotently); answers arrive as separate new receipts.
        await _announce_questions(receipt, run, answered=session.pending_answers or {})
        return
    await _dispatch_or_defer(receipt, run)


async def _process_pending(
    receipt: WeChatAgentReceipt,
    binding: WeChatKnowledgeBinding,
    session,
    run: AgentRun | None,
) -> None:
    payload = json.loads(decrypt_secret(receipt.payload))
    text = _text_of(payload)
    context_token = str(payload.get("context_token") or "")
    if context_token and session.context_token != encrypt_secret(context_token):
        session.context_token = encrypt_secret(context_token)
        session.last_context_at = utcnow()
        await session.save(
            update_fields=["context_token", "last_context_at", "updated_at"]
        )

    try:
        binding, user, agent = await _authorized_context(receipt)
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            return
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="error",
            error=exc.msg_key or "wechat_agent_binding_disconnected",
            updated_at=utcnow(),
        )
        return
    set_language(getattr(user, "locale", None) or "en")

    if text:
        command = _command_of(text)
        if command:
            if command in ("agents", "use"):
                # Control replies need the ordinary authorized delivery context
                # even when no normal chat message has created a conversation.
                await _ensure_conversation(session, agent, user)
            applied = await _apply_command(receipt, session, run, command)
            if applied or (
                command == "skip"
                and run is not None
                and run.status == AgentRunStatus.WAITING
            ):
                return

    if run is not None and run.status == AgentRunStatus.WAITING:
        if not text:
            # Media cannot answer a structured question; consume it with an
            # explicit explanation instead of leaving it pending forever.
            await _reply_text(
                receipt,
                t("wechat_agent_media_unsupported"),
                key="answer_error",
            )
            await _consume(receipt, error="wechat_agent_media_unsupported")
            return
        cutoff = await _answer_cutoff(run)
        if cutoff is None:
            # The structured question has not been persisted yet, so no message
            # can be attributed to it. Persist it on the receipt that owns the
            # run, then compare this message against that timestamp.
            owner = await WeChatAgentReceipt.filter(run_id=run.id).first()
            if owner is None:
                return
            await _announce_questions(
                owner, run, answered=session.pending_answers or {}
            )
            cutoff = await _answer_cutoff(run)
            if cutoff is None:
                return
        if receipt.created_at <= cutoff:
            return
        await _consume_answers(receipt, session, run, text=text)
        return

    if run is not None and run.status not in TERMINAL_RUN_STATUSES:
        if not await IntegrationDelivery.filter(
            provider_type="wechat", receipt_id=receipt.id, event_key="busy"
        ).exists():
            await _reply_text(receipt, t("wechat_agent_busy"), key="busy")
        return

    await _ensure_conversation(session, agent, user)
    # Persist and send before downloads, transcription or model submission.
    # The durable event key prevents a recovery pass from acknowledging twice.
    if not await IntegrationDelivery.filter(
        provider_type="wechat", receipt_id=receipt.id, event_key="busy"
    ).exists():
        await _reply_text(receipt, t("wechat_agent_received"), key="received")
        await _deliver(binding, user)
    from app.services.wechat_agent_io import normalize_input

    try:
        async with WeChatClient(
            binding.base_url, decrypt_secret(binding.token)
        ) as client:
            prepared = await normalize_input(receipt, session, agent, user, client)
    except BusinessError as exc:
        key = exc.msg_key or "wechat_agent_media_unsupported"
        # Unsupported input must still reach the phone as an explicit,
        # localized explanation; it is never silently dropped.
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="error", error=key, updated_at=utcnow()
        )
        await _reply_text(receipt, t(key), key="final")
        return
    except Exception:
        # A provider/CDN failure is not a permanent input rejection, but the
        # message must not sit pending forever without any explanation.
        logger.exception("WeChat agent input preparation failed for %s", receipt.id)
        await WeChatAgentReceipt.filter(id=receipt.id).update(
            status="error", error="wechat_agent_media_failed", updated_at=utcnow()
        )
        await _reply_text(receipt, t("wechat_agent_media_failed"), key="final")
        return
    try:
        await _submit_receipt(receipt, session, agent, user, binding, prepared=prepared)
    except BusinessError:
        logger.warning("WeChat agent submission busy for %s", receipt.id)
    except Exception as exc:
        logger.warning("WeChat agent submission failed for %s", receipt.id)
        await WeChatAgentReceipt.filter(id=receipt.id, status="pending").update(
            error=_error_key(exc), updated_at=utcnow()
        )


async def _process_receipt(receipt: WeChatAgentReceipt, binding) -> None:
    """Advance one receipt through command, answer, submit or finalize."""
    config = await WeChatAgentConfig.filter(binding_id=binding.id).first()
    if "agent_chat" not in await enabled_features("wechat"):
        return
    if not config or not config.agent_id:
        if receipt.status == "pending":
            await WeChatAgentReceipt.filter(id=receipt.id).update(
                status="error",
                error="wechat_agent_config_missing",
                updated_at=utcnow(),
            )
        return
    session = await _session_for(binding.id, receipt.agent_id)
    if session is None:
        session = await WeChatAgentSession.create(
            binding_id=binding.id, agent_id=receipt.agent_id
        )
    run = await _active_run(session)

    if receipt.status == "submitted":
        # Prefer the receipt's own run: the session pointer is cleared as soon
        # as the run is terminal, and a stale in-memory run must never decide
        # whether this receipt is finished.
        if receipt.run_id:
            run = await AgentRun.get_or_none(id=receipt.run_id)
        if run is None:
            await WeChatAgentReceipt.filter(id=receipt.id).update(
                status="error",
                error="wechat_agent_run_failed",
                updated_at=utcnow(),
            )
            return
        await _process_submitted(receipt, session, run)
        return

    if receipt.status == "pending":
        await _process_pending(receipt, binding, session, run)


async def _deliver(binding, user) -> None:
    """Advance the durable outbox; each row re-checks its own authorization.

    Rows that can no longer be sent are resolved as ``unavailable`` by the IO
    layer instead of being left pending forever.
    """
    from app.services.wechat_agent_io import deliver_pending

    if user is None:
        return
    await deliver_pending(binding, user)


async def process_binding(binding_id: str) -> dict:
    """Advance every ready receipt for one binding; called under the binding lock."""
    if "agent_chat" not in await enabled_features("wechat"):
        return {"pending": True, "processed": 0}
    binding = await WeChatKnowledgeBinding.filter(id=binding_id).first()
    if binding is None:
        return {"pending": False, "processed": 0}

    fresh = list(
        await WeChatAgentReceipt.filter(binding_id=binding.id, status="pending")
        .order_by("created_at")
        .limit(MAX_BATCH)
    )
    # Submitted receipts are polled every pass: a terminal run must surface its
    # answer within one Beat interval. Re-publishing a still-queued run is what
    # the backoff in ``_dispatch_or_defer`` throttles.
    submitted = list(
        await WeChatAgentReceipt.filter(binding_id=binding.id, status="submitted")
        .order_by("created_at")
        .limit(MAX_BATCH)
    )
    # Advance in true arrival order: an announcement for an earlier message
    # must be persisted before a later message can be judged as answering it.
    ordered = sorted([*fresh, *submitted], key=lambda row: (row.created_at, row.id))
    for receipt in ordered:
        try:
            await _process_receipt(receipt, binding)
        except Exception:
            logger.exception(
                "WeChat agent receipt %s failed; it stays recoverable", receipt.id
            )
    remaining = await WeChatAgentReceipt.filter(
        binding_id=binding.id, status__in=["pending", "submitted"]
    ).count()
    user = await User.filter(id=binding.user_id).first()
    await _deliver(binding, user)
    return {
        "pending": remaining > 0,
        "processed": len(ordered),
    }

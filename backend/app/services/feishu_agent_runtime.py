"""Durable multi-Agent runtime for Feishu private chats.

Feishu is a transport: this service turns one accepted Feishu message into one
durable Clouisle AgentRun on the shared submission pipeline and back into a
Feishu reply.  Clouisle stays the only Agent runtime — there is no second tool
loop, memory or conversation history here.

Durable state (PostgreSQL is the truth, never Redis/SSE):

* ``FeishuAgentReceipt`` is created by authenticated transport intake and is
  immutable afterwards: the accepted message, the
  resolved actor, the selected Agent and (once submitted) its run.  A replayed
  provider event hits the unique ``(integration, message_id)`` constraint and
  is dropped, so one message can never create two runs.
* ``FeishuAgentSession`` maps ``(integration, chat, user, agent)`` to one
  Clouisle conversation, the active run and the accumulated ``ask_user``
  answers.  A receipt keeps the Agent it was accepted with even if the user
  switches Agents afterwards.
* ``IntegrationDelivery`` is the outbound queue.  Each row carries a
  deterministic provider ``uuid`` so a retry after a crash is deduplicated by
  Feishu instead of reaching the chat twice, and a send whose outcome is
  unknown is never blind-resent.

Guarantees:

- authorization is re-checked before every submit and before every send;
  a revoked user or a deconfigured Agent produces an explained delivery
  record, never a silent success,
- the run, the receipt claim and the session pointer commit in one
  transaction before the broker publish; a crash before publishing leaves a
  ``QUEUED`` run that recovery re-dispatches with a bounded backoff,
- a waiting ``ask_user`` run consumes only messages created after the
  question delivery was persisted, so an already-queued message is never
  silently used as an answer.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core.i18n import set_language, t
from app.models.agent import Agent, AgentStatus, Conversation
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.feishu_agent import (
    FeishuAgentPreference,
    FeishuAgentReceipt,
    FeishuAgentSession,
)
from app.models.integration_delivery import IntegrationDelivery
from app.models.integration import Integration
from app.models.user import User
from app.schemas.response import BusinessError
from app.services.integration_features import active_features
from app.services.message_split import split_message_text

logger = logging.getLogger(__name__)

# One sweep claims a bounded batch so no transaction stays open across model
# calls or network sends.
MAX_BATCH = 10
# A submitted-but-unclaimed run is re-dispatched at most this often, which
# keeps a crash loop from flooding the agent queue.
REDISPATCH_BACKOFF = timedelta(seconds=10)
# A claimed send is retried only after this lease expires; the row is resolved
# as ``unknown`` instead of being resent blind.
SEND_LEASE_SECONDS = 600
TERMINAL_RUN_STATUSES = (
    AgentRunStatus.COMPLETED,
    AgentRunStatus.STOPPED,
    AgentRunStatus.FAILED,
    AgentRunStatus.INTERRUPTED,
)
# Feishu rejects text messages longer than this; split on UTF-8 boundaries so a
# chunk is never sent half-encoded.
TEXT_CHUNK_LIMIT = 3500
# Provider-side dedup ids are capped at 50 characters.
UUID_LIMIT = 50
COMMANDS = {
    "/agents": "agents",
    "/智能体": "agents",
    "/use": "use",
    "/使用": "use",
    "/new": "new",
    "/新对话": "new",
    "/status": "status",
    "/状态": "status",
    "/stop": "stop",
    "/停止": "stop",
    "/help": "help",
    "/帮助": "help",
}


def utcnow():
    from app.services.wechat_connection import utcnow as _utcnow

    return _utcnow()


def channel_error(key: str, status: int = 400) -> BusinessError:
    from app.schemas.response import ResponseCode

    return BusinessError(
        code=ResponseCode.VALIDATION_ERROR, msg_key=key, status_code=status
    )


def _error_key(exc: BaseException) -> str:
    if isinstance(exc, BusinessError) and exc.msg_key:
        return exc.msg_key
    return "feishu_agent_run_failed"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _event_text(event: dict) -> str:
    """Plain text of a decrypted ``im.message.receive_v1`` message body."""
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return ""
    if not isinstance(content, dict):
        return ""
    text = content.get("text")
    return _text(text)


def _split_text_chunks(text: str, *, limit: int = TEXT_CHUNK_LIMIT) -> list[str]:
    return split_message_text(text, limit=limit)


def _delivery_uuid(receipt_id: UUID, event_key: str, sequence: int) -> str:
    """Deterministic provider dedup key; retries can never duplicate a reply."""
    digest = hashlib.sha256(f"{receipt_id}:{event_key}:{sequence}".encode()).hexdigest()
    return digest[:UUID_LIMIT]


# --- inbound validation ------------------------------------------------------


def _sender_ids(event: dict) -> list[tuple[str, str]]:
    """Candidate identities, preferring a mapped tenant id over SSO subject."""
    sender = event.get("sender")
    if not isinstance(sender, dict) or _text(sender.get("sender_type")) == "app":
        return []
    sender_id = sender.get("sender_id")
    if not isinstance(sender_id, dict):
        return []
    identifiers: list[tuple[str, str]] = []
    for namespace, field in (
        ("user_id", "user_id"),
        ("subject", "union_id"),
        ("subject", "open_id"),
    ):
        identifier = _text(sender_id.get(field))
        pair = (namespace, identifier)
        if identifier and pair not in identifiers:
            identifiers.append(pair)
    return identifiers


async def _resolve_integration(app_id: str) -> Integration | None:
    if not app_id:
        return None
    # The app id lives inside a JSON column, so the match is made in Python:
    # there is exactly one enabled Feishu integration per deployment.
    for integration in await Integration.filter(provider_type="feishu"):
        if "agent_chat" not in active_features(integration):
            continue
        if _text((integration.config or {}).get("app_id")) != app_id:
            continue
        return integration
    return None


async def _resolve_user(
    integration: Integration, namespace: str, identifier: str
) -> User | None:
    """Map the Feishu sender to a real, usable local account.

    A tenant ``user_id`` resolves through the directory-sync mapping; an SSO
    subject (``union_id`` else ``open_id``) resolves through the SSO connection
    of this integration.  Each identifier space is only probed against its own
    table, and email is never used for matching.
    """
    from app.models.feishu_user import FeishuUser
    from app.models.user_sso_connection import UserSSOConnection

    if namespace == "user_id":
        user_id = await FeishuUser.filter(feishu_user_id=identifier).values_list(
            "user_id", flat=True
        )
    else:
        user_id = await UserSSOConnection.filter(
            integration_id=integration.id, provider_user_id=identifier
        ).values_list("user_id", flat=True)
    if not user_id:
        return None
    user = await User.filter(id=user_id[0]).first()
    if user is None or not user.is_active:
        return None
    if getattr(user, "approval_status", "approved") != "approved":
        return None
    return user


async def _authorized_agent(agent_id: UUID, user: User) -> Agent:
    """The same authorization the web chat endpoint applies."""
    from app.api.v1.endpoints.chat import check_agent_chat_access

    agent = await check_agent_chat_access(agent_id, user)
    if agent.status != AgentStatus.PUBLISHED:
        raise channel_error("feishu_agent_agent_unavailable", 403)
    if not agent.team or agent.team.is_deleted:
        raise channel_error("feishu_agent_agent_unavailable", 403)
    return agent


async def _selectable_agents(integration: Integration, user: User) -> list[Agent]:
    """Published Agents accessible to this user, independent of administrators."""
    from app.services.feishu_agent_preferences import available_agents

    return await available_agents(user)


async def _session_agent(
    session: FeishuAgentSession | None, integration: Integration, user: User
) -> Agent | None:
    """The Agent a session is bound to, if it is still usable."""
    if session is None or not session.agent_id:
        return None
    try:
        return await _authorized_agent(session.agent_id, user)
    except BusinessError:
        return None


async def accept_message(event: dict) -> str | None:
    """Persist one validated inbound message; ``None`` means "not accepted".

    The transport authenticates the event envelope. A shared per-chat lock
    serializes selection updates and receipt creation across API, receiver and
    Celery processes, so a message after ``/use`` snapshots the new Agent.
    """
    if not isinstance(event, dict):
        return None
    senders = _sender_ids(event)
    message = event.get("message")
    if not senders or not isinstance(message, dict):
        return None
    if _text(message.get("message_type")) not in ("text", "file", "image", "post"):
        return None
    if _text(message.get("chat_type")) != "p2p":
        return None
    message_id = _text(message.get("message_id"))
    chat_id = _text(message.get("chat_id"))
    if not message_id or not chat_id:
        return None
    from app.services.feishu_agent_input import parse_message

    text, attachments = parse_message(message)
    if not text and not attachments:
        return None
    integration = await _resolve_integration(_text(event.get("app_id")))
    if integration is None:
        return None
    user = None
    resolved_sender_id = ""
    for namespace, identifier in senders:
        user = await _resolve_user(integration, namespace, identifier)
        if user is not None:
            resolved_sender_id = identifier
            break
    if user is None:
        return None
    command = _command_of(text)

    from app.services.feishu_agent_locks import chat_lock

    # Settings and /use serialize on the same actor lock before the chat lock.
    async with (
        chat_lock(integration.id, "", user.id),
        chat_lock(integration.id, chat_id, user.id),
    ):
        try:
            async with in_transaction() as db:
                replay = (
                    await FeishuAgentReceipt.filter(
                        integration_id=integration.id, message_id=message_id
                    )
                    .using_db(db)
                    .first()
                )
                if replay is not None:
                    return None
                preference = (
                    await FeishuAgentPreference.filter(
                        integration_id=integration.id, user_id=user.id
                    )
                    .using_db(db)
                    .first()
                )
                if preference is None or not preference.is_enabled:
                    return None
                selected_id = preference.agent_id if preference else None
                target = None
                if command is not None and command[0] == "use":
                    target = await _resolve_use_argument(command[1], integration, user)
                if selected_id is not None:
                    try:
                        await _authorized_agent(selected_id, user)
                    except BusinessError:
                        if command is None:
                            return None
                        selected_id = None
                receipt_agent_id = selected_id
                if target is not None:
                    from app.services.feishu_agent_preferences import set_preference

                    await set_preference(integration, user, target.id, db=db)
                    if receipt_agent_id is None:
                        receipt_agent_id = target.id
                if receipt_agent_id is not None:
                    await FeishuAgentSession.get_or_create(
                        integration_id=integration.id,
                        chat_id=chat_id,
                        user_id=user.id,
                        agent_id=receipt_agent_id,
                        using_db=db,
                    )
                if target is not None and target.id != receipt_agent_id:
                    await FeishuAgentSession.get_or_create(
                        integration_id=integration.id,
                        chat_id=chat_id,
                        user_id=user.id,
                        agent_id=target.id,
                        using_db=db,
                    )
                receipt = await FeishuAgentReceipt.create(
                    integration_id=integration.id,
                    user_id=user.id,
                    agent_id=receipt_agent_id,
                    chat_id=chat_id,
                    chat_type=_text(message.get("chat_type")) or "p2p",
                    message_id=message_id,
                    sender_id=resolved_sender_id,
                    text=text,
                    attachments=attachments,
                    using_db=db,
                )
        except Exception:
            # Replays are handled under the chat lock above. A failed write
            # must remain a failure so the long connection can request redelivery.
            logger.exception("Feishu receipt %s could not be committed", message_id)
            raise
    return str(receipt.id)


# --- processing --------------------------------------------------------------


async def _session_for(
    integration_id: UUID, chat_id: str, user_id: UUID, agent_id: UUID | None
) -> FeishuAgentSession | None:
    if not agent_id:
        return None
    return await FeishuAgentSession.filter(
        integration_id=integration_id,
        chat_id=chat_id,
        user_id=user_id,
        agent_id=agent_id,
    ).first()


async def _active_run(session: FeishuAgentSession | None) -> AgentRun | None:
    if session is None or not session.active_run_id:
        return None
    return await AgentRun.get_or_none(id=session.active_run_id)


async def _clear_active_run(
    session: FeishuAgentSession | None, run: AgentRun | None
) -> None:
    """Clear the session pointer only once the run is really terminal."""
    if session is None or run is None or run.status not in TERMINAL_RUN_STATUSES:
        return
    if session.active_run_id == run.id:
        await FeishuAgentSession.filter(id=session.id).update(active_run_id=None)
        session.active_run_id = None


async def _create_delivery(
    receipt: FeishuAgentReceipt,
    *,
    event_key: str,
    sequence: int,
    text: str = "",
    status: str = "pending",
    error: str | None = None,
    kind: str = "text",
    asset=None,
) -> None:
    """Idempotent outbound row; its deterministic uuid dedups the provider."""
    await IntegrationDelivery.get_or_create(
        provider_type="feishu",
        receipt_id=receipt.id,
        event_key=event_key,
        sequence=sequence,
        defaults={
            "integration_id": receipt.integration_id,
            "user_id": receipt.user_id,
            "agent_id": receipt.agent_id,
            "run_id": receipt.run_id,
            "chat_id": receipt.chat_id,
            "message_id": receipt.message_id,
            "provider_uuid": _delivery_uuid(receipt.id, event_key, sequence),
            "text": text,
            "kind": kind,
            "asset_id": asset.id if asset is not None else None,
            "filename": asset.display_filename if asset is not None else None,
            "content_type": asset.content_type if asset is not None else None,
            "size": asset.size if asset is not None else None,
            "status": status,
            "error": error,
        },
    )


async def _reply_text(
    receipt: FeishuAgentReceipt, text: str, *, key: str = "command"
) -> None:
    for sequence, chunk in enumerate(_split_text_chunks(text)):
        await _create_delivery(receipt, event_key=key, sequence=sequence, text=chunk)


async def _consume(receipt: FeishuAgentReceipt, *, error: str | None = None) -> None:
    """Mark one inbound message consumed so recovery never replays it."""
    await FeishuAgentReceipt.filter(id=receipt.id).update(
        status="completed", error=error, updated_at=utcnow()
    )


async def _announce_questions(
    receipt: FeishuAgentReceipt,
    run: AgentRun,
    *,
    answered: dict[str, Any],
) -> None:
    """Persist the question delivery; its created_at is the answer cutoff."""
    questions = (run.pending_tool_input or {}).get("questions") or []
    event_key = f"ask:{run.pending_tool_call_id}"
    if await IntegrationDelivery.filter(
        provider_type="feishu",
        receipt_id=receipt.id,
        event_key=event_key,
        status="sent",
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
        notice = t("feishu_agent_questions_partial", done=done, total=total)
        text = f"{notice}\n\n{text}" if text else notice
    for sequence, chunk in enumerate(_split_text_chunks(text)):
        await _create_delivery(
            receipt, event_key=event_key, sequence=sequence, text=chunk
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


async def _answer_cutoff(run: AgentRun) -> Any:
    """Only messages created after the question delivery may answer it."""
    receipt_ids = await FeishuAgentReceipt.filter(run_id=run.id).values_list(
        "id", flat=True
    )
    if not receipt_ids:
        return None
    delivery = (
        await IntegrationDelivery.filter(
            provider_type="feishu",
            receipt_id__in=list(receipt_ids),
            event_key=f"ask:{run.pending_tool_call_id}",
        )
        .order_by("sequence")
        .first()
    )
    return delivery.created_at if delivery else None


def _command_of(text: str) -> tuple[str, str] | None:
    """``(command, argument)`` for a recognized command, else ``None``."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split(maxsplit=1)
    command = COMMANDS.get(parts[0].lower())
    if command is None:
        return None
    return command, (parts[1].strip() if len(parts) > 1 else "")


async def _agents_text(agents: list[Agent]) -> str:
    if not agents:
        return t("feishu_agent_no_agents")
    lines = [t("feishu_agent_agents_header")]
    for index, agent in enumerate(agents, start=1):
        lines.append(f"{index}. {agent.name}")
    lines.append(t("feishu_agent_agents_footer"))
    return "\n".join(lines)


async def _status_text(
    session: FeishuAgentSession | None,
    agent: Agent | None,
    run: AgentRun | None,
) -> str:
    agent_name = agent.name if agent is not None else t("feishu_agent_agent_none")
    status = (
        t("run_status_idle") if run is None else t(f"run_status_{run.status.value}")
    )
    return t("feishu_agent_status", agent=agent_name, status=status)


async def _stop_current(
    session: FeishuAgentSession | None, run: AgentRun | None
) -> None:
    """Stop the current run and cancel its queued receipts."""
    from app.services.agent_run_store import (
        enqueue_input,
        stop_queued_run,
        stop_waiting_run,
        transition_run_if_status,
    )
    from app.models.agent_run import AgentRunInputKind

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
    if session is not None:
        await FeishuAgentReceipt.filter(
            integration_id=session.integration_id,
            chat_id=session.chat_id,
            user_id=session.user_id,
            agent_id=session.agent_id,
            status="pending",
        ).update(status="error", error="feishu_agent_stopped", updated_at=utcnow())
        # A cooperative stop keeps the run pointer until the run is really
        # terminal, so a racing message cannot start a second run.
        await _clear_active_run(session, run)
        session.pending_answers = {}
        session.pending_tool_call_id = None
        await session.save(
            update_fields=["pending_answers", "pending_tool_call_id", "updated_at"]
        )


async def _reset_session(session: FeishuAgentSession) -> None:
    """Apply a new-conversation reset once the previous run is terminal."""
    await FeishuAgentSession.filter(id=session.id).update(
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


async def _ensure_conversation(
    session: FeishuAgentSession, agent: Agent, user: User
) -> None:
    if session.conversation_id:
        return
    conversation = await Conversation.create(agent=agent, user=user)
    await FeishuAgentSession.filter(id=session.id).update(
        conversation_id=conversation.id
    )
    session.conversation_id = conversation.id


async def _apply_command(
    receipt: FeishuAgentReceipt,
    session: FeishuAgentSession | None,
    agent: Agent | None,
    run: AgentRun | None,
    command: str,
    argument: str,
    integration: Integration,
    user: User,
) -> tuple[bool, FeishuAgentSession | None]:
    """Deterministic command handling; commands preempt queued messages.

    Returns ``(applied, session)`` where the session is the (possibly newly
    created or rebound) session the caller should keep using.
    """
    if command == "help":
        await _reply_text(receipt, t("feishu_agent_help"))
    elif command == "agents":
        await _reply_text(
            receipt, await _agents_text(await _selectable_agents(integration, user))
        )
    elif command == "use":
        if not argument:
            await _reply_text(receipt, t("feishu_agent_use_missing"), key="command")
            await _consume(receipt)
            return True, session
        selected = await _resolve_use_argument(argument, integration, user)
        if selected is None:
            await _reply_text(receipt, t("feishu_agent_use_invalid"), key="command")
            await _consume(receipt)
            return True, session
        if session is not None and session.agent_id == selected.id:
            await _reply_text(
                receipt,
                t("feishu_agent_use_current", agent=selected.name),
                key="command",
            )
            await _consume(receipt)
            return True, session
        await _reply_text(
            receipt, t("feishu_agent_use_selected", agent=selected.name), key="command"
        )
    elif command == "status":
        await _reply_text(receipt, await _status_text(session, agent, run))
    elif command == "stop":
        await _stop_current(session, run)
        await _reply_text(receipt, t("feishu_agent_stopped"))
    elif command == "new":
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            await _reply_text(receipt, t("feishu_agent_busy"), key="busy")
            return False, session
        if session is not None:
            await _reset_session(session)
        await _reply_text(receipt, t("feishu_agent_new_conversation"))
    else:
        return False, session
    await _consume(receipt)
    return True, session


async def _resolve_use_argument(
    argument: str, integration: Integration, user: User
) -> Agent | None:
    """Accept a 1-based list index or an exact configured Agent id."""
    agents = await _selectable_agents(integration, user)
    if argument.isdigit():
        index = int(argument)
        if 1 <= index <= len(agents):
            return agents[index - 1]
        return None
    try:
        identifier = UUID(argument)
    except ValueError:
        return None
    for agent in agents:
        if agent.id == identifier:
            return agent
    return None


async def _select_session(
    receipt: FeishuAgentReceipt, selected: Agent
) -> FeishuAgentSession:
    """Select the session row for the chosen Agent, creating it on first use.

    Each Agent keeps its own row, so switching away and back restores that
    Agent's conversation and run state instead of discarding it.
    """
    session, _ = await FeishuAgentSession.get_or_create(
        integration_id=receipt.integration_id,
        chat_id=receipt.chat_id,
        user_id=receipt.user_id,
        agent_id=selected.id,
    )
    return session


async def _resume_run(run: AgentRun) -> None:
    """Re-dispatch a resumed waiting run with its stored payload."""
    from app.services.agent_submission import dispatch_run

    payload = run.worker_payload
    if not isinstance(payload, dict):
        raise RuntimeError("run resume payload is missing")
    await dispatch_run(payload, run)


async def _consume_answers(
    receipt: FeishuAgentReceipt,
    session: FeishuAgentSession,
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
                    "feishu_agent_answer_invalid_choice",
                    options=" / ".join(str(option) for option in options),
                ),
                key="answer_error",
            )
            # The message was consumed: recovery must not replay it as the
            # answer to a different question.
            await _consume(receipt, error="feishu_agent_answer_invalid_choice")
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
                    "feishu_agent_answer_required",
                    question=str(required.get("question") or "").strip(),
                ),
                key="answer_error",
            )
        session.pending_answers = pending_answers
        await session.save(update_fields=["pending_answers", "updated_at"])
        await _consume(receipt, error="feishu_agent_answer_required")
        return False
    resumed = await submit_user_answers(
        run.id,
        tool_call_id=run.pending_tool_call_id,
        answers=pending_answers,
        skipped=False,
    )
    if resumed is None:
        await _consume(receipt, error="feishu_agent_run_failed")
        return False
    session.pending_answers = {}
    session.pending_tool_call_id = None
    await session.save(
        update_fields=["pending_answers", "pending_tool_call_id", "updated_at"]
    )
    await _consume(receipt)
    await _resume_run(resumed)
    return True


async def _dispatch_or_defer(receipt: FeishuAgentReceipt, run: AgentRun) -> None:
    """Publish after the receipt mapping committed; recovery repeats safely."""
    from app.services.agent_submission import dispatch_run

    if run.status != AgentRunStatus.QUEUED:
        return
    if receipt.updated_at and utcnow() - receipt.updated_at < REDISPATCH_BACKOFF:
        return
    try:
        await dispatch_run(run.worker_payload, run)
        await FeishuAgentReceipt.filter(id=receipt.id).update(updated_at=utcnow())
    except Exception:
        logger.warning("Feishu agent dispatch failed for run %s", run.id)
        await FeishuAgentReceipt.filter(id=receipt.id, status="submitted").update(
            error="feishu_agent_run_failed", updated_at=utcnow()
        )


async def _submit_receipt(
    receipt: FeishuAgentReceipt,
    session: FeishuAgentSession,
    agent: Agent,
    user: User,
) -> None:
    """Create the run, claim the receipt, then publish.

    The session row is locked for the whole transaction so a concurrent Agent
    switch or ``/new`` cannot interleave, and the receipt claim, the run row and
    the session pointer commit together.  The broker publish happens only after
    that commit.
    """
    from app.services.agent_submission import submit_chat_run
    from app.models.agent_run import AgentRunMode

    from app.services.feishu_agent_input import prepare_input

    integration = await Integration.get(id=receipt.integration_id)
    prepared = await prepare_input(
        receipt, session, agent, user, await _client_for(integration)
    )

    async with in_transaction() as db:
        locked = (
            await FeishuAgentSession.filter(id=session.id)
            .using_db(db)
            .select_for_update()
            .first()
        )
        # Re-validate under the lock: the caller authorized the receipt before
        # this transaction, and a switch may have landed in between.
        if locked is None or locked.agent_id != session.agent_id:
            raise channel_error("feishu_agent_agent_unavailable", 409)
        integration = (
            await Integration.filter(id=receipt.integration_id).using_db(db).first()
        )
        if "agent_chat" not in active_features(integration):
            raise channel_error("feishu_agent_channel_disabled", 403)
        submission = await submit_chat_run(
            session.agent_id,
            prepared,
            user,
            mode=AgentRunMode.SEND,
            conversation_id=locked.conversation_id,
            defer_dispatch=True,
        )
        claimed = (
            await FeishuAgentReceipt.filter(id=receipt.id, status="pending")
            .using_db(db)
            .update(
                status="submitted",
                run_id=submission.run_id,
                error=None,
                updated_at=utcnow(),
            )
        )
        if not claimed:
            raise channel_error("feishu_agent_busy", 409)
        await (
            FeishuAgentSession.filter(id=session.id)
            .using_db(db)
            .update(active_run_id=submission.run_id)
        )
        session.active_run_id = submission.run_id
    await _dispatch_or_defer(receipt, submission.run)


async def _finalize_receipt(
    receipt: FeishuAgentReceipt,
    session: FeishuAgentSession | None,
    run: AgentRun,
) -> None:
    """Map a terminal run to its outbound delivery rows."""
    # Resolve the recipient locale before any localized text is produced: the
    # failure branch emits text without the full authorization path, so the
    # process-context language may still belong to an unrelated message.
    recipient = await User.filter(id=receipt.user_id).first()
    set_language(getattr(recipient, "locale", None) or "en")

    if run.status == AgentRunStatus.STOPPED:
        # The stop command already told the user; never imply a reply was sent.
        await _consume(receipt, error="feishu_agent_stopped")
        await _clear_active_run(session, run)
        return
    if run.status in (AgentRunStatus.FAILED, AgentRunStatus.INTERRUPTED):
        # A lost or failed worker produced no trustworthy canonical output, so
        # only the generic localized failure is sent, never a partial result.
        await FeishuAgentReceipt.filter(id=receipt.id).update(
            status="error", error="feishu_agent_run_failed", updated_at=utcnow()
        )
        await _reply_text(receipt, t("feishu_agent_run_failed"), key="final")
        await _clear_active_run(session, run)
        return
    if not await _delivery_authorized(receipt):
        # The run finished, but the reply must never look like it was sent.
        key = "feishu_agent_channel_disabled"
        await _consume(receipt, error=key)
        await _create_delivery(
            receipt,
            event_key="final",
            sequence=0,
            text=t(key),
            status="unavailable",
            error=key,
        )
        await _clear_active_run(session, run)
        return
    chunks = await _canonical_chunks(run)
    # Claim finalization once: two recovery passes can observe the same
    # terminal run, and without this claim both would append the same outbox
    # rows. A duplicate event key would also re-send the answer.
    claimed = await FeishuAgentReceipt.filter(id=receipt.id, status="submitted").update(
        status="completed", error=None, updated_at=utcnow()
    )
    if not claimed:
        await _clear_active_run(session, run)
        return
    assets: list = []
    agent = await Agent.filter(id=run.agent_id).first()
    if agent is not None:
        from app.services.channel_artifacts import resolve_run_assets

        assets = await resolve_run_assets(run, agent, recipient)
    if not chunks and not assets:
        # A completed run with no visible content still owes the user an
        # explicit answer instead of an empty outbox.
        await _reply_text(receipt, t("feishu_agent_no_output"), key="final")
    for sequence, chunk in enumerate(chunks):
        await _create_delivery(
            receipt,
            event_key="final",
            sequence=sequence,
            text=chunk,
            kind="markdown",
        )
    for sequence, asset in enumerate(assets):
        await _create_delivery(
            receipt,
            event_key="final-asset",
            sequence=sequence,
            text=asset.display_filename,
            kind="asset",
            asset=asset,
        )
    await _clear_active_run(session, run)


async def _delivery_authorized(receipt: FeishuAgentReceipt) -> bool:
    """Re-authorize this receipt's bound Agent before sending its reply."""
    integration = await Integration.filter(id=receipt.integration_id).first()
    if integration is None or not integration.is_enabled:
        return False
    user = await User.filter(id=receipt.user_id).first()
    if user is None or not user.is_active:
        return False
    if getattr(user, "approval_status", "approved") != "approved":
        return False
    if receipt.agent_id is None:
        # Configuration/help notices contain no Agent output.
        return (
            _command_of(receipt.text) is not None
            or receipt.error == "feishu_agent_agent_none"
        )
    try:
        await _authorized_agent(receipt.agent_id, user)
    except BusinessError:
        return False
    return True


async def _canonical_chunks(run: AgentRun) -> list[str]:
    """The run's canonical assistant output, split for Feishu."""
    from app.models.agent import Message

    if not run.canonical_message_id:
        return []
    canonical = await Message.get_or_none(id=run.canonical_message_id)
    if canonical is None or canonical.conversation_id != run.conversation_id:
        # A foreign or detached message is never this run's visible output.
        return []
    text = (canonical.content or "").strip() if canonical else ""
    return _split_text_chunks(text)


async def _process_submitted(
    receipt: FeishuAgentReceipt,
    session: FeishuAgentSession | None,
    run: AgentRun,
) -> None:
    if run.status in TERMINAL_RUN_STATUSES:
        await _finalize_receipt(receipt, session, run)
        return
    if run.status == AgentRunStatus.WAITING:
        # Announce (idempotently); answers arrive as separate new receipts.
        await _announce_questions(
            receipt, run, answered=(session.pending_answers if session else {}) or {}
        )
        return
    await _dispatch_or_defer(receipt, run)


async def _process_pending(
    receipt: FeishuAgentReceipt,
    integration: Integration,
    user: User,
    session: FeishuAgentSession | None,
    run: AgentRun | None,
) -> None:
    set_language(getattr(user, "locale", None) or "en")
    command = _command_of(receipt.text)
    if receipt.agent_id is None:
        if command is not None:
            applied, _ = await _apply_command(
                receipt, None, None, None, command[0], command[1], integration, user
            )
            if applied:
                return
        await _reply_text(receipt, t("feishu_agent_help"), key="configuration")
        await _consume(receipt, error="feishu_agent_agent_none")
        return
    if session is None:
        # The receipt already carries the Agent it was bound to at acceptance;
        # create that Agent's session row for this chat and user.
        session, _ = await FeishuAgentSession.get_or_create(
            integration_id=integration.id,
            chat_id=receipt.chat_id,
            user_id=receipt.user_id,
            agent_id=receipt.agent_id,
        )
    agent = await _session_agent(session, integration, user)
    if agent is None:
        # The bound Agent is no longer usable; the message is explained rather
        # than silently rerouted to a different Agent.
        await FeishuAgentReceipt.filter(id=receipt.id).update(
            status="error",
            error="feishu_agent_agent_unavailable",
            updated_at=utcnow(),
        )
        return
    command = _command_of(receipt.text)
    if command is not None:
        applied, session = await _apply_command(
            receipt, session, agent, run, command[0], command[1], integration, user
        )
        if applied:
            return
        # A refused command falls through to the ordinary message path.
    if run is not None and run.status == AgentRunStatus.WAITING:
        if session is None:
            return
        if receipt.attachments:
            await _reply_text(
                receipt, t("feishu_agent_answer_text_required"), key="answer_error"
            )
            await _consume(receipt, error="feishu_agent_answer_text_required")
            return
        cutoff = await _answer_cutoff(run)
        if cutoff is None:
            # The structured question has not been persisted yet, so no message
            # can be attributed to it. Persist it on the receipt that owns the
            # run, then compare this message against that timestamp.
            owner = await FeishuAgentReceipt.filter(run_id=run.id).first()
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
        await _consume_answers(receipt, session, run, text=receipt.text)
        return

    if run is not None and run.status not in TERMINAL_RUN_STATUSES:
        if not await IntegrationDelivery.filter(
            provider_type="feishu", receipt_id=receipt.id, event_key="busy"
        ).exists():
            await _reply_text(receipt, t("feishu_agent_busy"), key="busy")
        return

    await _ensure_conversation(session, agent, user)
    # Persist progress before submission. Delivery runs outside the chat lock
    # so provider latency cannot prevent durable intake of the next message.
    progress_key = f"received:{receipt.id}"
    if not await IntegrationDelivery.filter(
        provider_type="feishu", receipt_id=receipt.id, event_key=progress_key
    ).exists():
        await _reply_text(receipt, t("feishu_agent_received"), key=progress_key)
    try:
        await _submit_receipt(receipt, session, agent, user)
    except BusinessError as exc:
        if exc.status_code == 409:
            return
        await FeishuAgentReceipt.filter(id=receipt.id, status="pending").update(
            status="error", error=_error_key(exc), updated_at=utcnow()
        )
        await _reply_text(receipt, t(_error_key(exc)), key="final")
    except Exception as exc:
        logger.exception("Feishu agent submission failed for %s", receipt.id)
        if receipt.attachments:
            await FeishuAgentReceipt.filter(id=receipt.id, status="pending").update(
                status="error", error="feishu_agent_media_failed", updated_at=utcnow()
            )
            await _reply_text(receipt, t("feishu_agent_media_failed"), key="final")
        else:
            await FeishuAgentReceipt.filter(id=receipt.id, status="pending").update(
                error=_error_key(exc), updated_at=utcnow()
            )


async def _process_receipt(receipt: FeishuAgentReceipt) -> None:
    """Advance one receipt through command, answer, submit or finalize."""
    integration = await Integration.filter(id=receipt.integration_id).first()
    user = await User.filter(id=receipt.user_id).first()
    if integration is None or user is None:
        await FeishuAgentReceipt.filter(id=receipt.id, status="pending").update(
            status="error", error="feishu_agent_channel_disabled", updated_at=utcnow()
        )
        return
    if "agent_chat" not in active_features(integration):
        return
    from app.services.feishu_agent_preferences import personal_enabled

    if not await personal_enabled(receipt.integration_id, receipt.user_id):
        return
    # The session is resolved strictly by the agent the receipt was bound to at
    # acceptance, never by chat alone: a /use that landed after this message was
    # accepted must not reroute it to another Agent's conversation.
    session = await _session_for(
        receipt.integration_id, receipt.chat_id, receipt.user_id, receipt.agent_id
    )
    run = await _active_run(session)

    if receipt.status == "submitted":
        # Prefer the receipt's own run: the session pointer is cleared as soon
        # as the run is terminal, and a stale in-memory run must never decide
        # whether this receipt is finished.
        if receipt.run_id:
            run = await AgentRun.get_or_none(id=receipt.run_id)
        if run is None:
            await FeishuAgentReceipt.filter(id=receipt.id).update(
                status="error",
                error="feishu_agent_run_failed",
                updated_at=utcnow(),
            )
            return
        await _process_submitted(receipt, session, run)
        return

    if receipt.status == "pending":
        await _process_pending(receipt, integration, user, session, run)


async def _chat_receipts(chat_key: tuple[UUID, str, UUID]) -> list[FeishuAgentReceipt]:
    """Unfinished receipts for one chat, in true arrival order."""
    integration_id, chat_id, user_id = chat_key
    rows = await FeishuAgentReceipt.filter(
        integration_id=integration_id,
        chat_id=chat_id,
        user_id=user_id,
        status__in=["pending", "submitted"],
    ).order_by("created_at", "id")
    return list(rows)


async def _drain_chat(chat_key: tuple[UUID, str, UUID]) -> dict:
    """Process every unfinished receipt of one chat in arrival order.

    A ``/use`` and the message that follows it are two independent Celery
    tasks, so their relative order is not guaranteed.  Draining the chat queue
    in ``created_at`` order makes the selection visible to every later message
    while keeping chats independent: a slow chat never blocks another chat, and
    a late task simply finds its own receipt already processed.
    """
    processed = 0
    for receipt in await _chat_receipts(chat_key):
        if receipt.status not in ("pending", "submitted"):
            continue
        processed += 1
        try:
            await _process_receipt(receipt)
        except Exception:
            logger.exception(
                "Feishu agent receipt %s failed; it stays recoverable", receipt.id
            )
    return {"processed": processed}


async def process_message(receipt_id: str) -> dict:
    """Advance ready receipts for one external chat in arrival order."""
    receipt = await FeishuAgentReceipt.filter(id=receipt_id).first()
    if receipt is None:
        return {"processed": 0, "status": "not_found"}
    from app.services.feishu_agent_locks import chat_lock

    chat_key = (receipt.integration_id, receipt.chat_id, receipt.user_id)
    async with chat_lock(*chat_key):
        summary = await _drain_chat(chat_key)
    await deliver_pending_for_integration(receipt.integration_id)
    refreshed = await FeishuAgentReceipt.filter(id=receipt.id).first()
    return {
        "processed": summary["processed"],
        "status": refreshed.status if refreshed else "not_found",
    }


async def process_pending() -> dict:
    """Advance every ready receipt; the recovery task calls this."""
    fresh = list(
        await FeishuAgentReceipt.filter(status="pending")
        .order_by("created_at")
        .limit(MAX_BATCH)
    )
    submitted = list(
        await FeishuAgentReceipt.filter(status="submitted")
        .order_by("created_at")
        .limit(MAX_BATCH)
    )
    ordered = sorted([*fresh, *submitted], key=lambda row: (row.created_at, row.id))
    processed = 0
    chats: dict[tuple[UUID, str, UUID], None] = {}
    for receipt in ordered:
        chats[(receipt.integration_id, receipt.chat_id, receipt.user_id)] = None
    from app.services.feishu_agent_locks import chat_lock

    for key in chats:
        async with chat_lock(*key):
            summary = await _drain_chat(key)
            processed += summary["processed"]
    drained = {row.integration_id for row in ordered}
    unsent_receipt_ids = (
        await IntegrationDelivery.filter(
            Q(status="pending") | Q(status="sending"), provider_type="feishu"
        )
        .order_by("created_at")
        .limit(100)
        .values_list("receipt_id", flat=True)
    )
    if unsent_receipt_ids:
        drained.update(
            await FeishuAgentReceipt.filter(
                id__in=list(unsent_receipt_ids)
            ).values_list("integration_id", flat=True)
        )
    for integration_id in drained:
        await deliver_pending_for_integration(integration_id)
    return {"processed": processed}


async def recover_pending() -> dict:
    """Queue work that survived a crash or a cold start.

    An unsent delivery can outlive its receipt (the receipt completes as soon
    as its answer is queued), so delivery work is discovered from the delivery
    rows themselves and never inferred from unfinished receipts.
    """
    identifiers = set(
        await FeishuAgentReceipt.filter(status__in=["pending", "submitted"])
        .order_by("created_at")
        .limit(100)
        .values_list("integration_id", flat=True)
    )
    delivery_receipt_ids = (
        await IntegrationDelivery.filter(
            Q(status="pending") | Q(status="sending"), provider_type="feishu"
        )
        .order_by("created_at")
        .limit(100)
        .values_list("receipt_id", flat=True)
    )
    if delivery_receipt_ids:
        identifiers.update(
            await FeishuAgentReceipt.filter(
                id__in=list(delivery_receipt_ids)
            ).values_list("integration_id", flat=True)
        )
    return {"integrations": len(identifiers)}


# --- outbound delivery -------------------------------------------------------


async def _client_for(integration: Integration):
    """Build the provider client for one enabled integration."""
    from app.integrations.feishu import FeishuClient

    app_id = _text((integration.config or {}).get("app_id"))
    encrypted_secret = _text((integration.credentials or {}).get("app_secret"))
    if not app_id or not encrypted_secret:
        raise channel_error("feishu_agent_channel_disabled", 503)
    return FeishuClient(app_id, encrypted_secret)


async def _send_one(delivery: IntegrationDelivery) -> None:
    """Send one claimed row; every failure mode is recorded, never guessed."""
    receipt = await FeishuAgentReceipt.filter(id=delivery.receipt_id).first()
    if receipt is None:
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="unavailable", error="feishu_agent_channel_disabled"
        )
        return
    from app.services.feishu_agent_preferences import personal_enabled

    if not await personal_enabled(receipt.integration_id, receipt.user_id):
        await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
            status="pending"
        )
        return
    integration = await Integration.filter(id=receipt.integration_id).first()
    if integration is not None and "agent_chat" not in active_features(integration):
        await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
            status="pending"
        )
        return
    if integration is None or not integration.is_enabled:
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="unavailable", error="feishu_agent_channel_disabled"
        )
        return
    try:
        client = await _client_for(integration)
        current = await Integration.filter(id=receipt.integration_id).first()
        if current is not None and "agent_chat" not in active_features(current):
            await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
                status="pending"
            )
            return
        if not await personal_enabled(receipt.integration_id, receipt.user_id):
            await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
                status="pending"
            )
            return
        if delivery.kind == "asset":
            status, error, detail = await _send_asset(client, delivery, receipt)
            if status != "sent":
                await IntegrationDelivery.filter(id=delivery.id).update(
                    status=status, error=error, error_detail=detail, updated_at=utcnow()
                )
                return
        else:
            reply = (
                client.reply_markdown
                if delivery.kind == "markdown"
                else client.reply_text
            )
            await reply(receipt.message_id, delivery.text, uuid=delivery.provider_uuid)
    except ValueError as exc:
        from app.services.delivery_errors import error_detail

        # Rejected parameters can never succeed on a retry.
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="error",
            error=_error_key(exc),
            error_detail=error_detail(exc),
            updated_at=utcnow(),
        )
        return
    except Exception as exc:
        import asyncio

        from app.integrations.feishu import FeishuAPIError

        cause = getattr(exc, "__cause__", None)
        # A timeout after transmission is ambiguous: never blind-resend.
        ambiguous = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
        if isinstance(exc, FeishuAPIError) and (
            isinstance(cause, TimeoutError)
            or cause.__class__.__name__ == "TimeoutException"
        ):
            ambiguous = True
        from app.services.delivery_errors import error_detail

        detail = error_detail(exc)
        if ambiguous:
            await IntegrationDelivery.filter(id=delivery.id).update(
                status="unknown", error_detail=detail, updated_at=utcnow()
            )
            return
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="error",
            error=_error_key(exc),
            error_detail=detail,
            updated_at=utcnow(),
        )
        return
    await IntegrationDelivery.filter(id=delivery.id).update(
        status="sent", error=None, error_detail=None, updated_at=utcnow()
    )


IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "image/tiff",
        "image/heic",
    }
)
FEISHU_FILE_SUBTYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
}


def _asset_media_type(content_type: str) -> str:
    """Feishu-native image and MP4 video; every other Asset is a file."""
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in IMAGE_CONTENT_TYPES:
        return "image"
    if normalized == "video/mp4":
        return "media"
    return "file"


async def _send_asset(
    client, delivery: IntegrationDelivery, receipt
) -> tuple[str, str | None, str | None]:
    """Upload once, remember the provider key, then reply with it.

    Upload failures happen before any message reaches the chat, so they are
    permanent delivery errors rather than ambiguous sends. Only the reply
    propagates its timeout to the caller, which marks the row ``unknown``.
    """
    from app.services.channel_artifacts import (
        authorize_output_asset,
        read_asset_bytes,
    )
    from app.services.delivery_errors import error_detail

    if delivery.asset_id is None or receipt.run_id is None or receipt.agent_id is None:
        return "error", "feishu_agent_asset_unavailable", None
    run = await AgentRun.filter(id=receipt.run_id).first()
    user = await User.filter(id=receipt.user_id).first()
    agent = await Agent.filter(id=receipt.agent_id).first()
    if run is None or user is None or agent is None or run.conversation_id is None:
        return "error", "feishu_agent_asset_unavailable", None
    asset = await authorize_output_asset(
        delivery.asset_id,
        conversation_id=run.conversation_id,
        agent=agent,
        user=user,
    )
    if asset is None:
        return "error", "feishu_agent_asset_unavailable", None
    try:
        content = await read_asset_bytes(asset)
    except Exception as exc:
        logger.warning(
            "Failed to read Feishu delivery asset %s", delivery.asset_id, exc_info=True
        )
        return "error", "feishu_agent_asset_unreadable", error_detail(exc)
    if not content:
        return "error", "feishu_agent_asset_unreadable", None

    media_type = delivery.media_type
    media_key = delivery.media_key
    if not media_key:
        content_type = asset.content_type or "application/octet-stream"
        filename = asset.display_filename or "attachment"
        media_type = _asset_media_type(content_type)
        try:
            if media_type == "image":
                media_key = await client.upload_image(
                    content, filename=filename, content_type=content_type
                )
            else:
                media_key = await client.upload_file(
                    content,
                    filename=filename,
                    content_type=content_type,
                    file_type=(
                        "mp4"
                        if media_type == "media"
                        else FEISHU_FILE_SUBTYPES.get(content_type, "stream")
                    ),
                )
        except ValueError as exc:
            from app.integrations.feishu import FeishuAPIError

            # FeishuAPIError subclasses ValueError: a provider rejection (scope,
            # size limit, storage) must not be recorded as a local format
            # rejection, and its code is what operators need to fix it.
            if isinstance(exc, FeishuAPIError):
                logger.warning(
                    "Feishu rejected upload for delivery %s (run %s, %s): "
                    "HTTP %s code %s: %s",
                    delivery.id,
                    receipt.run_id,
                    content_type,
                    exc.status_code,
                    exc.code,
                    exc,
                )
                return "error", "feishu_agent_asset_upload_failed", error_detail(exc)
            logger.warning(
                "Rejected local upload parameters for delivery %s (run %s, %s, %s bytes)",
                delivery.id,
                receipt.run_id,
                content_type,
                len(content),
            )
            return "error", "feishu_agent_asset_unsupported", error_detail(exc)
        except Exception as exc:
            logger.warning(
                "Failed to upload Feishu delivery asset %s (run %s, %s)",
                delivery.asset_id,
                receipt.run_id,
                content_type,
                exc_info=True,
            )
            return "error", "feishu_agent_asset_upload_failed", error_detail(exc)
        await IntegrationDelivery.filter(id=delivery.id).update(
            media_type=media_type, media_key=media_key, updated_at=utcnow()
        )
    await client.reply_media(
        receipt.message_id,
        msg_type=media_type,
        key=media_key,
        uuid=delivery.provider_uuid,
    )
    return "sent", None, None


async def deliver_pending_for_integration(integration_id: UUID) -> None:
    """Claim and send pending deliveries for one integration.

    Every row resolves its own receipt and recipient, so an older Agent's
    result is never sent through a newer session, one chat's locale never
    leaks into another's reply, and an unauthorized row is resolved as
    ``unavailable`` instead of being retried forever.
    """
    integration = await Integration.filter(id=integration_id).first()
    if "agent_chat" not in active_features(integration):
        return
    lease_cutoff = utcnow() - timedelta(seconds=SEND_LEASE_SECONDS)
    receipt_ids = await FeishuAgentReceipt.filter(
        integration_id=integration_id
    ).values_list("id", flat=True)
    if not receipt_ids:
        return
    rows = (
        await IntegrationDelivery.filter(
            provider_type="feishu", receipt_id__in=list(receipt_ids)
        )
        .filter(Q(status="pending") | Q(status="sending", updated_at__lt=lease_cutoff))
        .order_by("created_at", "sequence")
    )
    recipients: dict[UUID, User | None] = {}
    for row in rows:
        recipient = recipients.get(row.receipt_id, False)
        if recipient is False:
            recipient = (
                await User.filter(id=row.user_id).first()
                if row.user_id is not None
                else None
            )
            recipients[row.receipt_id] = recipient
        # Localized text was already produced per row; this only keeps the
        # process language aligned with the row's own recipient.
        set_language(getattr(recipient, "locale", None) or "en")
        if row.status == "sending" and row.updated_at < lease_cutoff:
            # A crash left the claim behind: the outcome is unknown, so the row
            # is never blind-resent.
            await IntegrationDelivery.filter(
                id=row.id, status="sending", updated_at__lt=lease_cutoff
            ).update(status="unknown")
            continue
        if row.status != "pending":
            continue
        claimed = await IntegrationDelivery.filter(id=row.id, status="pending").update(
            status="sending"
        )
        if not claimed:
            continue
        await _send_one(row)


__all__ = [
    "accept_message",
    "process_message",
    "process_pending",
    "recover_pending",
    "deliver_pending_for_integration",
]

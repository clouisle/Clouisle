"""Shared durable chat submission used by the web routes and the WeChat runtime.

This is the single durable submit pipeline moved out of the chat endpoint: it
authorizes the actor, resolves the owned conversation, persists the user
``Message`` and the ``AgentRun`` with its worker payload, and only then
publishes to the broker.  A crash before publishing leaves a ``QUEUED`` run
that recovery can re-dispatch safely, because the worker claims a queued run
with a conditional status update and a per-conversation lock before doing any
work.

The web routes call :func:`submit_chat_run` and dispatch immediately.  The
WeChat runtime calls it with ``defer_dispatch=True`` inside its own
transaction that also claims the durable receipt, and publishes only after
that transaction commits.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from app.core.i18n import resolve_language
from app.models.agent import Message, MessageRole, MessageRoundRole, RAGMode
from app.models.agent_run import AgentRun
from app.models.user import User

logger = logging.getLogger(__name__)

AUTO_RAG_HISTORY_LIMIT = 6


def _split_run_auth(auth_result: Any) -> tuple[User, "Any | None"]:
    """Accept dependency tuples and direct-user calls used by unit tests."""
    if isinstance(auth_result, tuple) and len(auth_result) == 2:
        return auth_result
    return auth_result, None


class RunSubmission:
    """A committed run plus the payload needed to publish it."""

    def __init__(
        self,
        *,
        run: AgentRun,
        payload: dict[str, Any],
        agent_id: UUID,
        conversation_id: UUID,
        user_message_id: UUID,
        stream_url: str,
        prepared: Any = None,
    ):
        self.run = run
        self.payload = payload
        self.run_id = run.id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.user_message_id = user_message_id
        self.status = run.status.value
        self.stream_url = stream_url
        self.prepared = prepared
        self.dispatched = False

    async def dispatch(self) -> None:
        """Publish the committed run exactly once per call."""
        if self.dispatched:
            return
        await _publish(self.run, self.payload)
        self.dispatched = True


async def _publish(run: AgentRun, payload: dict[str, Any]) -> None:
    from app.tasks.agent import run_agent_task

    task_result = run_agent_task.apply_async(args=(payload,), task_id=str(run.id))
    task_id = getattr(task_result, "id", None)
    if task_id:
        run.celery_task_id = task_id
        await run.save(update_fields=["celery_task_id"])


async def dispatch_run(payload: dict[str, Any], run: AgentRun) -> None:
    """Publish one already-committed payload to the agent queue.

    Callers re-check ``run.status == QUEUED`` before calling this: the worker
    claims queued runs with a conditional update and a per-conversation lock,
    so a duplicate publish never executes the run twice.  The deterministic
    ``task_id`` is for traceability only and does not deduplicate messages.
    """
    await _publish(run, payload)


async def submit_chat_run(
    agent_id: UUID,
    chat_in: Any,
    auth_result: Any,
    *,
    mode: Any = None,
    conversation_id: UUID | None = None,
    defer_dispatch: bool = False,
) -> RunSubmission:
    """Create the durable input row and enqueue one worker-owned run.

    ``conversation_id`` overrides ``chat_in.conversation_id`` so a caller that
    already owns the conversation (the WeChat session) can continue it without
    mutating the request object.  With ``defer_dispatch=True`` nothing is
    published: the caller commits its own mapping (receipt -> run) and then
    calls :meth:`RunSubmission.dispatch`, so a crash can never leave a receipt
    pointing at a run that was never queued.
    """
    if mode is None:
        from app.models.agent_run import AgentRunMode

        mode = AgentRunMode.SEND
    from app.api.v1.endpoints.chat import (
        AgentKnowledgeBase,
        _bind_workflow_assets_to_conversation,
        _message_asset_transaction,
        _resolve_message_assets,
        _resolve_workflow_asset_refs,
        check_agent_chat_access,
        get_next_user_branch_parent_id,
        get_or_create_conversation,
        update_message_stats,
    )
    from app.api.v1.endpoints.chat_helpers import get_streaming_config
    from app.api.v1.endpoints.chat_rag import (
        aggregate_rag_contexts,
        perform_rag_retrieval,
    )
    from app.api.v1.endpoints.chat_tools import build_file_content_for_context
    from app.schemas.response import BusinessError, ResponseCode
    from app.services.agent_run_store import create_run, transition_run_if_status
    from app.services.agent_run_worker import build_payload
    from app.services.message_branching import get_visible_conversation_messages

    current_user, api_key = _split_run_auth(auth_result)
    if not current_user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key="inactive_user",
            status_code=401,
        )
    from app.api import deps

    await deps.check_api_key_agent_access(api_key, agent_id)

    agent = await check_agent_chat_access(agent_id, current_user)
    conversation = await get_or_create_conversation(
        agent,
        current_user,
        conversation_id if conversation_id is not None else chat_in.conversation_id,
        chat_in.variables,
    )

    rag_contexts: list[dict[str, Any]] | None = None
    if agent.rag_mode == RAGMode.AUTO and await AgentKnowledgeBase.exists(
        agent_id=agent.id
    ):
        rag_contexts = aggregate_rag_contexts(
            await perform_rag_retrieval(
                agent,
                current_user,
                chat_in.message,
                await get_visible_conversation_messages(
                    conversation.id, limit=AUTO_RAG_HISTORY_LIMIT
                ),
            )
        )

    workflow_assets = (
        await _resolve_workflow_asset_refs(
            references=chat_in.workflow_asset_refs,
            agent=agent,
            user=current_user,
            api_key=api_key,
        )
        if chat_in.workflow_asset_refs
        else []
    )

    message_assets = await _resolve_message_assets(
        attachments=[*chat_in.images, *chat_in.file_urls],
        agent=agent,
        user=current_user,
        conversation_id=conversation.id,
        api_key=api_key,
    )
    if chat_in.variable_asset_ids:
        variable_assets = await _resolve_message_assets(
            attachments=chat_in.variable_asset_ids,
            agent=agent,
            user=current_user,
            conversation_id=conversation.id,
            api_key=api_key,
        )
        message_assets.extend(
            (asset, "variable", index)
            for index, (asset, _, _) in enumerate(variable_assets)
        )
    round_id = uuid4()
    user_branch_parent_id = await get_next_user_branch_parent_id(conversation)

    async with _message_asset_transaction(bool(message_assets or workflow_assets)):
        if workflow_assets:
            existing_asset_ids = {asset.id for asset, _, _ in message_assets}
            first_position = (
                max((position for _, _, position in message_assets), default=-1) + 1
            )
            (
                imported_images,
                imported_files,
                imported_links,
            ) = await _bind_workflow_assets_to_conversation(
                assets=workflow_assets,
                conversation_id=conversation.id,
                existing_asset_ids=existing_asset_ids,
                first_position=first_position,
                user=current_user,
                api_key=api_key,
                expected_team_id=UUID(str(agent.team_id)) if agent.team_id else None,
            )
            chat_in.images.extend(imported_images)
            chat_in.file_urls.extend(imported_files)
            message_assets.extend(imported_links)
        user_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.USER,
            content=chat_in.message,
            images=[img.model_dump() for img in chat_in.images]
            if chat_in.images
            else None,
            file_urls=[f.model_dump() for f in chat_in.file_urls]
            if chat_in.file_urls
            else None,
            rag_context=rag_contexts,
            branch_parent_id=user_branch_parent_id,
            round_id=round_id,
            round_index=0,
            round_role=MessageRoundRole.USER_INPUT,
            is_round_canonical=True,
        )
        for asset, role, position in message_assets:
            from app.services.asset import asset_service

            await asset_service.attach_to_message(
                asset=asset, message_id=user_msg.id, role=role, position=position
            )

    await update_message_stats(agent, token_usage=None)
    effective_locale = await resolve_language(getattr(current_user, "locale", None))
    streaming_config = get_streaming_config(agent)
    await build_file_content_for_context(
        agent=agent,
        file_urls=[
            file
            for file in chat_in.file_urls
            if not file.asset_id and not file.asset_ref
        ],
        legacy_files=chat_in.files,
        user_locale=effective_locale,
        tool_timeouts=streaming_config["tool_timeouts"],
        user=current_user,
    )

    run = await create_run(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        resource_name=agent.name,
        team_id=str(agent.team_id) if agent.team_id else None,
        source_message_id=user_msg.id,
    )
    run.active_round_id = round_id
    await run.save(update_fields=["active_round_id"])
    payload = build_payload(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        user_message_id=user_msg.id,
        round_id=round_id,
        run_id=run.id,
        message=chat_in.message,
        images=[image.model_dump() for image in chat_in.images],
        file_urls=[file.model_dump() for file in chat_in.file_urls],
        legacy_files=[file.model_dump() for file in chat_in.files],
        history_override=(
            [
                message.model_dump(exclude_none=True)
                for message in chat_in.history_override
            ]
            if chat_in.history_override
            else None
        ),
        variables=chat_in.variables,
        branch_parent_id=user_branch_parent_id,
        locale=effective_locale,
        rag_contexts=rag_contexts,
    )
    run.worker_payload = payload
    await run.save(update_fields=["worker_payload"])

    submission = RunSubmission(
        run=run,
        payload=payload,
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_message_id=user_msg.id,
        stream_url=f"/agents/{agent.id}/chat/runs/{run.id}/stream",
        prepared=chat_in,
    )

    if not defer_dispatch:
        try:
            await submission.dispatch()
        except Exception as exc:
            from app.models.agent_run import AgentRunStatus

            await transition_run_if_status(
                run,
                AgentRunStatus.QUEUED,
                AgentRunStatus.FAILED,
                error_code="enqueue_failed",
                error_message=str(exc),
            )
            raise

    return submission


def start_out(submission: RunSubmission) -> dict:
    """API ``RunStartOut`` response envelope used by the web chat routes."""
    from app.schemas.agent import RunStartOut
    from app.schemas.response import success

    return success(
        data=RunStartOut(
            run_id=submission.run_id,
            conversation_id=submission.conversation_id,
            user_message_id=submission.user_message_id,
            status=submission.status,
            stream_url=submission.stream_url,
        )
    )


__all__ = ["RunSubmission", "submit_chat_run", "dispatch_run", "start_out"]

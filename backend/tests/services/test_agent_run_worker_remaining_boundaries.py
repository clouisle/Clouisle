"""Remaining durable AgentRun worker finalization boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_finalize_completed_activates_existing_branch_and_sets_missing_title(
    monkeypatch,
):
    from app.services import agent_run_worker

    conversation_id = uuid4()
    parent = SimpleNamespace(id=uuid4())
    prefix = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    canonical = SimpleNamespace(
        id=uuid4(),
        branch_parent_id=parent.id,
        content="",
        reasoning_content=None,
        model_used=None,
        duration_ms=0,
        first_token_ms=None,
        is_manually_stopped=False,
        round_status=None,
        round_index=0,
        token_usage=None,
        save=AsyncMock(),
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        title=None,
        message_count=4,
        token_usage=10,
    )
    agent = SimpleNamespace(id=uuid4(), message_count=4, total_tokens=10)
    result = SimpleNamespace(
        full_content="completed answer",
        full_reasoning=None,
        max_iterations_reached=False,
        aggregate_input_tokens=3,
        aggregate_output_tokens=5,
        aggregate_cache_read_tokens=0,
        aggregate_cache_creation_tokens=0,
        aggregate_total_input_tokens=3,
        duration_ms=25,
        first_token_ms=8,
        created_message_count=2,
        final_round_index=2,
    )
    conversation_update = AsyncMock()
    agent_update = AsyncMock()
    activated = AsyncMock()
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=conversation_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Agent,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=agent_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=parent)
    )
    monkeypatch.setattr(
        "app.services.message_branching.get_prefix_path_before",
        AsyncMock(return_value=prefix),
    )
    monkeypatch.setattr(
        "app.services.message_branching.activate_conversation_branch", activated
    )
    stream = SimpleNamespace(publish=AsyncMock())

    await agent_run_worker._finalize_completed(
        canonical,
        result,
        conversation,
        agent,
        stream,
        user_message=SimpleNamespace(content="new question"),
        model_used="model",
        locale="en",
    )

    activated.assert_awaited_once_with(conversation_id, [*prefix, parent, canonical])
    conversation_update.assert_awaited_once()
    assert conversation_update.await_args.kwargs["title"] == "new question"
    assert conversation_update.await_args.kwargs["message_count"] == 6
    assert conversation_update.await_args.kwargs["token_usage"] == 18
    assert canonical.content == "completed answer"
    stream.publish.assert_awaited_once_with(
        "message_end",
        {
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 5,
                "total_tokens": 8,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "total_input_tokens": 3,
            }
        },
    )
    agent_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_completed_falls_back_to_direct_canonical_branch(monkeypatch):
    """A deleted branch parent still activates the canonical-only branch path."""
    from app.services import agent_run_worker

    conversation_id = uuid4()
    canonical = SimpleNamespace(
        id=uuid4(),
        branch_parent_id=uuid4(),
        content="",
        reasoning_content=None,
        model_used=None,
        duration_ms=0,
        first_token_ms=None,
        is_manually_stopped=False,
        round_status=None,
        round_index=0,
        token_usage=None,
        save=AsyncMock(),
    )
    conversation = SimpleNamespace(
        id=conversation_id,
        title="existing title",
        message_count=1,
        token_usage=2,
    )
    agent = SimpleNamespace(id=uuid4(), message_count=1, total_tokens=2)
    result = SimpleNamespace(
        full_content="",
        full_reasoning="",
        max_iterations_reached=True,
        aggregate_input_tokens=1,
        aggregate_output_tokens=1,
        aggregate_cache_read_tokens=0,
        aggregate_cache_creation_tokens=0,
        aggregate_total_input_tokens=1,
        duration_ms=5,
        first_token_ms=None,
        created_message_count=1,
        final_round_index=3,
    )
    conversation_update = AsyncMock()
    agent_update = AsyncMock()
    activated = AsyncMock()
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=conversation_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Agent,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=agent_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Message,
        "get_or_none",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.message_branching.activate_conversation_branch", activated
    )
    stream = SimpleNamespace(publish=AsyncMock())

    await agent_run_worker._finalize_completed(
        canonical,
        result,
        conversation,
        agent,
        stream,
        user_message=SimpleNamespace(content="ignored"),
        model_used="model",
        locale="en",
    )

    activated.assert_awaited_once_with(conversation_id, [canonical])
    assert canonical.content
    assert canonical.round_index == 3
    assert "title" not in conversation_update.await_args.kwargs
    assert conversation_update.await_args.kwargs["message_count"] == 3
    assert conversation_update.await_args.kwargs["token_usage"] == 4


@pytest.mark.asyncio
async def test_rebuild_context_raises_when_user_message_missing(monkeypatch):
    """A vanished user message aborts the round before any model work."""
    from app.services import agent_run_worker

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        rag_mode=SimpleNamespace(value="off"),
        tools_config=[],
        enable_user_input_request=False,
        enable_memory=False,
        enable_attachments=False,
        streaming_config=None,
    )
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    created_sessions: list[dict[str, str | None]] = []

    async def _create_session(**kwargs):
        created_sessions.append(kwargs)
        return "session-missing"

    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        _create_session,
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=None)
    )

    with pytest.raises(LookupError, match="user message not found"):
        await agent_run_worker._rebuild_context(
            {
                "run_id": str(uuid4()),
                "round_id": str(uuid4()),
                "user_message_id": str(uuid4()),
                "mode": "send",
                "message": "hello",
            },
            agent=agent,
            conversation=conversation,
            event_queue=asyncio.Queue(),
        )

    assert created_sessions == []


@pytest.mark.asyncio
async def test_rebuild_context_filters_ask_user_and_applies_payload_rag(
    monkeypatch,
):
    from app.models.agent import RAGMode
    from app.services import agent_run_worker

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        rag_mode=RAGMode.AUTO,
        tools_config=[],
        enable_user_input_request=True,
        enable_memory=False,
        enable_attachments=False,
        enable_image_generation=False,
        enable_video_generation=False,
        streaming_config=None,
    )
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(
        id=uuid4(), rag_context=None, content="original question"
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.Message.get_or_none",
        AsyncMock(return_value=user_msg),
    )
    round_id = uuid4()
    chat_model = SimpleNamespace(
        model_id="db-model",
        tokenizer_model_id=None,
        provider=None,
        context_length=128_000,
        max_output_tokens=None,
        model=SimpleNamespace(),
        input_capabilities=SimpleNamespace(modalities=frozenset()),
    )
    seeded = AsyncMock()

    async def _create_session(**_kwargs):
        return "session-2"

    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session", _create_session
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_agent_tools",
        AsyncMock(
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "ask_user",
                        "description": "ask",
                        "parameters": {},
                    },
                }
            ]
        ),
    )

    async def no_asset_links(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(
            prefetch_related=lambda *_args: SimpleNamespace(
                order_by=lambda *_args: no_asset_links()
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.resolve_agent_chat_model",
        AsyncMock(return_value=chat_model),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("", None)),
    )
    monkeypatch.setattr(
        "app.services.message_branching.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.chat_context.build_context_plan",
        AsyncMock(return_value=SimpleNamespace(will_summarize=True, compression=None)),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.build_rag_prompt",
        lambda contexts, message, **_kwargs: f"{message} [rag:{len(contexts)}]",
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=user_msg)
    )
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=seeded),
    )

    loop_context, loaded_message, loop = await agent_run_worker._rebuild_context(
        {
            "run_id": str(uuid4()),
            "round_id": str(round_id),
            "user_message_id": str(user_msg.id),
            "mode": "non_stream",
            "message": "original question",
            "locale": "zh",
            "history_override": [{"role": "user", "content": "prior"}],
            "history_before_message_created_at": "2026-01-01T00:00:00+00:00",
            "exclude_message_ids": [str(uuid4())],
            "rag_contexts": [{"citation_id": "1"}],
            "first_round_index": "4",
            "iteration_offset": "2",
        },
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )

    assert loaded_message is user_msg
    assert loop_context.tools is None
    assert loop_context.streaming is False
    assert loop_context.model_id == "db-model"
    assert loop_context.sandbox_session_id == "session-2"
    assert loop_context.user_message == "original question [rag:1]"
    assert loop_context.working_history_override == [
        {"role": "user", "content": "prior"}
    ]
    assert len(loop_context.exclude_message_ids) == 1
    assert loop_context.first_round_index == 4
    assert loop_context.iteration_offset == 2
    assert loop_context.user_locale == "zh"
    assert loop.context is loop_context
    seeded.assert_awaited_once()


@pytest.mark.asyncio
async def test_rebuild_context_tool_concurrency_reads_registry(monkeypatch):
    """tool_concurrency maps registered concurrency and defaults to exclusive."""
    from app.services import agent_run_worker

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        rag_mode=SimpleNamespace(value="off"),
        tools_config=[],
        enable_user_input_request=False,
        enable_memory=False,
        enable_image_generation=False,
        enable_video_generation=False,
        streaming_config=None,
    )
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="q")
    monkeypatch.setattr(
        "app.services.agent_run_worker.Message.get_or_none",
        AsyncMock(return_value=user_msg),
    )
    chat_model = SimpleNamespace(
        model_id="db-model",
        tokenizer_model_id=None,
        provider=None,
        context_length=128_000,
        model_context_limit=128_000,
        model_max_output_tokens=None,
        model_used="db-model",
        max_output_tokens=None,
        model=SimpleNamespace(),
        input_capabilities=SimpleNamespace(modalities=frozenset()),
    )

    async def _create_session(**_kwargs):
        return "session-3"

    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session", _create_session
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_agent_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.resolve_agent_chat_model",
        AsyncMock(return_value=chat_model),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("", None)),
    )

    async def no_asset_links_2(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(
            prefetch_related=lambda *_args: SimpleNamespace(
                order_by=lambda *_args: no_asset_links_2()
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.message_branching.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.chat_context.build_context_plan",
        AsyncMock(return_value=SimpleNamespace(will_summarize=False, compression=None)),
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=user_msg)
    )
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=AsyncMock()),
    )

    loop_context, _, _ = await agent_run_worker._rebuild_context(
        {
            "run_id": str(uuid4()),
            "round_id": str(uuid4()),
            "user_message_id": str(user_msg.id),
            "mode": "send",
            "message": "q",
        },
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )

    from app.llm.tools.builtin import register_all_builtin_tools
    from app.llm.tools.registry import ToolConcurrency, ToolInfo, tool_registry

    register_all_builtin_tools()
    registered = tool_registry.get_tool("get_current_time")
    assert registered is not None
    assert (
        loop_context.tool_concurrency("get_current_time")
        == registered.concurrency.value
    )
    assert loop_context.tool_concurrency("unknown_tool_name") == "exclusive"
    shared = ToolInfo(
        name="__probe_shared_tool__",
        description="probe",
        concurrency=ToolConcurrency.SHARED,
    )
    tool_registry.register_tool(shared)
    try:
        assert loop_context.tool_concurrency("__probe_shared_tool__") == "shared"
    finally:
        tool_registry.unregister("__probe_shared_tool__")


@pytest.mark.asyncio
async def test_micro_batching_collector_flushes_on_batch_timeout(monkeypatch):
    from app.services.agent_run_worker import MicroBatchingCollector

    published: list[tuple[str, dict]] = []

    class _Stream:
        async def publish(self, event_type, payload=None, **_kwargs):
            published.append((event_type, payload or {}))
            return None

    event_queue: asyncio.Queue = asyncio.Queue()
    collector = MicroBatchingCollector(
        event_queue=event_queue,
        stream=_Stream(),
        run=SimpleNamespace(id=uuid4(), active_round_id=uuid4()),
        canonical_message_id=uuid4(),
    )
    task = asyncio.create_task(collector.run_loop())

    event_queue.put_nowait(("content_delta", {"delta": "a"}))
    await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    assert published == [("content_delta", {"delta": "a"})]

    event_queue.put_nowait(None)
    await task


@pytest.mark.asyncio
async def test_micro_batching_collector_logs_and_continues_after_publish_error(
    monkeypatch,
    caplog,
):
    """A broken event stream never kills the publisher loop."""
    from app.services import agent_run_worker

    published: list[str] = []
    failing_calls = {"n": 0}

    class _Stream:
        async def publish(self, event_type, _payload=None, **_kwargs):
            if failing_calls["n"] == 0:
                failing_calls["n"] += 1
                raise RuntimeError("stream down")
            published.append(event_type)
            return None

    event_queue: asyncio.Queue = asyncio.Queue()
    collector = agent_run_worker.MicroBatchingCollector(
        event_queue=event_queue,
        stream=_Stream(),
        run=SimpleNamespace(id=uuid4(), active_round_id=None),
    )
    task = asyncio.create_task(collector.run_loop())

    event_queue.put_nowait(("tool_call", {"name": "broken"}))
    event_queue.put_nowait(("tool_call", {"name": "second"}))
    await asyncio.sleep(0.05)

    assert published == ["tool_call"]
    assert any(
        "Failed to publish AgentRun" in record.message for record in caplog.records
    )

    event_queue.put_nowait(None)
    await task


@pytest.mark.asyncio
async def test_run_agent_round_records_first_token_progress_and_dependency_metrics(
    monkeypatch,
):
    from app.services import agent_run_worker

    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=agent_run_worker.AgentRunStatus.RUNNING,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        started_at=None,
        message_started_at=None,
        first_token_ms=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock()
    agent = SimpleNamespace(
        id=run.agent_id,
        team_id=None,
        rag_mode=SimpleNamespace(value="off"),
        streaming_config=None,
        message_count=0,
        total_tokens=0,
    )
    conversation = SimpleNamespace(
        id=run.conversation_id,
        user_id=run.user_id,
        title=None,
        message_count=0,
        token_usage=0,
    )
    user_msg = SimpleNamespace(
        id=uuid4(), content="question", rag_context=[], round_id=uuid4()
    )
    conversation_update = AsyncMock()
    agent_update = AsyncMock()
    round_id = uuid4()
    canonical = SimpleNamespace(id=uuid4(), branch_parent_id=None, save=AsyncMock())
    metrics_recorded: list[tuple] = []

    async def _record_metrics(run_id, metrics, *, truncated=False):
        metrics_recorded.append((run_id, list(metrics), truncated))

    async def _transition(run_obj, expected, status, **_kwargs):
        assert run_obj.status == expected
        run_obj.status = status
        return run_obj

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    class _Loop:
        def __init__(self):
            self.result = SimpleNamespace(
                waiting_for_user=False,
                deadline_exceeded=False,
                manually_stopped=False,
                full_content="answer",
                full_reasoning=None,
                aggregate_input_tokens=1,
                aggregate_output_tokens=1,
                aggregate_cache_read_tokens=0,
                aggregate_cache_creation_tokens=0,
                aggregate_total_input_tokens=1,
                duration_ms=3,
                first_token_ms=42,
                dependency_metrics=[{"tool_name": "get_current_time"}],
                dependency_metrics_truncated=False,
                created_message_count=2,
                final_round_index=1,
                max_iterations_reached=False,
            )

        async def run(self):
            if False:
                yield None

    async def _rebuild_context(_payload, *, agent, conversation, event_queue):
        context = SimpleNamespace(
            agent=agent,
            conversation=conversation,
            user=SimpleNamespace(id=conversation.user_id),
            model_id="model",
            tokenizer_model_id=None,
            model_provider=None,
            model_context_limit=None,
            model_max_output_tokens=None,
            model_used="model",
            sandbox_session_id=None,
            round_id=round_id,
            deadline_seconds=None,
            global_timeout=120.0,
            working_history_override=None,
        )
        return context, user_msg, _Loop()

    progress: list[dict] = []

    def _record_progress(run_id, **kwargs):
        progress.append({"run_id": run_id, **kwargs})

    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "get_run", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        agent_run_worker.Agent, "get_or_none", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "get_or_none",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=conversation_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Agent,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=agent_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        agent_run_worker,
        "_create_placeholder",
        AsyncMock(return_value=canonical),
    )
    monkeypatch.setattr(
        "app.services.message_branching.activate_conversation_branch", AsyncMock()
    )
    monkeypatch.setattr(agent_run_worker, "_rebuild_context", _rebuild_context)
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock()),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "acquire_run_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "release_run_lock", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "heartbeat_run_lock", _heartbeat
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "has_pending_inputs",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "consume_next_input",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "drop_pending_inputs", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "transition_run_if_status", _transition
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "record_observability_progress",
        _record_progress,
    )
    monkeypatch.setattr(
        agent_run_worker,
        "record_dependency_metrics",
        AsyncMock(side_effect=_record_metrics),
    )
    monkeypatch.setattr(
        agent_run_worker,
        "sandbox_gateway",
        SimpleNamespace(begin_round=AsyncMock(), finish_round=AsyncMock()),
    )
    monkeypatch.setattr(
        "app.tasks.memory.schedule_background_memory_extraction",
        AsyncMock(return_value=True),
    )

    output = await agent_run_worker.run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert output == {
        "status": agent_run_worker.AgentRunStatus.COMPLETED.value,
        "message_id": str(canonical.id),
    }
    from app.tasks.memory import schedule_background_memory_extraction

    schedule_background_memory_extraction.assert_awaited_once_with(
        conversation_id=conversation.id,
        agent_id=agent.id,
        user_id=run.user_id,
    )
    assert run.first_token_ms == 42
    assert "first_token_ms" in run.save.await_args.kwargs["update_fields"]
    assert any(call.get("first_token_ms") == 42 for call in progress)
    assert any(call.get("message_started_at") is not None for call in progress)
    assert metrics_recorded == [(run.id, [{"tool_name": "get_current_time"}], False)]


@pytest.mark.asyncio
async def test_run_agent_round_consumed_inputs_persist_step_message_and_history(
    monkeypatch,
):
    """A steer consumed before completion persists the step message + audit."""
    from app.models.agent_run import AgentRunInputKind, AgentRunStatus
    from app.services import agent_run_worker

    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=AgentRunStatus.RUNNING,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=uuid4(),
        started_at=None,
        message_started_at=None,
        first_token_ms=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock()
    agent = SimpleNamespace(
        id=run.agent_id,
        team_id=None,
        rag_mode=SimpleNamespace(value="off"),
        message_count=0,
        total_tokens=0,
    )
    conversation = SimpleNamespace(
        id=run.conversation_id,
        user_id=run.user_id,
        title=None,
        message_count=0,
        token_usage=0,
    )
    user_msg = SimpleNamespace(
        id=uuid4(), content="q", rag_context=[], round_id=run.active_round_id
    )
    canonical = SimpleNamespace(id=uuid4(), branch_parent_id=None, save=AsyncMock())
    consumed_items = [
        SimpleNamespace(
            kind=AgentRunInputKind.STEER,
            content="steer text",
            sequence=7,
        )
    ]
    created_messages = []
    audit_logs = []
    published = []
    conversation_update = AsyncMock()
    agent_update = AsyncMock()

    async def _consume_next_input(_run_id):
        if consumed_items:
            return consumed_items.pop(0)
        return None

    async def _message_create(**kwargs):
        created_messages.append(kwargs)
        return SimpleNamespace(id=uuid4(), **kwargs)

    async def _audit_log(**kwargs):
        audit_logs.append(kwargs)

    async def _transition(run_obj, expected, status, **_kwargs):
        assert run_obj.status == expected
        run_obj.status = status
        return run_obj

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    class _Loop:
        def __init__(self):
            self.result = SimpleNamespace(
                waiting_for_user=False,
                deadline_exceeded=False,
                manually_stopped=False,
                max_iterations_reached=False,
                full_content="answer",
                full_reasoning=None,
                aggregate_input_tokens=0,
                aggregate_output_tokens=0,
                aggregate_cache_read_tokens=0,
                aggregate_cache_creation_tokens=0,
                aggregate_total_input_tokens=0,
                duration_ms=1,
                first_token_ms=None,
                dependency_metrics=[],
                dependency_metrics_truncated=False,
                created_message_count=2,
                final_round_index=1,
            )
            self.working_history_override = None
            self.context = None

        async def run(self):
            for item in await self.context.consume_inputs():
                await self.context.input_consumed(item)
            if False:
                yield None

    loop_instance = _Loop()

    async def _rebuild_context(_payload, *, agent, conversation, event_queue):
        context = SimpleNamespace(
            agent=agent,
            conversation=conversation,
            user=SimpleNamespace(id=conversation.user_id),
            model_id="model",
            tokenizer_model_id=None,
            model_provider=None,
            model_context_limit=None,
            model_max_output_tokens=None,
            model_used="model",
            sandbox_session_id=None,
            round_id=run.active_round_id,
            deadline_seconds=None,
            global_timeout=60.0,
            working_history_override=None,
            pause_for_user=None,
        )
        loop_instance.context = context
        return context, user_msg, loop_instance

    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "get_run", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        agent_run_worker.Agent, "get_or_none", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "get_or_none",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=conversation_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Agent,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=agent_update),
    )
    monkeypatch.setattr(
        "app.services.message_branching.activate_conversation_branch", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(agent_run_worker.Message, "create", _message_create)
    monkeypatch.setattr(
        agent_run_worker,
        "_create_placeholder",
        AsyncMock(return_value=canonical),
    )
    monkeypatch.setattr(agent_run_worker, "_rebuild_context", _rebuild_context)
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(
            seed_sequence=AsyncMock(),
            publish=AsyncMock(side_effect=lambda *a, **_k: published.append(a)),
        ),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "acquire_run_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "release_run_lock", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "heartbeat_run_lock", _heartbeat
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "has_pending_inputs",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "consume_next_input", _consume_next_input
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "drop_pending_inputs", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "transition_run_if_status", _transition
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "record_observability_progress",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(agent_run_worker, "record_dependency_metrics", AsyncMock())
    monkeypatch.setattr(
        agent_run_worker,
        "sandbox_gateway",
        SimpleNamespace(begin_round=AsyncMock(), finish_round=AsyncMock()),
    )
    monkeypatch.setattr(
        "app.services.audit_log.AuditLogService.log",
        AsyncMock(side_effect=_audit_log),
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none",
        AsyncMock(return_value=SimpleNamespace(id=run.user_id)),
    )

    output = await agent_run_worker.run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert output["status"] == AgentRunStatus.COMPLETED.value
    assert len(created_messages) == 1
    step = created_messages[0]
    assert step["content"] == "steer text"
    assert step["round_index"] == 10_007
    assert step["is_round_canonical"] is False
    assert audit_logs and audit_logs[0]["action"] == "create_message"
    assert audit_logs[0]["metadata"]["sequence"] == 7
    assert ("input_accepted",) in [call[:1] for call in published]
    override = loop_instance.context.working_history_override
    assert override == [
        {
            "role": "user",
            "content": "steer text",
            "round_id": str(run.active_round_id),
            "round_index": 10_007,
            "round_role": "user_input",
            "is_round_canonical": True,
            "round_status": "completed",
        }
    ]


@pytest.mark.asyncio
async def test_run_agent_round_stop_requested_callback_detects_pending_stop_input(
    monkeypatch,
):
    """loop_context.stop_requested reads durable STOP inputs after RUNNING."""
    from app.models.agent_run import AgentRunInputKind, AgentRunStatus
    from app.services import agent_run_worker

    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=AgentRunStatus.RUNNING,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        started_at=None,
        message_started_at=None,
        first_token_ms=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock()
    agent = SimpleNamespace(
        id=run.agent_id, team_id=None, rag_mode=SimpleNamespace(value="off")
    )
    conversation = SimpleNamespace(id=run.conversation_id, user_id=run.user_id)
    user_msg = SimpleNamespace(id=uuid4(), content="q", rag_context=[])
    canonical = SimpleNamespace(id=uuid4(), branch_parent_id=None, save=AsyncMock())
    stop_checks: list[object] = []
    contexts: list[object] = []

    async def _has_pending_inputs(run_id, *, kind=None):
        stop_checks.append(kind)
        return kind == AgentRunInputKind.STOP

    async def _transition(run_obj, expected, status, **_kwargs):
        assert run_obj.status == expected
        run_obj.status = status
        return run_obj

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    class _Loop:
        def __init__(self):
            self.result = SimpleNamespace(
                waiting_for_user=False,
                deadline_exceeded=False,
                manually_stopped=False,
                max_iterations_reached=False,
                full_content="answer",
                full_reasoning=None,
                aggregate_input_tokens=0,
                aggregate_output_tokens=0,
                aggregate_cache_read_tokens=0,
                aggregate_cache_creation_tokens=0,
                aggregate_total_input_tokens=0,
                duration_ms=1,
                first_token_ms=None,
                dependency_metrics=[],
                dependency_metrics_truncated=False,
                created_message_count=2,
                final_round_index=1,
            )

        async def run(self):
            assert contexts
            assert await contexts[0].stop_requested() is True
            assert contexts[0].is_disconnected is contexts[0].stop_requested
            if False:
                yield None

    async def _rebuild_context(_payload, *, agent, conversation, event_queue):
        context = SimpleNamespace(
            agent=agent,
            conversation=conversation,
            user=SimpleNamespace(id=conversation.user_id),
            model_id="model",
            tokenizer_model_id=None,
            model_provider=None,
            model_context_limit=None,
            model_max_output_tokens=None,
            model_used="model",
            sandbox_session_id=None,
            round_id=uuid4(),
            deadline_seconds=None,
            global_timeout=60.0,
            working_history_override=None,
            pause_for_user=None,
        )
        contexts.append(context)
        return context, user_msg, _Loop()

    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "get_run", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        agent_run_worker.Agent, "get_or_none", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "get_or_none",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        agent_run_worker, "_create_placeholder", AsyncMock(return_value=canonical)
    )
    monkeypatch.setattr(agent_run_worker, "_rebuild_context", _rebuild_context)
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock()),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "acquire_run_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "release_run_lock", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "heartbeat_run_lock", _heartbeat
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "has_pending_inputs", _has_pending_inputs
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "consume_next_input",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "drop_pending_inputs", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "transition_run_if_status", _transition
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "record_observability_progress",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(agent_run_worker, "record_dependency_metrics", AsyncMock())
    monkeypatch.setattr(
        agent_run_worker,
        "sandbox_gateway",
        SimpleNamespace(begin_round=AsyncMock(), finish_round=AsyncMock()),
    )

    output = await agent_run_worker.run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert output["status"] == AgentRunStatus.STOPPED.value
    assert AgentRunInputKind.STOP in stop_checks


@pytest.mark.asyncio
async def test_run_agent_round_waiting_without_pending_interaction_raises(monkeypatch):
    """A loop that waits without parking a tool call fails the run loudly."""
    from app.services import agent_run_worker

    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=agent_run_worker.AgentRunStatus.RUNNING,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        started_at=None,
        message_started_at=None,
        first_token_ms=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock()
    agent = SimpleNamespace(
        id=run.agent_id, team_id=None, rag_mode=SimpleNamespace(value="off")
    )
    conversation = SimpleNamespace(id=run.conversation_id, user_id=run.user_id)
    user_msg = SimpleNamespace(id=uuid4(), content="q", rag_context=[])
    canonical = SimpleNamespace(id=uuid4(), branch_parent_id=None, save=AsyncMock())

    async def _transition(run_obj, expected, status, **values):
        assert run_obj.status == expected
        run_obj.status = status
        run_obj.error_code = values.get("error_code")
        run_obj.error_message = values.get("error_message")
        return run_obj

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    class _Loop:
        def __init__(self):
            self.result = SimpleNamespace(
                waiting_for_user=True,
                deadline_exceeded=False,
                manually_stopped=False,
                max_iterations_reached=False,
                full_content="",
                full_reasoning=None,
                aggregate_input_tokens=0,
                aggregate_output_tokens=0,
                aggregate_cache_read_tokens=0,
                aggregate_cache_creation_tokens=0,
                aggregate_total_input_tokens=0,
                duration_ms=0,
                first_token_ms=None,
                dependency_metrics=[],
                dependency_metrics_truncated=False,
                created_message_count=2,
                final_round_index=1,
            )

        async def run(self):
            if False:
                yield None

    async def _rebuild_context(_payload, *, agent, conversation, event_queue):
        context = SimpleNamespace(
            agent=agent,
            conversation=conversation,
            user=SimpleNamespace(id=conversation.user_id),
            model_id="model",
            tokenizer_model_id=None,
            model_provider=None,
            model_context_limit=None,
            model_max_output_tokens=None,
            model_used="model",
            sandbox_session_id=None,
            round_id=uuid4(),
            deadline_seconds=None,
            global_timeout=60.0,
            working_history_override=None,
            pause_for_user=None,
        )
        return context, user_msg, _Loop()

    park_run_waiting = AsyncMock()
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "get_run", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        agent_run_worker.Agent, "get_or_none", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "get_or_none",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        agent_run_worker.Message, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        agent_run_worker, "_create_placeholder", AsyncMock(return_value=canonical)
    )
    monkeypatch.setattr(agent_run_worker, "_rebuild_context", _rebuild_context)
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock()),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "acquire_run_lock",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "release_run_lock", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "heartbeat_run_lock", _heartbeat
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "has_pending_inputs",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "consume_next_input",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "drop_pending_inputs", AsyncMock()
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "transition_run_if_status", _transition
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store, "park_run_waiting", park_run_waiting
    )
    monkeypatch.setattr(
        agent_run_worker.agent_run_store,
        "record_observability_progress",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(agent_run_worker, "record_dependency_metrics", AsyncMock())
    monkeypatch.setattr(
        agent_run_worker,
        "sandbox_gateway",
        SimpleNamespace(begin_round=AsyncMock(), finish_round=AsyncMock()),
    )

    output = await agent_run_worker.run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert output["status"] == agent_run_worker.AgentRunStatus.FAILED.value
    assert "waiting without a pending tool call" in output["error"]
    assert run.error_code == "RuntimeError"
    park_run_waiting.assert_not_awaited()


# ---------------------------------------------------------------------------
# multi-tool resume: encrypted pending calls rebuild into the loop context
# ---------------------------------------------------------------------------


def _resume_agent():
    return SimpleNamespace(
        id=uuid4(),
        team_id=None,
        rag_mode=SimpleNamespace(value="off"),
        tools_config=[],
        enable_user_input_request=False,
        enable_memory=False,
        enable_image_generation=False,
        enable_video_generation=False,
        streaming_config=None,
    )


def _patch_resume_rebuild(monkeypatch, *, user_msg):
    """Minimal request-prep stubs so only the payload path under test is real."""

    async def _create_session(**_kwargs):
        return "session-resume"

    async def _no_asset_links(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        _create_session,
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.Message.get_or_none",
        AsyncMock(return_value=user_msg),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_agent_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_tool_display_names",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.resolve_agent_chat_model",
        AsyncMock(
            return_value=SimpleNamespace(
                model_id="db-model",
                tokenizer_model_id=None,
                provider=None,
                context_length=128_000,
                max_output_tokens=None,
                model=SimpleNamespace(),
                input_capabilities=SimpleNamespace(modalities=frozenset()),
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("", None)),
    )
    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(
            prefetch_related=lambda *_args: SimpleNamespace(
                order_by=lambda *_args: _no_asset_links()
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.message_branching.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.chat_context.build_context_plan",
        AsyncMock(return_value=SimpleNamespace(will_summarize=False, compression=None)),
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=AsyncMock()),
    )


def _resume_payload(user_msg, **values):
    payload = {
        "run_id": str(uuid4()),
        "round_id": str(uuid4()),
        "user_message_id": str(user_msg.id),
        "mode": "send",
        "message": "q",
    }
    payload.update(values)
    return payload


@pytest.mark.asyncio
async def test_rebuild_context_restores_encrypted_pending_tool_calls(monkeypatch):
    """The resumed worker receives the exact unstarted calls in order."""
    import json

    from app.core.tool_secrets import encrypt_tool_secret
    from app.llm.types import ToolCall
    from app.services import agent_run_worker

    agent = _resume_agent()
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="q")
    _patch_resume_rebuild(monkeypatch, user_msg=user_msg)

    expected = [
        ToolCall(
            id="call-2",
            function={"name": "db_query", "arguments": '{"q":"select 1"}'},
        ),
        ToolCall(
            id="call-3",
            function={
                "name": "http_get",
                "arguments": '{"url":"https://example.test"}',
            },
        ),
    ]
    calls_json = json.dumps([call.model_dump() for call in expected])
    payload = _resume_payload(
        user_msg,
        pending_tool_calls_cipher=encrypt_tool_secret(calls_json),
        pending_tool_visible_names=["ask_user", "safe_core"],
        resume_tool_result={
            "tool_call_id": "call-1",
            "tool_name": "db_query",
            "result": "{}",
        },
    )

    loop_context, loaded, _loop = await agent_run_worker._rebuild_context(
        payload,
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )

    assert loaded is user_msg
    assert loop_context.resume_tool_calls == expected
    assert loop_context.resume_tool_visible_names == {"ask_user", "safe_core"}
    assert payload["pending_tool_calls_cipher"]

    legacy_payload = _resume_payload(user_msg)
    legacy_context, _loaded, _loop = await agent_run_worker._rebuild_context(
        legacy_payload,
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )
    assert legacy_context.resume_tool_visible_names is None

    cipher_only_payload = _resume_payload(
        user_msg, pending_tool_calls_cipher=encrypt_tool_secret(calls_json)
    )
    cipher_only_context, _loaded, _loop = await agent_run_worker._rebuild_context(
        cipher_only_payload,
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )
    assert cipher_only_context.resume_tool_calls == expected
    assert cipher_only_context.resume_tool_visible_names is None


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["absent", "none", "empty"])
async def test_rebuild_context_without_pending_tool_calls_resumes_none(
    monkeypatch, variant
):
    """Legacy payloads keep their single-call resume semantics."""
    from app.services import agent_run_worker

    agent = _resume_agent()
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="q")
    _patch_resume_rebuild(monkeypatch, user_msg=user_msg)

    payload = _resume_payload(user_msg)
    if variant != "absent":
        payload["pending_tool_calls_cipher"] = "" if variant == "empty" else None

    loop_context, _loaded, _loop = await agent_run_worker._rebuild_context(
        payload,
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )

    assert loop_context.resume_tool_calls is None


@pytest.mark.asyncio
async def test_rebuild_context_fails_closed_on_malformed_pending_cipher(monkeypatch):
    """Corrupt ciphertext must abort the resume instead of dropping calls."""
    from app.core.tool_secrets import ToolSecretError
    from app.services import agent_run_worker

    agent = _resume_agent()
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="q")
    _patch_resume_rebuild(monkeypatch, user_msg=user_msg)

    payload = _resume_payload(user_msg, pending_tool_calls_cipher="not-an-envelope")

    with pytest.raises(ToolSecretError):
        await agent_run_worker._rebuild_context(
            payload,
            agent=agent,
            conversation=conversation,
            event_queue=asyncio.Queue(),
        )


@pytest.mark.asyncio
async def test_rebuild_context_fails_closed_on_retired_cipher_key(monkeypatch):
    """A key id removed from the keyring aborts rather than resuming empty."""
    from cryptography.fernet import Fernet

    from app.core.tool_secrets import (
        ENVELOPE_PREFIX,
        ToolSecretError,
        ToolSecretKeyError,
    )
    from app.services import agent_run_worker

    agent = _resume_agent()
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="q")
    _patch_resume_rebuild(monkeypatch, user_msg=user_msg)

    token = Fernet(Fernet.generate_key()).encrypt(b"[]").decode()
    payload = _resume_payload(
        user_msg,
        pending_tool_calls_cipher=f"{ENVELOPE_PREFIX}retired-key-id:{token}",
    )

    with pytest.raises(ToolSecretKeyError) as excinfo:
        await agent_run_worker._rebuild_context(
            payload,
            agent=agent,
            conversation=conversation,
            event_queue=asyncio.Queue(),
        )

    assert isinstance(excinfo.value, ToolSecretError)
    assert "retired-key-id" in str(excinfo.value)

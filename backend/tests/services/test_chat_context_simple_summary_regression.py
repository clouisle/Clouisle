import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_sse import build_compression_events
from app.llm.types import Message, MessageRole
from app.models.agent import MessageRole as ConversationMessageRole
from app.schemas.response import BusinessError
from app.services import chat_context


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        system_prompt="",
        enable_memory=False,
        tools_config=[],
        context_compression_config={},
    )


def _conversation():
    return SimpleNamespace(
        id=uuid4(),
        variables={},
        context_summary_text=None,
        context_summary_watermark_id=None,
    )


@pytest.mark.anyio
async def test_summary_watermark_is_reused_across_tool_iterations(monkeypatch):
    agent = _agent()
    conversation = _conversation()
    current_user_id = uuid4()
    watermark_id = uuid4()
    protected_round_id = uuid4()
    old_history = [
        SimpleNamespace(
            id=watermark_id,
            role=ConversationMessageRole.USER,
            content="old history",
            file_urls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="old answer",
            reasoning_content=None,
            tool_calls=None,
            round_id=None,
        ),
    ]
    current_user = Message(role=MessageRole.USER, content="current request")
    summarize_calls = 0
    persisted_values = {}

    class UpdateQuery:
        async def update(self, **values):
            persisted_values.update(values)

    async def visible_history(*_args, **_kwargs):
        return old_history

    async def active_branch(*_args, **_kwargs):
        return True

    async def build_messages(**_kwargs):
        if conversation.context_summary_text:
            return (
                [
                    Message(role=MessageRole.SYSTEM, content="system"),
                    Message(
                        role=MessageRole.USER,
                        content=(
                            f"{chat_context.CONTEXT_SUMMARY_PREFIX}\n\n"
                            f"{conversation.context_summary_text}"
                        ),
                    ),
                    current_user,
                    Message(role=MessageRole.ASSISTANT, content="active tool step"),
                ],
                [],
                set(),
            )
        return (
            [
                Message(role=MessageRole.SYSTEM, content="system"),
                Message(role=MessageRole.USER, content="old history"),
                Message(role=MessageRole.ASSISTANT, content="old answer"),
                current_user,
            ],
            [],
            set(),
        )

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        return "durable summary"

    def estimate(messages, *, model_id, provider):
        del model_id, provider
        return (
            9500
            if any(message.content == "old history" for message in messages)
            else 100
        )

    monkeypatch.setattr(
        chat_context.Conversation,
        "filter",
        lambda *_args, **_kwargs: UpdateQuery(),
    )
    monkeypatch.setattr(
        chat_context, "get_visible_conversation_messages", visible_history
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", active_branch)
    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)

    first_plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=10000,
        model_max_output_tokens=1000,
        current_user_message_id=current_user_id,
        include_current_user_message=True,
        protected_round_id=protected_round_id,
    )
    first_prepared = await first_plan.finalize()

    assert first_prepared.compression.stage == "macro"
    assert first_prepared.compression.summary_source_tokens == 9500
    assert first_prepared.compression.summary_result_tokens == 100
    assert first_prepared.compression.summary_saved_tokens == 9400
    assert summarize_calls == 1
    assert persisted_values["context_summary_text"] == "durable summary"
    assert persisted_values["context_summary_watermark_id"] == old_history[-1].id
    assert conversation.context_summary_watermark_id == old_history[-1].id

    second_plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=10000,
        model_max_output_tokens=1000,
        history_override=[
            {
                "role": "assistant",
                "content": "active tool step",
                "round_id": protected_round_id,
            }
        ],
        current_user_message_id=current_user_id,
        include_current_user_message=True,
        protected_round_id=protected_round_id,
    )

    assert second_plan.will_summarize is False
    assert summarize_calls == 1


@pytest.mark.anyio
async def test_over_input_budget_summarizes_before_hard_error(monkeypatch):
    agent = _agent()
    conversation = _conversation()
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old history"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
        Message(role=MessageRole.USER, content="current request"),
    ]
    summarize_calls = 0

    async def build_messages(**_kwargs):
        return messages, set(), []

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        return "durable summary"

    async def persist(**_kwargs):
        return None

    def estimate(items, *, model_id, provider):
        del model_id, provider
        return 8500 if any(item.content == "old history" for item in items) else 100

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    monkeypatch.setattr(chat_context, "_persist_context_summary", persist)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)

    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=10000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()

    assert plan.will_summarize is True
    assert prepared.compression.stage == "macro"
    assert prepared.compression.summary_source_tokens == 8500
    assert prepared.compression.summary_result_tokens == 100
    assert prepared.compression.summary_saved_tokens == 8400
    assert prepared.compression.after_tokens == 100
    assert summarize_calls == 1


@pytest.mark.anyio
async def test_summary_failure_logs_exception_details(monkeypatch, caplog):
    async def fail_team_chat(**_kwargs):
        raise TimeoutError()

    async def passthrough_wait_for(awaitable, *, timeout):
        del timeout
        return await awaitable

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(
        "app.llm.model_manager",
        SimpleNamespace(team_chat=fail_team_chat),
    )
    monkeypatch.setattr(chat_context.asyncio, "wait_for", passthrough_wait_for)
    monkeypatch.setattr(chat_context.asyncio, "sleep", no_sleep)
    caplog.set_level(logging.WARNING, logger="app.services.chat_context")

    with pytest.raises(BusinessError, match="context_summarization_failed"):
        await chat_context._summarize_context(
            agent=SimpleNamespace(team_id=uuid4()),
            conversation=SimpleNamespace(id=uuid4()),
            messages_to_summarize=[
                Message(role=MessageRole.USER, content="old history")
            ],
            model_id="model",
            tokenizer_model_id=None,
            provider=None,
            max_tokens=100,
            max_transcript_tokens=100,
        )

    assert "TimeoutError" in caplog.text
    assert "TimeoutError()" in caplog.text


def test_compression_sse_reports_replaced_segment_tokens(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config",
        lambda _agent: {"emit_sse_events": True},
    )
    compression = chat_context.CompressionMeta(
        stage="macro",
        before_tokens=90430,
        after_tokens=17049,
        input_budget=100000,
    )
    compression.summary_source_tokens = 89000
    compression.summary_result_tokens = 1200
    compression.summary_saved_tokens = 87800

    _, end_event = build_compression_events(
        agent=object(),
        compression=compression,
        trigger="proactive_threshold",
    )
    assert end_event is not None
    payload = json.loads(end_event.splitlines()[1].removeprefix("data: "))

    assert payload["before_tokens"] == 90430
    assert payload["after_tokens"] == 17049
    assert payload["summary_source_tokens"] == 89000
    assert payload["summary_result_tokens"] == 1200
    assert payload["summary_saved_tokens"] == 87800

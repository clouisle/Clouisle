from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.llm.types import (
    ContentPart,
    ContentType,
    FunctionCall,
    ImageContent,
    Message,
    MessageRole,
    ToolCall,
)
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context


def _data_url(mode: str = "RGB", size: tuple[int, int] = (2, 2)) -> str:
    source = io.BytesIO()
    Image.new(mode, size).save(source, format="PNG")
    encoded = base64.b64encode(source.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def _agent(**values):
    defaults = {
        "id": uuid4(),
        "team_id": uuid4(),
        "system_prompt": "prompt",
        "enable_memory": False,
        "tools_config": [],
        "context_compression_config": {},
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _conversation(**values):
    defaults = {
        "id": uuid4(),
        "variables": {},
        "context_summary_text": None,
        "context_summary_watermark_id": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_context_helper_boundaries_and_multimodal_variants():
    messages: list[Message] = []
    protected: set[int] = set()
    meta: list[dict] = []
    chat_context._append_message(
        messages,
        protected,
        Message(role=MessageRole.USER, content="protected"),
        protect=True,
        meta=meta,
        round_id="round-1",
        custom_flag=True,
    )
    assert protected == {0}
    assert meta[0]["custom_flag"] is True

    rgba = _data_url("RGBA", (3000, 2)).split(",", 1)[1]
    normalized, image_format = chat_context._normalize_vision_image(rgba, "png")
    assert image_format == "jpeg"
    with Image.open(io.BytesIO(base64.b64decode(normalized))) as image:
        assert image.mode == "RGB"

    content = chat_context.build_vision_content(
        "describe",
        [
            SimpleNamespace(url=None),
            {},
            {"url": "https://example.test/image.png"},
            {"url": _data_url()},
        ],
    )
    assert content[0].text == "describe"
    assert content[-2].type == ContentType.TEXT
    assert content[-1].type == ContentType.IMAGE
    assert content[-1].image is not None
    assert content[-1].image.base64 is not None

    refs = chat_context.build_uploaded_image_reference_text(
        [
            SimpleNamespace(url=None, base64="encoded"),
            {},
            {"url": "https://example.test/image.png"},
        ]
    )
    assert refs.count("available as a reference image") == 2


def test_context_text_json_and_media_helpers_cover_empty_and_fallbacks():
    assert chat_context._safe_json_loads(None) is None
    assert chat_context._safe_json_loads("not-json") is None
    assert chat_context._safe_json_loads("[]") is None
    assert chat_context._safe_json_loads('{"ok": true}') == {"ok": True}

    assert (
        chat_context._build_media_llm_summary(
            "image", {"kind": "media.image", "error": "bad"}
        )
        == "Image generation failed: bad"
    )
    assert (
        chat_context._build_media_llm_summary(
            "video", {"kind": "media.video", "status": "failed"}
        )
        == "Video generation failed: unknown error"
    )
    assert (
        chat_context._build_media_llm_summary(
            "video", {"kind": "media.video", "status": "pending"}
        )
        == "Video generation started. Task unknown is pending."
    )
    assert (
        chat_context._build_media_llm_summary(
            "video", {"kind": "media.video", "status": "completed"}
        )
        == "Video generation succeeded."
    )
    assert chat_context.summarize_tool_result_for_llm("tool", "plain") == "plain"

    assert chat_context._normalize_text(None) == ""
    assert chat_context._normalize_text(" a  b ") == "a b"
    assert chat_context._truncate_text(None, 4) == ""
    assert chat_context._truncate_text("short", 10) == "short"
    assert chat_context._truncate_text("one two three", 6).endswith("...")
    assert chat_context._limit_summary_text("short", 10) == "short"
    assert chat_context._limit_summary_text("abcdefgh", 5) == "ab..."

    parts = [
        ContentPart(type=ContentType.TEXT, text="text"),
        ContentPart(type=ContentType.TEXT),
        ContentPart(
            type=ContentType.IMAGE, image=ImageContent(url="https://example.test/a")
        ),
        ContentPart(type=ContentType.VIDEO),
    ]
    assert chat_context._stringify_content("plain") == "plain"
    assert chat_context._stringify_content(None) == ""
    assert chat_context._stringify_content([]) == ""
    assert chat_context._stringify_content(parts) == "text\n[image]"

    item = SimpleNamespace(value="assistant")
    assert chat_context._get_override_value({"role": "user"}, "role") == "user"
    assert chat_context._get_override_value(item, "role") is None
    assert chat_context._normalize_override_role(None) is None
    assert chat_context._normalize_override_role(item) == "assistant"
    assert chat_context._normalize_override_role("tool") == "tool"


def test_context_content_and_configuration_boundaries(monkeypatch):
    assert chat_context._build_current_user_content("", [{"url": None}], False) == ""
    assert (
        chat_context._append_file_content_to_user_content("", "file")
        == "<uploaded_files>\nfile\n</uploaded_files>"
    )
    assert chat_context._append_file_content_to_user_content([], "file")
    assert chat_context._append_file_content_to_user_content("text", None) == "text"
    assert chat_context._build_assistant_tool_calls(None) == (None, set())

    calls, ids = chat_context._build_assistant_tool_calls(
        [
            {"id": "dict", "name": "read", "arguments": {"path": "a"}},
            {"id": "json", "name": "write", "arguments": '{"x": 1}'},
        ]
    )
    assert ids == {"dict", "json"}
    assert calls[0].function.arguments == '{"path": "a"}'
    assert calls[1].function.arguments == '{"x": 1}'

    message = Message(role=MessageRole.USER, content="x")
    payload = chat_context._message_to_token_payload(message)
    assert payload["role"] == "user"
    monkeypatch.setattr(chat_context, "count_message_tokens", lambda *args, **kwargs: 7)
    assert chat_context._estimate_message_tokens([message], None, None) == 7

    assert (
        chat_context.get_context_compression_config(
            _agent(context_compression_config=[])
        )["enabled"]
        is True
    )
    assert (
        chat_context._build_token_budget(
            context_limit=10_000,
            model_max_output_tokens=512,
        ).input_budget
        > 0
    )


@pytest.mark.anyio
async def test_file_content_short_circuit_and_wrapper_delegation(monkeypatch):
    agent = _agent()
    assert (
        await chat_context._build_file_content_for_user_message(
            agent=agent,
            file_urls=None,
            legacy_files=None,
            user_locale=None,
            tool_timeouts=None,
            user=None,
        )
        == ""
    )

    async def fake_build(**kwargs):
        assert kwargs["file_urls"] == ["a"]
        return "parsed", None

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        fake_build,
    )
    assert (
        await chat_context._build_file_content_for_user_message(
            agent=agent,
            file_urls=["a"],
            legacy_files=["legacy"],
            user_locale="en",
            tool_timeouts={"read": 1},
            user=SimpleNamespace(id="u"),
        )
        == "parsed"
    )

    delegated = []

    async def fake_build_messages(**kwargs):
        delegated.append(kwargs)
        return [Message(role=MessageRole.USER, content="delegated")], set(), []

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", fake_build_messages
    )
    result = await chat_context.build_model_messages(
        agent=agent,
        conversation=_conversation(),
        user_message="q",
    )
    assert result[0].content == "delegated"
    assert delegated[0]["user_message"] == "q"


@pytest.mark.anyio
async def test_prepare_model_context_delegates_plan_finalization(monkeypatch):
    expected = SimpleNamespace(messages=["prepared"])

    class Plan:
        async def finalize(self):
            return expected

    async def fake_plan(**kwargs):
        assert kwargs["model_id"] == "model"
        return Plan()

    monkeypatch.setattr(chat_context, "build_context_plan", fake_plan)
    result = await chat_context.prepare_model_context(
        agent=_agent(),
        conversation=_conversation(),
        user_message="q",
        model_id="model",
        model_context_limit=1_000,
        model_max_output_tokens=100,
    )
    assert result is expected


@pytest.mark.anyio
async def test_override_history_builds_summary_protocol_and_current_user(monkeypatch):
    monkeypatch.setattr(chat_context, "_build_system_prompt", lambda **kwargs: "sys")
    round_id = uuid4()
    history = [
        {"role": "user", "content": "old", "round_id": uuid4()},
        {
            "role": "assistant",
            "content": "answer",
            "reasoning_content": "think",
            "round_id": round_id,
            "tool_calls": [{"id": "call-1", "name": "lookup", "arguments": {"q": "x"}}],
        },
        {
            "role": "tool",
            "content": '{"result": "ok"}',
            "round_id": round_id,
            "tool_call_id": "call-1",
            "tool_name": "lookup",
        },
        {
            "role": "tool",
            "content": "ignored",
            "round_id": round_id,
            "tool_call_id": "missing",
            "tool_name": "lookup",
        },
    ]
    messages, protected, meta = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        file_content=None,
        user_locale="en",
        history_override=history,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=round_id,
    )
    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[2].content == "current"
    assert messages[-1].content == '{"result": "ok"}'
    assert protected
    assert len(meta) == len(messages)


@pytest.mark.anyio
async def test_database_history_paths_and_active_round_delta(monkeypatch):
    monkeypatch.setattr(chat_context, "_build_system_prompt", lambda **kwargs: "sys")
    current_id = uuid4()
    old_round = uuid4()
    current_round = uuid4()
    assistant = SimpleNamespace(
        id=uuid4(),
        role=ConversationMessageRole.ASSISTANT,
        content="assistant",
        reasoning_content="reasoning",
        tool_calls=[{"id": "call-1", "name": "lookup", "arguments": "{}"}],
        round_id=old_round,
        round_role=None,
        is_round_canonical=False,
    )
    tool = SimpleNamespace(
        id=uuid4(),
        role=ConversationMessageRole.TOOL,
        content="tool result",
        tool_name="lookup",
        tool_call_id="call-1",
        round_id=old_round,
        round_role=None,
        is_round_canonical=False,
    )
    invalid_tool = SimpleNamespace(
        id=uuid4(),
        role=ConversationMessageRole.TOOL,
        content="invalid",
        tool_name="lookup",
        tool_call_id="bad",
        round_id=old_round,
        round_role=None,
        is_round_canonical=False,
    )
    current = SimpleNamespace(
        id=current_id,
        role=ConversationMessageRole.USER,
        content="stored current",
        file_urls=None,
        round_id=current_round,
        round_role=None,
        is_round_canonical=True,
    )
    old_user = SimpleNamespace(
        id=uuid4(),
        role=ConversationMessageRole.USER,
        content="old user",
        file_urls=None,
        round_id=old_round,
        round_role=None,
        is_round_canonical=True,
    )
    rows = [old_user, current, assistant, tool, invalid_tool]

    async def visible(_conversation_id, **kwargs):
        assert kwargs["exclude_message_ids"] is None
        return rows

    async def visible_after(_conversation_id, **kwargs):
        return None

    monkeypatch.setattr(chat_context, "get_visible_conversation_messages", visible)
    monkeypatch.setattr(
        chat_context, "get_visible_conversation_messages_after", visible_after
    )
    messages, _, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="new current",
        file_content=None,
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=current_id,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        history_after_message_id=current_id,
    )
    assert messages[-1].content == "new current"
    assert any(message.tool_call_id == "call-1" for message in messages)

    active_rows = [old_user]

    async def visible_active(_conversation_id, **kwargs):
        return active_rows

    monkeypatch.setattr(
        chat_context, "get_visible_conversation_messages", visible_active
    )
    active_override = [
        {
            "role": "assistant",
            "content": "active",
            "round_id": current_round,
            "tool_calls": [{"id": "active-call", "name": "lookup", "arguments": {}}],
        },
        {
            "role": "tool",
            "content": "active result",
            "round_id": current_round,
            "tool_call_id": "active-call",
            "tool_name": "lookup",
        },
    ]
    messages, _, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="active current",
        file_content=None,
        user_locale="en",
        history_override=active_override,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=current_round,
    )

    assert any(message.content == "active" for message in messages)
    assert any(message.tool_call_id == "active-call" for message in messages)


def test_context_rendering_and_token_boundaries(monkeypatch):
    messages: list[Message] = []
    protected: set[int] = set()
    chat_context._append_message(
        messages,
        protected,
        Message(role=MessageRole.USER, content="no metadata"),
        meta=None,
    )
    assert messages[0].content == "no metadata"
    assert protected == set()

    assert (
        chat_context.get_context_compression_config(
            _agent(context_compression_config="invalid")
        )["enabled"]
        is True
    )

    monkeypatch.setattr(chat_context, "count_tokens", lambda *_args, **_kwargs: 10)
    assert chat_context.truncate_text_to_tokens("", max_tokens=2) == ("", False)
    truncated, was_truncated = chat_context.truncate_text_to_tokens(
        "abcdefghij", max_tokens=2
    )
    assert was_truncated is True
    assert "truncated" in truncated

    transcript = chat_context._render_summary_transcript(
        [
            Message(role=MessageRole.TOOL, name="lookup", content=""),
            Message(
                role=MessageRole.ASSISTANT,
                content="assistant text",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function=FunctionCall(name="lookup", arguments="{}"),
                    )
                ],
            ),
        ]
    )
    assert "TOOL result for lookup:\n(empty)" in transcript
    assert "ASSISTANT tool calls: lookup({})\nassistant text" in transcript


def test_context_round_selection_and_completion_boundaries(monkeypatch):
    system = Message(role=MessageRole.SYSTEM, content="system")
    old = Message(role=MessageRole.USER, content="old")
    current = Message(role=MessageRole.USER, content="current")
    messages = [system, old, current]
    same_round_meta = [
        {"role": "system", "round_id": None},
        {"role": "user", "round_id": "round"},
        {"role": "user", "round_id": "round"},
    ]
    cut = chat_context._select_summary_cut_index(
        messages,
        same_round_meta,
        2,
        0,
        tokenizer_model_id=None,
        provider=None,
    )
    assert cut == 2
    assert (
        chat_context._select_summary_cut_index(
            messages,
            same_round_meta,
            1,
            0,
            tokenizer_model_id=None,
            provider=None,
        )
        == 1
    )

    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *_args, **_kwargs: 10
    )
    assert (
        chat_context._select_summary_cut_index(
            messages,
            same_round_meta,
            2,
            10,
            tokenizer_model_id=None,
            provider=None,
        )
        == 1
    )

    assert (
        chat_context._round_is_complete(
            [{"role": "assistant", "tool_calls": [{"id": ""}]}]
        )
        is True
    )
    assert (
        chat_context._round_is_complete([{"role": "tool", "tool_call_id": ""}]) is True
    )
    assert (
        chat_context._round_is_complete(
            [
                {"role": "assistant", "tool_calls": [{"id": "call-1"}]},
                {"role": "tool", "tool_call_id": "call-1"},
            ]
        )
        is True
    )
    assert (
        chat_context._round_is_complete(
            [{"role": "assistant", "tool_calls": [{"id": "call-1"}]}]
        )
        is False
    )


@pytest.mark.anyio
async def test_context_summary_success_retry_and_empty_transcript(monkeypatch):
    assert (
        await chat_context._summarize_context(
            agent=SimpleNamespace(team_id=uuid4()),
            conversation=SimpleNamespace(id=uuid4()),
            messages_to_summarize=[],
            model_id="model",
            tokenizer_model_id=None,
            provider=None,
            max_tokens=20,
            max_transcript_tokens=20,
        )
        is None
    )

    responses = [SimpleNamespace(content=""), SimpleNamespace(content="summary")]
    calls = []

    async def team_chat(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    async def wait_for(awaitable, *, timeout):
        del timeout
        return await awaitable

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("app.llm.model_manager", SimpleNamespace(team_chat=team_chat))
    monkeypatch.setattr(chat_context.asyncio, "wait_for", wait_for)
    monkeypatch.setattr(chat_context.asyncio, "sleep", no_sleep)
    result = await chat_context._summarize_context(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        messages_to_summarize=[Message(role=MessageRole.USER, content="new")],
        model_id="model",
        tokenizer_model_id=None,
        provider=None,
        max_tokens=20,
        max_transcript_tokens=20,
        previous_summary="previous",
    )
    assert result == "summary"
    assert len(calls) == 2
    assert "Previous summary:" in calls[0]["messages"][1].content


@pytest.mark.anyio
async def test_context_summary_persistence_handles_current_and_empty_history(
    monkeypatch,
):
    updates = []

    class Query:
        async def update(self, **values):
            updates.append(values)

    monkeypatch.setattr(
        chat_context.Conversation,
        "filter",
        lambda *_args, **_kwargs: Query(),
    )
    history_row = SimpleNamespace(id=uuid4())
    visible_calls = 0

    async def visible(*_args, **_kwargs):
        nonlocal visible_calls
        visible_calls += 1
        return [history_row] if visible_calls == 1 else []

    monkeypatch.setattr(chat_context, "get_visible_conversation_messages", visible)
    conversation = _conversation()
    current_id = uuid4()
    await chat_context._persist_context_summary(
        conversation=conversation,
        summary_text="summary",
        current_user_message_id=current_id,
        exclude_message_ids=[uuid4()],
        history_before_message_created_at=None,
    )
    assert updates[0]["context_summary_text"] == "summary"
    assert conversation.context_summary_watermark_id == history_row.id

    await chat_context._persist_context_summary(
        conversation=conversation,
        summary_text="empty",
        current_user_message_id=None,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )
    assert len(updates) == 1


@pytest.mark.anyio
async def test_context_message_builder_covers_summary_active_delta_and_unknown_roles(
    monkeypatch,
):
    monkeypatch.setattr(chat_context, "_build_system_prompt", lambda **_kwargs: "sys")
    current_id = uuid4()
    round_id = uuid4()
    current = SimpleNamespace(
        id=current_id,
        role=ConversationMessageRole.USER,
        content="stored",
        file_urls=None,
        round_id=round_id,
        round_role=None,
        is_round_canonical=True,
    )

    async def visible(*_args, **_kwargs):
        return [current]

    monkeypatch.setattr(chat_context, "get_visible_conversation_messages", visible)
    messages, _, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        file_content=None,
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=current_id,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        context_summary_text="old summary",
    )
    assert messages[1].content.startswith(chat_context.CONTEXT_SUMMARY_PREFIX)
    assert messages[-1].content == "current"

    monkeypatch.setattr(
        chat_context, "_history_override_is_active_delta", lambda *_args: True
    )
    active_override = [
        {"role": "user", "content": "ignored", "round_id": round_id},
        {
            "role": "assistant",
            "content": "active",
            "round_id": round_id,
            "tool_calls": [{"id": "active-call", "name": "lookup", "arguments": {}}],
        },
        {
            "role": "tool",
            "content": "missing result",
            "round_id": round_id,
            "tool_call_id": "missing-call",
            "tool_name": "lookup",
        },
        {"role": "other", "content": "ignored", "round_id": round_id},
    ]
    messages, _, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="active current",
        file_content=None,
        user_locale="en",
        history_override=active_override,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=round_id,
    )
    assert any(message.content == "active" for message in messages)
    assert any(message.content == "active current" for message in messages)

    monkeypatch.setattr(
        chat_context, "_history_override_is_active_delta", lambda *_args: False
    )
    inactive_override = [{"role": "other", "content": "ignored"}]
    messages, _, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="fallback current",
        file_content=None,
        user_locale="en",
        history_override=inactive_override,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )
    assert messages[-1].content == "fallback current"


@pytest.mark.anyio
async def test_context_plan_watermark_and_finalize_no_summary_paths(monkeypatch):
    system = Message(role=MessageRole.SYSTEM, content="system")
    current = Message(role=MessageRole.USER, content="current")

    async def build_messages(**_kwargs):
        return (
            [system, current],
            set(),
            [
                {"role": "system", "round_id": None},
                {"role": "user", "round_id": None},
            ],
        )

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *_args, **_kwargs: 10
    )
    disabled = await chat_context.build_context_plan(
        agent=_agent(context_compression_config={"enabled": False}),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
    )
    prepared = await disabled.finalize()
    assert prepared.compression.stage == "none"
    assert disabled._new_watermark_id is None

    conversation = _conversation(
        context_summary_text="stored",
        context_summary_watermark_id=uuid4(),
    )
    monkeypatch.setattr(
        chat_context, "is_message_on_active_branch", lambda **_kwargs: False
    )
    invalid_watermark = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=conversation,
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
    )
    assert invalid_watermark.previous_summary_text is None

    watermark_plan = object.__new__(chat_context.ContextPlan)
    watermark_plan.summarized = [current]
    watermark_plan.tail_start_index = 2
    watermark_plan.meta = [{}, {}, {"source_message_id": None}]
    assert watermark_plan._new_watermark_id is None


@pytest.mark.anyio
async def test_context_plan_finalize_keeps_messages_when_summary_is_empty(monkeypatch):
    system = Message(role=MessageRole.SYSTEM, content="system")
    old = Message(role=MessageRole.USER, content="old")
    current = Message(role=MessageRole.USER, content="current")
    meta = [
        {"role": "system", "round_id": None, "source_message_id": None},
        {"role": "user", "round_id": "old", "source_message_id": None},
        {"role": "user", "round_id": "current", "source_message_id": None},
    ]

    async def build_messages(**_kwargs):
        return [system, old, current], set(), meta

    estimate_calls = 0

    def estimate(messages, **_kwargs):
        nonlocal estimate_calls
        if any(message.content == "old" for message in messages):
            estimate_calls += 1
            return 8_500 if estimate_calls == 1 else 100
        return 100

    async def no_summary(**_kwargs):
        return None

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)
    monkeypatch.setattr(
        chat_context, "_select_summary_cut_index", lambda *_args, **_kwargs: 2
    )
    monkeypatch.setattr(chat_context, "_summarize_context", no_summary)
    plan = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()
    assert plan.will_summarize is True
    assert [message.content for message in prepared.messages] == [
        "system",
        "old",
        "current",
    ]


@pytest.mark.anyio
async def test_context_finalize_persists_summary_and_rejects_over_budget(monkeypatch):
    system = Message(role=MessageRole.SYSTEM, content="system")
    old = Message(role=MessageRole.USER, content="old")
    current = Message(role=MessageRole.USER, content="current")
    source_id = uuid4()
    meta = [
        {"role": "system", "round_id": None, "source_message_id": None},
        {"role": "user", "round_id": "old", "source_message_id": source_id},
        {"role": "user", "round_id": "current", "source_message_id": None},
    ]

    async def build_messages(**_kwargs):
        return [system, old, current], set(), meta

    estimates = []

    def estimate(messages, **_kwargs):
        estimates.append([message.content for message in messages])
        if any(message.content == "old" for message in messages):
            return 9_000
        if any(
            isinstance(message.content, str)
            and message.content.startswith(chat_context.CONTEXT_SUMMARY_PREFIX)
            for message in messages
        ):
            return 2_000
        return 100

    async def summarize(**_kwargs):
        return "summary"

    persisted = []

    async def persist(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)
    monkeypatch.setattr(
        chat_context, "_select_summary_cut_index", lambda *_args, **_kwargs: 2
    )
    monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    monkeypatch.setattr(chat_context, "_persist_context_summary", persist)
    plan = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()
    assert prepared.compression.stage == "macro"
    assert persisted[0]["watermark_message_id"] == source_id

    oversized = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
    )

    def too_large(messages, **_kwargs):
        return 10_000

    monkeypatch.setattr(chat_context, "_estimate_message_tokens", too_large)
    with pytest.raises(chat_context.ContextLengthError, match="protected payload"):
        await oversized.finalize()


def test_context_render_transcript_handles_tool_call_without_function():
    message = Message(role=MessageRole.ASSISTANT, content="text", tool_calls=[])
    assert chat_context._render_summary_transcript([message]) == "ASSISTANT:\ntext"


def test_context_summary_transcript_omits_empty_optional_parts():
    transcript = chat_context._render_summary_transcript(
        [
            Message(role=MessageRole.TOOL, content=""),
            Message(
                role=MessageRole.ASSISTANT,
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function=FunctionCall(name="lookup", arguments="{}"),
                    )
                ],
            ),
        ]
    )
    assert "TOOL result:\n(empty)" in transcript
    assert "ASSISTANT tool calls: lookup({})" in transcript
    assert "ASSISTANT tool calls: lookup({})\n" not in transcript


@pytest.mark.anyio
async def test_context_summary_skips_override_persistence_and_reports_over_budget(
    monkeypatch,
):
    system = Message(role=MessageRole.SYSTEM, content="system")
    old = Message(role=MessageRole.USER, content="old")
    current = Message(role=MessageRole.USER, content="current")
    meta = [
        {"role": "system", "round_id": None, "source_message_id": None},
        {"role": "user", "round_id": "old", "source_message_id": uuid4()},
        {"role": "user", "round_id": "current", "source_message_id": None},
    ]

    async def build_messages(**_kwargs):
        return [system, old, current], set(), meta

    summary_tokens = 2_000

    def estimate(messages, **_kwargs):
        if any(message.content == "old" for message in messages):
            return 9_000
        if any(
            isinstance(message.content, str)
            and message.content.startswith(chat_context.CONTEXT_SUMMARY_PREFIX)
            for message in messages
        ):
            return summary_tokens
        return 100

    async def summarize(**_kwargs):
        return "summary"

    async def fail_if_persisted(**_kwargs):
        raise AssertionError("history overrides must not persist summaries")

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)
    monkeypatch.setattr(
        chat_context, "_select_summary_cut_index", lambda *_args, **_kwargs: 2
    )
    monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    monkeypatch.setattr(chat_context, "_persist_context_summary", fail_if_persisted)
    override = [{"role": "user", "content": "request"}]

    plan = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        history_override=override,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()
    assert prepared.compression.stage == "macro"

    summary_tokens = 9_000
    over_budget = await chat_context.build_context_plan(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        history_override=override,
        include_current_user_message=True,
    )
    with pytest.raises(chat_context.ContextLengthError, match="after context summary"):
        await over_budget.finalize()

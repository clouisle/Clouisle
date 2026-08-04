import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

from app.llm.errors import ContextLengthError
from app.llm.types import (
    ContentPart,
    ContentType,
    FunctionCall,
    Message,
    MessageRole,
    ToolCall,
)
from app.services import chat_context


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "system_prompt": "Hello {{name}} {{query}}",
        "enable_memory": False,
        "enable_user_input_request": False,
        "tools_config": [],
        "context_compression_config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={"name": "Ada"})


def test_language_prompt_and_small_helpers_cover_fallbacks():
    instruction = chat_context.get_language_instruction("ZH-cn")
    assert "中文" in instruction
    assert chat_context.get_language_instruction("unknown").startswith(
        "## Response Language"
    )
    assert chat_context.build_system_prompt_with_language(None, "en").startswith(
        "## Response"
    )
    assert (
        chat_context.build_system_prompt_with_language(instruction, "zh") == instruction
    )
    assert chat_context.get_user_input_request_instruction("zh").startswith("## 用户")
    assert chat_context._append_prompt_section("base", "  ") == "base"
    assert chat_context._append_prompt_section("", " section ") == "section"
    assert chat_context._normalize_text(None) == ""
    assert chat_context._normalize_text(" a\n b ") == "a b"
    assert chat_context._truncate_text("abcdef", 5) == "ab..."
    assert chat_context._limit_summary_text("abcdef", 5) == "ab..."
    assert chat_context._safe_json_loads(None) is None
    assert chat_context._safe_json_loads("[") is None
    assert chat_context._safe_json_loads("[]") is None
    assert chat_context._get_override_value({"x": 1}, "x") == 1
    assert chat_context._get_override_value(SimpleNamespace(x=2), "x") == 2
    assert chat_context._normalize_override_role(None) is None
    assert chat_context._normalize_override_role(MessageRole.USER) == "user"


def test_system_prompt_adds_memory_and_user_input_sections():
    prompt = chat_context._build_system_prompt(
        _agent(enable_memory=True, enable_user_input_request=True),
        _conversation(),
        "question",
        "zh",
    )

    assert "Hello Ada question" in prompt
    assert "## Memory System" in prompt
    assert "## 用户输入请求功能" in prompt


def test_vision_helpers_cover_invalid_transparent_remote_and_missing_images():
    assert chat_context._normalize_vision_image("not-base64", None) == (
        "not-base64",
        "png",
    )

    source = io.BytesIO()
    Image.new("RGBA", (2050, 1), (255, 0, 0, 128)).save(source, format="PNG")
    encoded = base64.b64encode(source.getvalue()).decode()
    normalized, image_format = chat_context._normalize_vision_image(encoded, "png")
    assert image_format == "jpeg"
    assert normalized != encoded

    content = chat_context.build_vision_content(
        "look", [{}, SimpleNamespace(url=None), {"url": "https://example.test/a.png"}]
    )
    assert len(content) == 3
    assert content[-1].image.url == "https://example.test/a.png"
    assert chat_context.build_uploaded_image_reference_text(
        [{}, {"base64": "abc"}, SimpleNamespace(url="remote")]
    ).splitlines() == [
        "Uploaded image #2: available as a reference image.",
        "Uploaded image #3: available as a reference image.",
    ]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"kind": "media.image", "error": "bad"}, "Image generation failed: bad"),
        (
            {"kind": "media.image", "images": [{}], "model": "m"},
            "Generated 1 image using model m",
        ),
        (
            {"kind": "media.video", "status": "failed"},
            "Video generation failed: unknown error",
        ),
        (
            {"kind": "media.video", "status": "processing", "task_id": "t"},
            "Task t is processing",
        ),
        (
            {"kind": "media.video", "status": "done", "model": "m"},
            "Video generation succeeded using model m",
        ),
        (
            {"result": {"type": "skill_instructions", "skill": {"name": "S"}}},
            "Skill instructions for S were loaded",
        ),
    ],
)
def test_tool_result_summary_matrix(payload, expected):
    result = chat_context.summarize_tool_result_for_llm(
        None, chat_context.json.dumps(payload)
    )
    assert expected in result


def test_tool_result_summary_preserves_unrecognized_content():
    assert chat_context.summarize_tool_result_for_llm(None, "plain") == "plain"
    raw = '{"other": true}'
    assert chat_context.summarize_tool_result_for_llm(None, raw) == raw
    assert chat_context._build_skill_llm_summary({"result": "bad"}) is None
    assert chat_context._build_media_llm_summary(None, {}) is None


def test_file_content_and_content_string_helpers_cover_edges():
    short = "short"
    assert chat_context._trim_file_content(short) == (short, False)
    trimmed, changed = chat_context._trim_file_content("x" * 17000, aggressive=True)
    assert changed and "file content trimmed" in trimmed
    assert chat_context._append_file_content_to_user_content("", " data ").startswith(
        "<uploaded_files>"
    )
    parts = [
        ContentPart(type=ContentType.TEXT, text="text"),
        ContentPart(type=ContentType.IMAGE, image={"url": "https://example.test/i"}),
    ]
    appended = chat_context._append_file_content_to_user_content(parts, "data")
    assert len(appended) == 3
    assert chat_context._stringify_content(None) == ""
    assert chat_context._stringify_content(parts) == "text\n[image]"


def test_tool_call_building_and_turn_summaries_cover_role_matrix():
    calls, ids = chat_context._build_assistant_tool_calls(
        [{"id": "call", "name": "search", "arguments": {"q": "x"}}]
    )
    assert ids == {"call"}
    assert calls[0].function.arguments == '{"q": "x"}'
    assert chat_context._build_assistant_tool_calls(None) == (None, set())

    block = [
        Message(role=MessageRole.USER, content="question"),
        Message(
            role=MessageRole.ASSISTANT,
            content="answer",
            tool_calls=[
                ToolCall(
                    id="call",
                    type="function",
                    function=FunctionCall(name="search", arguments="{}"),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content="result", tool_call_id="call"),
    ]
    summary = chat_context._summarize_block(block)
    assert "User asked" in summary
    assert "Assistant responded" in summary
    assert "Tools involved" in summary
    assert "Tool outcomes" in summary
    assert chat_context._summarize_block([Message(role=MessageRole.ASSISTANT)]) == (
        "Conversation turn preserved in compact summary."
    )
    assert chat_context._build_macro_summary_message([]) is None


def test_budget_pressure_and_reasoning_compaction_matrix():
    budget = chat_context._build_token_budget(
        context_limit=None,
        model_max_output_tokens=None,
        output_token_reserve=4000,
        safety_margin_tokens=1000,
    )
    assert budget.context_limit == chat_context.DEFAULT_CONTEXT_LIMIT
    thresholds = chat_context._build_compression_thresholds(
        token_budget=chat_context.TokenBudget(100, 0, 0, 100),
        warning_ratio=0.5,
        trigger_ratio=0.7,
        blocking_ratio=0.9,
    )
    assert [
        chat_context._assess_context_pressure(
            before_tokens=value,
            token_budget=chat_context.TokenBudget(100, 0, 0, 100),
            thresholds=thresholds,
        )
        for value in (10, 50, 70, 90, 101)
    ] == ["normal", "warning", "auto_compact", "blocking", "over_budget"]

    messages = [
        Message(role=MessageRole.ASSISTANT, reasoning_content="old"),
        Message(role=MessageRole.ASSISTANT, reasoning_content="new"),
    ]
    compacted, trimmed, protected = chat_context._compact_message_reasoning(
        messages, keep_recent_reasoning_messages=0, protected_indexes={1}
    )
    assert trimmed is True
    assert compacted[0].reasoning_content is None
    assert compacted[1].reasoning_content == "new"
    assert protected == {1}


@pytest.mark.anyio
async def test_session_memory_failures_clone_messages(monkeypatch):
    messages = [Message(role=MessageRole.USER, content="hello")]
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="m",
        provider=None,
        protected_indexes={0},
    )
    assert changed is False
    assert protected == {0}
    assert compacted == messages and compacted is not messages


@pytest.mark.anyio
async def test_file_content_builder_skips_empty_and_unchanged_metadata(monkeypatch):
    assert (
        await chat_context._build_file_content_for_user_message(
            agent=_agent(),
            file_urls=None,
            user_locale=None,
            tool_timeouts=None,
            user=None,
        )
        == ""
    )

    source = SimpleNamespace(file_urls=[{"url": "same"}], save=AsyncMock())
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("content", source.file_urls)),
    )
    assert (
        await chat_context._build_file_content_for_user_message(
            agent=_agent(),
            file_urls=source.file_urls,
            user_locale=None,
            tool_timeouts=None,
            user=None,
            source_message=source,
        )
        == "content"
    )
    source.save.assert_not_awaited()


@pytest.mark.anyio
async def test_retry_prepare_model_context_enables_aggressive_mode():
    prepared = MagicMock()
    with patch(
        "app.services.chat_context.prepare_model_context",
        new=AsyncMock(return_value=prepared),
    ) as prepare:
        assert (
            await chat_context.retry_prepare_model_context(
                agent=_agent(),
                conversation=_conversation(),
                user_message="hi",
                model_id="m",
                model_context_limit=100,
                model_max_output_tokens=10,
            )
            is prepared
        )
    assert prepare.await_args.kwargs["aggressive"] is True


@pytest.mark.anyio
async def test_emergency_fallback_raises_when_protected_context_still_exceeds_budget(
    monkeypatch,
):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="current"),
    ]
    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        AsyncMock(return_value=(messages, {1})),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        AsyncMock(return_value=(messages, False, {1})),
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 100
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_micro_compaction",
        AsyncMock(
            return_value=(
                messages,
                chat_context.CompressionMeta("micro", 100, 100, 1, actions=[]),
                {1},
            )
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_budget_compaction",
        lambda **kwargs: (kwargs["messages"], kwargs["compression"], {1}),
    )

    with pytest.raises(ContextLengthError):
        await chat_context.prepare_model_context(
            agent=_agent(
                context_compression_config={
                    "output_token_reserve": 1,
                    "safety_margin_tokens": 1,
                    "checkpoint_summary_enabled": False,
                }
            ),
            conversation=_conversation(),
            user_message="current",
            model_id="m",
            model_context_limit=3,
            model_max_output_tokens=1,
            protected_round_id="round",
        )

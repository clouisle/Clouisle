import base64
import io
from enum import Enum
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.llm.types import ContentPart, ContentType, Message, MessageRole
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


def test_prompt_and_content_helper_fallback_branches():
    instruction = chat_context.get_language_instruction("FR-ca")
    assert instruction == chat_context.LANGUAGE_INSTRUCTIONS["en"]
    assert chat_context.build_system_prompt_with_language(None, "zh").startswith(
        "## 回复语言"
    )
    assert (
        chat_context.build_system_prompt_with_language(instruction, "en") == instruction
    )
    assert "用户输入请求功能" in chat_context.get_user_input_request_instruction("zh")

    prompt = chat_context._build_system_prompt(
        _agent(enable_memory=True, enable_user_input_request=True),
        _conversation(),
        "question",
        "zh",
    )
    assert "Ada question" in prompt
    assert "## Memory System" in prompt
    assert "## 用户输入请求功能" in prompt

    assert chat_context._append_prompt_section("base", "  ") == "base"
    assert chat_context._append_prompt_section("", "section") == "section"
    assert chat_context._append_file_content_to_user_content("", " data ") == (
        "<uploaded_files>\ndata\n</uploaded_files>"
    )


def test_image_and_text_helper_edge_branches():
    class ImageObject:
        url = "https://example.com/image.png"

    content = chat_context.build_vision_content(
        "look",
        [{}, ImageObject(), {"url": "not-an-image-data-url"}],
    )
    assert [part.type for part in content].count(ContentType.IMAGE) == 2
    assert content[2].image.url == "https://example.com/image.png"

    assert chat_context.build_uploaded_image_reference_text(
        [SimpleNamespace(base64="abc"), {}, {"base64": "def"}]
    ).splitlines() == [
        "Uploaded image #1: available as a reference image.",
        "Uploaded image #3: available as a reference image.",
    ]
    assert chat_context._normalize_vision_image("invalid", None) == ("invalid", "png")

    source = io.BytesIO()
    Image.new("RGBA", (2050, 1), (255, 0, 0, 100)).save(source, format="PNG")
    normalized, image_format = chat_context._normalize_vision_image(
        base64.b64encode(source.getvalue()).decode(), "png"
    )
    assert image_format == "jpeg"
    with Image.open(io.BytesIO(base64.b64decode(normalized))) as image:
        assert image.mode == "RGB"

    parts = [
        ContentPart(type=ContentType.TEXT, text="text"),
        ContentPart(type=ContentType.IMAGE),
    ]
    assert chat_context._stringify_content(parts) == "text\n[image]"
    assert chat_context._stringify_content(None) == ""
    assert chat_context._truncate_text(" a   long value ", 9) == "a long..."
    assert chat_context._limit_summary_text("abcdef", 5) == "ab..."


def test_json_tool_and_config_helper_branches():
    assert chat_context._safe_json_loads(None) is None
    assert chat_context._safe_json_loads("[]") is None
    assert chat_context._safe_json_loads("{") is None
    assert chat_context.summarize_tool_result_for_llm(None, "plain") == "plain"

    calls, ids = chat_context._build_assistant_tool_calls(
        [
            {"id": "one", "name": "search", "arguments": {"q": "x"}},
            {"name": "empty", "arguments": "{}"},
        ]
    )
    assert calls is not None
    assert calls[0].function.arguments == '{"q": "x"}'
    assert ids == {"one", ""}
    assert chat_context._build_assistant_tool_calls([]) == (None, set())

    assert chat_context.get_context_compression_config(
        _agent(context_compression_config="invalid")
    )["enabled"]
    assert not chat_context.get_context_compression_config(
        _agent(context_compression_config={"enabled": False})
    )["enabled"]

    class Role(Enum):
        USER = "user"

    assert chat_context._get_override_value({"key": 1}, "key") == 1
    assert chat_context._get_override_value(SimpleNamespace(key=2), "key") == 2
    assert chat_context._normalize_override_role(None) is None
    assert chat_context._normalize_override_role(Role.USER) == "user"


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (101, "over_budget"),
        (92, "blocking"),
        (80, "auto_compact"),
        (70, "warning"),
        (69, "normal"),
    ],
)
def test_context_pressure_levels(tokens, expected):
    budget = chat_context.TokenBudget(100, 0, 0, 100)
    thresholds = chat_context._build_compression_thresholds(
        token_budget=budget,
        warning_ratio=0.7,
        trigger_ratio=0.8,
        blocking_ratio=0.92,
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=tokens,
            token_budget=budget,
            thresholds=thresholds,
        )
        == expected
    )


def test_turn_splitting_summaries_and_reasoning_compaction():
    assert chat_context._split_turn_blocks([]) == ([], [], [], [])
    messages = [
        Message(role=MessageRole.ASSISTANT, content="orphan"),
        Message(role=MessageRole.USER, content="ask"),
        Message(role=MessageRole.ASSISTANT, content="answer", reasoning_content="old"),
        Message(role=MessageRole.USER, content="next"),
        Message(role=MessageRole.ASSISTANT, content=None, reasoning_content="recent"),
    ]
    prefix, _, blocks, _ = chat_context._split_turn_blocks(messages)
    assert prefix == []
    assert len(blocks) == 3

    compacted, trimmed, protected = chat_context._compact_message_reasoning(
        messages, keep_recent_reasoning_messages=0, protected_indexes={2}
    )
    assert trimmed
    assert compacted[2].reasoning_content == "old"
    assert compacted[4].reasoning_content is None
    assert protected == {2}

    summary = chat_context._summarize_block(
        [
            Message(role=MessageRole.USER, content="ask"),
            Message(role=MessageRole.ASSISTANT, content="answer"),
            Message(role=MessageRole.TOOL, content="result", tool_call_id="call-1"),
        ]
    )
    assert "User asked: ask" in summary
    assert "Assistant responded: answer" in summary
    assert "Tools involved: call-1" in summary
    assert "Tool outcomes: result" in summary
    assert chat_context._summarize_block([Message(role=MessageRole.SYSTEM)]) == (
        "Conversation turn preserved in compact summary."
    )
    assert chat_context._build_macro_summary_message([]) is None


@pytest.mark.anyio
async def test_override_inserts_and_protects_current_round():
    round_id = uuid4()
    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "calling",
                "round_id": round_id,
                "tool_calls": [{"id": "call-1", "name": "search", "arguments": {}}],
            },
            {
                "role": "tool",
                "content": "result",
                "round_id": round_id,
                "tool_call_id": "call-1",
            },
            {"role": "tool", "content": "ignored", "tool_call_id": "unknown"},
        ],
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
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert protected == {1, 2, 3}


@pytest.mark.anyio
async def test_session_memory_failure_and_inactive_snapshot_clone(monkeypatch):
    messages = [Message(role=MessageRole.USER, content="hello")]
    conversation = _conversation()

    async def failing_snapshot(_conversation_id):
        raise RuntimeError("offline")

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", failing_snapshot
    )
    cloned, compacted, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        protected_indexes={0},
    )
    assert not compacted
    assert protected == {0}
    assert cloned[0] is not messages[0]

    async def ready_snapshot(_conversation_id):
        return SimpleNamespace(summary_text="summary", source_message_id=uuid4())

    async def inactive(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", ready_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", inactive)
    _, compacted, _ = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
    )
    assert not compacted


@pytest.mark.anyio
async def test_disabled_compression_and_retry_forwarding(monkeypatch):
    agent = _agent(context_compression_config={"enabled": False})
    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=_conversation(),
        user_message="hello",
        model_id="gpt-4",
        model_context_limit=1000,
        model_max_output_tokens=100,
        history_override=[],
    )
    assert prepared.compression.stage == "none"
    assert prepared.messages[-1].content == "hello"

    captured = {}

    async def fake_prepare(**kwargs):
        captured.update(kwargs)
        return prepared

    monkeypatch.setattr(chat_context, "prepare_model_context", fake_prepare)
    retried = await chat_context.retry_prepare_model_context(
        agent=agent,
        conversation=_conversation(),
        user_message="again",
        model_id="gpt-4",
        model_context_limit=1000,
        model_max_output_tokens=100,
    )
    assert retried is prepared
    assert captured["aggressive"] is True

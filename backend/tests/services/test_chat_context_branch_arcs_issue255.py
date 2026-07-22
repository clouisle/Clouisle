import base64
from types import SimpleNamespace

import pytest

from app.llm.types import ContentPart, ContentType, Message, MessageRole
from app.services import chat_context


def test_prompt_and_content_helper_branch_matrix():
    chinese = chat_context.get_language_instruction("zh-CN")
    assert "中文" in chinese
    assert (
        chat_context.get_language_instruction("fr")
        == chat_context.LANGUAGE_INSTRUCTIONS["en"]
    )
    assert chat_context.build_system_prompt_with_language(None, "en").startswith(
        "## Response Language"
    )
    assert chat_context.build_system_prompt_with_language(chinese, "zh") == chinese
    assert "用户输入请求功能" in chat_context.get_user_input_request_instruction("zh")

    assert chat_context._append_prompt_section("base", "  ") == "base"
    assert chat_context._append_prompt_section("", " section ") == "section"
    assert chat_context._normalize_text(None) == ""
    assert chat_context._normalize_text(" a\n b ") == "a b"
    assert chat_context._truncate_text("abcdef", 5) == "ab..."
    assert chat_context._limit_summary_text("abcdef", 5) == "ab..."
    assert chat_context._stringify_content(None) == ""
    assert (
        chat_context._stringify_content(
            [
                ContentPart(type=ContentType.TEXT, text="caption"),
                ContentPart(type=ContentType.IMAGE),
                ContentPart(type=ContentType.TEXT, text=""),
            ]
        )
        == "caption\n[image]"
    )


def test_vision_and_uploaded_image_branch_matrix():
    raw = base64.b64encode(b"not an image").decode()
    assert chat_context._normalize_vision_image(raw, None) == (raw, "png")

    parts = chat_context.build_vision_content(
        "look",
        [
            SimpleNamespace(url=None),
            {"url": "https://example.test/image.png"},
            {"url": f"data:image/png;base64,{raw}"},
        ],
    )
    assert [part.type for part in parts] == [
        ContentType.TEXT,
        ContentType.TEXT,
        ContentType.IMAGE,
        ContentType.TEXT,
        ContentType.IMAGE,
    ]
    assert parts[2].image.url == "https://example.test/image.png"
    assert parts[4].image.base64 == raw
    assert parts[4].image.format == "png"

    references = chat_context.build_uploaded_image_reference_text(
        [
            SimpleNamespace(url="one", base64=None),
            {"base64": "two"},
            {},
        ]
    )
    assert references.splitlines() == [
        "Uploaded image #1: available as a reference image.",
        "Uploaded image #2: available as a reference image.",
    ]
    assert chat_context._build_current_user_content(
        "", [{"url": "one"}], False
    ).startswith("Uploaded image #1")
    assert chat_context._append_file_content_to_user_content("", " file ") == (
        "<uploaded_files>\nfile\n</uploaded_files>"
    )


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("", ""),
        ("not-json", "not-json"),
        ("[]", "[]"),
        ('{"kind":"media.image","error":"denied"}', "Image generation failed: denied"),
        (
            '{"kind":"media.image","images":[{},{}],"model":"paint"}',
            "Image generation succeeded. Generated 2 images using model paint.",
        ),
        (
            '{"kind":"media.video","status":"processing","task_id":"job-1"}',
            "Video generation started. Task job-1 is processing.",
        ),
        (
            '{"kind":"media.video","status":"failed"}',
            "Video generation failed: unknown error",
        ),
        (
            '{"kind":"media.video","status":"complete","model":"movie"}',
            "Video generation succeeded using model movie.",
        ),
        (
            '{"result":{"type":"skill_instructions","status":"ready",'
            '"skill":{"display_name":"Writer"}}}',
            "Skill instructions for Writer were ready.",
        ),
    ],
)
def test_tool_result_summary_branch_matrix(stored, expected):
    assert chat_context.summarize_tool_result_for_llm(None, stored) == expected


def test_budget_pressure_and_reasoning_compaction_branches():
    budget = chat_context.TokenBudget(100, 10, 10, 80)
    thresholds = chat_context.CompressionThresholds(40, 55, 70)
    assert [
        chat_context._assess_context_pressure(
            before_tokens=value, token_budget=budget, thresholds=thresholds
        )
        for value in (20, 40, 55, 70, 81)
    ] == ["normal", "warning", "auto_compact", "blocking", "over_budget"]

    messages = [
        Message(role=MessageRole.ASSISTANT, content="old", reasoning_content="old-r"),
        Message(role=MessageRole.USER, content="question"),
        Message(role=MessageRole.ASSISTANT, content="new", reasoning_content="new-r"),
    ]
    compacted, trimmed, protected = chat_context._compact_message_reasoning(
        messages, keep_recent_reasoning_messages=0, protected_indexes={0}
    )
    assert compacted[0].reasoning_content == "old-r"
    assert compacted[2].reasoning_content is None
    assert trimmed is True
    assert protected == {0}


def test_turn_summary_and_macro_summary_branch_matrix(monkeypatch):
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 1
    )
    blocks = [
        [Message(role=MessageRole.USER, content="first")],
        [
            Message(role=MessageRole.USER, content="second"),
            Message(role=MessageRole.ASSISTANT, content="answer"),
        ],
    ]
    summary = chat_context._build_macro_summary_message(blocks, summary_max_chars=500)
    assert summary is not None
    assert summary.content.startswith(chat_context.MACRO_SUMMARY_PREFIX)
    assert "User asked: first" in summary.content
    assert "Assistant responded: answer" in summary.content
    assert chat_context._build_macro_summary_message([]) is None

    messages = [Message(role=MessageRole.SYSTEM, content="system"), *sum(blocks, [])]
    compacted, turns, recent, tools, count, protected = (
        chat_context._apply_macro_compaction(
            messages,
            model_id="model",
            provider=None,
            recent_raw_turns=1,
            recent_tool_turns=0,
            protected_indexes={3},
        )
    )
    assert turns == 1
    assert recent == 1
    assert tools == 0
    assert count == 1
    assert compacted[0].role == MessageRole.SYSTEM
    assert compacted[1].content.startswith(chat_context.MACRO_SUMMARY_PREFIX)
    assert protected == {3}

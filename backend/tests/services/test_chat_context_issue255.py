"""Issue #255 — targeted branch coverage for chat_context pure helpers.

Focuses on branches in:
  - language / locale helpers
  - media / skill tool-result summarisers
  - file-content trimming
  - text normalisation / truncation
  - content stringification
  - sandbox-tools detection
  - token-budget and compression-threshold computation
  - context-pressure assessment
  - reasoning compaction
  - rich-media detection
  - turn-block splitting
  - block summarisation and macro-summary message
  - macro-summary extraction
  - assistant tool-call builder
  - compression-config merging
  - uploaded-image reference text
  - prompt-section appending
  - override-role normalisation
"""

from types import SimpleNamespace

import pytest

from app.llm.types import (
    ContentPart,
    ContentType,
    ImageContent,
    Message,
    MessageRole,
    ToolCall,
    FunctionCall,
)
from app.services.chat_context import (
    FILE_CONTENT_PLACEHOLDER,
    MACRO_SUMMARY_PREFIX,
    SANDBOX_SYSTEM_INSTRUCTION,
    _append_prompt_section,
    _assess_context_pressure,
    _build_assistant_tool_calls,
    _build_compression_thresholds,
    _build_macro_summary_message,
    _build_media_llm_summary,
    _build_skill_llm_summary,
    _build_token_budget,
    _compact_message_reasoning,
    _has_rich_media_context,
    _has_sandbox_tools,
    _is_tool_turn,
    _limit_summary_text,
    _normalize_override_role,
    _normalize_text,
    _safe_json_loads,
    _should_keep_tool_result_raw,
    _split_turn_blocks,
    _stringify_content,
    _summarize_block,
    _trim_file_content,
    _truncate_text,
    build_system_prompt_with_language,
    build_uploaded_image_reference_text,
    extract_macro_summary_text,
    get_context_compression_config,
    get_language_instruction,
    get_user_input_request_instruction,
    summarize_tool_result_for_llm,
)


# ---------------------------------------------------------------------------
# get_language_instruction
# ---------------------------------------------------------------------------


class TestGetLanguageInstruction:
    def test_none_defaults_to_en(self):
        result = get_language_instruction(None)
        assert "English" in result or result  # instruction exists

    def test_en_explicit(self):
        assert get_language_instruction("en") == get_language_instruction(None)

    def test_zh_returns_chinese_instruction(self):
        result = get_language_instruction("zh")
        assert (
            "中文" in result
            or "Chinese" in result
            or result != get_language_instruction("en")
        )

    def test_zh_cn_region_code_stripped(self):
        assert get_language_instruction("zh-CN") == get_language_instruction("zh")

    def test_uppercase_locale_normalised(self):
        assert get_language_instruction("EN") == get_language_instruction("en")

    def test_unknown_locale_falls_back_to_en(self):
        assert get_language_instruction("fr") == get_language_instruction("en")


# ---------------------------------------------------------------------------
# build_system_prompt_with_language
# ---------------------------------------------------------------------------


class TestBuildSystemPromptWithLanguage:
    def test_empty_prompt_returns_instruction_only(self):
        result = build_system_prompt_with_language(None, "en")
        assert result == get_language_instruction("en")

    def test_blank_prompt_returns_instruction_only(self):
        result = build_system_prompt_with_language("", "en")
        assert result == get_language_instruction("en")

    def test_appends_instruction_when_not_present(self):
        result = build_system_prompt_with_language("You are helpful.", "en")
        assert result.startswith("You are helpful.")
        assert get_language_instruction("en") in result

    def test_does_not_duplicate_instruction_already_present(self):
        instruction = get_language_instruction("en")
        prompt = f"Prefix.\n\n{instruction}"
        result = build_system_prompt_with_language(prompt, "en")
        assert result == prompt

    def test_sandbox_prompt_requires_fresh_artifacts_after_edits(self):
        assert "Artifact URLs are snapshots" in SANDBOX_SYSTEM_INSTRUCTION
        assert "call `artifact` again before answering" in SANDBOX_SYSTEM_INSTRUCTION
        assert (
            "include every newest Markdown download link" in SANDBOX_SYSTEM_INSTRUCTION
        )


# ---------------------------------------------------------------------------
# get_user_input_request_instruction
# ---------------------------------------------------------------------------


class TestGetUserInputRequestInstruction:
    def test_en_returns_english_text(self):
        result = get_user_input_request_instruction("en")
        assert "User Input Request" in result

    def test_zh_returns_chinese_text(self):
        result = get_user_input_request_instruction("zh")
        assert "用户输入请求" in result

    def test_default_is_en(self):
        assert (
            get_user_input_request_instruction()
            == get_user_input_request_instruction("en")
        )


# ---------------------------------------------------------------------------
# _safe_json_loads
# ---------------------------------------------------------------------------


class TestSafeJsonLoads:
    def test_none_returns_none(self):
        assert _safe_json_loads(None) is None

    def test_empty_string_returns_none(self):
        assert _safe_json_loads("") is None

    def test_valid_dict_returns_dict(self):
        result = _safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_list_returns_none(self):
        # Non-dict JSON returns None
        assert _safe_json_loads("[1, 2, 3]") is None

    def test_invalid_json_returns_none(self):
        assert _safe_json_loads("not-json") is None

    def test_plain_string_returns_none(self):
        assert _safe_json_loads('"just a string"') is None


# ---------------------------------------------------------------------------
# _build_skill_llm_summary
# ---------------------------------------------------------------------------


class TestBuildSkillLlmSummary:
    def test_correct_type_with_named_skill(self):
        payload = {
            "result": {
                "type": "skill_instructions",
                "status": "loaded",
                "skill": {"display_name": "MySkill"},
            }
        }
        result = _build_skill_llm_summary(payload)
        assert result == "Skill instructions for MySkill were loaded."

    def test_correct_type_skill_name_fallback(self):
        payload = {
            "result": {
                "type": "skill_instructions",
                "skill": {"name": "fallback-name"},
            }
        }
        result = _build_skill_llm_summary(payload)
        assert "fallback-name" in result

    def test_correct_type_no_skill_field(self):
        payload = {"result": {"type": "skill_instructions"}}
        result = _build_skill_llm_summary(payload)
        assert result is not None and "Skill" in result

    def test_wrong_type_returns_none(self):
        payload = {"result": {"type": "other_type"}}
        assert _build_skill_llm_summary(payload) is None

    def test_no_result_field_returns_none(self):
        assert _build_skill_llm_summary({}) is None

    def test_result_not_dict_returns_none(self):
        assert _build_skill_llm_summary({"result": "not a dict"}) is None


# ---------------------------------------------------------------------------
# _build_media_llm_summary — media.image branches
# ---------------------------------------------------------------------------


class TestBuildMediaLlmSummaryImage:
    def test_image_error_branch(self):
        payload = {"kind": "media.image", "error": "quota exceeded"}
        result = _build_media_llm_summary("gen_image", payload)
        assert result == "Image generation failed: quota exceeded"

    def test_image_success_single_no_model(self):
        payload = {"kind": "media.image", "images": ["img1"]}
        result = _build_media_llm_summary("gen_image", payload)
        assert "1 image" in result
        assert "model" not in result

    def test_image_success_plural_with_model(self):
        payload = {"kind": "media.image", "images": ["a", "b"], "model": "dalle3"}
        result = _build_media_llm_summary("gen_image", payload)
        assert "2 images" in result
        assert "dalle3" in result

    def test_image_zero_images(self):
        payload = {"kind": "media.image", "images": []}
        result = _build_media_llm_summary("gen_image", payload)
        assert "0 image" in result


# ---------------------------------------------------------------------------
# _build_media_llm_summary — media.video branches
# ---------------------------------------------------------------------------


class TestBuildMediaLlmSummaryVideo:
    def test_video_failed_via_status(self):
        payload = {"kind": "media.video", "status": "failed"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "failed" in result

    def test_video_failed_via_error_field(self):
        payload = {"kind": "media.video", "error": "timeout", "status": "running"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "timeout" in result

    def test_video_pending(self):
        payload = {"kind": "media.video", "status": "pending", "task_id": "tid-1"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "pending" in result and "tid-1" in result

    def test_video_processing(self):
        payload = {"kind": "media.video", "status": "processing", "task_id": "t2"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "processing" in result

    def test_video_succeeded_no_model(self):
        payload = {"kind": "media.video", "status": "succeeded"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "succeeded" in result
        assert "model" not in result

    def test_video_succeeded_with_model(self):
        payload = {"kind": "media.video", "status": "succeeded", "model": "sora"}
        result = _build_media_llm_summary("gen_video", payload)
        assert "sora" in result

    def test_unknown_kind_returns_none(self):
        payload = {"kind": "media.audio"}
        assert _build_media_llm_summary("gen_audio", payload) is None


# ---------------------------------------------------------------------------
# summarize_tool_result_for_llm
# ---------------------------------------------------------------------------


class TestSummarizeToolResultForLlm:
    def test_non_json_returned_as_is(self):
        assert summarize_tool_result_for_llm(None, "plain text") == "plain text"

    def test_image_payload_summarised(self):
        import json

        payload = json.dumps({"kind": "media.image", "images": ["x"]})
        result = summarize_tool_result_for_llm("gen_image", payload)
        assert "image" in result.lower()

    def test_skill_payload_summarised(self):
        import json

        payload = json.dumps(
            {
                "result": {
                    "type": "skill_instructions",
                    "skill": {"display_name": "TestSkill"},
                }
            }
        )
        result = summarize_tool_result_for_llm("skill_tool", payload)
        assert "TestSkill" in result

    def test_unrecognised_dict_payload_returned_as_is(self):
        import json

        payload = json.dumps({"some": "data"})
        result = summarize_tool_result_for_llm("unknown_tool", payload)
        assert result == payload


# ---------------------------------------------------------------------------
# _trim_file_content
# ---------------------------------------------------------------------------


class TestTrimFileContent:
    def test_none_returns_none_not_trimmed(self):
        content, trimmed = _trim_file_content(None)
        assert content is None
        assert not trimmed

    def test_empty_string_returns_as_is(self):
        content, trimmed = _trim_file_content("")
        assert content == ""
        assert not trimmed

    def test_short_content_not_trimmed(self):
        short = "hello world"
        content, trimmed = _trim_file_content(short)
        assert content == short
        assert not trimmed

    def test_long_content_is_trimmed(self):
        # 12000 + 4000 = 16000 chars threshold; create something larger
        long_content = "x" * 20000
        content, trimmed = _trim_file_content(long_content)
        assert trimmed
        assert "trimmed" in content
        assert len(content) < len(long_content)

    def test_aggressive_uses_smaller_limits(self):
        long_content = "a" * 20000
        normal_content, _ = _trim_file_content(long_content, aggressive=False)
        aggressive_content, _ = _trim_file_content(long_content, aggressive=True)
        # aggressive result should be shorter or equal
        assert len(aggressive_content) <= len(normal_content)


# ---------------------------------------------------------------------------
# _normalize_text / _truncate_text / _limit_summary_text
# ---------------------------------------------------------------------------


class TestTextHelpers:
    def test_normalize_text_none(self):
        assert _normalize_text(None) == ""

    def test_normalize_text_empty(self):
        assert _normalize_text("") == ""

    def test_normalize_text_collapses_whitespace(self):
        assert _normalize_text("hello   world\n\tthere") == "hello world there"

    def test_truncate_short_string_unchanged(self):
        assert _truncate_text("hello", 10) == "hello"

    def test_truncate_long_string_adds_ellipsis(self):
        result = _truncate_text("abcdefghij", 5)
        assert result.endswith("...")
        assert len(result) == 5

    def test_limit_summary_text_short(self):
        assert _limit_summary_text("hi", 100) == "hi"

    def test_limit_summary_text_truncated(self):
        result = _limit_summary_text("abcdefghij", 5)
        assert result.endswith("...")
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _stringify_content
# ---------------------------------------------------------------------------


class TestStringifyContent:
    def test_string_returned_directly(self):
        assert _stringify_content("hello") == "hello"

    def test_none_returns_empty(self):
        assert _stringify_content(None) == ""

    def test_empty_list_returns_empty(self):
        assert _stringify_content([]) == ""

    def test_text_parts_joined(self):
        parts = [
            ContentPart(type=ContentType.TEXT, text="hello"),
            ContentPart(type=ContentType.TEXT, text="world"),
        ]
        result = _stringify_content(parts)
        assert "hello" in result and "world" in result

    def test_image_part_becomes_placeholder(self):
        parts = [
            ContentPart(
                type=ContentType.IMAGE, image=ImageContent(url="http://x.com/img.png")
            ),
        ]
        result = _stringify_content(parts)
        assert result == "[image]"

    def test_mixed_text_and_image(self):
        parts = [
            ContentPart(type=ContentType.TEXT, text="caption"),
            ContentPart(
                type=ContentType.IMAGE, image=ImageContent(url="http://x.com/img.png")
            ),
        ]
        result = _stringify_content(parts)
        assert "caption" in result
        assert "[image]" in result


# ---------------------------------------------------------------------------
# _has_sandbox_tools
# ---------------------------------------------------------------------------


class TestHasSandboxTools:
    def _agent(self, tools_config):
        return SimpleNamespace(tools_config=tools_config)

    def test_empty_tools_config_false(self):
        assert not _has_sandbox_tools(self._agent([]))

    def test_none_tools_config_false(self):
        assert not _has_sandbox_tools(self._agent(None))

    def test_builtin_bash_true(self):
        assert _has_sandbox_tools(self._agent([{"type": "builtin", "name": "bash"}]))

    def test_builtin_write_true(self):
        assert _has_sandbox_tools(self._agent([{"type": "builtin", "name": "write"}]))

    def test_builtin_read_true(self):
        assert _has_sandbox_tools(self._agent([{"type": "builtin", "name": "read"}]))

    def test_builtin_edit_true(self):
        assert _has_sandbox_tools(self._agent([{"type": "builtin", "name": "edit"}]))

    def test_builtin_artifact_true(self):
        assert _has_sandbox_tools(
            self._agent([{"type": "builtin", "name": "artifact"}])
        )

    def test_skill_type_true(self):
        assert _has_sandbox_tools(self._agent([{"type": "skill", "name": "any"}]))

    def test_unrecognised_builtin_false(self):
        assert not _has_sandbox_tools(
            self._agent([{"type": "builtin", "name": "search"}])
        )


# ---------------------------------------------------------------------------
# Token budget / thresholds / pressure
# ---------------------------------------------------------------------------


class TestTokenBudgetAndPressure:
    def test_context_limit_defaults_when_none(self):
        budget = _build_token_budget(context_limit=None, model_max_output_tokens=None)
        assert budget.context_limit > 0
        assert budget.input_budget > 0

    def test_output_reserve_capped_by_model_max(self):
        budget = _build_token_budget(
            context_limit=10000,
            model_max_output_tokens=500,
            output_token_reserve=4000,
            safety_margin_tokens=100,
        )
        assert budget.output_reserve == 500
        assert budget.input_budget == 9400

    def test_output_reserve_capped_to_third_of_context(self):
        budget = _build_token_budget(
            context_limit=300,
            model_max_output_tokens=1000,
            output_token_reserve=1000,
            safety_margin_tokens=0,
        )
        assert budget.output_reserve == 100

    def test_input_budget_never_below_one(self):
        budget = _build_token_budget(
            context_limit=10,
            model_max_output_tokens=100,
            output_token_reserve=100,
            safety_margin_tokens=100,
        )
        assert budget.input_budget == 1

    def test_thresholds_clamped_to_budget(self):
        budget = _build_token_budget(
            context_limit=100,
            model_max_output_tokens=1,
            output_token_reserve=1,
            safety_margin_tokens=0,
        )
        thresholds = _build_compression_thresholds(
            token_budget=budget,
            warning_ratio=2.0,
            trigger_ratio=0.0,
            blocking_ratio=0.5,
        )
        assert thresholds.warning_input_budget == budget.input_budget
        assert thresholds.trigger_input_budget == 1

    @pytest.mark.parametrize(
        ("tokens", "expected"),
        [
            (10, "normal"),
            (70, "warning"),
            (80, "auto_compact"),
            (92, "blocking"),
            (101, "over_budget"),
        ],
    )
    def test_pressure_levels(self, tokens, expected):
        budget = SimpleNamespace(input_budget=100)
        thresholds = SimpleNamespace(
            warning_input_budget=70,
            trigger_input_budget=80,
            blocking_input_budget=92,
        )
        assert (
            _assess_context_pressure(
                before_tokens=tokens,
                token_budget=budget,
                thresholds=thresholds,
            )
            == expected
        )


# ---------------------------------------------------------------------------
# Reasoning compaction / rich media / tool turn
# ---------------------------------------------------------------------------


class TestReasoningAndMediaHelpers:
    def test_compact_reasoning_keeps_most_recent(self):
        messages = [
            Message(role=MessageRole.ASSISTANT, content="a", reasoning_content="old"),
            Message(role=MessageRole.ASSISTANT, content="b", reasoning_content="new"),
        ]
        compacted, trimmed, protected = _compact_message_reasoning(
            messages, keep_recent_reasoning_messages=1
        )
        assert trimmed
        assert compacted[0].reasoning_content is None
        assert compacted[1].reasoning_content == "new"
        assert protected == set()

    def test_protected_old_reasoning_is_kept_and_remapped(self):
        messages = [
            Message(
                role=MessageRole.ASSISTANT, content="a", reasoning_content="protected"
            ),
            Message(
                role=MessageRole.ASSISTANT, content="b", reasoning_content="recent"
            ),
        ]
        compacted, trimmed, protected = _compact_message_reasoning(
            messages,
            keep_recent_reasoning_messages=0,
            protected_indexes={0},
        )
        assert compacted[0].reasoning_content == "protected"
        assert compacted[1].reasoning_content is None
        assert trimmed
        assert protected == {0}

    def test_rich_media_content_part(self):
        message = Message(
            role=MessageRole.USER,
            content=[
                ContentPart(
                    type=ContentType.IMAGE, image=ImageContent(url="https://x/img")
                )
            ],
        )
        assert _has_rich_media_context(message)

    @pytest.mark.parametrize("content", [FILE_CONTENT_PLACEHOLDER, "look [image]"])
    def test_rich_media_text_markers(self, content):
        assert _has_rich_media_context(Message(role=MessageRole.USER, content=content))

    def test_plain_text_not_rich_media(self):
        assert not _has_rich_media_context(
            Message(role=MessageRole.USER, content="plain")
        )

    def test_tool_turn_true_for_tool_call(self):
        tool_call = ToolCall(
            id="call-1",
            type="function",
            function=FunctionCall(name="search", arguments="{}"),
        )
        message = Message(
            role=MessageRole.ASSISTANT, content=None, tool_calls=[tool_call]
        )
        assert _is_tool_turn([message])

    def test_tool_turn_false_for_plain_assistant(self):
        message = Message(role=MessageRole.ASSISTANT, content="answer")
        assert not _is_tool_turn([message])

    def test_should_keep_tool_result_raw_boundary(self):
        assert _should_keep_tool_result_raw(
            tool_result_index_from_end=1, keep_recent_tool_results=2
        )
        assert not _should_keep_tool_result_raw(
            tool_result_index_from_end=2, keep_recent_tool_results=2
        )


# ---------------------------------------------------------------------------
# Turn blocks / summaries
# ---------------------------------------------------------------------------


class TestTurnBlocksAndSummaries:
    def test_split_empty_messages(self):
        assert _split_turn_blocks([]) == ([], [], [], [])

    def test_split_system_prefix_and_user_turns(self):
        messages = [
            Message(role=MessageRole.SYSTEM, content="system"),
            Message(role=MessageRole.USER, content="question 1"),
            Message(role=MessageRole.ASSISTANT, content="answer 1"),
            Message(role=MessageRole.USER, content="question 2"),
        ]
        prefix, prefix_indexes, blocks, block_indexes = _split_turn_blocks(messages)
        assert [m.content for m in prefix] == ["system"]
        assert prefix_indexes == [0]
        assert len(blocks) == 2
        assert block_indexes == [[1, 2], [3]]

    def test_split_non_user_leading_message_creates_block(self):
        messages = [Message(role=MessageRole.ASSISTANT, content="orphan")]
        prefix, _, blocks, _ = _split_turn_blocks(messages)
        assert prefix == []
        assert len(blocks) == 1

    def test_summarize_empty_block_fallback(self):
        assert _summarize_block([]) == "Conversation turn preserved in compact summary."

    def test_summarize_user_and_assistant(self):
        block = [
            Message(role=MessageRole.USER, content="What is two plus two?"),
            Message(role=MessageRole.ASSISTANT, content="Four."),
        ]
        result = _summarize_block(block)
        assert "User asked:" in result
        assert "Assistant responded:" in result

    def test_summarize_tool_names_and_results(self):
        tool_call = ToolCall(
            id="call-1",
            type="function",
            function=FunctionCall(name="calculator", arguments="{}"),
        )
        block = [
            Message(role=MessageRole.ASSISTANT, content=None, tool_calls=[tool_call]),
            Message(role=MessageRole.TOOL, content="4", tool_call_id="call-1"),
        ]
        result = _summarize_block(block)
        assert "Tools involved:" in result
        assert "Tool outcomes:" in result

    def test_build_macro_summary_none_for_no_blocks(self):
        assert _build_macro_summary_message([]) is None

    def test_build_macro_summary_message(self):
        block = [[Message(role=MessageRole.USER, content="hello")]]
        message = _build_macro_summary_message(block)
        assert message is not None
        assert message.role == MessageRole.ASSISTANT
        assert message.content.startswith(MACRO_SUMMARY_PREFIX)

    def test_extract_macro_summary_skips_other_messages(self):
        messages = [
            Message(
                role=MessageRole.USER, content=f"{MACRO_SUMMARY_PREFIX} not assistant"
            ),
            Message(role=MessageRole.ASSISTANT, content="ordinary answer"),
        ]
        assert extract_macro_summary_text(messages) is None

    def test_extract_macro_summary_returns_first_match(self):
        summary = f"{MACRO_SUMMARY_PREFIX}\n- Turn 1: hello"
        messages = [Message(role=MessageRole.ASSISTANT, content=summary)]
        assert extract_macro_summary_text(messages) == summary


# ---------------------------------------------------------------------------
# Tool-call building / config / misc helpers
# ---------------------------------------------------------------------------


class TestMiscHelpers:
    def test_build_assistant_tool_calls_empty(self):
        assert _build_assistant_tool_calls(None) == (None, set())
        assert _build_assistant_tool_calls([]) == (None, set())

    def test_build_assistant_tool_calls_serializes_dict_arguments(self):
        calls, ids = _build_assistant_tool_calls(
            [{"id": "call-1", "name": "search", "arguments": {"q": "hello"}}]
        )
        assert ids == {"call-1"}
        assert calls[0].function.name == "search"
        assert '"q": "hello"' in calls[0].function.arguments

    def test_build_assistant_tool_calls_preserves_string_arguments(self):
        calls, ids = _build_assistant_tool_calls(
            [{"id": "call-2", "name": "raw", "arguments": '{"x":1}'}]
        )
        assert ids == {"call-2"}
        assert calls[0].function.arguments == '{"x":1}'

    def test_context_compression_config_merges_dict(self):
        agent = SimpleNamespace(context_compression_config={"enabled": False})
        config = get_context_compression_config(agent)
        assert config["enabled"] is False
        assert "recent_raw_turns" in config

    def test_context_compression_config_ignores_non_dict(self):
        agent = SimpleNamespace(context_compression_config="invalid")
        config = get_context_compression_config(agent)
        assert config["enabled"] is True

    def test_uploaded_image_reference_supports_object_and_dict(self):
        images = [
            SimpleNamespace(url="https://example.com/a.png", base64=None),
            {"base64": "abc"},
            {},
        ]
        result = build_uploaded_image_reference_text(images)
        assert "#1" in result
        assert "#2" in result
        assert "#3" not in result

    def test_append_prompt_section_empty(self):
        assert _append_prompt_section("base", None) == "base"
        assert _append_prompt_section("base", "   ") == "base"

    def test_append_prompt_section_to_base(self):
        assert _append_prompt_section("base", " section ") == "base\n\nsection"

    def test_append_prompt_section_without_base(self):
        assert _append_prompt_section("", "section") == "section"

    def test_normalize_override_role_none(self):
        assert _normalize_override_role(None) is None

    def test_normalize_override_role_enum_like(self):
        role = SimpleNamespace(value="user")
        assert _normalize_override_role(role) == "user"

    def test_normalize_override_role_string(self):
        assert _normalize_override_role("assistant") == "assistant"

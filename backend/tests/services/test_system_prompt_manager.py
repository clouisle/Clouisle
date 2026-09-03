"""Tests for the unified system prompt injection manager (YUN-127)."""

from types import SimpleNamespace

import pytest

from app.services.system_prompt import (
    CHAT_MODE,
    FILE_CONTENT_PLACEHOLDER,
    WORKFLOW_MODE,
    build_system_prompt,
    has_sandbox_tools,
    normalize_locale,
)


def _agent(
    *,
    tools_config=None,
    system_prompt="Base prompt",
    enable_memory=False,
):
    return SimpleNamespace(
        id="agent-1",
        system_prompt=system_prompt,
        enable_memory=enable_memory,
        tools_config=tools_config or [],
    )


# ---------------------------------------------------------------------------
# has_sandbox_tools
# ---------------------------------------------------------------------------


def test_has_sandbox_tools_detects_builtin_sandbox_tools():
    for name in ("bash", "read", "edit", "write", "artifact"):
        assert has_sandbox_tools(
            _agent(tools_config=[{"type": "builtin", "name": name}])
        )


def test_has_sandbox_tools_detects_skill_tools():
    assert has_sandbox_tools(_agent(tools_config=[{"type": "skill", "skill_id": "s1"}]))


def test_has_sandbox_tools_false_for_non_sandbox_tools():
    assert not has_sandbox_tools(
        _agent(tools_config=[{"type": "builtin", "name": "generate_image"}])
    )
    assert not has_sandbox_tools(_agent(tools_config=[]))
    assert not has_sandbox_tools(_agent(tools_config=None))


# ---------------------------------------------------------------------------
# Locale normalization
# ---------------------------------------------------------------------------


def test_normalize_locale_returns_base_subtag():
    assert normalize_locale("zh-CN") == "zh"
    assert normalize_locale("ZH") == "zh"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("") == "en"
    assert normalize_locale(None) == "en"


# ---------------------------------------------------------------------------
# Chat mode (interactive endpoint) parity
# ---------------------------------------------------------------------------


def test_chat_mode_injects_sandbox_markdown_and_language():
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "builtin", "name": "bash"}]),
        user_message="run a task",
        user_locale="en",
        invocation_mode=CHAT_MODE,
    )
    assert "## Markdown Output" in prompt
    assert "## Sandbox Environment Guidance" in prompt
    assert "## Response Language\nYou MUST respond in English only." in prompt


def test_chat_mode_injects_memory_when_enabled():
    prompt = build_system_prompt(
        _agent(enable_memory=True),
        user_message="hi",
        user_locale="en",
        invocation_mode=CHAT_MODE,
    )
    assert "## Memory System" in prompt


def test_chat_mode_skips_sandbox_without_sandbox_tools():
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "builtin", "name": "generate_image"}]),
        user_message="draw",
        user_locale="en",
        invocation_mode=CHAT_MODE,
    )
    assert "## Sandbox Environment Guidance" not in prompt
    assert "Base prompt" in prompt


def test_chat_mode_empty_base_still_emits_markdown_and_language():
    prompt = build_system_prompt(
        _agent(system_prompt=""),
        user_message="show the image",
        user_locale="zh",
        invocation_mode=CHAT_MODE,
    )
    assert "## Markdown Output" in prompt
    assert "## 回复语言" in prompt


def test_template_substitution_replaces_query_variables_and_file_placeholder():
    prompt = build_system_prompt(
        _agent(
            system_prompt="Hello {{name}}, you asked: {{query}}. File: {{fileContent}}"
        ),
        user_message="do the thing",
        variables={"name": "Alice"},
        user_locale="en",
        invocation_mode=CHAT_MODE,
    )
    assert "Hello Alice" in prompt
    assert "you asked: do the thing" in prompt
    assert FILE_CONTENT_PLACEHOLDER not in prompt


def test_section_order_is_markdown_then_sandbox_then_language():
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "builtin", "name": "bash"}]),
        user_message="run",
        user_locale="en",
        invocation_mode=CHAT_MODE,
    )
    assert prompt.index("## Markdown Output") < prompt.index(
        "## Sandbox Environment Guidance"
    )
    assert prompt.index("## Sandbox Environment Guidance") < prompt.index(
        "## Response Language"
    )


# ---------------------------------------------------------------------------
# Workflow mode (agent node in a pipeline) - the alignment fix
# ---------------------------------------------------------------------------


def test_workflow_mode_injects_sandbox_guidance_for_sandbox_tools():
    """The bug fix: workflow agents running bash/read/edit/write now get
    sandbox environment guidance they previously lacked."""
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "builtin", "name": "bash"}]),
        user_message="run a task",
        user_locale="en",
        invocation_mode=WORKFLOW_MODE,
    )
    assert "## Sandbox Environment Guidance" in prompt
    assert "## Markdown Output" in prompt
    assert "## Response Language" in prompt


def test_workflow_mode_injects_sandbox_guidance_for_skill_tools():
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "skill", "skill_id": "s1"}]),
        user_message="run",
        user_locale="en",
        invocation_mode=WORKFLOW_MODE,
    )
    assert "## Sandbox Environment Guidance" in prompt


def test_workflow_mode_skips_memory_guidance_even_when_enabled():
    """Workflow path does not wire memory tools; injecting the guidance would
    make the model call tools it does not have."""
    prompt = build_system_prompt(
        _agent(tools_config=[{"type": "builtin", "name": "bash"}], enable_memory=True),
        user_message="run",
        user_locale="en",
        invocation_mode=WORKFLOW_MODE,
    )
    assert "## Memory System" not in prompt


def test_workflow_mode_locale_none_defaults_to_english():
    prompt = build_system_prompt(
        _agent(system_prompt="base"),
        user_message="hi",
        user_locale=None,
        invocation_mode=WORKFLOW_MODE,
    )
    assert "You MUST respond in English only." in prompt


def test_workflow_mode_locale_drives_language_instruction():
    prompt = build_system_prompt(
        _agent(system_prompt="base"),
        user_message="hi",
        user_locale="zh",
        invocation_mode=WORKFLOW_MODE,
    )
    assert "你必须使用中文回复" in prompt


def test_base_prompt_override_is_used_instead_of_agent_prompt():
    prompt = build_system_prompt(
        _agent(system_prompt="original"),
        base_prompt="overridden base",
        user_message="hi",
        user_locale="en",
        invocation_mode=WORKFLOW_MODE,
    )
    assert "overridden base" in prompt
    assert "original" not in prompt


# ---------------------------------------------------------------------------
# AgentService workflow integration
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_service_workflow_build_messages_injects_sandbox_skips_memory():
    from app.models.agent import RAGMode
    from app.services.agent import AgentService

    agent = SimpleNamespace(
        id="agent-1",
        system_prompt="You are a helper.",
        tools_config=[{"type": "builtin", "name": "bash"}],
        enable_memory=True,
        rag_mode=RAGMode.OFF,
        team_id=None,
    )
    messages = await AgentService()._build_messages(
        agent=agent, message="run", user_locale="en"
    )
    # System message is first; assert capability-aware workflow injection.
    system_content = messages[0].content
    assert "## Sandbox Environment Guidance" in system_content
    assert "## Markdown Output" in system_content
    assert "## Response Language" in system_content
    assert "## Memory System" not in system_content


@pytest.mark.anyio
async def test_agent_service_workflow_appends_context_to_base_prompt():
    from app.models.agent import RAGMode
    from app.services.agent import AgentService

    agent = SimpleNamespace(
        id="agent-1",
        system_prompt="You are a helper.",
        tools_config=[],
        enable_memory=False,
        rag_mode=RAGMode.OFF,
        team_id=None,
    )
    messages = await AgentService()._build_messages(
        agent=agent,
        message="go",
        context={"topic": "pricing"},
        user_locale="en",
    )
    system_content = messages[0].content
    assert "Context:" in system_content
    assert "topic: pricing" in system_content

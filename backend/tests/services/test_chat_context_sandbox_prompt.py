from types import SimpleNamespace

from app.services.chat_context import _build_system_prompt


def _agent(*, tools_config=None, system_prompt="Base prompt"):
    return SimpleNamespace(
        id="agent-1",
        system_prompt=system_prompt,
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=tools_config or [],
    )


def _conversation():
    return SimpleNamespace(variables={})


def test_build_system_prompt_injects_sandbox_guidance_for_builtin_sandbox_tools():
    prompt = _build_system_prompt(
        agent=_agent(tools_config=[{"type": "builtin", "name": "bash"}]),
        conversation=_conversation(),
        user_message="run a task",
        user_locale="en",
    )

    assert "## Sandbox Environment Guidance" in prompt
    assert "## Sandbox Environment Guidance" in prompt
    assert "`/workspace` is the intended working area" in prompt
    assert "logical alias used by the sandbox tools" in prompt
    assert (
        "Do not assume code written inside a generated Python or Node script should hardcode `/workspace/...`"
        in prompt
    )
    assert "prefer paths relative to the script's working directory" in prompt
    assert "Path behavior must be observed, not assumed" in prompt
    assert "Do not rely on ad-hoc `PYTHONPATH` or `sys.path` hacks" in prompt
    assert "Install output can be misleading if filtered" in prompt
    assert "`artifact` depends on backend connectivity, not just local files" in prompt


def test_build_system_prompt_injects_sandbox_guidance_for_skill_tools():
    prompt = _build_system_prompt(
        agent=_agent(tools_config=[{"type": "skill", "skill_id": "skill-1"}]),
        conversation=_conversation(),
        user_message="run a task",
        user_locale="en",
    )

    assert "## Sandbox Environment Guidance" in prompt


def test_build_system_prompt_skips_sandbox_guidance_without_sandbox_tools():
    prompt = _build_system_prompt(
        agent=_agent(tools_config=[{"type": "builtin", "name": "generate_image"}]),
        conversation=_conversation(),
        user_message="draw a cat",
        user_locale="en",
    )

    assert "## Sandbox Environment Guidance" not in prompt
    assert "Base prompt" in prompt


def test_build_system_prompt_formats_sections_with_clear_spacing():
    prompt = _build_system_prompt(
        agent=_agent(tools_config=[{"type": "builtin", "name": "bash"}]),
        conversation=_conversation(),
        user_message="run a task",
        user_locale="en",
    )

    assert "Base prompt\n\n## Markdown Output" in prompt
    assert "## Markdown Output" in prompt
    assert "## Sandbox Environment Guidance" in prompt
    assert "## Response Language\nYou MUST respond in English only." in prompt


def test_build_system_prompt_injects_standard_math_markdown_guidance():
    prompt = _build_system_prompt(
        agent=_agent(system_prompt="Base prompt"),
        conversation=_conversation(),
        user_message="explain cosine similarity",
        user_locale="en",
    )

    assert "## Markdown Output" in prompt
    assert "$...$" in prompt
    assert "$$...$$" in prompt
    assert "inline math" in prompt
    assert "display/block math" in prompt
    assert "[ ... ]" in prompt
    assert r"\[ ... \]" in prompt
    assert r"\( ... \)" in prompt
    assert r"(\mathbf{A})" in prompt
    assert r"$\mathbf{A}$" in prompt
    assert "Keep the whole formula inside one delimiter pair" in prompt


def test_build_system_prompt_injects_markdown_image_display_guidance_without_base_prompt():
    prompt = _build_system_prompt(
        agent=_agent(system_prompt=""),
        conversation=_conversation(),
        user_message="show the generated image",
        user_locale="en",
    )

    assert "## Markdown Output" in prompt
    assert "normal Markdown image syntax" in prompt
    assert "Do not wrap the Markdown image in a code block" in prompt

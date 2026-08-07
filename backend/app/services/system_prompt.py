"""Unified system prompt injection manager.

Single source of truth for assembling an agent's system prompt: the user-authored
base prompt, template variable substitution, and the capability-driven instruction
sections (Markdown output rules, memory guidance, sandbox guidance, language
instruction, user-input-request format).

Both the chat endpoint (via ``chat_context._build_system_prompt``) and the workflow
Agent path (via ``AgentService``) delegate to :func:`build_system_prompt` so that
injection rules are declared once and applied consistently. Rules are gated on the
agent's actual configured capabilities and the invocation mode, so a section is
only injected when the corresponding tools/parsers are genuinely available in that
path (see ``SECTIONS``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.models.agent import Agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILE_CONTENT_PLACEHOLDER = "{{fileContent}}"

MARKDOWN_IMAGE_DISPLAY_INSTRUCTION = r"""## Markdown Output

When the user asks you to show or display an image, output the image using normal Markdown image syntax, for example `![alt text](image-url)`. Do not wrap the Markdown image in a code block unless the user explicitly asks for the literal Markdown source.

When writing math, use standard Markdown/LaTeX delimiters that render correctly:
- Use `$...$` for inline math.
- Use `$$...$$` on separate lines for display/block math.
- Do not use nonstandard math delimiters such as `[ ... ]`, `\[ ... \]`, `( ... )`, `\( ... \)`, or bare parenthesized TeX like `(\mathbf{A})`. Write those as `$\mathbf{A}$` inline, or use `$$...$$` for standalone equations. Keep the whole formula inside one delimiter pair; do not put only part of an equation in `$...$`."""

LANGUAGE_INSTRUCTIONS = {
    "en": "## Response Language\nYou MUST respond in English only. Do not use any other language.",
    "zh": "## 回复语言\n你必须使用中文回复。不要使用其他语言。",
}

MEMORY_SYSTEM_INSTRUCTION = """
## Memory System

You have access to these memory tools:
- `search_memory(query)`: Search what you know about the user
- `create_memory_entity(name, entity_type, description)`: Save new information
- `update_memory_entity(entity_name, description)`: Update existing information
- `create_memory_relation(source, target, relation_type)`: Connect related information

### Required Workflow

1. Before **any** `create_memory_entity()` call, you **must** call `search_memory()` first.
2. When the user shares information such as a name, preference, or skill:
   - Step 1: Call `search_memory(query="keywords about the information")`
   - Step 2: Read the search results carefully
   - Step 3: Decide based on the results:
     - Found a similar entity -> use `update_memory_entity(entity_name="existing name", ...)`
     - Found nothing relevant -> use `create_memory_entity(name="new name", ...)`
3. Never skip `search_memory()`, even if you think the information is new.
4. Never say you do not have access to memory tools.

### Examples

**Wrong**

User: "I'm Alice"

❌ Directly calling `create_memory_entity(name="Alice", ...)` is wrong because no search happened first.

**Correct**

User: "I'm Alice"
- Call `search_memory(query="user name")`
- Check results -> No "Alice" found
- Call `create_memory_entity(name="Alice", entity_type="person", description="User's name")`

User: "Actually, I'm Alice Smith"
- Call `search_memory(query="user name Alice")`
- Check results -> Found entity "Alice"
- Call `update_memory_entity(entity_name="Alice", description="Full name: Alice Smith")`

User: "What's my name?"
- Call `search_memory(query="user name")`
- Then answer using the result
"""

SANDBOX_SYSTEM_INSTRUCTION = """
## Sandbox Environment Guidance

You have access to sandbox tools: `bash`, `read`, `edit`, `write`, and `artifact`. Use them with an accurate mental model of the environment instead of guessing how the sandbox works.

### Environment Reality

1. **`/workspace` is the sandbox filesystem root**
   - `/workspace` is mounted to the current session workspace and is visible to sandbox tools, generated Python and Node scripts, and child processes
   - Use `/workspace/...` for absolute paths; relative paths are resolved from the configured working directory under `/workspace`
   - Keep generated scripts, inputs, temporary files, and outputs under `/workspace`; paths outside it are not part of the job filesystem
   - Prefer stable locations such as `/workspace/src`, `/workspace/data`, `/workspace/output`, and `/workspace/tmp`

2. **Path behavior must be observed, not assumed**
   - Do not infer path semantics from one successful command
   - If a path behaves unexpectedly, inspect it with `pwd`, `ls /workspace`, `find /workspace`, or a short Python check before changing the script or explanation
   - Prefer absolute paths for file operations instead of relying on prior `cd` state

3. **Interpreter and package state may differ from your assumptions**
   - The interpreter that installs a package and the interpreter that runs a script must be treated as concrete facts to verify
   - If an import fails, first verify interpreter identity, import path, and installed package visibility before changing code
   - Do not rely on ad-hoc `PYTHONPATH` or `sys.path` hacks unless the task explicitly requires local package loading

4. **Install output can be misleading if filtered**
   - Do not pipe install output through `tail`, `grep`, or similar filters that can hide errors
   - Do not assume an install succeeded just because the final lines look harmless
   - Confirm package availability with a real import check using the same interpreter that will run the script

5. **Command success should be interpreted narrowly**
   - One successful `touch`, `ls`, or minimal script does not prove the whole environment behaves the same way for another library or another path
   - Treat each surprising result as something to inspect, not something to explain from guesswork

6. **`artifact` depends on backend connectivity, not just local files**
   - A file existing locally does not mean artifact upload will succeed
   - If `artifact` upload fails with a connection or network error, report it clearly instead of retrying with equivalent paths

### Tool Usage Expectations

- Use `write` to create files or replace their complete content; prefer it for real scripts instead of embedding complex scripts inline in `bash`
- Before changing an existing text file, call `read`; every returned line has a `LINE#ID` anchor whose four-hex ID binds it to that full-file snapshot
- For large files, use `read` with `start_line` and `end_line` for an inclusive range, or `search` for case-sensitive literal text; only returned lines are valid edit targets
- Use one `edit` call for related changes. Pass the shared four-hex `tag` once with integer lines, then use compact `replace`, `*_block`, `cut`, `insert_*`, and `paste_*` operations; omit `op` only for a single-line replacement
- `cut` stores text in a persistent named register for later `paste`; block operations resolve Python AST nodes, Markdown sections, brace blocks, or indented blocks. Re-read only when a target changed or became ambiguous
- Keep each `bash` call focused so failures stay attributable
- Use `read`, `ls -lh`, or `find` to confirm what actually exists before changing the approach
- Use `artifact` only for final deliverables after the output file has been verified locally. Artifact URLs are snapshots: if `write`, `edit`, or `bash` changes a collected file, verify it again and call `artifact` again before answering; never reuse the earlier URL
- Before the final response, collect every final user-facing deliverable in its latest state and include every newest Markdown download link returned by `artifact`

### Avoid These Mistakes

- Do not explain sandbox behavior from guesswork
- Do not keep retrying the same install or upload with superficial variations
- Do not use relative paths that depend on prior shell state
- Do not mistake filtered output for a successful environment change
"""

# Invocation modes: "chat" (interactive chat endpoint) or "workflow" (agent node
# executed inside a workflow pipeline).
CHAT_MODE = "chat"
WORKFLOW_MODE = "workflow"

# Sections logged at info when applied (the capability-driven ones); always-on
# sections (Markdown, language) are silent to match prior noise levels.
_LOGGED_SECTIONS = frozenset({"memory", "sandbox"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_locale(user_locale: str | None) -> str:
    """Return the base language subtag, defaulting to ``en``."""
    return (user_locale or "en").lower().split("-")[0]


def get_language_instruction(user_locale: str | None = None) -> str:
    """Get language instruction based on user's locale setting."""
    return LANGUAGE_INSTRUCTIONS.get(
        normalize_locale(user_locale), LANGUAGE_INSTRUCTIONS["en"]
    )


def build_system_prompt_with_language(
    system_prompt: str | None, user_locale: str | None = None
) -> str:
    """Build system prompt with language instruction."""
    instruction = get_language_instruction(user_locale)
    if not system_prompt:
        return instruction
    if instruction in system_prompt:
        return system_prompt
    return f"{system_prompt}\n\n{instruction}"


def get_user_input_request_instruction(locale: str = "en") -> str:
    """Get user input request instruction for system prompt."""
    if normalize_locale(locale) == "zh":
        return """## 用户输入请求功能

当你需要用户从预定义选项中选择时，可以使用以下 XML 格式：

<user_input_request>
<question>你的问题文本</question>
<options>
<option>选项 1</option>
<option>选项 2</option>
<option>选项 3</option>
</options>
</user_input_request>

**使用规则：**
- 问题应该清晰简洁
- 提供 2-6 个选项（超过 6 个也会显示，但建议控制数量以保持界面简洁）
- 每个选项应该简短（建议不超过 50 字符）
- 用户可以点击选项或输入自定义文本
- 在一条消息中只使用一次
- 不要在 user_input_request 标签外添加其他内容

**使用场景：**
- 需要用户做出选择时
- 提供快捷操作选项时
- 引导对话流程时"""
    return """## User Input Request Feature

When you need the user to choose from predefined options, use this XML format:

<user_input_request>
<question>Your question text</question>
<options>
<option>Option 1</option>
<option>Option 2</option>
<option>Option 3</option>
</options>
</user_input_request>

**Rules:**
- Keep questions clear and concise
- Provide 2-6 options
- Keep each option short (recommended max 50 characters)
- Users can click an option or type custom text
- Use only once per message
- Do not add any other content outside the user_input_request tags

**Use cases:**
- When you need the user to make a choice
- When offering quick action options
- When guiding the conversation flow"""


def has_sandbox_tools(agent: Agent) -> bool:
    """Return True when the agent's tool config includes sandbox-capable tools.

    Sandbox tools are the builtins ``bash``/``read``/``edit``/``write``/``artifact``
    or any skill tool. Both the chat and workflow paths execute these, so the
    sandbox guidance is safe to inject in either mode.
    """
    tools_config = getattr(agent, "tools_config", None) or []
    for config in tools_config:
        if config.get("type") == "builtin" and config.get("name") in {
            "bash",
            "read",
            "edit",
            "write",
            "artifact",
        }:
            return True
        if config.get("type") == "skill":
            return True
    return False


def append_prompt_section(base: str, section: str | None) -> str:
    """Append a section to the base prompt with a blank-line separator."""
    normalized_section = (section or "").strip()
    if not normalized_section:
        return base
    return f"{base}\n\n{normalized_section}" if base else normalized_section


# ---------------------------------------------------------------------------
# Declarative injection rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromptSection:
    """A single conditionally-injected system prompt section.

    Attributes:
        name: stable identifier (used for logging).
        applies: predicate ``(agent, invocation_mode) -> bool`` deciding injection.
        transform: ``(base, agent, locale) -> new_base`` applying the section text.
    """

    name: str
    applies: Callable[[Agent, str], bool]
    transform: Callable[[str, Agent, str | None], str]


def _always(_agent: Agent, _mode: str) -> bool:
    return True


def _memory_applies(agent: Agent, mode: str) -> bool:
    # Memory tools are only wired in the chat endpoint; injecting the guidance in
    # the workflow path would tell the model to call tools it does not have.
    return bool(getattr(agent, "enable_memory", False)) and mode == CHAT_MODE


def _user_input_applies(agent: Agent, mode: str) -> bool:
    # The <user_input_request> XML is parsed by the chat frontend only; a workflow
    # has no parser, so emitting it would produce ignored/broken output.
    return (
        bool(getattr(agent, "enable_user_input_request", False)) and mode == CHAT_MODE
    )


def _sandbox_applies(agent: Agent, _mode: str) -> bool:
    return has_sandbox_tools(agent)


def _append_constant(constant: str) -> Callable[[str, Agent, str | None], str]:
    def transform(base: str, _agent: Agent, _locale: str | None) -> str:
        return append_prompt_section(base, constant)

    return transform


# Order matters: Markdown -> Memory -> Sandbox -> Language -> UserInput.
# This preserves the historical chat-endpoint ordering exactly.
SECTIONS: tuple[PromptSection, ...] = (
    PromptSection(
        name="markdown",
        applies=_always,
        transform=_append_constant(MARKDOWN_IMAGE_DISPLAY_INSTRUCTION),
    ),
    PromptSection(
        name="memory",
        applies=_memory_applies,
        transform=_append_constant(MEMORY_SYSTEM_INSTRUCTION),
    ),
    PromptSection(
        name="sandbox",
        applies=_sandbox_applies,
        transform=_append_constant(SANDBOX_SYSTEM_INSTRUCTION),
    ),
    PromptSection(
        name="language",
        applies=_always,
        transform=lambda base, _agent, locale: build_system_prompt_with_language(
            base, locale
        ),
    ),
    PromptSection(
        name="user_input",
        applies=_user_input_applies,
        transform=lambda base, _agent, locale: append_prompt_section(
            base, get_user_input_request_instruction(locale or "en")
        ),
    ),
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_system_prompt(
    agent: Agent,
    *,
    base_prompt: str | None = None,
    user_message: str = "",
    variables: dict[str, Any] | None = None,
    user_locale: str | None = None,
    invocation_mode: str = CHAT_MODE,
) -> str:
    """Assemble the final system prompt for an agent.

    Args:
        agent: Agent instance (duck-typed; needs ``system_prompt``,
            ``tools_config``, and the capability flags used by the rules).
        base_prompt: override for the user-authored base prompt. Defaults to
            ``agent.system_prompt``. The workflow path passes the base with its
            runtime context already appended.
        user_message: current user message, used to substitute ``{{query}}``.
        variables: template variables substituted as ``{{key}}`` in the base.
        user_locale: user locale (e.g. ``"en"``, ``"zh-CN"``) for the language
            and user-input-request instructions.
        invocation_mode: ``"chat"`` (interactive endpoint) or ``"workflow"``
            (agent node in a workflow pipeline). Gates chat-only sections.

    Returns:
        The fully assembled system prompt string.
    """
    base = base_prompt if base_prompt is not None else (agent.system_prompt or "")

    if base:
        for key, value in (variables or {}).items():
            base = base.replace(f"{{{{{key}}}}}", str(value))
        base = base.replace("{{query}}", user_message)
        base = base.replace(FILE_CONTENT_PLACEHOLDER, "")

    agent_id = getattr(agent, "id", None)
    for section in SECTIONS:
        if not section.applies(agent, invocation_mode):
            continue
        previous = base
        base = section.transform(base, agent, user_locale)
        if section.name in _LOGGED_SECTIONS and base != previous:
            logger.info(
                "Added %s instructions to system prompt for agent %s",
                section.name,
                agent_id,
            )

    return base

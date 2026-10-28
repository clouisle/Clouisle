"""Task-local tool invocation identity, established only by trusted runtimes."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RuntimeToolIdentity:
    run_id: UUID | None = None
    tool_call_id: str | None = None
    entrypoint: str = "chat"
    entrypoint_id: str | None = None
    #: Authenticated API key that owns an ``api_key`` entrypoint run. Read by
    #: the approval boundary so every execution is bound to that credential.
    api_key_id: UUID | None = None
    interactive: bool = False
    #: Durable run kind owning ``run_id`` (``agent``/``workflow``). Workflow
    #: delegated calls must not be attributed to a non-existent AgentRun.
    run_kind: str = "agent"
    #: Stable prefix composed with the model tool-call id by callers that own
    #: the per-call boundary (a workflow Agent node, for example).
    tool_call_prefix: str | None = None


_identity: ContextVar[RuntimeToolIdentity | None] = ContextVar(
    "tool_identity", default=None
)
_execution_id: ContextVar[UUID | None] = ContextVar("tool_execution_id", default=None)


def current_execution_id() -> UUID | None:
    return _execution_id.get()


@contextmanager
def execution_identity_scope(execution_id: UUID) -> Iterator[None]:
    token = _execution_id.set(execution_id)
    try:
        yield
    finally:
        _execution_id.reset(token)


def entrypoint_is_interactive(entrypoint: str | None) -> bool:
    """Interactive only when the stored origin is a known foreground entrypoint.

    Legacy runs without a persisted origin are treated as non-interactive so a
    personal connection needs an explicit owner grant instead of silently
    using the owner's default account.
    """
    from app.schemas.tool_approval import (
        NON_INTERACTIVE_ENTRYPOINTS,
        ExecutionEntrypoint,
    )

    if not entrypoint:
        return False
    try:
        value = ExecutionEntrypoint(str(entrypoint))
    except ValueError:
        return False
    return value not in NON_INTERACTIVE_ENTRYPOINTS


def coerce_execution_entrypoint(entrypoint: str | None, *, default: str = "agent_run"):
    """Persisted enum values only; malformed legacy values fall back safely."""
    from app.schemas.tool_approval import ExecutionEntrypoint

    try:
        return ExecutionEntrypoint(str(entrypoint))
    except (TypeError, ValueError):
        return ExecutionEntrypoint(default)


def coerce_execution_run_kind(value: str | None, *, default: str = "agent"):
    from app.schemas.tool_approval import ExecutionRunKind

    try:
        return ExecutionRunKind(str(value))
    except (TypeError, ValueError):
        return ExecutionRunKind(default)


def current_tool_identity() -> RuntimeToolIdentity | None:
    return _identity.get()


@contextmanager
def tool_identity_scope(identity: RuntimeToolIdentity) -> Iterator[None]:
    token = _identity.set(identity)
    try:
        yield
    finally:
        _identity.reset(token)


def get_agent_tool_require_approval(
    agent: Any,
    tool_name: str,
    tool_id: UUID | str | None = None,
) -> bool:
    """Check if the user explicitly enabled confirmation for this tool in the agent."""
    if not agent:
        return False
    tools_config = getattr(agent, "tools_config", None)
    if not tools_config and isinstance(agent, dict):
        tools_config = agent.get("tools_config")
    if not tools_config or not isinstance(tools_config, list):
        return False
    target_id_str = str(tool_id) if tool_id else None
    for tc in tools_config:
        if not isinstance(tc, dict):
            continue
        if not tc.get("require_approval"):
            continue
        tc_type = tc.get("type")
        # 1. Builtin
        if tc_type == "builtin" and tc.get("name") == tool_name:
            return True
        # 2. Custom
        if tc_type == "custom":
            tc_id = str(tc.get("tool_id") or "")
            if target_id_str and tc_id == target_id_str:
                return True
            tc_name = tc.get("name")
            if tc_name and (tool_name == tc_name or tool_name == f"custom_{tc_name}"):
                return True
        # 3. MCP
        if tc_type == "mcp":
            tc_id = str(tc.get("server_id") or tc.get("tool_id") or "")
            if target_id_str and tc_id == target_id_str:
                return True
            tc_name = tc.get("name")
            if tc_name and tool_name.startswith(f"mcp_{tc_name}_"):
                return True
        # 4. Skill
        if tc_type == "skill":
            tc_id = str(tc.get("skill_id") or tc.get("tool_id") or "")
            if target_id_str and tc_id == target_id_str:
                return True
            if tool_name.startswith("skill_"):
                return True
    return False

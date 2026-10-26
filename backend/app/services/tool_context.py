"""Task-local tool invocation identity, established only by trusted runtimes."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RuntimeToolIdentity:
    run_id: UUID | None = None
    tool_call_id: str | None = None
    entrypoint: str = "chat"
    entrypoint_id: str | None = None
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

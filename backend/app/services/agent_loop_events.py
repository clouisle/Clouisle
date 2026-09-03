"""Typed AgentLoop events shared by the four chat execution paths.

The duplicated tool loops are centralized into a single ``AgentLoop``; the
loop emits typed events through a sink. Each transport (SSE generator,
non-stream API, later replayable run stream) formats or ignores them without
owning the execution state machine.

Every event carries the common envelope fields required by the future
replayable run contract: ``run_id``, ``sequence``, ``timestamp`` and optional
``round_id`` / ``message_id``.

Event names deliberately mirror the existing public SSE names
(``message_start``, ``tool_call``, ``compression_start``, ...) so the SSE
formatter stays a pure mapping and already-public payloads keep their shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Event names (aligned with ``SSEEventType`` in ``app/schemas/agent.py``).
MESSAGE_START = "message_start"
RAG_START = "rag_start"
RAG_CONTEXT = "rag_context"
REASONING_START = "reasoning_start"
REASONING_DELTA = "reasoning_delta"
REASONING_END = "reasoning_end"
CONTENT_DELTA = "content_delta"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
MEDIA_RESULT = "media_result"
COMPRESSION_START = "compression_start"
COMPRESSION_END = "compression_end"
OUTPUT_TRUNCATED = "output_truncated"
ITERATION_CAP_REACHED = "iteration_cap_reached"
MESSAGE_END = "message_end"
ERROR = "error"

# AgentRun-scoped events (added by Stage 4/5; declared here so the loop
# contract is stable from the start).
RUN_START = "run_start"
RUN_STATUS = "run_status"
INPUT_ACCEPTED = "input_accepted"
RUN_END = "run_end"


@dataclass(slots=True)
class AgentLoopEvent:
    """A single ordered event produced by ``AgentLoop``.

    ``type`` uses the public SSE name; ``payload`` is JSON-serializable and
    formatted verbatim by the transport. ``sequence`` is assigned by the
    loop's sink and is monotonically increasing within a run.
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: UUID | None = None
    sequence: int = 0
    timestamp: str = field(default_factory=_now_iso)
    round_id: UUID | None = None
    message_id: UUID | None = None

    def envelope(self) -> dict[str, Any]:
        """Common envelope fields shared by every event."""
        return {
            "run_id": str(self.run_id) if self.run_id else None,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "round_id": str(self.round_id) if self.round_id else None,
            "message_id": str(self.message_id) if self.message_id else None,
        }


class EventSink:
    """Ordered collector for loop events.

    Subclasses format events to a transport (SSE strings, a run buffer) or
    discard them (non-stream result collection). A fresh sink instance is used
    per AgentRun; the loop owns the sequence counter so replay and live
    delivery share the same monotonic order.
    """

    def __init__(self) -> None:
        self.run_id: UUID | None = None
        self._sequence = 0
        self.events: list[AgentLoopEvent] = []

    def assign_run_id(self, run_id: UUID) -> None:
        self.run_id = run_id

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def emit(
        self, event_type: str, payload: dict[str, Any] | None = None, **envelope: Any
    ) -> AgentLoopEvent:
        """Create, stamp, record and return an event.

        ``envelope`` may carry ``round_id`` / ``message_id`` overrides.
        """
        event = AgentLoopEvent(
            type=event_type,
            payload=payload or {},
            run_id=self.run_id,
            sequence=self._next_sequence(),
            round_id=envelope.pop("round_id", None),
            message_id=envelope.pop("message_id", None),
        )
        self.events.append(event)
        return event

    def reset(self) -> None:
        self._sequence = 0
        self.events.clear()


class NullSink(EventSink):
    """Discards events while still assigning sequences (non-stream result
    collection only needs the final ``AgentLoopResult``)."""

    def emit(
        self, event_type: str, payload: dict[str, Any] | None = None, **envelope: Any
    ) -> AgentLoopEvent:
        event = super().emit(event_type, payload, **envelope)
        self.events.pop()
        return event


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort JSON-safe payload copy (drops unserializable values)."""
    import json

    try:
        json.dumps(payload)
        return payload
    except (TypeError, ValueError):
        return {"_unserializable": True}

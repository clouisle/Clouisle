"""Model-callable interactive tool results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolInteractionRequest:
    """A validated tool call that pauses execution for a user response."""

    tool_name: str
    arguments: dict[str, Any]

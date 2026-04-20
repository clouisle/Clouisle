"""
Workflow debugger.

Provides advanced debugging capabilities for workflow development:
- Breakpoints and step-by-step execution
- Variable inspection
- Execution path visualization
- Replay and time-travel debugging
"""

import json
import logging
import asyncio
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from enum import Enum

from app.core.redis import get_redis
from app.services.error_messages import resolve_user_visible_error

logger = logging.getLogger(__name__)


class DebugAction(str, Enum):
    """Debug actions."""

    CONTINUE = "continue"
    STEP_OVER = "step_over"
    STEP_INTO = "step_into"
    STEP_OUT = "step_out"
    PAUSE = "pause"
    STOP = "stop"


class BreakpointType(str, Enum):
    """Breakpoint types."""

    NODE = "node"  # Break at specific node
    CONDITION = "condition"  # Break when condition is true
    ERROR = "error"  # Break on error
    OUTPUT = "output"  # Break when output matches


@dataclass
class Breakpoint:
    """Debug breakpoint."""

    id: str
    breakpoint_type: BreakpointType
    node_id: str | None = None
    condition: str | None = None  # Python expression
    hit_count: int = 0
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.breakpoint_type.value,
            "node_id": self.node_id,
            "condition": self.condition,
            "hit_count": self.hit_count,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class DebugFrame:
    """Represents a single execution frame in debug history."""

    frame_id: str
    timestamp: datetime
    node_id: str
    node_type: str
    node_label: str
    action: str  # "enter", "exit", "error"
    variables: dict
    inputs: dict
    outputs: dict | None = None
    error: str | None = None
    duration_ms: int = 0
    stack_depth: int = 0

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat(),
            "node_id": self.node_id,
            "node_type": self.node_type,
            "node_label": self.node_label,
            "action": self.action,
            "variables": self.variables,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "stack_depth": self.stack_depth,
        }


@dataclass
class DebugSession:
    """Debug session state."""

    session_id: str
    run_id: str
    workflow_id: str
    status: str = "running"  # running, paused, stopped, completed
    current_node_id: str | None = None
    current_frame_index: int = -1
    frames: list[DebugFrame] = field(default_factory=list)
    breakpoints: list[Breakpoint] = field(default_factory=list)
    watches: list[str] = field(default_factory=list)  # Variable names to watch
    call_stack: list[str] = field(default_factory=list)  # Node IDs
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "current_node_id": self.current_node_id,
            "current_frame_index": self.current_frame_index,
            "frame_count": len(self.frames),
            "breakpoint_count": len(self.breakpoints),
            "watches": self.watches,
            "call_stack": self.call_stack,
            "created_at": self.created_at.isoformat(),
        }


class WorkflowDebugger:
    """
    Workflow debugger for interactive debugging.

    Provides:
    - Breakpoint management
    - Step-by-step execution control
    - Variable inspection
    - Execution history (time-travel)
    - Watch expressions

    Example:
        debugger = WorkflowDebugger()

        # Create debug session
        session = await debugger.create_session(run_id, workflow_id)

        # Add breakpoint
        await debugger.add_breakpoint(session.session_id, node_id="llm_1")

        # When paused, inspect variables
        variables = await debugger.get_variables(session.session_id)

        # Continue execution
        await debugger.continue_execution(session.session_id)

        # Time-travel to previous frame
        await debugger.goto_frame(session.session_id, frame_index=5)
    """

    def __init__(self):
        self._sessions: dict[str, DebugSession] = {}
        self._action_events: dict[str, asyncio.Event] = {}
        self._pending_actions: dict[str, DebugAction] = {}
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    # Session Management

    async def create_session(
        self,
        run_id: str,
        workflow_id: str,
    ) -> DebugSession:
        """Create a new debug session."""
        session = DebugSession(
            session_id=str(uuid4()),
            run_id=run_id,
            workflow_id=workflow_id,
        )
        self._sessions[session.session_id] = session
        self._action_events[session.session_id] = asyncio.Event()

        # Store in Redis for distributed access
        await self._save_session(session)

        logger.info(f"Created debug session {session.session_id}")
        return session

    async def get_session(self, session_id: str) -> DebugSession | None:
        """Get debug session by ID."""
        return self._sessions.get(session_id)

    async def end_session(self, session_id: str) -> None:
        """End a debug session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.status = "stopped"
            self._action_events.pop(session_id, None)
            self._pending_actions.pop(session_id, None)
            logger.info(f"Ended debug session {session_id}")

    async def _save_session(self, session: DebugSession) -> None:
        """Save session to Redis."""
        try:
            redis = await self._get_redis()
            await redis.setex(
                f"debug:session:{session.session_id}",
                3600,  # 1 hour TTL
                json.dumps(session.to_dict()),
            )
        except Exception as e:
            logger.warning(f"Failed to save debug session: {e}")

    # Breakpoint Management

    async def add_breakpoint(
        self,
        session_id: str,
        node_id: str | None = None,
        condition: str | None = None,
        breakpoint_type: BreakpointType = BreakpointType.NODE,
    ) -> Breakpoint:
        """Add a breakpoint to the session."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        breakpoint = Breakpoint(
            id=str(uuid4()),
            breakpoint_type=breakpoint_type,
            node_id=node_id,
            condition=condition,
        )
        session.breakpoints.append(breakpoint)

        logger.debug(f"Added breakpoint {breakpoint.id} to session {session_id}")
        return breakpoint

    async def remove_breakpoint(
        self,
        session_id: str,
        breakpoint_id: str,
    ) -> bool:
        """Remove a breakpoint."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.breakpoints = [
            bp for bp in session.breakpoints if bp.id != breakpoint_id
        ]
        return True

    async def toggle_breakpoint(
        self,
        session_id: str,
        breakpoint_id: str,
    ) -> bool:
        """Toggle breakpoint enabled state."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        for bp in session.breakpoints:
            if bp.id == breakpoint_id:
                bp.enabled = not bp.enabled
                return True
        return False

    async def get_breakpoints(
        self,
        session_id: str,
    ) -> list[Breakpoint]:
        """Get all breakpoints for a session."""
        session = self._sessions.get(session_id)
        return session.breakpoints if session else []

    # Execution Control

    async def should_break(
        self,
        session_id: str,
        node_id: str,
        variables: dict,
    ) -> bool:
        """Check if execution should break at this point."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        for bp in session.breakpoints:
            if not bp.enabled:
                continue

            # Check node breakpoint
            if bp.breakpoint_type == BreakpointType.NODE:
                if bp.node_id == node_id:
                    bp.hit_count += 1
                    return True

            # Check conditional breakpoint
            elif bp.breakpoint_type == BreakpointType.CONDITION:
                if bp.condition:
                    try:
                        # Safely evaluate condition
                        result = eval(bp.condition, {"__builtins__": {}}, variables)
                        if result:
                            bp.hit_count += 1
                            return True
                    except Exception as e:
                        logger.warning(f"Breakpoint condition error: {e}")

        return False

    async def pause(self, session_id: str) -> None:
        """Pause execution at next opportunity."""
        session = self._sessions.get(session_id)
        if session:
            session.status = "paused"
            logger.debug(f"Pausing session {session_id}")

    async def resume(
        self,
        session_id: str,
        action: DebugAction = DebugAction.CONTINUE,
    ) -> None:
        """Resume execution with specified action."""
        session = self._sessions.get(session_id)
        if not session:
            return

        session.status = "running"
        self._pending_actions[session_id] = action

        # Signal waiting execution to continue
        event = self._action_events.get(session_id)
        if event:
            event.set()

        logger.debug(f"Resuming session {session_id} with action {action}")

    async def wait_for_action(
        self,
        session_id: str,
        timeout: float = 300,
    ) -> DebugAction:
        """Wait for user action (used when paused)."""
        event = self._action_events.get(session_id)
        if not event:
            return DebugAction.CONTINUE

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            event.clear()
            return self._pending_actions.pop(session_id, DebugAction.CONTINUE)
        except asyncio.TimeoutError:
            return DebugAction.STOP

    async def stop(self, session_id: str) -> None:
        """Stop execution."""
        session = self._sessions.get(session_id)
        if session:
            session.status = "stopped"
            self._pending_actions[session_id] = DebugAction.STOP
            event = self._action_events.get(session_id)
            if event:
                event.set()

    # Frame Recording

    async def record_frame(
        self,
        session_id: str,
        node_id: str,
        node_type: str,
        node_label: str,
        action: str,
        variables: dict,
        inputs: dict,
        outputs: dict | None = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> DebugFrame:
        """Record an execution frame."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Update call stack
        if action == "enter":
            session.call_stack.append(node_id)
        elif (
            action == "exit"
            and session.call_stack
            and session.call_stack[-1] == node_id
        ):
            session.call_stack.pop()

        frame = DebugFrame(
            frame_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            action=action,
            variables=variables.copy(),
            inputs=inputs.copy(),
            outputs=outputs.copy() if outputs else None,
            error=error,
            duration_ms=duration_ms,
            stack_depth=len(session.call_stack),
        )

        session.frames.append(frame)
        session.current_frame_index = len(session.frames) - 1
        session.current_node_id = node_id

        return frame

    async def get_frames(
        self,
        session_id: str,
        start: int = 0,
        limit: int = 100,
    ) -> list[DebugFrame]:
        """Get execution frames."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.frames[start : start + limit]

    async def get_current_frame(
        self,
        session_id: str,
    ) -> DebugFrame | None:
        """Get current execution frame."""
        session = self._sessions.get(session_id)
        if not session or session.current_frame_index < 0:
            return None
        if session.current_frame_index >= len(session.frames):
            return None
        return session.frames[session.current_frame_index]

    # Time-Travel Debugging

    async def goto_frame(
        self,
        session_id: str,
        frame_index: int,
    ) -> DebugFrame | None:
        """
        Navigate to a specific frame (time-travel).

        Note: This is for inspection only, not actual re-execution.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        if 0 <= frame_index < len(session.frames):
            session.current_frame_index = frame_index
            return session.frames[frame_index]
        return None

    async def step_back(self, session_id: str) -> DebugFrame | None:
        """Step back one frame."""
        session = self._sessions.get(session_id)
        if not session or session.current_frame_index <= 0:
            return None
        return await self.goto_frame(session_id, session.current_frame_index - 1)

    async def step_forward(self, session_id: str) -> DebugFrame | None:
        """Step forward one frame."""
        session = self._sessions.get(session_id)
        if not session or session.current_frame_index >= len(session.frames) - 1:
            return None
        return await self.goto_frame(session_id, session.current_frame_index + 1)

    # Variable Inspection

    async def get_variables(
        self,
        session_id: str,
        frame_index: int | None = None,
    ) -> dict:
        """Get variables at current or specified frame."""
        session = self._sessions.get(session_id)
        if not session:
            return {}

        idx = frame_index if frame_index is not None else session.current_frame_index
        if 0 <= idx < len(session.frames):
            return session.frames[idx].variables
        return {}

    async def evaluate_expression(
        self,
        session_id: str,
        expression: str,
        frame_index: int | None = None,
    ) -> Any:
        """
        Evaluate an expression in the context of a frame.

        Warning: Uses eval() - should be sandboxed in production.
        """
        variables = await self.get_variables(session_id, frame_index)

        try:
            # Restricted eval for safety
            allowed_builtins = {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "type": type,
            }
            result = eval(expression, {"__builtins__": allowed_builtins}, variables)
            return {"success": True, "result": result}
        except Exception as e:
            return {
                "success": False,
                "error": resolve_user_visible_error(
                    str(e),
                    fallback_key="workflow_execution_error",
                ),
            }

    # Watch Expressions

    async def add_watch(
        self,
        session_id: str,
        expression: str,
    ) -> bool:
        """Add a watch expression."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        if expression not in session.watches:
            session.watches.append(expression)
        return True

    async def remove_watch(
        self,
        session_id: str,
        expression: str,
    ) -> bool:
        """Remove a watch expression."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        if expression in session.watches:
            session.watches.remove(expression)
            return True
        return False

    async def evaluate_watches(
        self,
        session_id: str,
        frame_index: int | None = None,
    ) -> dict[str, Any]:
        """Evaluate all watch expressions."""
        session = self._sessions.get(session_id)
        if not session:
            return {}

        results = {}
        for expr in session.watches:
            result = await self.evaluate_expression(session_id, expr, frame_index)
            results[expr] = result
        return results

    # Execution Path Analysis

    async def get_execution_path(
        self,
        session_id: str,
    ) -> list[dict]:
        """Get the execution path (sequence of nodes executed)."""
        session = self._sessions.get(session_id)
        if not session:
            return []

        path = []
        for frame in session.frames:
            if frame.action == "enter":
                path.append(
                    {
                        "node_id": frame.node_id,
                        "node_type": frame.node_type,
                        "node_label": frame.node_label,
                        "timestamp": frame.timestamp.isoformat(),
                    }
                )
        return path

    async def get_call_stack(
        self,
        session_id: str,
    ) -> list[str]:
        """Get current call stack."""
        session = self._sessions.get(session_id)
        return session.call_stack.copy() if session else []


# Global debugger instance
_debugger: WorkflowDebugger | None = None


def get_debugger() -> WorkflowDebugger:
    """Get global debugger instance."""
    global _debugger
    if _debugger is None:
        _debugger = WorkflowDebugger()
    return _debugger

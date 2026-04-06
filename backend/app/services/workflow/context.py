"""
Execution context for workflow runs.

Manages state during workflow execution using Redis for distributed access:
- Variables storage
- Node outputs
- Run status
- Stream events (Pub/Sub)
"""

import asyncio
import json
import re
import logging
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import redis.asyncio as redis

logger = logging.getLogger(__name__)


async def _resolve_redis_result(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return await result
    return result


class ExecutionContext:
    """
    Execution context - manages workflow state during execution.

    Uses Redis for distributed access:
    - workflow:run:{run_id}:variables  - Global variables (Hash)
    - workflow:run:{run_id}:outputs    - Node outputs (Hash, JSON encoded)
    - workflow:run:{run_id}:status     - Run status (String)
    - workflow:run:{run_id}:branches   - Active branches (Hash)
    - workflow:run:{run_id}:stream     - Stream channel (Pub/Sub)
    - workflow:run:{run_id}:meta       - Metadata (Hash)
    """

    # Redis key patterns
    VARIABLES_KEY = "workflow:run:{run_id}:variables"
    OUTPUTS_KEY = "workflow:run:{run_id}:outputs"
    STATUS_KEY = "workflow:run:{run_id}:status"
    BRANCHES_KEY = "workflow:run:{run_id}:branches"
    STREAM_KEY = "workflow:run:{run_id}:stream"
    META_KEY = "workflow:run:{run_id}:meta"

    # Default TTL: 24 hours
    DEFAULT_TTL = 86400

    def __init__(self, run_id: str | UUID, redis_client: redis.Redis):
        self.run_id = str(run_id)
        self.redis = redis_client
        self._system_variables: dict[str, Any] = {}
        # 内存缓存：存储无法 JSON 序列化的对象（如 LazyStreamResult）
        self._memory_cache: dict[str, dict[str, Any]] = {}

    # ==================== Factory Methods ====================

    @classmethod
    async def create(
        cls,
        run_id: str | UUID,
        redis_client: redis.Redis,
        workflow_id: str | UUID,
        user_id: str | UUID | None = None,
        ttl: int = DEFAULT_TTL,
    ) -> "ExecutionContext":
        """
        Create a new execution context.

        Args:
            run_id: Workflow run ID
            redis_client: Redis connection
            workflow_id: Workflow ID
            user_id: User who triggered the run
            ttl: Time-to-live for context data in seconds
        """
        ctx = cls(run_id, redis_client)

        # Initialize system variables
        ctx._system_variables = {
            "user_id": str(user_id) if user_id else None,
            "workflow_id": str(workflow_id),
            "workflow_run_id": str(run_id),
            "timestamp": int(datetime.utcnow().timestamp()),
        }

        # Store metadata
        meta_key = cls.META_KEY.format(run_id=ctx.run_id)
        await _resolve_redis_result(
            redis_client.hset(
                meta_key,
                mapping={
                    "workflow_id": str(workflow_id),
                    "user_id": str(user_id) if user_id else "",
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
        )

        # Set initial status
        status_key = cls.STATUS_KEY.format(run_id=ctx.run_id)
        await _resolve_redis_result(redis_client.set(status_key, "pending"))

        # Set TTL on all keys
        await ctx.set_ttl(ttl)

        return ctx

    @classmethod
    async def load(
        cls,
        run_id: str | UUID,
        redis_client: redis.Redis,
    ) -> "ExecutionContext":
        """
        Load an existing execution context (for distributed workers).

        Args:
            run_id: Workflow run ID
            redis_client: Redis connection
        """
        ctx = cls(run_id, redis_client)

        # Load system variables from metadata
        meta_key = cls.META_KEY.format(run_id=ctx.run_id)
        meta = cast(
            dict[str, Any], await _resolve_redis_result(redis_client.hgetall(meta_key))
        )

        if meta:
            ctx._system_variables = {
                "user_id": meta.get("user_id") or None,
                "workflow_id": meta.get("workflow_id", ""),
                "workflow_run_id": str(run_id),
                "timestamp": int(datetime.utcnow().timestamp()),
            }

        return ctx

    # ==================== Variable Management ====================

    async def set_inputs(self, inputs: dict[str, Any]):
        """
        Set workflow input variables.

        These are stored:
        1. Under a special '_inputs' node output for backward compatibility
        2. As sys.inputs.xxx variables for start node to access
        """
        # Store inputs as outputs of the _inputs pseudo-node
        await self.set_node_outputs("_inputs", inputs)

        # Also store as sys.inputs.xxx variables for start node executor
        for key, value in inputs.items():
            await self.set_variable(f"sys.inputs.{key}", value)

    async def get_inputs(self) -> dict[str, Any]:
        """Get workflow input variables."""
        return await self.get_node_outputs("_inputs") or {}

    async def set_variable(self, name: str, value: Any):
        """Set a global variable."""
        key = self.VARIABLES_KEY.format(run_id=self.run_id)
        await _resolve_redis_result(
            self.redis.hset(key, name, json.dumps(value, ensure_ascii=False))
        )

    async def get_variable(self, name: str) -> Any:
        """Get a global variable."""
        key = self.VARIABLES_KEY.format(run_id=self.run_id)
        value = await _resolve_redis_result(self.redis.hget(key, name))
        return json.loads(value) if value else None

    async def get_all_variables(self) -> dict[str, Any]:
        """Get all global variables."""
        key = self.VARIABLES_KEY.format(run_id=self.run_id)
        data = cast(
            dict[str, str], await _resolve_redis_result(self.redis.hgetall(key))
        )
        return {k: json.loads(v) for k, v in data.items()}

    # ==================== Node Output Management ====================

    async def set_node_outputs(self, node_id: str, outputs: dict[str, Any]):
        """
        Save node outputs.

        Args:
            node_id: Node ID
            outputs: Output variables dictionary
        """
        from .lazy_stream import LazyStreamResult

        # Separate serializable and non-serializable (lazy) outputs
        serializable_outputs = {}
        lazy_outputs = {}

        for key, value in outputs.items():
            if isinstance(value, LazyStreamResult):
                lazy_outputs[key] = value
                serializable_outputs[key] = "__LAZY_STREAM__"  # Placeholder
            else:
                serializable_outputs[key] = value

        # Store serializable outputs in Redis
        key = self.OUTPUTS_KEY.format(run_id=self.run_id)
        await _resolve_redis_result(
            self.redis.hset(
                key, node_id, json.dumps(serializable_outputs, ensure_ascii=False)
            )
        )

        # Store lazy outputs in memory
        if lazy_outputs:
            self._memory_cache[node_id] = lazy_outputs

        logger.debug(f"Set outputs for node {node_id}: {list(outputs.keys())}")

    async def get_node_outputs(self, node_id: str) -> dict[str, Any] | None:
        """
        Get node outputs.

        Args:
            node_id: Node ID

        Returns:
            Output variables dictionary or None if not found
        """
        key = self.OUTPUTS_KEY.format(run_id=self.run_id)
        value = await _resolve_redis_result(self.redis.hget(key, node_id))
        if not value:
            return None

        outputs = json.loads(value)

        # Merge lazy outputs from memory cache
        if node_id in self._memory_cache:
            for key, lazy_value in self._memory_cache[node_id].items():
                outputs[key] = lazy_value

        return outputs

    async def get_all_node_outputs(self) -> dict[str, dict[str, Any]]:
        """Get all node outputs."""
        key = self.OUTPUTS_KEY.format(run_id=self.run_id)
        data = cast(
            dict[str, str], await _resolve_redis_result(self.redis.hgetall(key))
        )
        return {k: json.loads(v) for k, v in data.items()}

    # ==================== Variable Resolution ====================

    def _get_system_variable(self, name: str) -> Any:
        """Get a system variable value."""
        return self._system_variables.get(name)

    async def resolve_variable_ref(
        self, ref: str, stream_to_node_id: str | None = None
    ) -> Any:
        """
        Resolve a variable reference.

        Supports formats:
        - {{node_id.variable_name}} - Node output variable
        - {{sys.xxx}} - System variable
        - Plain string with embedded references

        Args:
            ref: Variable reference string
            stream_to_node_id: If provided and the value is a LazyStreamResult,
                              execute it and stream tokens to this node ID

        Returns:
            Resolved value
        """
        if not ref or not isinstance(ref, str):
            return ref

        pattern = r"\{\{([^}]+)\}\}"

        # Check if the entire string is a single variable reference
        single_match = re.fullmatch(pattern, ref.strip())
        if single_match:
            var_path = single_match.group(1).strip()
            return await self._resolve_single_variable(var_path, stream_to_node_id)

        # Multiple references or embedded in text - do string replacement
        async def replace_var(match: re.Match) -> str:
            var_path = match.group(1).strip()
            value = await self._resolve_single_variable(var_path, stream_to_node_id)
            return str(value) if value is not None else ""

        # Process all matches
        result = ref
        for match in re.finditer(pattern, ref):
            var_path = match.group(1).strip()
            value = await self._resolve_single_variable(var_path, stream_to_node_id)
            result = result.replace(
                match.group(0), str(value) if value is not None else ""
            )

        return result

    async def _resolve_single_variable(
        self, var_path: str, stream_to_node_id: str | None = None
    ) -> Any:
        """
        Resolve a single variable path.

        Args:
            var_path: Variable path like "node_id.var_name" or "sys.xxx" or "conversation.xxx" or just "var_name"
            stream_to_node_id: If provided and the value is a LazyStreamResult,
                              execute it and stream tokens to this node ID

        Returns:
            Resolved value or None
        """
        from .lazy_stream import LazyStreamResult

        parts = var_path.split(".", 1)

        if len(parts) == 1:
            var_name = parts[0]

            # Check for sys_ prefixed system variables (e.g. sys_user_id)
            if var_name.startswith("sys_"):
                sys_key = var_name[4:]  # Strip "sys_" prefix
                sys_value = self._get_system_variable(sys_key)
                if sys_value is not None:
                    return sys_value

            # Single part - could be:
            # 1. A node ID returning all outputs
            # 2. An input variable name (no node prefix)
            # 3. A global variable name

            # First try as input variable (stored under _inputs)
            inputs = await self.get_node_outputs("_inputs")
            if inputs and var_name in inputs:
                return inputs[var_name]

            # Try as a global variable
            global_value = await self.get_variable(var_name)
            if global_value is not None:
                return global_value

            # Then try as node ID returning all outputs
            outputs = await self.get_node_outputs(var_name)
            return outputs

        source, var_name = parts

        if source == "sys":
            # System variable
            return self._get_system_variable(var_name)

        if source == "conversation":
            # Conversation variable (stored via variable assignment node)
            return await self.get_variable(var_name)

        # Node output variable
        outputs = await self.get_node_outputs(source)
        if outputs:
            value = outputs.get(var_name)

            # Check if it's a lazy stream result
            if isinstance(value, LazyStreamResult):
                # Execute the lazy result, streaming to the specified node
                logger.info(
                    f"Executing lazy stream result for {var_path}, streaming to {stream_to_node_id}"
                )
                result = await value.execute(stream_to_node_id)
                # Update the stored value with the actual result
                outputs[var_name] = result
                # Also update reasoning and usage if they were captured
                if value.reasoning is not None:
                    outputs["reasoning"] = value.reasoning
                if value.usage is not None:
                    outputs["usage"] = value.usage
                await self.set_node_outputs(source, outputs)
                return result

            return value

        return None

    async def resolve_template(self, template: str) -> str:
        """
        Resolve all variable references in a template string.

        Args:
            template: Template string with {{var}} placeholders

        Returns:
            Resolved string
        """
        if not template:
            return template

        result = await self.resolve_variable_ref(template)
        return str(result) if result is not None else ""

    # ==================== Branch Management ====================

    async def set_branch(self, node_id: str, handle: str):
        """
        Set a single active output branch for a node.

        Args:
            node_id: Node ID
            handle: Active source handle ID
        """
        await self.set_active_branches(node_id, [handle])

    async def set_active_branches(self, node_id: str, handles: list[str]):
        """
        Set active output branches for a node (used by condition/classifier nodes).

        Args:
            node_id: Node ID
            handles: List of active source handle IDs
        """
        key = self.BRANCHES_KEY.format(run_id=self.run_id)
        await _resolve_redis_result(self.redis.hset(key, node_id, json.dumps(handles)))

    async def get_active_branches(self, node_id: str) -> list[str] | None:
        """
        Get active branches for a node.

        Args:
            node_id: Node ID

        Returns:
            List of active handle IDs or None
        """
        key = self.BRANCHES_KEY.format(run_id=self.run_id)
        value = await _resolve_redis_result(self.redis.hget(key, node_id))
        return json.loads(value) if value else None

    async def should_execute_node(
        self,
        node_id: str,
        incoming_edges: list[dict],
    ) -> bool:
        """
        Check if a node should be executed based on branch conditions.

        Args:
            node_id: Node ID to check
            incoming_edges: List of edges pointing to this node

        Returns:
            True if the node should be executed
        """
        if not incoming_edges:
            # No incoming edges = start node, always execute
            return True

        for edge in incoming_edges:
            source_node = edge.get("source")
            source_handle = edge.get("sourceHandle")

            # Check if source node has active branches
            if not isinstance(source_node, str):
                continue
            active_branches = await self.get_active_branches(source_node)

            if active_branches is None:
                # No branch restriction, check if source node has outputs
                outputs = await self.get_node_outputs(source_node)
                if outputs is not None:
                    return True
            elif source_handle in active_branches:
                # This branch is active
                return True

        return False

    # ==================== Status Management ====================

    async def set_status(self, status: str):
        """Set run status."""
        key = self.STATUS_KEY.format(run_id=self.run_id)
        await _resolve_redis_result(self.redis.set(key, status))

    async def get_status(self) -> str | None:
        """Get run status."""
        key = self.STATUS_KEY.format(run_id=self.run_id)
        return cast(str | None, await _resolve_redis_result(self.redis.get(key)))

    # ==================== Stream Publishing ====================

    async def publish_event(self, event_data: dict):
        """
        Publish a stream event.

        Args:
            event_data: Event data dictionary
        """
        key = self.STREAM_KEY.format(run_id=self.run_id)
        await _resolve_redis_result(
            self.redis.publish(key, json.dumps(event_data, ensure_ascii=False))
        )

    def get_stream_channel(self) -> str:
        """Get the Redis Pub/Sub channel name for this run."""
        return self.STREAM_KEY.format(run_id=self.run_id)

    # ==================== TTL Management ====================

    async def set_ttl(self, seconds: int = DEFAULT_TTL):
        """
        Set TTL on all context keys.

        Args:
            seconds: Time-to-live in seconds
        """
        key_patterns = [
            self.VARIABLES_KEY,
            self.OUTPUTS_KEY,
            self.STATUS_KEY,
            self.BRANCHES_KEY,
            self.META_KEY,
        ]

        for pattern in key_patterns:
            key = pattern.format(run_id=self.run_id)
            await _resolve_redis_result(self.redis.expire(key, seconds))

    async def cleanup(self):
        """Remove all context data immediately."""
        key_patterns = [
            self.VARIABLES_KEY,
            self.OUTPUTS_KEY,
            self.STATUS_KEY,
            self.BRANCHES_KEY,
            self.META_KEY,
        ]

        for pattern in key_patterns:
            key = pattern.format(run_id=self.run_id)
            await _resolve_redis_result(self.redis.delete(key))

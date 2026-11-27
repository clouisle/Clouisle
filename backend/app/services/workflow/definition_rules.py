"""Structural rules a workflow definition must satisfy when it is saved.

A run inside an iteration/loop body cannot pause: the container executes one
round at a time and has no way to resume mid-round without replaying earlier
rounds. Pause nodes therefore cannot live inside a container, and neither can a
tool node whose tool can require approval. The runtime keeps a fail-closed
guard for definitions that predate this rule or whose tool policy changed after
saving, but the editor and API reject the shape up front.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.models.tool import Tool, ToolType
from app.schemas.tool_approval import ApprovalDecision, ToolApprovalPolicy
from app.services import tool_approvals

logger = logging.getLogger(__name__)

CONTAINER_NODE_TYPES = frozenset({"iteration", "loop"})

#: Reasons a node may not sit inside a container, in report order.
PAUSE_REASON = "pause"
APPROVAL_REASON = "approval"


def _node_type(node: dict[str, Any]) -> str:
    return str(node.get("type") or "")


def _parent_id(node: dict[str, Any]) -> str | None:
    data = node.get("data")
    parent = node.get("parentId") or node.get("parent_id")
    if not parent and isinstance(data, dict):
        parent = data.get("parentId") or data.get("parent_id")
    return str(parent) if parent else None


def _node_config(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    if not isinstance(data, dict):
        return {}
    config = data.get("toolConfig") or data.get("config")
    return config if isinstance(config, dict) else {}


def _enclosing_container(
    node: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> str | None:
    """Nearest iteration/loop ancestor id, walking ``parentId`` upwards."""
    seen: set[str] = set()
    parent_id = _parent_id(node)
    while parent_id and parent_id in by_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id[parent_id]
        if _node_type(parent) in CONTAINER_NODE_TYPES:
            return parent_id
        parent_id = _parent_id(parent)
    return None


def policy_may_require_approval(policy: object) -> bool:
    """Whether any operation of this stored policy can require approval.

    An unparseable policy counts as requiring approval: the runtime rejects a
    broken policy anyway, and treating it as permissive would let a definition
    save only to fail at run time.
    """
    if not policy:
        return False
    try:
        normalized: ToolApprovalPolicy = tool_approvals.normalize_tool_approval_policy(
            policy
        )
    except tool_approvals.PolicyConfigurationError:
        return True
    candidates = [normalized, *normalized.operation_overrides.values()]
    return any(
        item.default_decision == ApprovalDecision.REQUIRE_APPROVAL
        for item in candidates
    )


async def _load_tool_config(
    team_id: UUID, node: dict[str, Any]
) -> dict[str, Any] | None:
    """The stored policy of the tool this node calls, when one is resolvable.

    Read-only on purpose: a validator must not materialize a builtin definition
    while merely checking a definition. An unresolvable tool is left to the
    runtime, which reports `tool_not_found` with the real context.
    """
    config = _node_config(node)
    tool_id = config.get("toolId") or config.get("tool_id")
    tool_name = config.get("toolName") or config.get("tool_name")
    tool_type = config.get("toolType") or config.get("tool_type")

    tool: Tool | None = None
    if tool_id:
        try:
            tool = await Tool.filter(id=UUID(str(tool_id))).first()
        except (ValueError, TypeError):
            return None
    elif tool_type == ToolType.BUILTIN.value and tool_name:
        tool = await Tool.filter(
            team_id=team_id, name=str(tool_name), type=ToolType.BUILTIN.value
        ).first()
    if tool is None:
        return None
    policy = tool.approval_policy
    return policy if isinstance(policy, dict) else None


async def validate_container_nodes(
    team_id: UUID, definition: object
) -> list[tuple[str, str]]:
    """Return ``(node_id, reason)`` for nodes that cannot live in a container."""
    if not isinstance(definition, dict):
        return []
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return []

    by_id = {
        str(node["id"]): node
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }

    problems: list[tuple[str, str]] = []
    for node_id, node in by_id.items():
        if _enclosing_container(node, by_id) is None:
            continue
        node_type = _node_type(node)
        if node_type == "pause":
            problems.append((node_id, PAUSE_REASON))
        elif node_type == "tool":
            policy = await _load_tool_config(team_id, node)
            if policy is not None and policy_may_require_approval(policy):
                problems.append((node_id, APPROVAL_REASON))
    return problems

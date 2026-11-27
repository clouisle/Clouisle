from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.workflow import definition_rules


class _ToolQuery:
    """Stand-in for ``Tool.filter(...)`` returning one row per lookup."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def filter(self, **kwargs):
        self.calls.append(kwargs)
        rows = self.rows

        class _Awaitable:
            async def first(self_inner):
                return rows.pop(0) if rows else None

        return _Awaitable()


def _definition(*nodes):
    return {"nodes": list(nodes), "edges": []}


def _node(node_id, node_type, parent=None, **config):
    data = {"type": node_type, "label": node_id}
    if parent:
        data["parentId"] = parent
    if node_type == "tool":
        data["toolConfig"] = config
    return {"id": node_id, "type": node_type, "data": data}


def test_policy_may_require_approval_reads_default_and_overrides():
    assert (
        definition_rules.policy_may_require_approval({"default_decision": "allow"})
        is False
    )
    assert definition_rules.policy_may_require_approval({}) is False
    assert (
        definition_rules.policy_may_require_approval(
            {"default_decision": "require_approval"}
        )
        is True
    )
    # A single operation override is enough: that call can still park.
    assert (
        definition_rules.policy_may_require_approval(
            {
                "default_decision": "allow",
                "operation_overrides": {
                    "tool:delete": {"default_decision": "require_approval"}
                },
            }
        )
        is True
    )
    # An unparseable policy must not pass as permissive.
    assert definition_rules.policy_may_require_approval({"nope": 1}) is True


@pytest.mark.asyncio
async def test_pause_node_inside_container_is_rejected(monkeypatch):
    monkeypatch.setattr(
        definition_rules,
        "Tool",
        SimpleNamespace(filter=lambda **_kwargs: None),
    )
    definition = _definition(
        _node("loop-1", "loop"),
        _node("pause-1", "pause", parent="loop-1"),
    )

    problems = await definition_rules.validate_container_nodes(uuid4(), definition)

    assert problems == [("pause-1", definition_rules.PAUSE_REASON)]


@pytest.mark.asyncio
async def test_editor_top_level_parent_id_is_rejected():
    definition = _definition(
        _node("loop-1", "loop"),
        {**_node("pause-1", "pause"), "parentId": "loop-1"},
    )

    assert await definition_rules.validate_container_nodes(uuid4(), definition) == [
        ("pause-1", definition_rules.PAUSE_REASON)
    ]


@pytest.mark.asyncio
async def test_nodes_outside_containers_are_allowed(monkeypatch):
    monkeypatch.setattr(
        definition_rules,
        "Tool",
        SimpleNamespace(filter=lambda **_kwargs: None),
    )
    definition = _definition(
        _node("loop-1", "loop"),
        _node("pause-1", "pause"),
        _node("tool-1", "tool", toolId=str(uuid4()), toolType="custom"),
    )

    assert await definition_rules.validate_container_nodes(uuid4(), definition) == []


@pytest.mark.asyncio
async def test_approval_tool_inside_container_is_rejected(monkeypatch):
    nested = SimpleNamespace(loop=uuid4())
    tool_id = uuid4()

    async def _first():
        return SimpleNamespace(approval_policy={"default_decision": "require_approval"})

    monkeypatch.setattr(
        definition_rules,
        "Tool",
        SimpleNamespace(filter=lambda **_kwargs: SimpleNamespace(first=_first)),
    )
    definition = _definition(
        _node("iteration-1", "iteration"),
        _node(
            "nested-iteration-1", "iteration", parent="iteration-1", **{"loop": nested}
        ),
        _node("tool-1", "tool", parent="nested-iteration-1", toolId=str(tool_id)),
    )

    problems = await definition_rules.validate_container_nodes(uuid4(), definition)

    assert problems == [("tool-1", definition_rules.APPROVAL_REASON)]


@pytest.mark.asyncio
async def test_allow_tool_inside_container_is_accepted(monkeypatch):
    async def _first():
        return SimpleNamespace(approval_policy={"default_decision": "allow"})

    monkeypatch.setattr(
        definition_rules,
        "Tool",
        SimpleNamespace(filter=lambda **_kwargs: SimpleNamespace(first=_first)),
    )
    definition = _definition(
        _node("loop-1", "loop"),
        _node("tool-1", "tool", parent="loop-1", toolId=str(uuid4())),
    )

    assert await definition_rules.validate_container_nodes(uuid4(), definition) == []


@pytest.mark.asyncio
async def test_unresolvable_tool_is_left_to_the_runtime(monkeypatch):
    async def _first():
        return None

    monkeypatch.setattr(
        definition_rules,
        "Tool",
        SimpleNamespace(filter=lambda **_kwargs: SimpleNamespace(first=_first)),
    )
    definition = _definition(
        _node("loop-1", "loop"),
        _node("tool-1", "tool", parent="loop-1", toolId=str(uuid4())),
    )

    assert await definition_rules.validate_container_nodes(uuid4(), definition) == []


@pytest.mark.asyncio
async def test_builtin_tool_resolves_by_team_and_name(monkeypatch):
    seen: list[dict] = []

    async def _first():
        return None

    def _filter(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(first=_first)

    monkeypatch.setattr(definition_rules, "Tool", SimpleNamespace(filter=_filter))
    team_id = uuid4()
    definition = _definition(
        _node("loop-1", "loop"),
        _node(
            "tool-1",
            "tool",
            parent="loop-1",
            toolType="builtin",
            toolName="get_current_time",
        ),
    )

    await definition_rules.validate_container_nodes(team_id, definition)

    assert seen == [{"team_id": team_id, "name": "get_current_time", "type": "builtin"}]

"""End-to-end check that workflow values keep their native types across the
ExecutionContext serialization boundary, including:

- dict / list survive set/get without becoming JSON strings
- single `{{node.field}}` references return the raw native value
- multi-reference / embedded interpolation renders dicts as JSON, not Python repr
- numeric / bool / None scalars round-trip as their Python types
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.services.workflow.context import ExecutionContext


class _InMemoryRedis:
    """Minimal async Redis stand-in for the hash / pub-sub / string ops used by
    ExecutionContext during these tests. Stores everything as Python `str`,
    matching the real `decode_responses=True` client.
    """

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._strings: dict[str, str] = {}

    async def hset(
        self,
        key: str,
        field: str | None = None,
        value: Any = None,
        *,
        mapping: dict[str, Any] | None = None,
    ) -> int:
        bucket = self._hashes.setdefault(key, {})
        if mapping is not None:
            for k, v in mapping.items():
                bucket[k] = v if isinstance(v, str) else str(v)
            return len(mapping)
        if field is None:
            raise ValueError("hset requires field or mapping")
        bucket[field] = value if isinstance(value, str) else str(value)
        return 1

    async def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def set(self, key: str, value: str) -> bool:
        self._strings[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._strings.get(key)

    async def expire(self, key: str, seconds: int) -> bool:  # pragma: no cover - no-op
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._hashes:
                del self._hashes[k]
                n += 1
            if k in self._strings:
                del self._strings[k]
                n += 1
        return n

    async def publish(self, channel: str, message: str) -> int:  # pragma: no cover
        return 0


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(run_id=str(uuid4()), redis_client=_InMemoryRedis())  # type: ignore[arg-type]


class TestNodeOutputNativeRoundTrip:
    @pytest.mark.asyncio
    async def test_list_of_dicts_survives_round_trip(self, context: ExecutionContext):
        outputs = {"items": [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]}
        await context.set_node_outputs("code-1", outputs)
        got = await context.get_node_outputs("code-1")
        assert got == outputs
        assert isinstance(got["items"], list)
        assert isinstance(got["items"][0], dict)
        assert got["items"][0]["a"] == 1

    @pytest.mark.asyncio
    async def test_nested_dict_survives_round_trip(self, context: ExecutionContext):
        payload = {"user": {"name": "张三", "age": 30, "tags": ["a", "b"]}}
        await context.set_node_outputs("n1", payload)
        got = await context.get_node_outputs("n1")
        assert got == payload
        assert got["user"]["age"] == 30

    @pytest.mark.asyncio
    async def test_scalar_types_preserved(self, context: ExecutionContext):
        await context.set_node_outputs(
            "n",
            {"i": 42, "f": 1.5, "b": True, "n": None, "s": "hi"},
        )
        got = await context.get_node_outputs("n")
        assert got["i"] == 42 and isinstance(got["i"], int)
        assert got["f"] == 1.5 and isinstance(got["f"], float)
        assert got["b"] is True
        assert got["n"] is None
        assert got["s"] == "hi"


class TestVariableRefReturnsNative:
    @pytest.mark.asyncio
    async def test_single_ref_returns_dict(self, context: ExecutionContext):
        await context.set_node_outputs("upstream", {"obj": {"k": "v", "n": 1}})
        value = await context.resolve_variable_ref("{{upstream.obj}}")
        assert value == {"k": "v", "n": 1}
        assert isinstance(value, dict)

    @pytest.mark.asyncio
    async def test_single_ref_returns_list(self, context: ExecutionContext):
        await context.set_node_outputs("upstream", {"items": [1, 2, 3]})
        value = await context.resolve_variable_ref("{{upstream.items}}")
        assert value == [1, 2, 3]
        assert isinstance(value, list)

    @pytest.mark.asyncio
    async def test_embedded_dict_renders_as_json_not_pyrepr(
        self, context: ExecutionContext
    ):
        await context.set_node_outputs("u", {"obj": {"k": "v"}})
        rendered = await context.resolve_variable_ref("name=test data={{u.obj}} done")
        # Pre-Stage 1 this would have been "{'k': 'v'}" (Python repr).
        assert rendered == 'name=test data={"k": "v"} done'

    @pytest.mark.asyncio
    async def test_embedded_chinese_dict_keeps_unicode(self, context: ExecutionContext):
        await context.set_node_outputs("u", {"obj": {"姓名": "张三"}})
        rendered = await context.resolve_variable_ref("{{u.obj}}")
        # Single-ref returns native dict, not string
        assert rendered == {"姓名": "张三"}

    @pytest.mark.asyncio
    async def test_resolve_template_renders_dict_as_json(
        self, context: ExecutionContext
    ):
        await context.set_node_outputs("u", {"obj": {"k": 1}})
        rendered = await context.resolve_template("{{u.obj}}")
        assert rendered == '{"k": 1}'


class TestVariableRoundTrip:
    @pytest.mark.asyncio
    async def test_global_variable_preserves_list(self, context: ExecutionContext):
        await context.set_variable("v", [{"a": 1}])
        got = await context.get_variable("v")
        assert got == [{"a": 1}]
        assert isinstance(got, list)

    @pytest.mark.asyncio
    async def test_global_variable_preserves_dict(self, context: ExecutionContext):
        await context.set_variable("v", {"a": [1, 2]})
        got = await context.get_variable("v")
        assert got == {"a": [1, 2]}


class TestActiveBranches:
    @pytest.mark.asyncio
    async def test_branches_round_trip_as_list(self, context: ExecutionContext):
        await context.set_active_branches("cond-1", ["if", "default"])
        got = await context.get_active_branches("cond-1")
        assert got == ["if", "default"]
        assert isinstance(got, list)

"""Boundary behavior for trajectory capture without a healthy run context.

Covers the capture contract at its edges: missing run correlation, conversations
whose messages are not plain mappings, non-JSON model configuration, legacy and
mapping tool definitions, unparseable stored legacy text, a model turn whose
request and response both exceed the bounded snapshot, and the best-effort
write policy that must never break the model or tool outcome it records.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.observability_payload import ObservabilityTrajectoryEntry
from app.services import observability_trajectory as trajectory
from app.services.observability_trajectory import (
    MAX_ENTRY_BYTES,
    WRITE_TIMEOUT_SECONDS,
    _one_line,
    entry_payload,
    finish_model_call,
    record_model_request,
    record_tool_call,
    safe_model_options,
    serialize_tools,
)


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


async def _request(run_id, *, messages, model="test-model", tools=None):
    return await record_model_request(
        run_id=run_id,
        conversation_id=None,
        model=model,
        provider="openai",
        model_id="model-uuid",
        streaming=False,
        messages=messages,
        tools=tools,
        options={"temperature": 0.2},
    )


async def _finish(handle, *, content=None, tool_calls=None, error=None):
    await finish_model_call(
        handle,
        status="completed",
        content=content,
        reasoning=None,
        tool_calls=tool_calls,
        finish_reason="stop",
        token_usage={"total_tokens": 3},
        error=error,
    )


async def _count_entries() -> int:
    return await ObservabilityTrajectoryEntry.all().count()


@pytest.mark.asyncio
async def test_request_without_run_correlation_is_not_persisted(database):
    before = await _count_entries()

    handle = await _request(None, messages=[{"role": "user", "content": "hello"}])

    assert handle is None
    assert await _count_entries() == before


@pytest.mark.asyncio
async def test_preview_skips_non_mapping_messages_and_falls_back_to_model(database):
    run_id = uuid4()
    # Reverse scan must ignore a non-mapping entry and a mapping with no
    # usable content instead of failing the capture.
    handle = await _request(
        run_id,
        messages=[
            {"role": "system", "content": "   "},
            object(),
            {"role": "assistant", "content": None},
        ],
        model="fallback-model",
    )

    assert handle is not None
    assert handle.request_preview == "fallback-model"
    stored = await ObservabilityTrajectoryEntry.get(id=handle.entry_id)
    assert stored.preview == "fallback-model"
    assert stored.payload_state == "partial"


@pytest.mark.asyncio
async def test_preview_serializes_structured_message_content(database):
    run_id = uuid4()
    handle = await _request(
        run_id,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": "inspect the attached asset"}],
            }
        ],
    )

    assert handle is not None
    assert handle.request_preview is not None
    assert "inspect the attached asset" in handle.request_preview
    stored = await ObservabilityTrajectoryEntry.get(id=handle.entry_id)
    assert stored.preview == handle.request_preview


def test_one_line_never_raises_on_unserializable_or_missing_values():
    assert _one_line(None) is None

    circular: list[object] = []
    circular.append(circular)
    preview = _one_line(circular)
    assert preview is not None
    assert "..." in preview


def test_mapping_model_config_keeps_only_allowlisted_inference_parameters():
    options = safe_model_options(
        {
            "default_params": {
                "temperature": 0.4,
                "max_tokens": 128,
                "api_key": "sk-secret",
                "base_url": "https://internal.example",
            }
        },
        top_p=0.8,
        seed=None,
        api_key="sk-override-secret",
    )

    assert options == {"temperature": 0.4, "max_tokens": 128, "top_p": 0.8}


def test_serialize_tools_accepts_dict_pydantic_like_and_attribute_definitions():
    openai_tool = {
        "type": "function",
        "function": {"name": "search", "parameters": {"type": "object"}},
    }

    class _DumpNeedsNoArguments:
        def model_dump(self, **kwargs):
            if kwargs:
                raise TypeError("exclude_none is not supported")
            return {"type": "function", "function": {"name": "legacy_dump"}}

    legacy_tool = SimpleNamespace(
        type="function",
        function=SimpleNamespace(
            name="read_asset",
            description="Read one asset",
            parameters={"type": "object"},
        ),
    )

    assert serialize_tools([openai_tool, _DumpNeedsNoArguments(), legacy_tool]) == [
        openai_tool,
        {"type": "function", "function": {"name": "legacy_dump"}},
        {
            "type": "function",
            "function": {
                "name": "read_asset",
                "description": "Read one asset",
                "parameters": {"type": "object"},
            },
        },
    ]


@pytest.mark.asyncio
async def test_finishing_without_a_handle_is_a_noop(database):
    before = await _count_entries()

    await _finish(None, content="ignored")

    assert await _count_entries() == before


@pytest.mark.asyncio
async def test_dict_shaped_tool_calls_are_ignored_without_losing_the_turn(database):
    run_id = uuid4()
    handle = await _request(
        run_id, messages=[{"role": "user", "content": "use a tool"}]
    )

    await _finish(
        handle,
        content=None,
        tool_calls=[
            {"id": "call-1", "function": {"name": "search"}},
            SimpleNamespace(function=SimpleNamespace(name="missing-id")),
        ],
    )

    stored = await ObservabilityTrajectoryEntry.get(id=handle.entry_id)
    output = json.loads(stored.output_text)
    assert output["tool_calls"] == []
    assert stored.tool_call_ids == []
    # The request preview is retained so the empty-content turn stays readable.
    assert stored.preview == "use a tool"
    assert stored.payload_state == "recorded"


@pytest.mark.asyncio
async def test_both_sides_oversized_leaves_the_entry_unrecorded(database):
    run_id = uuid4()
    handle = await _request(
        run_id,
        messages=[{"role": "user", "content": "q" * (MAX_ENTRY_BYTES + 1)}],
    )
    assert handle is not None
    assert handle.input_recorded is False
    assert handle.input_partial is True

    await _finish(handle, content="a" * (MAX_ENTRY_BYTES + 1))

    stored = await ObservabilityTrajectoryEntry.get(id=handle.entry_id)
    assert stored.input_text is None
    assert stored.output_text is None
    assert stored.payload_state == "unrecorded"
    assert stored.partial is True
    assert len(stored.preview) < len("a" * (MAX_ENTRY_BYTES + 1))

    input_value, output_value, partial, recorded = entry_payload(stored)
    assert input_value is None
    assert output_value is None
    assert partial is True
    assert recorded is False


@pytest.mark.asyncio
async def test_tool_call_without_run_or_call_id_is_not_persisted(database):
    before = await _count_entries()

    await record_tool_call(
        run_id=None,
        conversation_id=None,
        parent_id=None,
        tool_call_id="call-1",
        tool_name="search",
        arguments={"query": "x"},
        status="completed",
        started_at=None,
        finished_at=None,
        duration_ms=1,
    )
    await record_tool_call(
        run_id=uuid4(),
        conversation_id=None,
        parent_id=None,
        tool_call_id="",
        tool_name="search",
        arguments={"query": "x"},
        status="completed",
        started_at=None,
        finished_at=None,
        duration_ms=1,
    )

    assert await _count_entries() == before


@pytest.mark.asyncio
async def test_non_json_legacy_input_is_returned_verbatim(database):
    entry = await ObservabilityTrajectoryEntry.create(
        id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        kind="model",
        name="test-model",
        status="completed",
        payload_state="recorded",
        input_text="legacy plain-text prompt",
        output_text=json.dumps({"content": "ok", "tool_calls": []}),
        partial=False,
    )

    input_value, output_value, partial, recorded = entry_payload(entry)

    assert input_value == "legacy plain-text prompt"
    assert output_value == {"content": "ok", "tool_calls": []}
    assert partial is False
    assert recorded is True


@pytest.mark.asyncio
async def test_slow_write_times_out_without_failing_the_model_boundary(
    monkeypatch, database
):
    class _SlowEntry:
        @staticmethod
        async def create(**_kwargs):
            await asyncio.sleep(WRITE_TIMEOUT_SECONDS * 50)

    monkeypatch.setattr(trajectory, "ObservabilityTrajectoryEntry", _SlowEntry)
    before = await _count_entries()

    started = time.monotonic()
    handle = await _request(uuid4(), messages=[{"role": "user", "content": "hello"}])
    elapsed = time.monotonic() - started

    assert handle is not None
    assert handle.input_recorded is True
    assert handle.request_preview == "hello"
    assert elapsed < WRITE_TIMEOUT_SECONDS * 10
    assert await _count_entries() == before


@pytest.mark.asyncio
async def test_storage_errors_fail_open_for_request_response_and_tool_writes(
    monkeypatch, database
):
    class _ExplodingEntry:
        @staticmethod
        async def create(**_kwargs):
            raise RuntimeError("trajectory store unavailable")

        @classmethod
        def filter(cls, **_kwargs):
            return cls()

        async def update(self, **_kwargs):
            raise RuntimeError("trajectory store unavailable")

    monkeypatch.setattr(trajectory, "ObservabilityTrajectoryEntry", _ExplodingEntry)

    handle = await _request(uuid4(), messages=[{"role": "user", "content": "hello"}])
    assert handle is not None

    await _finish(handle, content="ok")
    await record_tool_call(
        run_id=uuid4(),
        conversation_id=None,
        parent_id=None,
        tool_call_id="call-1",
        tool_name="search",
        arguments={"query": "x"},
        status="completed",
        started_at=None,
        finished_at=None,
        duration_ms=1,
    )

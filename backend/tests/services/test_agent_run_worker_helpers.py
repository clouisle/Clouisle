"""Branch coverage for the durable AgentRun worker helpers.

These tests pin the pure helper layer of agent_run_worker: payload
normalization, SSE decoding, JSON-safe conversion, and the run finalization
helpers. They run without the ORM: models and services are mocked at
module level per project convention.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.services.agent_run_worker import (
    _RunFormatter,
    _decode_sse_payload,
    _json_safe,
)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


class _PydanticLike(BaseModel):
    name: str
    tags: list[str]


# ---------------------------------------------------------------------------
# _decode_sse_payload
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [None, "", "not-an-sse-event", "event: x\n\n", _sse("x", "not-json")],
)
def test_decode_sse_payload_returns_none_for_unusable_input(raw):
    assert _decode_sse_payload(raw) is None


def test_decode_sse_payload_rejects_non_dict_json():
    assert _decode_sse_payload(_sse("x", "[1, 2, 3]")) is None
    assert _decode_sse_payload(_sse("x", '"text"')) is None


def test_decode_sse_payload_decodes_data_line():
    assert _decode_sse_payload(_sse("tool_call", '{"tool_call_id": "c1"}')) == {
        "tool_call_id": "c1"
    }


# ---------------------------------------------------------------------------
# _json_safe
# ---------------------------------------------------------------------------


def test_json_safe_passthrough_scalars():
    assert _json_safe(None) is None
    assert _json_safe(3) == 3
    assert _json_safe("text") == "text"
    assert _json_safe(True) is True


def test_json_safe_converts_uuid():
    value = uuid.uuid4()
    assert _json_safe(value) == str(value)


def test_json_safe_converts_pydantic_models():
    model = _PydanticLike(name="x", tags=["a"])
    assert _json_safe(model) == {"name": "x", "tags": ["a"]}


def test_json_safe_walks_dict_list_tuple():
    value = uuid.uuid4()
    result = _json_safe(
        {
            "id": value,
            "items": [_PydanticLike(name="n", tags=[])],
            "pair": (1, "two"),
        }
    )
    assert result == {
        "id": str(value),
        "items": [{"name": "n", "tags": []}],
        "pair": [1, "two"],
    }


# ---------------------------------------------------------------------------
# _RunFormatter normalization branches
# ---------------------------------------------------------------------------


def _formatter() -> tuple[_RunFormatter, asyncio.Queue]:
    queue: asyncio.Queue = asyncio.Queue()
    return _RunFormatter(queue, agent=SimpleNamespace()), queue


def test_formatter_queues_compression_events_with_normalized_payloads(monkeypatch):
    """compression_start/end are re-encoded as typed dict payloads."""
    formatter, queue = _formatter()

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_sse.build_compression_start_event",
        lambda **_: _sse("compression_start", '{"stage": "macro"}'),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_sse.build_compression_events",
        lambda **_: (None, _sse("compression_end", '{"trigger": "context_limit"}')),
    )

    assert formatter("compression_start", {"stage": "macro"}) is None
    assert formatter("compression_end", {"trigger": "context_limit"}) is None

    first_type, first_payload = queue.get_nowait()
    second_type, second_payload = queue.get_nowait()
    assert first_type == "compression_start"
    assert first_payload == {"stage": "macro"}
    assert second_type == "compression_end"
    assert second_payload == {"trigger": "context_limit"}


def test_formatter_decodes_plain_sse_string_payload():
    formatter, queue = _formatter()
    formatter("content_delta", {"sse": _sse("content_delta", '{"delta": "Hi"}')})
    event_type, payload = queue.get_nowait()
    assert event_type == "content_delta"
    assert payload == {"delta": "Hi"}


def test_formatter_falls_back_to_json_safe_payload():
    formatter, queue = _formatter()
    marker = uuid.uuid4()
    formatter("tool_result", {"result": {"id": marker}})
    event_type, payload = queue.get_nowait()
    assert event_type == "tool_result"
    assert payload == {"result": {"id": str(marker)}}


def test_formatter_drops_unusable_sse_payload():
    """An sse string that cannot be decoded produces no event."""
    formatter, queue = _formatter()
    formatter("content_delta", {"sse": "not-an-sse-event"})
    assert queue.empty()

    # A payload without the sse key uses the structured fallback.
    formatter("other", {"keep": 1})
    event_type, payload = queue.get_nowait()
    assert event_type == "other"
    assert payload == {"keep": 1}

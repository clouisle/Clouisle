"""MRTR (``input_required``) round-trip behavior for the MCP adapter.

A modern server answers a request with ``input_required`` instead of a result.
These tests pin the two halves that must stay together: the adapter surfaces
the parked requests together with the opaque state, and a retry that carries
answers reaches the SDK instead of asking the server the same question again.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _caps(**overrides):
    values = {
        "protocol_version": "2026-07-28",
        "tools": True,
        "resources": True,
        "prompts": True,
    }
    values.update(overrides)
    return mcp.McpServerCapabilities(**values)


def _install(monkeypatch, client, session):
    @asynccontextmanager
    async def fake_open(deadline):
        yield session, _caps()

    monkeypatch.setattr(client, "_open", fake_open)


class _Session:
    """Records the keyword arguments of each SDK request."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, arguments, **kwargs):
        self.calls.append(("call_tool", kwargs))
        return self.result

    async def read_resource(self, uri, **kwargs):
        self.calls.append(("read_resource", kwargs))
        return self.result

    async def get_prompt(self, name, arguments=None, **kwargs):
        self.calls.append(("get_prompt", kwargs))
        return self.result


def _parked() -> types.InputRequiredResult:
    return types.InputRequiredResult(
        input_requests={
            "q1": types.ElicitRequest(
                params=types.ElicitRequestFormParams(
                    message="Which environment?",
                    requestedSchema={"type": "object", "properties": {}},
                )
            )
        },
        request_state="state-1",
    )


ANSWERS = {"q1": {"method": "elicitation/create", "result": {"action": "accept"}}}


# ---------------------------------------------------------------------------
# Surfacing the parked request
# ---------------------------------------------------------------------------


async def test_execute_tool_returns_the_requests_and_state(monkeypatch):
    client = mcp.McpClient({})
    _install(monkeypatch, client, _Session(_parked()))

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert result.input_required is not None
    assert result.input_required.request_state == "state-1"
    # The caller answers by request key, so the method it answers has to be
    # visible in the payload rather than inferred.
    assert result.input_required.requests["q1"]["method"] == "elicitation/create"


async def test_interactive_tool_resolves_input_on_same_session(monkeypatch):
    seen = []

    async def elicit(_context, params):
        seen.append(params.message)
        return types.ElicitResult(action="accept", content={"choice": "beta"})

    class Session(_Session):
        async def call_tool(self, name, arguments, **kwargs):
            self.calls.append((name, kwargs))
            if len(self.calls) == 1:
                return _parked()
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="ok")]
            )

    session = Session(None)
    client = mcp.McpClient({}, callbacks=mcp.McpCallbacks(elicitation=elicit))
    _install(monkeypatch, client, session)
    result = await client.execute_tool("search", {}, resolve_input_required=True)

    assert result.success
    assert seen == ["Which environment?"]
    assert session.calls[1][1]["request_state"] == "state-1"
    assert session.calls[1][1]["input_responses"]["q1"].content == {"choice": "beta"}


async def test_interactive_tool_bounds_repeated_requests(monkeypatch):
    async def elicit(_context, _params):
        return types.ElicitResult(action="cancel")

    session = _Session(_parked())
    callbacks = mcp.McpCallbacks(
        elicitation=elicit, policy=mcp.McpCallbackPolicy(max_elicitation_requests=1)
    )
    client = mcp.McpClient({}, callbacks=callbacks)
    _install(monkeypatch, client, session)
    result = await client.execute_tool("search", {}, resolve_input_required=True)

    assert result.input_required is not None
    assert len(session.calls) == 2


async def test_interactive_tool_without_handler_does_not_retry(monkeypatch):
    session = _Session(_parked())
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {}, resolve_input_required=True)

    assert result.input_required is not None
    assert len(session.calls) == 1


async def test_interactive_tool_rejects_mixed_requests_before_prompting(monkeypatch):
    asked = []

    async def elicit(_context, params):
        asked.append(params)
        return types.ElicitResult(action="accept")

    parked = _parked()
    parked.input_requests["other"] = types.ListRootsRequest()
    session = _Session(parked)
    client = mcp.McpClient({}, callbacks=mcp.McpCallbacks(elicitation=elicit))
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {}, resolve_input_required=True)

    assert result.input_required is not None
    assert asked == []
    assert len(session.calls) == 1


async def test_interactive_tool_invalid_request_fails_without_prompt(monkeypatch):
    async def elicit(_context, _params):
        pytest.fail("invalid request must not be presented")

    class InvalidResult:
        result_type = "input_required"
        input_requests = {"q1": {"method": "elicitation/create", "params": {}}}
        request_state = "state"

    client = mcp.McpClient({}, callbacks=mcp.McpCallbacks(elicitation=elicit))
    _install(monkeypatch, client, _Session(InvalidResult()))
    result = await client.execute_tool("search", {}, resolve_input_required=True)
    assert not result.success
    assert result.input_required is None


# ---------------------------------------------------------------------------
# Forwarding the answers
# ---------------------------------------------------------------------------


async def test_execute_tool_forwards_answers_and_state(monkeypatch):
    session = _Session(
        types.CallToolResult(content=[types.TextContent(type="text", text="ok")])
    )
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)
    answers = mcp.parse_input_responses(ANSWERS)

    result = await client.execute_tool(
        "search", {"q": 1}, input_responses=answers, request_state="state-1"
    )

    assert result.success is True
    kwargs = session.calls[0][1]
    assert kwargs["input_responses"] == answers
    assert kwargs["request_state"] == "state-1"
    assert kwargs["allow_input_required"] is True


async def test_read_resource_forwards_answers_and_state(monkeypatch):
    session = _Session(
        types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri="file:///a", mimeType="text/plain", text="body"
                )
            ]
        )
    )
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)
    answers = mcp.parse_input_responses(ANSWERS)

    contents = await client.read_resource(
        "file:///a", input_responses=answers, request_state="state-1"
    )

    assert [item.text for item in contents] == ["body"]
    kwargs = session.calls[0][1]
    assert kwargs["input_responses"] == answers
    assert kwargs["request_state"] == "state-1"


async def test_get_prompt_forwards_answers_and_state(monkeypatch):
    session = _Session(
        types.GetPromptResult(
            messages=[
                types.PromptMessage(
                    role="user", content=types.TextContent(type="text", text="hi")
                )
            ]
        )
    )
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)
    answers = mcp.parse_input_responses(ANSWERS)

    prompt = await client.get_prompt(
        "greet", {}, input_responses=answers, request_state="state-1"
    )

    assert prompt.messages[0].content.text == "hi"
    kwargs = session.calls[0][1]
    assert kwargs["input_responses"] == answers
    assert kwargs["request_state"] == "state-1"


async def test_answers_fail_loudly_when_the_sdk_cannot_carry_them(monkeypatch):
    """Silently dropping the answers would loop on the same question."""
    session = _Session(types.CallToolResult(content=[]))
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)
    monkeypatch.setattr(mcp, "_CALL_TOOL_ACCEPTS_INPUT_RESPONSES", False)

    with pytest.raises(mcp.McpInvalidRequest):
        await client.execute_tool(
            "search",
            {},
            input_responses=mcp.parse_input_responses(ANSWERS),
            request_state="state-1",
        )

    assert session.calls == []


async def test_answers_without_server_state_omit_the_field(monkeypatch):
    """A server that issues no ``request_state`` is still resumable."""
    session = _Session(
        types.CallToolResult(content=[types.TextContent(type="text", text="ok")])
    )
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    await client.execute_tool(
        "search", {}, input_responses=mcp.parse_input_responses(ANSWERS)
    )

    kwargs = session.calls[0][1]
    assert "request_state" not in kwargs
    assert kwargs["input_responses"] == mcp.parse_input_responses(ANSWERS)


async def test_a_session_without_input_required_support_sends_no_flag(monkeypatch):
    """An older SDK that cannot park a call must not be told it can."""
    session = _Session(
        types.CallToolResult(content=[types.TextContent(type="text", text="ok")])
    )
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)
    monkeypatch.setattr(mcp, "_CALL_TOOL_ALLOWS_INPUT_REQUIRED", False)

    await client.execute_tool("search", {})

    assert "allow_input_required" not in session.calls[0][1]


async def test_module_helper_forwards_answers(monkeypatch):
    captured: dict = {}

    async def fake_execute(self, tool_name, arguments, timeout=60.0, **kwargs):
        captured.update(kwargs)
        return mcp.McpToolResult(success=True)

    monkeypatch.setattr(mcp.McpClient, "execute_tool", fake_execute)
    answers = mcp.parse_input_responses(ANSWERS)

    await mcp.execute_mcp_tool(
        {}, "search", {}, input_responses=answers, request_state="state-1"
    )

    assert captured == {
        "input_responses": answers,
        "request_state": "state-1",
        "resolve_input_required": False,
    }


# ---------------------------------------------------------------------------
# Answer validation
# ---------------------------------------------------------------------------


async def test_no_answers_means_no_round_trip():
    assert mcp.parse_input_responses(None) is None
    assert mcp.parse_input_responses({}) is None


async def test_elicitation_answer_is_validated():
    parsed = mcp.parse_input_responses(
        {"q1": {"method": "elicitation/create", "result": {"action": "decline"}}}
    )

    assert parsed is not None
    assert isinstance(parsed["q1"], types.ElicitResult)
    assert parsed["q1"].action == "decline"


async def test_roots_answer_is_validated():
    parsed = mcp.parse_input_responses(
        {
            "r1": {
                "method": "roots/list",
                "result": {"roots": [{"uri": "file:///work", "name": "work"}]},
            }
        }
    )

    assert parsed is not None
    assert isinstance(parsed["r1"], types.ListRootsResult)
    assert str(parsed["r1"].roots[0].uri) == "file:///work"


async def test_plain_sampling_answer_keeps_its_narrow_type():
    parsed = mcp.parse_input_responses(
        {
            "s1": {
                "method": "sampling/createMessage",
                "result": {
                    "role": "assistant",
                    "model": "m",
                    "content": {"type": "text", "text": "hi"},
                },
            }
        }
    )

    assert parsed is not None
    assert type(parsed["s1"]).__name__ == "CreateMessageResult"


async def test_sampling_answer_with_tool_use_uses_the_tool_enabled_type():
    parsed = mcp.parse_input_responses(
        {
            "s1": {
                "method": "sampling/createMessage",
                "result": {
                    "role": "assistant",
                    "model": "m",
                    "content": [
                        {"type": "tool_use", "id": "c1", "name": "x", "input": {}}
                    ],
                },
            }
        }
    )

    assert parsed is not None
    assert type(parsed["s1"]).__name__ == "CreateMessageResultWithTools"


@pytest.mark.parametrize(
    "payload",
    [
        {"": {"method": "elicitation/create", "result": {"action": "accept"}}},
        {"q1": "not-an-object"},
        {"q1": {"result": {"action": "accept"}}},
        {"q1": {"method": "elicitation/create"}},
        {"q1": {"method": "tools/call", "result": {}}},
        {"q1": {"method": "elicitation/create", "result": {"action": "maybe"}}},
        {"q1": {"method": "roots/list", "result": {}}},
        {"q1": {"method": "sampling/createMessage", "result": {"role": "user"}}},
    ],
)
async def test_malformed_answers_are_rejected(payload):
    with pytest.raises(mcp.McpInvalidRequest):
        mcp.parse_input_responses(payload)

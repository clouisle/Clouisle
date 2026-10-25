"""End-to-end evidence that observability records the exact model input."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.llm.types import ChatResponse, FinishReason, FunctionCall, ToolCall, Usage
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn
from app.services.observability_payload import load_tool_payload


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


class _History:
    def __init__(self):
        self.entries = []

    def append(self, **entry):
        self.entries.append(entry)


@pytest.mark.asyncio
async def test_loop_records_exact_model_input_for_a_tool_call(database):
    run_id = uuid4()
    document = {
        "ref": "a1b2",
        "citation_id": "asset_1",
        "filename": "报价.pptx",
        "total_lines": 2,
        "segments": [
            {"line": 1, "text": "第一页", "continuation": False},
            {"line": 2, "text": "第二页", "continuation": False},
        ],
        "eof": True,
        "next_cursor": None,
    }
    calls = []

    async def tool_runner(name, arguments, **_kwargs):
        calls.append(name)
        if len(calls) == 1:
            return document
        return {"ok": True}

    responses = [
        ChatResponse(
            id="r1",
            model="m",
            content="",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(
                        name="read_asset", arguments=json.dumps({"ref": "a1b2"})
                    ),
                )
            ],
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        ChatResponse(
            id="r2",
            model="m",
            content="done",
            tool_calls=[],
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
    ]
    seen = []

    async def build_turn(**_kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[], compression=None, compacted_messages=0
            )
        )

    async def chat(**_kwargs):
        seen.append(_kwargs.get("messages"))
        return responses.pop(0)

    async def persist_step(**_kwargs):
        return 0

    async def persist_result(**kwargs):
        return 0

    from app.services import agent_round

    original_step = agent_round.persist_assistant_step
    original_result = agent_round.persist_tool_result
    agent_round.persist_assistant_step = persist_step
    agent_round.persist_tool_result = persist_result
    try:
        context = AgentLoopContext(
            agent=SimpleNamespace(id=uuid4(), team_id=None),
            conversation=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(id=uuid4()),
            model_id="m",
            tokenizer_model_id=None,
            model_provider="p",
            model_context_limit=100_000,
            model_max_output_tokens=1000,
            model_used="m",
            max_iterations=4,
            streaming=False,
            working_history_override=[],
            round_id=uuid4(),
            team_chat=chat,
            build_turn=build_turn,
            execute_tool_call=tool_runner,
            formatter=None,
            collect_dependency_metrics=True,
            observability_run_id=run_id,
        )
        loop = AgentLoop(context)
        async for _ in loop.run():
            pass
    finally:
        agent_round.persist_assistant_step = original_step
        agent_round.persist_tool_result = original_result

    payload = await load_tool_payload(run_id=run_id, tool_call_id="call-1")
    assert payload is not None
    assert payload["recorded"] is True
    assert payload["model_input"].startswith("ref=a1b2")
    assert "1│第一页" in payload["model_input"]
    assert "segments" not in payload["model_input"]
    assert payload["display"].startswith('{"ref": "a1b2"')
    assert payload["eof"] is True

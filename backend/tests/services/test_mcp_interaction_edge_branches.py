"""Edge/safety branches for the MCP interaction bridge.

The main bridge suite covers approved sampling, quota failures and normal
elicitation. These checks pin the remaining fail-closed paths: malformed
previews, over-long content truncation, URL allowlist parsing, unknown run
kinds, caller cancellation and accepted forms whose encrypted answer cannot
be read back.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from mcp import types
import pytest
from tortoise.context import TortoiseContext

import app.llm as llm_package
from app.llm.tools.mcp_client import McpCallbackPolicy
from app.models.tool import Tool, ToolType
from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionRequest,
    InteractionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.tool_approval import ExecutionEntrypoint, ExecutionRunKind
from app.services import mcp_interactions, tool_interactions
from app.services.tool_execution import ToolCallContext


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'mcp-interaction-edges.sqlite3'}"

    def run(scenario):
        async def _wrapped():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                await context.generate_schemas()
                return await scenario()

        return runner.run(_wrapped())

    try:
        yield run
    finally:
        runner.close()


async def _user(label: str) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@mcp-interaction-edges.test",
        hashed_password="x",
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _tool(team: Team, **config) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="MCP bridge",
        description="mcp interaction edge test",
        type=ToolType.MCP,
        mcp_config=config,
    )


def _context(user: User, team: Team, **overrides) -> ToolCallContext:
    values = dict(
        actor=user,
        team_id=team.id,
        entrypoint=ExecutionEntrypoint.TOOL_TEST,
        interactive=True,
    )
    values.update(overrides)
    return ToolCallContext(**values)


async def _pending_one() -> InteractionRequest:
    for _ in range(300):
        row = await InteractionRequest.filter(status=InteractionStatus.PENDING).first()
        if row is not None:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError("no pending interaction appeared")


def _sampling_params() -> types.CreateMessageRequestParams:
    return types.CreateMessageRequestParams(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(type="text", text="Summarize this"),
            )
        ],
        maxTokens=16,
    )


class _FakeModelManager:
    def __init__(self, error: Exception | None = None, content: str = "answer"):
        self.calls: list[dict] = []
        self.error = error
        self.content = content

    async def team_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.content, model="fake-model")


def test_content_text_supports_scalar_mapping_and_sequence_shapes():
    assert mcp_interactions._content_text("plain") == "plain"
    assert mcp_interactions._content_text(SimpleNamespace(text="block")) == "block"
    assert mcp_interactions._content_text({"text": "mapped"}) == "mapped"
    assert mcp_interactions._content_text({"other": "ignored"}) is None
    assert (
        mcp_interactions._content_text(
            [SimpleNamespace(text="a"), {"text": "b"}, {"missing": 1}]
        )
        == "a\nb"
    )
    assert mcp_interactions._content_text([]) is None
    assert mcp_interactions._content_text(42) is None


def test_sampling_messages_reads_raw_mappings_and_truncates():
    params = SimpleNamespace(
        messages=[
            {"role": "assistant", "content": {"text": "mapped"}},
            {"content": [{"text": "a"}, SimpleNamespace(text="b")]},
        ]
    )
    messages, truncated = mcp_interactions._sampling_messages(params)
    assert messages == [
        {"role": "assistant", "content": "mapped"},
        {"role": "user", "content": "a\nb"},
    ]
    assert truncated is False

    long_params = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="x" * 5000)]
    )
    long_messages, long_truncated = mcp_interactions._sampling_messages(long_params)
    assert long_truncated is True
    assert len(long_messages[0]["content"]) == 4001

    # The total preview budget slices the tail message instead of dropping the
    # row, and the request is marked truncated.
    total_params = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="y" * 4000) for _ in range(9)]
    )
    total_messages, total_truncated = mcp_interactions._sampling_messages(total_params)
    assert total_truncated is True
    assert len(total_messages) == 9
    assert total_messages[-1]["content"] == ""

    many_params = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="z") for _ in range(21)]
    )
    many_messages, many_truncated = mcp_interactions._sampling_messages(many_params)
    assert many_truncated is True
    assert len(many_messages) == 20


def test_sampling_payload_defaults_invalid_prompts_and_token_budgets():
    policy = McpCallbackPolicy(sampling_max_tokens=64)
    params = SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt=None,
        systemPrompt=None,
        max_tokens=True,
        include_context="all",
    )
    payload = mcp_interactions._sampling_payload(params, policy)
    assert payload["system_prompt"] is None
    assert payload["max_tokens"] == 64
    assert payload["include_context"] == "all"
    assert payload["truncated"] is False


def test_approved_sampling_skips_non_mapping_items_and_requires_messages(
    run_orm, monkeypatch
):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        context = _context(owner, team)
        fake = _FakeModelManager()
        monkeypatch.setattr(llm_package, "model_manager", fake)

        result = await mcp_interactions._run_approved_sampling(
            context,
            {
                "messages": [
                    {"role": "assistant", "content": "answer"},
                    {"role": "user", "content": "question"},
                    "not-a-mapping",
                ],
                "max_tokens": 8,
            },
        )
        assert result == ("answer", "endTurn", "fake-model")
        sent = fake.calls[0]["messages"]
        assert [message.content for message in sent] == ["answer", "question"]

        with pytest.raises(ValueError):
            await mcp_interactions._run_approved_sampling(
                context, {"messages": ["only junk"]}
            )

    run_orm(scenario)


def test_elicitation_url_allowlist_rejects_unsafe_urls():
    hosts = frozenset({"auth.example.com"})
    assert mcp_interactions._elicitation_url_allowed(None, hosts) is False
    assert mcp_interactions._elicitation_url_allowed("", hosts) is False
    assert mcp_interactions._elicitation_url_allowed(123, hosts) is False
    assert mcp_interactions._elicitation_url_allowed("https://[::1", hosts) is False
    assert (
        mcp_interactions._elicitation_url_allowed("http://auth.example.com", hosts)
        is False
    )
    assert (
        mcp_interactions._elicitation_url_allowed(
            "https://user:pass@auth.example.com/start", hosts
        )
        is False
    )
    assert (
        mcp_interactions._elicitation_url_allowed("https://evil.example.com", hosts)
        is False
    )
    assert (
        mcp_interactions._elicitation_url_allowed(
            "https://auth.example.com/start", hosts
        )
        is True
    )


def test_run_owner_lookup_covers_workflow_and_unknown_kinds(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)

        workflow_context = _context(
            owner,
            team,
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=uuid4(),
        )
        assert await mcp_interactions._run_owner_user_id(workflow_context) is None

        unknown_context = _context(
            owner,
            team,
            run_kind="background_job",
            run_id=uuid4(),
        )
        assert await mcp_interactions._run_owner_user_id(unknown_context) is None

    run_orm(scenario)


def test_bridge_sampling_preview_failure_returns_internal_error():
    class _BrokenParams:
        @property
        def messages(self):
            raise RuntimeError("preview exploded")

    bridge = mcp_interactions._McpInteractionBridge(
        tool=SimpleNamespace(id=uuid4(), name="broken", mcp_config={}),
        context=SimpleNamespace(
            actor=SimpleNamespace(id=uuid4()),
            team_id=uuid4(),
            run_id=None,
            run_kind=None,
            tool_call_id=None,
        ),
        execution_id=None,
        session=None,
        policy=McpCallbackPolicy(),
    )
    result = asyncio.run(bridge.sampling(None, _BrokenParams()))
    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert result.message == "Sampling request could not be previewed"


def test_bridge_sampling_model_failure_is_reported(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        fake = _FakeModelManager(error=ValueError("model exploded"))
        monkeypatch.setattr(llm_package, "model_manager", fake)

        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            idempotency_key="model-fail1",
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.ErrorData)
        assert result.message == "Sampling model call failed"

    run_orm(scenario)


def test_bridge_cancellation_terminates_the_pending_row(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        context = _context(owner, team)
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 4},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        bridge = mcp_interactions._McpInteractionBridge(
            tool=tool,
            context=context,
            execution_id=None,
            session=None,
            policy=McpCallbackPolicy(),
        )

        async def cancelled(*_args, **_kwargs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(tool_interactions, "wait_for_response", cancelled)
        with pytest.raises(asyncio.CancelledError):
            await bridge._await(row)
        assert (await InteractionRequest.get(id=row.id)).status == (
            InteractionStatus.CANCELLED
        )

    run_orm(scenario)


def test_bridge_elicitation_declines_missing_schema(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        params = SimpleNamespace(
            mode="form",
            message="No schema",
            requested_schema=None,
            requestedSchema=None,
        )
        result = await callbacks.elicitation(None, params)
        assert result.action == "decline"
        assert await InteractionRequest.all().count() == 0

    run_orm(scenario)


def test_bridge_elicitation_fails_closed_on_unreadable_acceptance(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        context = _context(owner, team)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, context)

        form = types.ElicitRequestFormParams(
            message="Your name?",
            requestedSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )

        accepted = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={"mode": "form", "message": "Your name?"},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        await InteractionRequest.filter(id=accepted.id).update(
            status=InteractionStatus.RESPONDED,
            outcome=InteractionOutcome.ACCEPT,
            response_cipher="",
        )

        async def resolved(*_args, **_kwargs):
            return await InteractionRequest.get(id=accepted.id)

        monkeypatch.setattr(tool_interactions, "wait_for_response", resolved)
        result = await callbacks.elicitation(None, form)
        # An accepted row without a readable answer must not become an empty
        # acceptance.
        assert result.action == "decline"

        await InteractionRequest.filter(id=accepted.id).update(
            outcome=InteractionOutcome.CANCEL
        )
        result = await callbacks.elicitation(None, form)
        assert result.action == "cancel"

    run_orm(scenario)

"""Behavioral tests for durable MCP interactions and managed session loss.

Real in-memory/file-backed SQLite Tortoise schema, no ORM fakes for the
interaction store. The model manager call is faked only at the exact boundary
that would otherwise spend a team's quota.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

from mcp import types
import pytest
from tortoise.context import TortoiseContext

import app.llm as llm_package
from app.llm.tools.mcp_client import McpCallbacks
from app.models.tool import Tool, ToolType
from app.models.tool_approval import ExecutionEntrypoint
from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionRequest,
    InteractionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.services import mcp_interactions, mcp_session_runtime, tool_interactions
from app.services.tool_execution import ToolCallContext


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'interactions.sqlite3'}"

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


async def _user(label: str, *, active: bool = True) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@interaction.test",
        hashed_password="x",
        is_active=active,
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
        description="interaction test",
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
    for _ in range(200):
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
        systemPrompt="Be brief",
        maxTokens=64,
    )


class _FakeResponse:
    def __init__(self, content: str = "model answer") -> None:
        self.content = content
        self.model = "fake-model"


class _FakeModelManager:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error

    async def team_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _FakeResponse()


# ---------------------------------------------------------------------------
# Durable store: ownership, response, idempotency and expiry
# ---------------------------------------------------------------------------


def test_audience_ownership_and_roles(run_orm):
    async def scenario():
        owner = await _user("owner")
        member = await _user("member")
        outsider = await _user("outsider")
        team = await _team(owner)
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=member.id, role="admin"
        )

        direct = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 32},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        assert await tool_interactions.get_interaction_for_user(direct.id, owner)
        for denied in (member, outsider):
            with pytest.raises(BusinessError) as exc:
                await tool_interactions.get_interaction_for_user(direct.id, denied)
            assert exc.value.code == ResponseCode.TOOL_INTERACTION_ACCESS_DENIED

        role_row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "Name?",
                "requested_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
            audience={"user_ids": [], "roles": ["admin"]},
            ttl_seconds=60,
        )
        assert await tool_interactions.get_interaction_for_user(role_row.id, member)
        listed, total = await tool_interactions.list_interactions_for_user(member)
        assert total == 1 and listed[0].id == role_row.id
        # Inactive users lose access even when listed.
        assert not tool_interactions.audience_matches(
            direct, member, {str(team.id): "admin"}
        )

        with pytest.raises(BusinessError) as missing:
            await tool_interactions.get_interaction_for_user(uuid4(), owner)
        assert missing.value.code == ResponseCode.TOOL_INTERACTION_NOT_FOUND

    run_orm(scenario)


def test_no_audience_is_not_created(run_orm):
    async def scenario():
        owner = await _user("owner")
        with pytest.raises(BusinessError) as exc:
            await tool_interactions.create_interaction(
                kind=InteractionKind.SAMPLING,
                actor=owner,
                team_id=None,
                payload={"mode": "sampling", "messages": [], "max_tokens": 8},
                audience={"user_ids": [], "roles": []},
                ttl_seconds=60,
            )
        assert exc.value.code == ResponseCode.TOOL_INTERACTION_ACCESS_DENIED
        assert await InteractionRequest.all().count() == 0

    run_orm(scenario)


def test_form_response_is_validated_encrypted_and_idempotent(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 20},
                "age": {"type": "integer"},
                "plan": {"type": "string", "enum": ["free", "pro"]},
            },
            "required": ["name"],
        }
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={"mode": "form", "message": "Profile", "requested_schema": schema},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )

        for bad in (
            {"name": "Ada", "unknown": "x"},
            {"age": 4},
            {"name": 7},
            {"name": "Ada", "plan": "gold"},
            {"name": "x" * 21},
        ):
            with pytest.raises(BusinessError):
                await tool_interactions.respond_to_interaction(
                    row.id,
                    owner,
                    action="accept",
                    content=bad,
                    idempotency_key="abcdefgh",
                )

        with pytest.raises(BusinessError):
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"name": "Ada", "password": "hunter2"},
                idempotency_key="abcdefgh",
            )

        answered = await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            content={"name": "Ada", "age": 36},
            idempotency_key="abcdefgh",
        )
        assert answered.status == InteractionStatus.RESPONDED
        assert answered.outcome == InteractionOutcome.ACCEPT
        assert answered.response_cipher and "Ada" not in answered.response_cipher
        assert tool_interactions.load_response_content(answered) == {
            "name": "Ada",
            "age": 36,
        }

        replay = await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            content={"name": "Ada", "age": 36},
            idempotency_key="abcdefgh",
        )
        assert replay.id == answered.id

        with pytest.raises(BusinessError) as conflict:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"name": "Grace"},
                idempotency_key="abcdefgh",
            )
        assert conflict.value.code == ResponseCode.TOOL_INTERACTION_IDEMPOTENCY_CONFLICT

        with pytest.raises(BusinessError) as decided:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="decline",
                idempotency_key="zzzzzzzz",
            )
        assert decided.value.code == ResponseCode.TOOL_INTERACTION_NOT_PENDING

        # Non-audience cannot answer, and get/respond use the same check.
        outsider = await _user("outsider")
        with pytest.raises(BusinessError) as denied:
            await tool_interactions.respond_to_interaction(
                row.id,
                outsider,
                action="decline",
                idempotency_key="outsider1",
            )
        assert denied.value.code == ResponseCode.TOOL_INTERACTION_ACCESS_DENIED

    run_orm(scenario)


def test_sampling_rejects_content_and_decline(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        with pytest.raises(BusinessError):
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"anything": True},
                idempotency_key="abcdefgh",
            )
        answered = await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="decline",
            idempotency_key="abcdefgh",
        )
        assert answered.outcome == InteractionOutcome.DECLINE
        assert tool_interactions.load_response_content(answered) is None

    run_orm(scenario)


def test_wait_timeout_expires_and_blocks_late_response(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "Name?",
                "requested_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )

        result = await tool_interactions.wait_for_response(row.id, deadline_seconds=0.1)
        assert result.status == InteractionStatus.EXPIRED

        with pytest.raises(BusinessError) as expired:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"name": "late"},
                idempotency_key="late-key1",
            )
        assert expired.value.code == ResponseCode.TOOL_INTERACTION_EXPIRED

    run_orm(scenario)


def test_wait_wakes_on_response_and_session_loss(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        session = await mcp_session_runtime.acquire_session(
            owner="test", execution_id=uuid4()
        )

        row = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            session_key=session.key,
        )
        waiter = asyncio.create_task(
            tool_interactions.wait_for_response(
                row.id,
                deadline_seconds=60,
                session_check=session.terminal_interaction_status,
            )
        )
        await asyncio.sleep(0)
        await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            idempotency_key="wake-key1",
        )
        answered = await asyncio.wait_for(waiter, timeout=5)
        assert answered.status == InteractionStatus.RESPONDED

        lost = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            session_key=session.key,
        )
        lost_waiter = asyncio.create_task(
            tool_interactions.wait_for_response(
                lost.id,
                deadline_seconds=60,
                session_check=session.terminal_interaction_status,
            )
        )
        await asyncio.sleep(0)
        await mcp_session_runtime.release_session(session)
        terminal = await asyncio.wait_for(lost_waiter, timeout=5)
        assert terminal.status == InteractionStatus.CONNECTION_LOST
        assert mcp_session_runtime.active_session_count() == 0

        with pytest.raises(BusinessError) as late:
            await tool_interactions.respond_to_interaction(
                lost.id,
                owner,
                action="accept",
                idempotency_key="late-key2",
            )
        assert late.value.code == ResponseCode.TOOL_INTERACTION_CONNECTION_LOST

    run_orm(scenario)


def test_expiry_reaper_only_touches_due_pending_rows(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        due = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        await InteractionRequest.filter(id=due.id).update(
            expires_at=tool_interactions.now_utc()
        )
        live = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        assert await tool_interactions.expire_stale_interactions() == 1
        assert (
            await InteractionRequest.get(id=due.id)
        ).status == InteractionStatus.EXPIRED
        assert (
            await InteractionRequest.get(id=live.id)
        ).status == InteractionStatus.PENDING

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Sampling / elicitation bridge
# ---------------------------------------------------------------------------


def test_capabilities_are_not_advertised_without_explicit_enable(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        assert isinstance(callbacks, McpCallbacks)
        assert callbacks.sampling is None
        assert callbacks.elicitation is None
        assert callbacks.policy.roots == ()

    run_orm(scenario)


def test_sampling_requires_human_approval_then_uses_team_model(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(
            team,
            enable_sampling=True,
            sampling_max_tokens=32,
            callback_timeout_seconds=30,
            roots=[{"uri": "file:///work/repo", "name": "repo"}],
        )
        fake = _FakeModelManager()
        monkeypatch.setattr(llm_package, "model_manager", fake)

        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        assert callbacks.sampling is not None
        assert [root.uri for root in callbacks.policy.roots] == ["file:///work/repo"]
        assert callbacks.policy.sampling_max_tokens == 32

        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        assert row.kind == InteractionKind.SAMPLING
        assert row.payload["max_tokens"] == 32
        assert row.payload["system_prompt"] == "Be brief"
        assert fake.calls == []  # no model call before approval

        await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            idempotency_key="approve1",
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.CreateMessageResult)
        assert result.content.text == "model answer"
        assert fake.calls and fake.calls[0]["tools"] is None
        assert fake.calls[0]["team_id"] == str(team.id)

    run_orm(scenario)


def test_sampling_decline_never_calls_model(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        fake = _FakeModelManager()
        monkeypatch.setattr(llm_package, "model_manager", fake)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        await tool_interactions.respond_to_interaction(
            row.id, owner, action="decline", idempotency_key="decline1"
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.ErrorData)
        assert fake.calls == []

    run_orm(scenario)


def test_sampling_quota_failure_is_reported(run_orm, monkeypatch):
    async def scenario():
        from app.services.usage_tracker import QuotaExceededError

        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        fake = _FakeModelManager(error=QuotaExceededError("no budget", "daily_token"))
        monkeypatch.setattr(llm_package, "model_manager", fake)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        await tool_interactions.respond_to_interaction(
            row.id, owner, action="accept", idempotency_key="accept-02"
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.ErrorData)
        assert "quota" in result.message.lower()

    run_orm(scenario)


def test_elicitation_form_validates_and_supports_url_hosts(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        form = types.ElicitRequestFormParams(
            message="Your name?",
            requestedSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        task = asyncio.create_task(callbacks.elicitation(None, form))
        row = await _pending_one()
        await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            content={"name": "Ada"},
            idempotency_key="form-key1",
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert result.action == "accept"
        assert result.content == {"name": "Ada"}

        # URL mode is only advertised/answered for configured exact hosts.
        url_tool = await _tool(
            team,
            enable_elicitation=True,
            elicitation_url_hosts=["auth.example.com"],
        )
        url_callbacks = mcp_interactions.build_mcp_callbacks(
            url_tool, _context(owner, team)
        )
        good = types.ElicitRequestURLParams(
            message="Sign in", url="https://auth.example.com/start"
        )
        task = asyncio.create_task(url_callbacks.elicitation(None, good))
        row = await _pending_one()
        assert row.payload["mode"] == "url"
        await tool_interactions.respond_to_interaction(
            row.id, owner, action="accept", idempotency_key="url-key01"
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert result.action == "accept" and result.content is None

        bad = types.ElicitRequestURLParams(
            message="Sign in", url="https://evil.example.net/start"
        )
        assert (await url_callbacks.elicitation(None, bad)).action == "decline"
        assert await InteractionRequest.all().count() == 2

    run_orm(scenario)


def test_secret_and_invalid_forms_are_declined_without_rows(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        secret = types.ElicitRequestFormParams(
            message="Login",
            requestedSchema={
                "type": "object",
                "properties": {"password": {"type": "string"}},
            },
        )
        assert (await callbacks.elicitation(None, secret)).action == "decline"

        invalid = types.ElicitRequestFormParams(
            message="Broken",
            requestedSchema={"type": "object", "properties": {}},
        )
        assert (await callbacks.elicitation(None, invalid)).action == "decline"
        assert await InteractionRequest.all().count() == 0

    run_orm(scenario)


def test_run_with_callbacks_always_closes_and_never_replays(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)

        pending_tasks: list[asyncio.Task] = []
        calls = 0

        async def invoke(callbacks: McpCallbacks):
            nonlocal calls
            calls += 1
            pending_tasks.append(
                asyncio.create_task(callbacks.sampling(None, _sampling_params()))
            )
            await _pending_one()
            raise RuntimeError("transport died")

        with pytest.raises(RuntimeError):
            await mcp_interactions.run_with_mcp_callbacks(
                tool, _context(owner, team), invoke
            )
        assert calls == 1
        assert mcp_session_runtime.active_session_count() == 0

        result = await asyncio.wait_for(pending_tasks[0], timeout=5)
        assert isinstance(result, types.ErrorData)
        row = await InteractionRequest.all().first()
        assert row.status == InteractionStatus.CONNECTION_LOST

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Edge behavior: config bounds, protocol failures, service guards, runtime
# ---------------------------------------------------------------------------


def test_callback_config_bounds_and_root_filtering(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(
            team,
            enable_sampling=1,  # not the boolean True: capability stays off
            max_sampling_requests="many",
            sampling_max_tokens=99999,
            max_elicitation_requests=-5,
            callback_timeout_seconds="soon",
            elicitation_url_hosts=[" HTTPS://bad/path ", "Good.Example.COM", 3],
            roots=[
                {"uri": "http://not-file"},
                {"uri": "file:///work/repo", "name": 123},
                "not-a-mapping",
            ],
            roots_allowlist=["file:///work/repo", "http://ignored"],
        )
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        assert callbacks.sampling is None
        assert callbacks.elicitation is None
        policy = callbacks.policy
        assert policy.max_sampling_requests == 4
        assert policy.sampling_max_tokens == 8192
        assert policy.max_elicitation_requests == 0
        # Ladder: adapter default 60s outer budget - 5s reserve = 55s window.
        assert policy.max_callback_seconds == 55.0
        larger = mcp_interactions.build_mcp_callbacks(
            tool,
            _context(owner, team),
            call_timeout_seconds=mcp_interactions.mcp_call_timeout_seconds(tool),
        )
        assert larger.policy.max_callback_seconds == 120.0
        assert policy.elicitation_modes == frozenset({"form", "url"})
        assert policy.elicitation_url_hosts == frozenset({"good.example.com"})
        assert [root.uri for root in policy.roots] == ["file:///work/repo"]
        assert policy.roots[0].name is None
        assert policy.roots_allowlist == ("file:///work/repo",)

    run_orm(scenario)


def test_sampling_declines_non_text_and_empty_requests(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        fake = _FakeModelManager()
        monkeypatch.setattr(llm_package, "model_manager", fake)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        image = types.CreateMessageRequestParams(
            messages=[
                types.SamplingMessage(
                    role="user",
                    content=types.ImageContent(
                        type="image", data="AAAA", mimeType="image/png"
                    ),
                )
            ],
            maxTokens=16,
        )
        result = await callbacks.sampling(None, image)
        assert isinstance(result, types.ErrorData)

        empty = types.CreateMessageRequestParams(messages=[], maxTokens=16)
        result = await callbacks.sampling(None, empty)
        assert isinstance(result, types.ErrorData)
        assert await InteractionRequest.all().count() == 0
        assert fake.calls == []

    run_orm(scenario)


def test_sampling_output_capped_to_approved_tokens(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True, sampling_max_tokens=2)
        fake = _FakeModelManager()
        fake_response_text = "word " * 200
        fake.team_chat = lambda **kwargs: _return(_FakeResponse(fake_response_text))
        monkeypatch.setattr(llm_package, "model_manager", fake)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))

        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        await tool_interactions.respond_to_interaction(
            row.id, owner, action="accept", idempotency_key="cap-key01"
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.CreateMessageResult)
        assert result.stop_reason == "maxTokens"
        assert len(result.content.text) < len(fake_response_text)

    run_orm(scenario)


async def _return(value):
    return value


def test_elicitation_decline_cancel_unknown_mode_and_no_audience(run_orm):
    async def scenario():
        from types import SimpleNamespace

        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        form = types.ElicitRequestFormParams(
            message="Name?",
            requestedSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )

        async with mcp_interactions.open_mcp_callbacks(
            tool, _context(owner, team)
        ) as callbacks:
            task = asyncio.create_task(callbacks.elicitation(None, form))
            row = await _pending_one()
            await tool_interactions.respond_to_interaction(
                row.id, owner, action="decline", idempotency_key="dec-key01"
            )
            assert (await asyncio.wait_for(task, timeout=5)).action == "decline"

            task = asyncio.create_task(callbacks.elicitation(None, form))
            row = await _pending_one()
            await mcp_session_runtime.close_all_sessions()
            result = await asyncio.wait_for(task, timeout=5)
            assert result.action == "cancel"
            assert (
                await InteractionRequest.get(id=row.id)
            ).status == InteractionStatus.CONNECTION_LOST

        unknown = SimpleNamespace(mode="weird", message="x")
        assert (await callbacks.elicitation(None, unknown)).action == "decline"

        # No resolvable audience means nothing can be delivered.
        original_id = owner.id
        owner.id = None  # type: ignore[assignment]
        try:
            no_audience = types.ElicitRequestFormParams(
                message="Name?",
                requestedSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            )
            assert (await callbacks.elicitation(None, no_audience)).action == "decline"
            sampling = mcp_interactions.build_mcp_callbacks(
                await _tool(team, enable_sampling=True), _context(owner, team)
            )
            assert isinstance(
                await sampling.sampling(None, _sampling_params()), types.ErrorData
            )
        finally:
            owner.id = original_id

    run_orm(scenario)


def test_nested_form_schema_is_declined(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        nested = types.ElicitRequestFormParams(
            message="Nested",
            requestedSchema={
                "type": "object",
                "properties": {"address": {"type": "object"}},
            },
        )
        assert (await callbacks.elicitation(None, nested)).action == "decline"
        assert await InteractionRequest.all().count() == 0

    run_orm(scenario)


def test_service_rejects_oversized_and_malformed_input(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        with pytest.raises(BusinessError) as huge:
            await tool_interactions.create_interaction(
                kind=InteractionKind.SAMPLING,
                actor=owner,
                team_id=team.id,
                payload={"x": "y" * (tool_interactions.MAX_PAYLOAD_BYTES + 1)},
                audience={"user_ids": [str(owner.id)]},
                ttl_seconds=60,
            )
        assert huge.value.code == ResponseCode.TOOL_INTERACTION_CONTENT_TOO_LARGE

        row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "Name?",
                "requested_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        for action, content, key in (
            ("maybe", None, "abcdefgh"),
            ("accept", None, "abcdefgh"),
            ("decline", {"name": "Ada"}, "abcdefgh"),
            ("accept", {"name": "Ada"}, "short"),
        ):
            with pytest.raises(BusinessError) as invalid:
                await tool_interactions.respond_to_interaction(
                    row.id,
                    owner,
                    action=action,
                    content=content,
                    idempotency_key=key,
                )
            assert invalid.value.code in {
                ResponseCode.TOOL_INTERACTION_INVALID_RESPONSE,
                ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
            }

        # Arrays of strings are supported; non-string items are not.
        array_row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "Tags",
                "requested_schema": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "note": {"type": "string", "enum": ["a", "b"]},
                    },
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        with pytest.raises(BusinessError):
            await tool_interactions.respond_to_interaction(
                array_row.id,
                owner,
                action="accept",
                content={"tags": [1]},
                idempotency_key="array-key",
            )
        answered = await tool_interactions.respond_to_interaction(
            array_row.id,
            owner,
            action="accept",
            content={"tags": ["x"], "note": "a"},
            idempotency_key="array-key",
        )
        assert tool_interactions.load_response_content(answered) == {
            "tags": ["x"],
            "note": "a",
        }

        # A corrupt cipher must not crash a DTO projection.
        await InteractionRequest.filter(id=answered.id).update(
            response_cipher="not-a-fernet-token"
        )
        broken = await InteractionRequest.get(id=answered.id)
        assert tool_interactions.load_response_content(broken) is None

    run_orm(scenario)


def test_close_helpers_require_selector_and_are_terminal(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        run_id = uuid4()
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            run_kind="workflow",
            run_id=run_id,
        )
        with pytest.raises(ValueError):
            await tool_interactions.close_interaction(row.id, InteractionStatus.PENDING)
        assert await tool_interactions.close_pending_for_run("workflow", run_id) == 1
        closed = await InteractionRequest.get(id=row.id)
        assert closed.status == InteractionStatus.CANCELLED

        with pytest.raises(ValueError):
            await tool_interactions._close_pending(status=InteractionStatus.CANCELLED)
        assert await tool_interactions.close_pending_for_execution(uuid4()) == 0

        # A cancelled row stays cancelled on a late response attempt.
        with pytest.raises(BusinessError) as late:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                idempotency_key="late-key9",
            )
        assert late.value.code == ResponseCode.TOOL_INTERACTION_NOT_PENDING

    run_orm(scenario)


def test_managed_session_refcount_lifetime_and_sweep(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        execution_id = uuid4()
        first = await mcp_session_runtime.acquire_session(
            owner="run", execution_id=execution_id, max_lifetime_seconds=60
        )
        second = await mcp_session_runtime.acquire_session(
            owner="run", execution_id=execution_id, max_lifetime_seconds=60
        )
        assert first is second and first.refs == 2
        assert mcp_session_runtime.session_for_execution(execution_id) is first
        assert not await first.wait_closed(timeout=0.01)

        row = await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            session_key=first.key,
        )
        await mcp_session_runtime.release_session(first)
        assert mcp_session_runtime.active_session_count() == 1
        await mcp_session_runtime.release_session(second)
        assert mcp_session_runtime.active_session_count() == 0
        assert (await InteractionRequest.get(id=row.id)).status == (
            InteractionStatus.CONNECTION_LOST
        )
        assert await first.wait_closed(timeout=0.1)

        # Lifetime sweep runs on the next acquire and terminates its rows.
        expiring = await mcp_session_runtime.acquire_session(
            owner="run", execution_id=uuid4(), max_lifetime_seconds=60
        )
        expiring.expires_at = tool_interactions.now_utc()
        stale_row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "x",
                "requested_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            session_key=expiring.key,
        )
        await mcp_session_runtime.acquire_session(owner="other", execution_id=uuid4())
        assert expiring.is_closed
        assert (await InteractionRequest.get(id=stale_row.id)).status == (
            InteractionStatus.CONNECTION_LOST
        )
        assert await mcp_session_runtime.close_all_sessions() == 1
        assert mcp_session_runtime.active_session_count() == 0

    run_orm(scenario)


def test_get_and_list_expire_due_rows(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "x",
                "requested_schema": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        await InteractionRequest.filter(id=row.id).update(
            expires_at=tool_interactions.now_utc() - timedelta(seconds=1)
        )
        fetched = await tool_interactions.get_interaction_for_user(row.id, owner)
        assert fetched.status == InteractionStatus.EXPIRED
        listed, total = await tool_interactions.list_interactions_for_user(
            owner, status=InteractionStatus.PENDING
        )
        assert total == 0 and listed == []

    run_orm(scenario)


def test_validate_form_content_rejects_every_unsupported_shape():
    invalid_schemas = [
        None,
        {"type": "string", "properties": {"a": {"type": "string"}}},
        {"type": "object"},
        {"type": "object", "properties": {}},
        {
            "type": "object",
            "properties": {f"f{index}": {"type": "string"} for index in range(51)},
        },
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": True,
        },
        {"type": "object", "properties": {"a": "not-a-mapping"}},
        {"type": "object", "properties": {"a": {"type": "object"}}},
        {
            "type": "object",
            "properties": {"a": {"type": "string", "format": "password"}},
        },
        {"type": "object", "properties": {"a": {"type": "array"}}},
        {
            "type": "object",
            "properties": {"a": {"type": "array", "items": {"type": "integer"}}},
        },
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": "a",
        },
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["b"],
        },
    ]
    for schema in invalid_schemas:
        assert tool_interactions.form_schema_supported(schema) is False

    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string", "maxLength": 3},
            "i": {"type": "integer"},
            "n": {"type": "number"},
            "b": {"type": "boolean"},
            "e": {"type": "string", "enum": ["x", "y"]},
            "arr": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["s"],
    }
    assert tool_interactions.form_schema_supported(schema) is True
    bad_contents = [
        "not-a-mapping",
        {"unknown": "x"},
        {"i": "1"},
        {"s": "x", "i": True},
        {"s": "x", "n": True},
        {"s": "x", "n": float("nan")},
        {"s": "x", "b": "true"},
        {"s": "x", "e": "z"},
        {"s": "x", "arr": ["ok", 2]},
        {"s": "x", "arr": [str(index) for index in range(101)]},
        {"s": "toolong"},
        {},
    ]
    for content in bad_contents:
        with pytest.raises(BusinessError):
            tool_interactions.validate_form_content(schema, content)
    assert tool_interactions.validate_form_content(
        schema, {"s": "ok", "i": 1, "n": 1.5, "b": True, "e": "x", "arr": ["a"]}
    ) == {"s": "ok", "i": 1, "n": 1.5, "b": True, "e": "x", "arr": ["a"]}


def test_validate_form_content_rejects_oversized_schema_and_content():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "description": "d" * (tool_interactions.MAX_SCHEMA_BYTES + 1),
    }
    with pytest.raises(BusinessError):
        tool_interactions.validate_form_content(schema, {"a": "x"})
    small = {"type": "object", "properties": {"a": {"type": "string"}}}
    with pytest.raises(BusinessError):
        tool_interactions.validate_form_content(
            small, {"a": "x" * (tool_interactions.MAX_RESPONSE_BYTES + 1)}
        )


def test_elicitation_cancel_and_expired_map_to_cancel(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_elicitation=True)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        form = types.ElicitRequestFormParams(
            message="Name?",
            requestedSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )
        for status in (InteractionStatus.CANCELLED, InteractionStatus.EXPIRED):
            task = asyncio.create_task(callbacks.elicitation(None, form))
            row = await _pending_one()
            await tool_interactions.close_interaction(row.id, status)
            result = await asyncio.wait_for(task, timeout=5)
            assert result.action == "cancel"

    run_orm(scenario)


def test_sampling_decline_cancel_and_preferences(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team, enable_sampling=True)
        fake = _FakeModelManager()
        monkeypatch.setattr(llm_package, "model_manager", fake)
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        params = types.CreateMessageRequestParams(
            messages=[
                types.SamplingMessage(
                    role="assistant",
                    content=types.TextContent(type="text", text="history"),
                )
            ],
            systemPrompt="s" * 5000,
            maxTokens=999,
            includeContext="thisServer",
            modelPreferences=types.ModelPreferences(
                hints=[types.ModelHint(name="claude-3")],
                costPriority=2.0,
                speedPriority=-1.0,
            ),
        )
        task = asyncio.create_task(callbacks.sampling(None, params))
        row = await _pending_one()
        assert row.payload["truncated"] is True
        assert row.payload["include_context"] == "thisServer"
        assert row.payload["model_preferences"]["hints"] == ["claude-3"]
        assert row.payload["model_preferences"]["costPriority"] == 1.0
        assert row.payload["model_preferences"]["speedPriority"] == 0.0
        await tool_interactions.respond_to_interaction(
            row.id, owner, action="cancel", idempotency_key="cancel-01"
        )
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.ErrorData)
        assert fake.calls == []

        # Expired while waiting maps to the same protocol refusal.
        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        await tool_interactions.close_interaction(row.id, InteractionStatus.EXPIRED)
        result = await asyncio.wait_for(task, timeout=5)
        assert isinstance(result, types.ErrorData)

    run_orm(scenario)


def test_url_elicitation_rejects_unsafe_urls(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(
            team,
            enable_elicitation=True,
            elicitation_url_hosts=["auth.example.com"],
        )
        callbacks = mcp_interactions.build_mcp_callbacks(tool, _context(owner, team))
        for url in (
            "http://auth.example.com/start",
            "https://user:pass@auth.example.com/start",
            "https://other.example.com/start",
            "not-a-url",
        ):
            params = types.ElicitRequestURLParams(message="Sign in", url=url)
            assert (await callbacks.elicitation(None, params)).action == "decline"
        assert await InteractionRequest.all().count() == 0

    run_orm(scenario)


def test_close_execution_interactions_is_terminal(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        execution_id = uuid4()
        await tool_interactions.create_interaction(
            kind=InteractionKind.SAMPLING,
            actor=owner,
            team_id=team.id,
            payload={"mode": "sampling", "messages": [], "max_tokens": 8},
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            execution_id=execution_id,
        )
        assert await mcp_interactions.close_execution_interactions(execution_id) == 1
        row = await InteractionRequest.all().first()
        assert row.status == InteractionStatus.CANCELLED
        assert await mcp_interactions.close_execution_interactions(execution_id) == 0

    run_orm(scenario)


def test_run_owner_is_added_to_the_interaction_audience(run_orm):
    async def scenario():
        from app.models.agent import Agent, Conversation
        from app.models.agent_run import AgentRun, AgentRunMode

        owner = await _user("owner")
        caller = await _user("caller")
        team = await _team(owner)
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=caller.id, role="member"
        )
        agent = await Agent.create(
            id=uuid4(), team_id=team.id, name=f"agent_{uuid4().hex[:6]}"
        )
        conversation = await Conversation.create(
            id=uuid4(), agent_id=agent.id, user_id=owner.id
        )
        run = await AgentRun.create(
            id=uuid4(),
            agent_id=agent.id,
            conversation_id=conversation.id,
            user_id=owner.id,
            mode=AgentRunMode.SEND,
        )
        tool = await _tool(team, enable_sampling=True)
        context = _context(
            caller,
            team,
            run_kind="agent",
            run_id=run.id,
            tool_call_id="call-1",
            execution_id=uuid4(),
        )
        callbacks = mcp_interactions.build_mcp_callbacks(tool, context)
        task = asyncio.create_task(callbacks.sampling(None, _sampling_params()))
        row = await _pending_one()
        assert set(row.audience["user_ids"]) == {str(owner.id), str(caller.id)}
        assert row.run_kind == "agent"
        assert row.run_id == run.id
        assert row.tool_name == tool.name
        assert row.tool_call_id == "call-1"
        await tool_interactions.close_interaction(row.id)
        await asyncio.wait_for(task, timeout=5)

    run_orm(scenario)

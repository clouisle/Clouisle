"""Behavior tests for tool execution claims, parameter handling and outcomes.

Covers the single-claim invariant (one worker, one side effect), binding
revalidation at claim time, secret-safe previews, claim-holder-only parameter
decryption, terminal outcome recording and the stale-claim sweep.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services import tool_approvals as service


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@approval.test",
        hashed_password="x",
    )


async def _team(name: str, owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _tool(team: Team, policy: dict) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Approval tool",
        description="behavior test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy=policy,
    )


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


def _team_binding(*, team_id=None, version: int = 1, **overrides):
    values = {
        "connection_id": uuid4(),
        "team_id": team_id,
        "scope": "team",
        "owner_user_id": None,
        "effective_user_id": None,
        "secret_version": version,
        "status": "active",
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _ready_execution(actor: User, team: Team, tool: Tool, **kwargs):
    params = {
        "tool": tool,
        "operation": "mail.send",
        "parameters": {"to": "a@example.test", "count": 1},
        "actor": actor,
        "team_id": team.id,
        "entrypoint": ExecutionEntrypoint.API_KEY,
        "entrypoint_id": "key-1",
    }
    params.update(kwargs)
    return await service.create_execution(**params)


async def _claimed(actor: User, team: Team, tool: Tool, token: str, **kwargs):
    execution = await _ready_execution(actor, team, tool, **kwargs)
    return await service.claim_execution(
        execution.id,
        claim_token=token,
        tool_definition_version=tool.definition_version,
        binding=kwargs.get("connection_binding"),
    )


@pytest.mark.asyncio
async def test_claim_requires_one_ready_binding_and_holder_token():
    async with _database():
        actor = await _user("claim-actor")
        team = await _team("claim-team", actor)
        tool = await _tool(team, _allow_policy())
        execution = await _ready_execution(actor, team, tool)

        for token in ("", "   ", "x" * 65):
            with pytest.raises(BusinessError) as invalid_token:
                await service.claim_execution(
                    execution.id,
                    claim_token=token,
                    tool_definition_version=tool.definition_version,
                )
            assert invalid_token.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as invalid_version:
            await service.claim_execution(
                execution.id,
                claim_token="claim-1",
                tool_definition_version=0,
            )
        assert invalid_version.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        claimed = await service.claim_execution(
            execution.id,
            claim_token="claim-1",
            tool_definition_version=tool.definition_version,
        )
        assert claimed.status == ToolExecutionStatus.EXECUTING
        assert claimed.claim_token == "claim-1"
        assert claimed.claimed_at is not None
        assert claimed.started_at is not None

        with pytest.raises(BusinessError) as second_claim:
            await service.claim_execution(
                execution.id,
                claim_token="claim-2",
                tool_definition_version=tool.definition_version,
            )
        assert second_claim.value.code == ResponseCode.TOOL_EXECUTION_CLAIM_CONFLICT
        assert second_claim.value.data == {"status": "executing"}
        assert (await service.get_execution(execution.id)).claim_token == "claim-1"

        with pytest.raises(BusinessError) as missing:
            await service.claim_execution(
                uuid4(),
                claim_token="claim-1",
                tool_definition_version=1,
            )
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        async def deny(_execution):
            raise RuntimeError("tool access revoked")

        pending = await _ready_execution(actor, team, tool)
        with pytest.raises(RuntimeError, match="tool access revoked"):
            await service.claim_execution(
                pending.id,
                claim_token="claim-denied",
                tool_definition_version=tool.definition_version,
                authorizer=deny,
            )
        assert (
            await service.get_execution(pending.id)
        ).status == ToolExecutionStatus.READY

        with pytest.raises(BusinessError) as missing_preflight:
            await service.claim_execution(
                uuid4(),
                claim_token="claim-missing",
                tool_definition_version=1,
                authorizer=deny,
            )
        assert missing_preflight.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        async def allow(_execution):
            return None

        authorized = await service.claim_execution(
            pending.id,
            claim_token="claim-authorized",
            tool_definition_version=tool.definition_version,
            authorizer=allow,
        )
        assert authorized.status == ToolExecutionStatus.EXECUTING


@pytest.mark.asyncio
async def test_claim_revalidates_expiry_definition_policy_and_binding():
    async with _database():
        actor = await _user("revalidate-actor")
        team = await _team("revalidate-team", actor)
        tool = await _tool(team, _allow_policy())
        now = datetime.now(timezone.utc)

        expired = await _ready_execution(
            actor,
            team,
            tool,
            now=now,
            expires_at=now + timedelta(seconds=5),
        )
        with pytest.raises(BusinessError) as expired_claim:
            await service.claim_execution(
                expired.id,
                claim_token="expired-claim",
                tool_definition_version=tool.definition_version,
                now=now + timedelta(seconds=6),
            )
        assert expired_claim.value.code == ResponseCode.TOOL_EXECUTION_INVALID_STATE
        expired_row = await service.get_execution(expired.id)
        assert expired_row.status == ToolExecutionStatus.CANCELLED
        assert expired_row.cancel_reason == ToolExecutionCancelReason.EXPIRED

        version_changed = await _ready_execution(actor, team, tool)
        with pytest.raises(BusinessError) as definition_mismatch:
            await service.claim_execution(
                version_changed.id,
                claim_token="version-claim",
                tool_definition_version=tool.definition_version + 1,
            )
        assert (
            definition_mismatch.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        )
        assert definition_mismatch.value.data == {"reason": "binding_changed"}
        changed_row = await service.get_execution(version_changed.id)
        assert changed_row.status == ToolExecutionStatus.CANCELLED
        assert changed_row.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED

        policy_changed = await _ready_execution(actor, team, tool)
        with pytest.raises(BusinessError) as policy_mismatch:
            await service.claim_execution(
                policy_changed.id,
                claim_token="policy-claim",
                tool_definition_version=tool.definition_version,
                policy_hash="0" * 64,
            )
        assert policy_mismatch.value.code == (
            ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        )

        bound_tool = await _tool(team, _allow_policy())
        bound = await _ready_execution(
            actor,
            team,
            bound_tool,
            connection_binding=_team_binding(team_id=team.id),
        )
        with pytest.raises(BusinessError) as missing_binding:
            await service.claim_execution(
                bound.id,
                claim_token="missing-binding",
                tool_definition_version=bound_tool.definition_version,
            )
        assert missing_binding.value.data == {"reason": "binding_missing"}

        invalid_bound = await _ready_execution(
            actor,
            team,
            bound_tool,
            connection_binding=_team_binding(team_id=team.id),
        )
        with pytest.raises(BusinessError) as invalid_binding:
            await service.claim_execution(
                invalid_bound.id,
                claim_token="invalid-binding",
                tool_definition_version=bound_tool.definition_version,
                binding=SimpleNamespace(
                    connection_id=uuid4(),
                    scope="galaxy",
                    status="active",
                    secret_version=1,
                ),
            )
        assert invalid_binding.value.data == {"reason": "binding_invalid"}

        unexpected = await _ready_execution(actor, team, tool)
        with pytest.raises(BusinessError) as unexpected_binding:
            await service.claim_execution(
                unexpected.id,
                claim_token="unexpected-binding",
                tool_definition_version=tool.definition_version,
                binding=_team_binding(team_id=team.id),
            )
        assert unexpected_binding.value.data == {"reason": "connection_unexpected"}

        cancellable = await _ready_execution(actor, team, tool)
        await service.cancel_execution(cancellable.id)
        with pytest.raises(BusinessError) as not_ready:
            await service.claim_execution(
                cancellable.id,
                claim_token="cancelled-claim",
                tool_definition_version=tool.definition_version,
            )
        assert not_ready.value.code == ResponseCode.TOOL_EXECUTION_CLAIM_CONFLICT
        assert not_ready.value.data == {"status": "cancelled"}


@pytest.mark.asyncio
async def test_parameters_are_claim_holder_only_and_digest_bound():
    async with _database():
        actor = await _user("params-actor")
        team = await _team("params-team", actor)
        tool = await _tool(team, _allow_policy())
        parameters = {"to": "b@example.test", "nested": {"count": 2}}
        claimed = await _claimed(
            actor, team, tool, "params-token", parameters=parameters
        )

        loaded = await service.load_execution_parameters(
            claimed.id, claim_token="params-token"
        )
        assert loaded == parameters

        with pytest.raises(BusinessError) as wrong_holder:
            await service.load_execution_parameters(
                claimed.id, claim_token="someone-else"
            )
        assert wrong_holder.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        ready = await _ready_execution(actor, team, tool)
        with pytest.raises(BusinessError) as not_executing:
            await service.load_execution_parameters(ready.id, claim_token="x")
        assert not_executing.value.code == ResponseCode.TOOL_EXECUTION_INVALID_STATE

        with pytest.raises(BusinessError) as missing:
            await service.load_execution_parameters(uuid4(), claim_token="x")
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        corrupt = await _claimed(actor, team, tool, "corrupt-token")
        await service.ToolExecution.filter(id=corrupt.id).update(
            parameters_cipher="not-a-fernet-token"
        )
        with pytest.raises(BusinessError) as unreadable:
            await service.load_execution_parameters(
                corrupt.id, claim_token="corrupt-token"
            )
        assert unreadable.value.code == (
            ResponseCode.TOOL_EXECUTION_PARAMETERS_UNREADABLE
        )

        tampered = await _claimed(actor, team, tool, "digest-token")
        await service.ToolExecution.filter(id=tampered.id).update(
            parameters_digest="0" * 64
        )
        with pytest.raises(BusinessError) as digest_mismatch:
            await service.load_execution_parameters(
                tampered.id, claim_token="digest-token"
            )
        assert digest_mismatch.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED


@pytest.mark.asyncio
async def test_finish_outcomes_require_the_claim_and_scalar_references():
    async with _database():
        actor = await _user("finish-actor")
        team = await _team("finish-team", actor)
        tool = await _tool(team, _allow_policy())

        with pytest.raises(BusinessError) as blank_token:
            await service.mark_execution_succeeded(uuid4(), claim_token="  ")
        assert blank_token.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        succeeded = await _claimed(actor, team, tool, "success-token")
        invalid_refs = [
            ["not", "mapping"],
            {"": "value"},
            {"k" * 65: "value"},
            {"summary": "x" * 1001},
            {"nested": {"object": True}},
            {f"key-{index}": "value" for index in range(33)},
            {f"key-{index}": "x" * 1000 for index in range(32)},
        ]
        for result_ref in invalid_refs:
            with pytest.raises(BusinessError) as invalid_ref:
                await service.mark_execution_succeeded(
                    succeeded.id,
                    claim_token="success-token",
                    result_ref=result_ref,
                )
            assert invalid_ref.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        finished = await service.mark_execution_succeeded(
            succeeded.id,
            claim_token="success-token",
            result_ref={"call_id": "call-1", "count": 2},
        )
        assert finished.status == ToolExecutionStatus.SUCCEEDED
        assert finished.result_ref == {"call_id": "call-1", "count": 2}
        assert finished.finished_at is not None

        wrong_holder_execution = await _claimed(actor, team, tool, "holder-token")
        with pytest.raises(BusinessError) as wrong_holder:
            await service.mark_execution_succeeded(
                wrong_holder_execution.id, claim_token="another-token"
            )
        assert wrong_holder.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        failed = await _claimed(actor, team, tool, "fail-token")
        with pytest.raises(BusinessError) as blank_error:
            await service.mark_execution_failed(
                failed.id, claim_token="fail-token", error_code="  "
            )
        assert blank_error.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as long_error:
            await service.mark_execution_failed(
                failed.id,
                claim_token="fail-token",
                error_code="E" * 101,
            )
        assert long_error.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as long_detail:
            await service.mark_execution_failed(
                failed.id,
                claim_token="fail-token",
                error_code="E_TIME",
                error_detail="x" * 2001,
            )
        assert long_detail.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        failed_row = await service.mark_execution_failed(
            failed.id,
            claim_token="fail-token",
            error_code=" E_TIME ",
            error_detail="  upstream timeout \x00 ",
        )
        assert failed_row.status == ToolExecutionStatus.FAILED
        assert failed_row.error_code == "E_TIME"
        assert failed_row.error_detail == "upstream timeout"

        unknown = await _claimed(actor, team, tool, "unknown-token")
        unknown_row = await service.mark_execution_outcome_unknown(
            unknown.id,
            claim_token="unknown-token",
            error_code=None,
        )
        assert unknown_row.status == ToolExecutionStatus.OUTCOME_UNKNOWN
        assert unknown_row.error_code == "outcome_unknown"

        ready = await _ready_execution(actor, team, tool)
        with pytest.raises(BusinessError) as not_executing:
            await service.mark_execution_succeeded(ready.id, claim_token="whatever")
        assert not_executing.value.code == ResponseCode.TOOL_EXECUTION_INVALID_STATE

        with pytest.raises(BusinessError) as missing:
            await service.mark_execution_succeeded(uuid4(), claim_token="whatever")
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND


@pytest.mark.asyncio
async def test_stale_claims_become_outcome_unknown_without_replay():
    async with _database():
        actor = await _user("stale-actor")
        team = await _team("stale-team", actor)
        tool = await _tool(team, _allow_policy())
        now = datetime.now(timezone.utc)

        def run_execution(run_kind: ExecutionRunKind, run_id):
            return _ready_execution(
                actor,
                team,
                tool,
                run_kind=run_kind,
                run_id=run_id,
                now=now,
            )

        agent_execution = await run_execution(ExecutionRunKind.AGENT, uuid4())
        await service.claim_execution(
            agent_execution.id,
            claim_token="agent-stale",
            tool_definition_version=tool.definition_version,
            now=now - timedelta(minutes=10),
        )
        await service.ToolExecution.filter(id=agent_execution.id).update(
            claimed_at=now - timedelta(minutes=10)
        )

        workflow_execution = await run_execution(ExecutionRunKind.WORKFLOW, uuid4())
        await service.claim_execution(
            workflow_execution.id,
            claim_token="workflow-stale",
            tool_definition_version=tool.definition_version,
            now=now - timedelta(minutes=10),
        )
        await service.ToolExecution.filter(id=workflow_execution.id).update(
            claimed_at=now - timedelta(minutes=10)
        )

        no_run = await _ready_execution(actor, team, tool, now=now)
        await service.claim_execution(
            no_run.id,
            claim_token="no-run-stale",
            tool_definition_version=tool.definition_version,
            now=now - timedelta(minutes=10),
        )
        await service.ToolExecution.filter(id=no_run.id).update(
            claimed_at=now - timedelta(minutes=10)
        )

        recent = await _ready_execution(actor, team, tool, now=now)
        await service.claim_execution(
            recent.id,
            claim_token="recent-claim",
            tool_definition_version=tool.definition_version,
            now=now,
        )
        await service.ToolExecution.filter(id=recent.id).update(claimed_at=now)

        marked = await service.mark_stale_executing_outcome_unknown(
            stale_after_seconds=60,
            now=now,
        )
        assert marked == 2

        for execution in (agent_execution, workflow_execution):
            row = await service.get_execution(execution.id)
            assert row.status == ToolExecutionStatus.OUTCOME_UNKNOWN
            assert row.error_code == "claim_expired"
            assert row.finished_at is not None

        untouched = await service.get_execution(no_run.id)
        assert untouched.status == ToolExecutionStatus.EXECUTING
        assert (await service.get_execution(recent.id)).status == (
            ToolExecutionStatus.EXECUTING
        )

        assert (
            await service.mark_stale_executing_outcome_unknown(
                stale_after_seconds=60,
                limit=0,
                now=now + timedelta(minutes=20),
            )
            == 0
        )


def test_parameter_snapshots_redact_nested_secrets_and_bound_preview_size():
    uuid_value = uuid4()
    moment = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    snapshot = service.build_parameter_snapshot(
        {
            "uuid": uuid_value,
            "when": moment,
            "profile": {"api_key": "profile-secret", "name": "Ada"},
            "password": "root-secret",
            "items": [1, 2, 3],
        },
        sensitive_keys=("profile.api_key",),
    )
    preview = snapshot.preview
    assert preview["uuid"] == str(uuid_value)
    assert preview["when"] == moment.isoformat()
    assert preview["profile"]["api_key"] == service.REDACTED
    assert preview["profile"]["name"] == "Ada"
    assert preview["password"] == service.REDACTED
    assert "profile-secret" not in str(preview)
    assert "root-secret" not in str(preview)
    assert "profile.api_key" in snapshot.redacted_paths

    deep: dict = {"leaf": "value"}
    for index in range(8):
        deep = {f"level-{index}": deep}
    deep_preview = service.redact_parameters(deep)
    assert service.TRUNCATED in str(deep_preview)

    wide = service.redact_parameters({f"key-{index}": index for index in range(120)})
    assert wide["_truncated"] is True
    assert len(wide) == 101

    long_list = service.redact_parameters({"items": list(range(60))})
    assert long_list["items"][-1] == service.TRUNCATED

    long_string = service.redact_parameters({"text": "x" * 600})
    assert long_string["text"].endswith("…(truncated)")

    oversized = service.redact_parameters(
        {f"field-{index}": "x" * 500 for index in range(40)}
    )
    assert oversized["_truncated"] is True
    assert len(oversized["_keys"]) == 40

    dotted = service.redact_parameters(
        {"Profile": {"Token": "hidden"}},
        sensitive_keys=("profile.token",),
    )
    assert dotted["Profile"]["Token"] == service.REDACTED


def test_parameter_validation_rejects_unsafe_json_shapes():
    for parameters in (
        ["not", "a", "mapping"],
        {"nested": {1: "non-string-key"}},
        {"bad\x01key": "value"},
        {"unsupported": object()},
        {"nan": float("nan")},
        {"inf": float("inf")},
        {"huge": "x" * (service.MAX_PARAMETERS_BYTES + 1)},
    ):
        with pytest.raises(BusinessError) as invalid:
            service.build_parameter_snapshot(parameters)
        assert invalid.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

    for sensitive_keys in ((1,), ("x" * 201,), ("bad\x01name",)):
        with pytest.raises(BusinessError) as invalid_key:
            service.build_parameter_snapshot({"a": 1}, sensitive_keys=sensitive_keys)
        assert invalid_key.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

    blank_sensitive = service.build_parameter_snapshot({"a": 1}, sensitive_keys=("  ",))
    assert blank_sensitive.preview == {"a": 1}

    datetime_value = datetime(2026, 10, 27, 12, 0)
    naive_snapshot = service.build_parameter_snapshot({"at": datetime_value})
    assert naive_snapshot.preview["at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_binding_snapshot_validation_rejects_every_inconsistent_field():
    async with _database():
        actor = await _user("binding-actor")
        team = await _team("binding-team", actor)
        other_team = await _team("binding-other-team", actor)
        tool = await _tool(team, _allow_policy())
        other_user = await _user("binding-other-user")

        bound = await _ready_execution(
            actor,
            team,
            tool,
            connection_binding=_team_binding(team_id=team.id, version=3),
        )
        valid = {
            "connection_id": bound.connection_id,
            "team_id": team.id,
            "scope": "team",
            "owner_user_id": None,
            "effective_user_id": None,
            "secret_version": 3,
            "status": "active",
            "is_active": True,
        }
        service.validate_binding_snapshot(bound, valid)

        invalid_snapshots = [
            ({**valid, "connection_id": None}, "connection_id_missing"),
            ({**valid, "connection_id": "not-a-uuid"}, "connection_id_invalid"),
            ({**valid, "scope": "galaxy"}, "connection_scope_invalid"),
            ({**valid, "status": ""}, "connection_status_missing"),
            ({**valid, "secret_version": "nope"}, "connection_version_invalid"),
            ({**valid, "secret_version": 0}, "connection_version_invalid"),
            ({**valid, "is_active": False}, "connection_inactive"),
            ({**valid, "status": "revoked"}, "connection_inactive"),
            (
                {**valid, "scope": "user", "team_id": None},
                "connection_owner_required",
            ),
            (
                {
                    **valid,
                    "scope": "user",
                    "team_id": None,
                    "owner_user_id": other_user.id,
                },
                "connection_effective_user_mismatch",
            ),
            (
                {**valid, "owner_user_id": other_user.id},
                "connection_owner_unexpected",
            ),
        ]
        for snapshot, reason in invalid_snapshots:
            with pytest.raises(BusinessError) as invalid:
                service.validate_binding_snapshot(bound, snapshot)
            assert invalid.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
            assert invalid.value.data == {"reason": reason}

        drifted_snapshots = [
            ({**valid, "connection_id": uuid4()}, "connection_changed"),
            ({**valid, "team_id": other_team.id}, "connection_team_changed"),
            ({**valid, "secret_version": 4}, "connection_version_changed"),
            (
                {
                    **valid,
                    "scope": "user",
                    "team_id": None,
                    "owner_user_id": other_user.id,
                    "effective_user_id": other_user.id,
                },
                "connection_scope_changed",
            ),
        ]
        for snapshot, reason in drifted_snapshots:
            with pytest.raises(BusinessError) as changed:
                service.validate_binding_snapshot(bound, snapshot)
            assert changed.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
            assert changed.value.data == {"reason": reason}

        user_bound = await _ready_execution(
            actor,
            team,
            tool,
            connection_binding=_team_binding(
                scope="user",
                team_id=team.id,
                owner_user_id=other_user.id,
                effective_user_id=other_user.id,
                version=1,
            ),
        )
        with pytest.raises(BusinessError) as owner_changed:
            service.validate_binding_snapshot(
                user_bound,
                {
                    "connection_id": user_bound.connection_id,
                    "team_id": team.id,
                    "scope": "user",
                    "owner_user_id": actor.id,
                    "effective_user_id": actor.id,
                    "secret_version": 1,
                    "status": "active",
                    "is_active": True,
                },
            )
        assert owner_changed.value.data == {"reason": "connection_owner_changed"}

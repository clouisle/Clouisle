"""Behavioral tests for persistent approval policy layers (real SQLite ORM).

These tests exercise the actual Tortoise schema, not ORM fakes: scope
authorization, entrypoint resource validation, layer precedence (a lower layer
can tighten but never relax), fail-closed decoding of corrupt rows, and the
version/hash metadata that invalidates pending approvals at claim time.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.models.agent import Agent
from app.models.api_key import APIKey
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_approval import (
    ApprovalVote,
    ExecutionEntrypoint,
    ToolApprovalRequest,
    ToolExecution,
    ToolExecutionCancelReason,
)
from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
)
from app.schemas.tool_approval_policy import (
    ToolApprovalEntrypointKind,
    ToolApprovalPolicyCreateIn,
    ToolApprovalPolicyScope,
    ToolApprovalPolicyUpdateIn,
)
from app.services.tool_approval_policies import (
    build_scope_key,
    create_policy_definition,
    delete_policy_definition,
    get_effective_policy,
    list_policy_definitions,
    load_effective_policy_binding,
    load_effective_policy_layers,
    policy_definition_hash,
    update_policy_definition,
)
from app.services import tool_approvals
from app.services.tool_approvals import evaluate_policy, normalize_tool_approval_policy
from app.services.tool_execution import ToolCallContext, execute_stored_tool


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'approval-policies.sqlite3'}"

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _user(label: str, *, superuser: bool = False) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@policies.test",
        hashed_password="x",
        is_superuser=superuser,
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _join(team: Team, user: User, role: str) -> None:
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role=role)


async def _permission(code: str) -> Permission:
    return await Permission.create(
        id=uuid4(), scope=code.split(":")[0], code=code, description=None
    )


async def _grant(user: User, permission: Permission) -> None:
    role = await Role.create(id=uuid4(), name=f"role_{uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    await user.fetch_related("roles__permissions")


async def _tool(
    team: Team,
    *,
    tool_type: ToolType = ToolType.CUSTOM,
    approval_policy: dict | None = None,
) -> Tool:
    if approval_policy is None:
        approval_policy = {"default_decision": "allow"}
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Policy tool",
        description="policy test",
        type=tool_type,
        custom_type=CustomToolType.HTTP if tool_type == ToolType.CUSTOM else None,
        approval_policy=approval_policy,
    )


async def _agent(team: Team, creator: User) -> Agent:
    return await Agent.create(
        id=uuid4(),
        team_id=team.id,
        name=f"agent_{uuid4().hex[:8]}",
        created_by_id=creator.id,
    )


def _context(
    team: Team,
    *,
    entrypoint: ExecutionEntrypoint = ExecutionEntrypoint.TOOL_TEST,
    entrypoint_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        team_id=team.id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
    )


def _approval_policy(
    decision: ApprovalDecision = ApprovalDecision.REQUIRE_APPROVAL,
    gates: tuple[ApprovalGate, ...] = (),
) -> ToolApprovalPolicy:
    return ToolApprovalPolicy(default_decision=decision, gates=gates)


def _tool_layer(tool: Tool) -> PolicyLayer:
    return PolicyLayer(
        source=PolicySource.TOOL,
        label="tool",
        policy=normalize_tool_approval_policy(tool.approval_policy),
    )


# ---------------------------------------------------------------------------
# Authorization and CRUD
# ---------------------------------------------------------------------------


def test_team_scope_requires_admin_and_global_permission(run_orm):
    async def scenario():
        owner = await _user("owner")
        admin = await _user("admin")
        team = await _team(owner)
        await _join(team, admin, "admin")
        manage = await _permission("tool:update")
        payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.TEAM,
            team_id=team.id,
            policy=_approval_policy(ApprovalDecision.DENY),
        )

        with pytest.raises(BusinessError) as owner_without_permission:
            await create_policy_definition(owner, payload)
        assert (
            owner_without_permission.value.msg_key
            == "tool_approval_policy_access_denied"
        )

        await _grant(owner, manage)
        created = await create_policy_definition(owner, payload)
        assert created.can_edit is True
        assert created.row.version == 1
        assert created.row.scope_key == build_scope_key(
            ToolApprovalPolicyScope.TEAM, team_id=team.id
        )

        with pytest.raises(BusinessError) as duplicate:
            await create_policy_definition(owner, payload)
        assert duplicate.value.msg_key == "tool_approval_policy_duplicate"

        # A team admin still needs the global permission.
        with pytest.raises(BusinessError) as admin_without_permission:
            await create_policy_definition(admin, payload)
        assert (
            admin_without_permission.value.msg_key
            == "tool_approval_policy_access_denied"
        )
        await _grant(admin, manage)
        listed = await list_policy_definitions(admin, team_id=team.id)
        assert [view.row.id for view in listed] == [created.row.id]
        assert listed[0].can_edit is True

        # Stale optimistic version never overwrites a newer write.
        first = await update_policy_definition(
            admin,
            created.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=_approval_policy(ApprovalDecision.ALLOW), expected_version=1
            ),
        )
        assert first.row.version == 2
        with pytest.raises(BusinessError) as stale:
            await update_policy_definition(
                admin,
                created.row.id,
                ToolApprovalPolicyUpdateIn(
                    policy=_approval_policy(ApprovalDecision.DENY), expected_version=1
                ),
            )
        assert stale.value.msg_key == "tool_approval_policy_version_conflict"

        await delete_policy_definition(admin, created.row.id)
        assert await ToolApprovalPolicyDefinition.all().count() == 0

    run_orm(scenario)


def test_site_scope_requires_site_administration(run_orm):
    async def scenario():
        site_admin = await _user("site-admin")
        regular = await _user("regular")
        team = await _team(regular)
        tool = await _tool(team)
        site_manage = await _permission("admin:settings:update")
        payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.SITE,
            tool_id=tool.id,
            policy=_approval_policy(ApprovalDecision.DENY),
        )

        with pytest.raises(BusinessError) as denied:
            await create_policy_definition(regular, payload)
        assert denied.value.msg_key == "tool_approval_policy_access_denied"

        await _grant(site_admin, site_manage)
        created = await create_policy_definition(site_admin, payload)
        assert created.row.scope == ToolApprovalPolicyScope.SITE
        assert created.row.team_id is None

        # A site row is a global floor: it applies to a different team's context.
        other_owner = await _user("other-owner")
        other_team = await _team(other_owner)
        layers = await load_effective_policy_layers(_context(other_team), tool)
        assert [layer.source for layer in layers] == [PolicySource.SITE]
        assert layers[0].label.startswith("site:")
        assert layers[0].label.endswith(":v1")
        evaluation = evaluate_policy(
            [*layers, _tool_layer(tool)], "delete", entrypoint_interactive=True
        )
        assert evaluation.decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_entrypoint_scope_validates_resource_and_creator(run_orm):
    async def scenario():
        owner = await _user("owner")
        creator = await _user("creator")
        bystander = await _user("bystander")
        outsider = await _user("outsider")
        team = await _team(owner)
        await _join(team, creator, "member")
        await _join(team, bystander, "member")
        await _team(outsider)
        agent = await _agent(team, creator)
        manage = await _permission("tool:update")

        for user in (creator, bystander, outsider):
            await _grant(user, manage)

        payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=team.id,
            entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
            entrypoint_id=agent.id,
            policy=_approval_policy(ApprovalDecision.DENY),
        )

        # A member who did not create the entrypoint cannot attach a layer.
        with pytest.raises(BusinessError) as bystander_denied:
            await create_policy_definition(bystander, payload)
        assert bystander_denied.value.msg_key == "tool_approval_policy_access_denied"

        # The creator can.
        created = await create_policy_definition(creator, payload)
        assert created.row.entrypoint_kind == ToolApprovalEntrypointKind.AGENT
        layers = await load_effective_policy_layers(
            _context(
                team,
                entrypoint=ExecutionEntrypoint.AGENT_RUN,
                entrypoint_id=str(agent.id),
            ),
            await _tool(team),
        )
        assert len(layers) == 1
        assert layers[0].label.startswith("entrypoint:")
        assert layers[0].label.endswith(":v1")

        # A team admin may configure it even when not the creator.
        admin_user = await _user("admin")
        await _join(team, admin_user, "admin")
        await _grant(admin_user, manage)
        # Same scope key already exists, so the admin attempt is a duplicate,
        # which proves the admin passed authorization.
        with pytest.raises(BusinessError) as duplicate:
            await create_policy_definition(admin_user, payload)
        assert duplicate.value.msg_key == "tool_approval_policy_duplicate"

        # An entrypoint that lives in another team is rejected, not accepted
        # just because the caller administers the policy team.
        outsider_member = await TeamMember.filter(user_id=outsider.id).first()
        assert outsider_member is not None
        foreign_team = await Team.get(id=outsider_member.team_id)
        with pytest.raises(BusinessError) as invalid:
            await create_policy_definition(
                outsider,
                ToolApprovalPolicyCreateIn(
                    scope=ToolApprovalPolicyScope.ENTRYPOINT,
                    team_id=foreign_team.id,
                    entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                    entrypoint_id=agent.id,
                    policy=_approval_policy(ApprovalDecision.DENY),
                ),
            )
        assert invalid.value.msg_key == "tool_approval_policy_entrypoint_invalid"

    run_orm(scenario)


def test_api_key_entrypoint_requires_team_member_owner(run_orm):
    async def scenario():
        owner = await _user("key-owner")
        outsider = await _user("key-outsider")
        team = await _team(owner)
        await _team(outsider)
        manage = await _permission("tool:update")
        await _grant(owner, manage)
        await _grant(outsider, manage)
        key = await APIKey.create(
            id=uuid4(),
            name="embed key",
            key_prefix="clou_abc",
            key_hash="h" * 64,
            user_id=owner.id,
        )
        tool = await _tool(team)
        payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=team.id,
            entrypoint_kind=ToolApprovalEntrypointKind.API_KEY,
            entrypoint_id=key.id,
            policy=_approval_policy(ApprovalDecision.DENY),
        )
        created = await create_policy_definition(owner, payload)
        assert created.row.entrypoint_kind == ToolApprovalEntrypointKind.API_KEY

        layers = await load_effective_policy_layers(
            _context(
                team,
                entrypoint=ExecutionEntrypoint.API_KEY,
                entrypoint_id=str(key.id),
            ),
            tool,
        )
        assert [layer.source for layer in layers] == [PolicySource.ENTRYPOINT]

        # A key owned by a user outside the target team is not a valid entrypoint.
        outsider_team = await TeamMember.filter(user_id=outsider.id).first()
        assert outsider_team is not None
        foreign_payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=outsider_team.team_id,
            entrypoint_kind=ToolApprovalEntrypointKind.API_KEY,
            entrypoint_id=key.id,
            tool_id=tool.id,
            policy=_approval_policy(ApprovalDecision.DENY),
        )
        with pytest.raises(BusinessError) as invalid:
            await create_policy_definition(outsider, foreign_payload)
        assert invalid.value.msg_key == "tool_approval_policy_entrypoint_invalid"

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Layer composition and invalidation metadata
# ---------------------------------------------------------------------------


def test_layer_precedence_tightens_but_never_relaxes(run_orm):
    async def scenario():
        site_admin = await _user("site-admin")
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        agent = await _agent(team, owner)

        site_manage = await _permission("admin:settings:update")
        manage = await _permission("tool:update")
        await _grant(site_admin, site_manage)
        await _grant(owner, manage)

        gate = ApprovalGate(kind=ApprovalGateKind.CALLER)
        await create_policy_definition(
            site_admin,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.SITE,
                policy=_approval_policy(ApprovalDecision.REQUIRE_APPROVAL, (gate,)),
            ),
        )
        team_view = await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.TEAM,
                team_id=team.id,
                policy=_approval_policy(ApprovalDecision.ALLOW),
            ),
        )
        await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=agent.id,
                policy=_approval_policy(ApprovalDecision.ALLOW),
            ),
        )

        context = _context(
            team,
            entrypoint=ExecutionEntrypoint.AGENT_RUN,
            entrypoint_id=str(agent.id),
        )
        binding = await load_effective_policy_binding(context, tool)
        assert [entry.layer.source for entry in binding.entries] == [
            PolicySource.SITE,
            PolicySource.TEAM,
            PolicySource.ENTRYPOINT,
        ]
        labels = [entry.layer.label for entry in binding.entries]
        assert len(labels) == 3
        for label, scope in zip(labels, ("site", "team", "entrypoint")):
            assert label.startswith(f"{scope}:")
            assert label.endswith(":v1")
        layers = binding.layers
        evaluation = evaluate_policy(
            [*layers, _tool_layer(tool)],
            "delete",
            entrypoint_interactive=True,
        )
        # Team/entrypoint allow layers cannot relax the site requirement.
        assert evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL
        assert evaluation.gates == (gate,)
        assert [source.split(":")[0] for source in evaluation.sources] == [
            "site",
            "team",
            "tool",
            "entrypoint",
        ]
        for source in (
            evaluation.sources[0],
            evaluation.sources[1],
            evaluation.sources[3],
        ):
            assert source.endswith(":v1")

        # The fingerprint is deterministic across reads.
        repeated = await load_effective_policy_binding(context, tool)
        assert repeated.fingerprint == binding.fingerprint

        # A team layer may tighten further; deny wins over every allow.
        await update_policy_definition(
            owner,
            team_view.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=_approval_policy(ApprovalDecision.DENY), expected_version=1
            ),
        )
        tightened = await load_effective_policy_binding(context, tool)
        tightened_eval = evaluate_policy(
            [*tightened.layers, _tool_layer(tool)],
            "delete",
            entrypoint_interactive=True,
        )
        assert tightened_eval.decision == ApprovalDecision.DENY
        assert tightened_eval.gates == ()

    run_orm(scenario)


def test_generic_and_tool_specific_rows_are_both_mandatory(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        manage = await _permission("tool:update")
        await _grant(owner, manage)

        generic_row = await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.TEAM,
                team_id=team.id,
                policy=ToolApprovalPolicy(
                    default_decision=ApprovalDecision.DENY,
                    operation_overrides={
                        "read": ToolApprovalPolicy(
                            default_decision=ApprovalDecision.ALLOW
                        )
                    },
                ),
            ),
        )
        specific_row = await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.TEAM,
                team_id=team.id,
                tool_id=tool.id,
                policy=_approval_policy(ApprovalDecision.ALLOW),
            ),
        )

        layers = await load_effective_policy_layers(_context(team), tool)
        assert len(layers) == 1
        merged = layers[0].policy
        # The tool-specific allow cannot relax the generic mandatory deny.
        assert merged.default_decision == ApprovalDecision.DENY
        assert merged.for_operation("write").default_decision == ApprovalDecision.DENY
        # The generic explicit allow still applies where both sides allow.
        assert merged.for_operation("read").default_decision == ApprovalDecision.ALLOW
        # Both definition rows identify the layer, so changing either one
        # invalidates pending approvals.
        assert layers[0].label == (
            f"team:{generic_row.row.id.hex[:8]}:v1+{specific_row.row.id.hex[:8]}:v1"
        )

        # An operation override on the more specific row can still tighten.
        await update_policy_definition(
            owner,
            specific_row.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=ToolApprovalPolicy(
                    default_decision=ApprovalDecision.ALLOW,
                    operation_overrides={
                        "read": ToolApprovalPolicy(
                            default_decision=ApprovalDecision.DENY
                        )
                    },
                ),
                expected_version=1,
            ),
        )
        tightened = await load_effective_policy_layers(_context(team), tool)
        assert (
            tightened[0].policy.for_operation("read").default_decision
            == ApprovalDecision.DENY
        )
        assert (
            tightened[0].policy.for_operation("write").default_decision
            == ApprovalDecision.DENY
        )

    run_orm(scenario)


def test_version_bump_changes_hash_and_fingerprint(run_orm):
    async def scenario():
        site_admin = await _user("site-admin")
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        site_manage = await _permission("admin:settings:update")
        manage = await _permission("tool:update")
        await _grant(site_admin, site_manage)
        await _grant(owner, manage)

        body = _approval_policy(ApprovalDecision.DENY)
        site_view = await create_policy_definition(
            site_admin,
            ToolApprovalPolicyCreateIn(scope=ToolApprovalPolicyScope.SITE, policy=body),
        )
        team_view = await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.TEAM,
                team_id=team.id,
                policy=_approval_policy(ApprovalDecision.ALLOW),
            ),
        )
        context = _context(team)
        before = await load_effective_policy_binding(context, tool)
        before_eval = evaluate_policy(
            [*before.layers, _tool_layer(tool)],
            "delete",
            entrypoint_interactive=True,
        )
        before_definition = policy_definition_hash(site_view.row)

        # Same policy body, new write: the definition version must invalidate
        # the previous evaluation fingerprint even though the decision is equal.
        updated = await update_policy_definition(
            site_admin,
            site_view.row.id,
            ToolApprovalPolicyUpdateIn(policy=body, expected_version=1),
        )
        assert updated.row.version == 2
        assert policy_definition_hash(updated.row) != before_definition

        after = await load_effective_policy_binding(context, tool)
        assert after.fingerprint != before.fingerprint
        labels = [entry.layer.label for entry in after.entries]
        assert len(labels) == 2
        assert labels[0].startswith("site:")
        assert labels[0].endswith(":v2")
        assert labels[1].startswith("team:")
        assert labels[1].endswith(":v1")
        after_eval = evaluate_policy(
            [*after.layers, _tool_layer(tool)],
            "delete",
            entrypoint_interactive=True,
        )
        assert after_eval.decision == before_eval.decision
        assert after_eval.policy_hash != before_eval.policy_hash

        # Deleting a layer changes the fingerprint too.
        await delete_policy_definition(owner, team_view.row.id)
        deleted = await load_effective_policy_binding(context, tool)
        assert deleted.fingerprint != after.fingerprint
        assert [entry.layer.source for entry in deleted.entries] == [PolicySource.SITE]

    run_orm(scenario)


def test_malformed_row_fails_closed(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        await ToolApprovalPolicyDefinition.create(
            id=uuid4(),
            scope=ToolApprovalPolicyScope.TEAM,
            scope_key=build_scope_key(ToolApprovalPolicyScope.TEAM, team_id=team.id),
            team_id=team.id,
            policy={"default_decision": "not-a-decision"},
            policy_hash="0" * 64,
            version=1,
        )
        layers = await load_effective_policy_layers(_context(team), tool)
        assert len(layers) == 1
        assert layers[0].label.startswith("team:")
        assert layers[0].label.endswith(":invalid")
        assert layers[0].policy.default_decision == ApprovalDecision.DENY
        evaluation = evaluate_policy(
            [*layers, _tool_layer(tool)], "read", entrypoint_interactive=True
        )
        assert evaluation.decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_effective_preview_matches_execution_composition(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        manage = await _permission("tool:update")
        await _grant(owner, manage)
        await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.TEAM,
                team_id=team.id,
                policy=_approval_policy(ApprovalDecision.DENY),
            ),
        )
        view = await get_effective_policy(
            owner,
            team_id=team.id,
            tool_id=tool.id,
            operation="delete",
        )
        assert view.evaluation.decision == ApprovalDecision.DENY
        assert view.can_edit_team is True
        assert len(view.layers) == 1
        assert view.layers[0].layer.label.startswith("team:")
        assert view.layers[0].layer.label.endswith(":v1")
        assert view.layer_can_edit == (True,)
        assert view.layers[0].rows[0].id is not None

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Execution boundary regressions
# ---------------------------------------------------------------------------


async def _execution_actor(team: Team) -> User:
    """Owner with the permissions required by the shared execution boundary."""
    owner = await User.get(
        id=(await TeamMember.filter(team_id=team.id, role="owner").first()).user_id
    )
    for code in ("team:read", "tool:update"):
        await _grant(owner, await _permission(code))
    return owner


def test_changed_tool_policy_invalidates_approval_before_invocation(run_orm):
    """An approved call is bound to the policy that produced it.

    Approval only applies to interactive Agent chat, and for an MCP child the
    tool's own explicit policy (including an operation override) is part of the
    evaluation. Editing that policy after approval must cancel the execution
    instead of running the previously approved side effect.
    """

    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        owner = await _execution_actor(team)
        tool = await _tool(
            team,
            tool_type=ToolType.MCP,
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        tool.created_by_id = owner.id
        await tool.save(update_fields=["created_by_id"])
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            interactive=True,
        )
        invoked: list[dict] = []

        async def invoke(parameters, resolved):
            invoked.append(parameters)
            return {"ok": True}

        pending = await execute_stored_tool(
            tool, "write", {"target": "x"}, context, invoke
        )
        assert invoked == []
        request = await ToolApprovalRequest.filter(
            execution_id=pending.execution_id
        ).first()
        assert request is not None
        await tool_approvals.decide_approval(
            request.id,
            owner,
            decision=ApprovalVote.APPROVE,
            idempotency_key="approve-1",
        )

        # The policy tightens after approval. The re-evaluated hash no longer
        # matches the binding, so the granted approval must not be reused.
        tool.approval_policy = {"default_decision": "deny"}
        await tool.save(update_fields=["approval_policy"])
        with pytest.raises(BusinessError) as changed:
            await execute_stored_tool(
                tool,
                "write",
                {"target": "x"},
                replace(context, execution_id=pending.execution_id),
                invoke,
            )
        assert changed.value.msg_key == "tool_approval_binding_changed"
        assert invoked == []
        execution = await ToolExecution.get(id=pending.execution_id)
        assert execution.status.value == "cancelled"
        assert execution.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED

    run_orm(scenario)


def test_deny_policy_cancels_before_any_invocation(run_orm):
    """A deny decision is terminal at the boundary, not just a pending gate."""

    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        owner = await _execution_actor(team)
        tool = await _tool(
            team,
            tool_type=ToolType.MCP,
            approval_policy={"default_decision": "deny"},
        )
        tool.created_by_id = owner.id
        await tool.save(update_fields=["created_by_id"])
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            interactive=True,
        )
        invoked: list[dict] = []

        async def invoke(parameters, resolved):
            invoked.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as denied:
            await execute_stored_tool(tool, "write", {"target": "x"}, context, invoke)
        assert denied.value.msg_key == "tool_execution_not_ready"
        assert invoked == []
        execution = await ToolExecution.filter(tool_id=tool.id).first()
        assert execution is not None
        assert execution.status.value == "cancelled"
        assert execution.cancel_reason == ToolExecutionCancelReason.POLICY_DENIED

    run_orm(scenario)

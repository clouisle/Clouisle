"""High-value behavior for persistent approval policy layers (real SQLite ORM).

Coverage is intentionally limited to observable authorization, cross-tenant
scope validation and policy precedence. Trivial property/forwarding tests live
with their production modules' existing suites.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tortoise.context import TortoiseContext

from app.models.agent import Agent
from app.models.tool import CustomToolType, Tool, ToolShare, ToolType
from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.models.user import Permission, Role, Team, TeamMember, User
from app.models.workflow import Workflow
from app.schemas.response import BusinessError
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ExecutionEntrypoint,
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
    load_effective_policy_layers,
    merge_tool_approval_policies,
    update_policy_definition,
)
from app.services.tool_approvals import policy_hash


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'approval-policy-gaps.sqlite3'}"

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
        email=f"{label}_{uuid4().hex[:8]}@policy-gaps.test",
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
    existing = await Permission.filter(code=code).first()
    if existing is not None:
        return existing
    return await Permission.create(
        id=uuid4(), scope=code.split(":")[0], code=code, description=None
    )


async def _grant(user: User, code: str) -> None:
    permission = await _permission(code)
    role = await Role.create(id=uuid4(), name=f"role_{uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    await user.fetch_related("roles__permissions")


async def _tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Policy gap tool",
        description="policy gap test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={"default_decision": "allow"},
    )


async def _agent(team: Team, creator: User) -> Agent:
    return await Agent.create(
        id=uuid4(),
        team_id=team.id,
        name=f"agent_{uuid4().hex[:8]}",
        created_by_id=creator.id,
    )


async def _workflow(team: Team, creator: User) -> Workflow:
    return await Workflow.create(
        id=uuid4(),
        team_id=team.id,
        name=f"workflow_{uuid4().hex[:8]}",
        created_by_id=creator.id,
    )


def _context(
    team: Team,
    *,
    entrypoint: ExecutionEntrypoint | str | None = None,
    entrypoint_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        team_id=team.id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
    )


def _policy(
    decision: ApprovalDecision = ApprovalDecision.REQUIRE_APPROVAL,
    gates: tuple[ApprovalGate, ...] = (),
) -> ToolApprovalPolicy:
    return ToolApprovalPolicy(default_decision=decision, gates=gates)


def _team_payload(team: Team, **kwargs) -> ToolApprovalPolicyCreateIn:
    return ToolApprovalPolicyCreateIn(
        scope=ToolApprovalPolicyScope.TEAM, team_id=team.id, **kwargs
    )


async def _raw_row(
    *,
    scope: ToolApprovalPolicyScope,
    scope_key: str,
    team_id: UUID | None = None,
    entrypoint_kind: ToolApprovalEntrypointKind | None = None,
    entrypoint_id: UUID | None = None,
    tool_id: UUID | None = None,
    decision: ApprovalDecision = ApprovalDecision.DENY,
    version: int = 1,
) -> ToolApprovalPolicyDefinition:
    policy = _policy(decision)
    return await ToolApprovalPolicyDefinition.create(
        id=uuid4(),
        scope=scope,
        scope_key=scope_key,
        team_id=team_id,
        entrypoint_kind=entrypoint_kind,
        entrypoint_id=entrypoint_id,
        tool_id=tool_id,
        policy=policy.model_dump(mode="json"),
        policy_hash=policy_hash(policy),
        version=version,
    )


# ---------------------------------------------------------------------------
# Listing authorization and server-computed editability
# ---------------------------------------------------------------------------


def test_site_reader_can_list_but_not_change_rows(run_orm):
    async def scenario():
        reader = await _user("site-reader")
        editor = await _user("site-editor")
        regular = await _user("regular")
        await _grant(reader, "admin:settings:read")
        await _grant(editor, "admin:settings:update")

        created = await create_policy_definition(
            editor,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.SITE,
                policy=_policy(ApprovalDecision.DENY),
            ),
        )

        listed = await list_policy_definitions(reader)
        assert [view.row.id for view in listed] == [created.row.id]
        assert listed[0].can_edit is False

        assert (await list_policy_definitions(editor))[0].can_edit is True
        with pytest.raises(BusinessError) as regular_denied:
            await list_policy_definitions(regular)
        assert regular_denied.value.msg_key == "tool_approval_policy_access_denied"

        with pytest.raises(BusinessError) as update_denied:
            await update_policy_definition(
                reader,
                created.row.id,
                ToolApprovalPolicyUpdateIn(policy=_policy(ApprovalDecision.ALLOW)),
            )
        assert update_denied.value.msg_key == "tool_approval_policy_access_denied"

        with pytest.raises(BusinessError) as delete_denied:
            await delete_policy_definition(reader, created.row.id)
        assert delete_denied.value.msg_key == "tool_approval_policy_access_denied"

    run_orm(scenario)


def test_team_listing_marks_layer_specific_editability(run_orm):
    async def scenario():
        owner = await _user("owner")
        admin = await _user("admin")
        member = await _user("member")
        plain = await _user("plain")
        outsider = await _user("outsider")
        superuser = await _user("root", superuser=True)
        team = await _team(owner)
        await _team(outsider)
        await _join(team, admin, "admin")
        await _join(team, member, "member")
        await _join(team, plain, "member")
        for user in (owner, admin, member):
            await _grant(user, "tool:update")

        tool = await _tool(team)
        agent_of_owner = await _agent(team, owner)
        agent_of_member = await _agent(team, member)

        site_row = await create_policy_definition(
            superuser,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.SITE,
                policy=_policy(ApprovalDecision.REQUIRE_APPROVAL),
            ),
        )
        team_row = await create_policy_definition(
            owner, _team_payload(team, policy=_policy(ApprovalDecision.DENY))
        )
        owner_entry = await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=agent_of_owner.id,
                policy=_policy(ApprovalDecision.ALLOW),
            ),
        )
        member_entry = await create_policy_definition(
            member,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=agent_of_member.id,
                policy=_policy(ApprovalDecision.ALLOW),
            ),
        )
        dangling_entrypoint_id = uuid4()
        dangling = await _raw_row(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            scope_key=build_scope_key(
                ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=dangling_entrypoint_id,
            ),
            team_id=team.id,
            entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
            entrypoint_id=dangling_entrypoint_id,
            tool_id=tool.id,
        )
        incomplete = await _raw_row(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            scope_key=build_scope_key(
                ToolApprovalPolicyScope.ENTRYPOINT, team_id=team.id
            ),
            team_id=team.id,
        )

        def flags(views):
            return {view.row.id: view.can_edit for view in views}

        owner_flags = flags(await list_policy_definitions(owner, team_id=team.id))
        assert owner_flags[site_row.row.id] is False
        assert owner_flags[team_row.row.id] is True
        assert owner_flags[owner_entry.row.id] is True
        assert owner_flags[member_entry.row.id] is True
        assert owner_flags[dangling.id] is True
        assert owner_flags[incomplete.id] is True

        member_flags = flags(await list_policy_definitions(member, team_id=team.id))
        assert member_flags[site_row.row.id] is False
        assert member_flags[team_row.row.id] is False
        assert member_flags[owner_entry.row.id] is False
        assert member_flags[member_entry.row.id] is True
        assert member_flags[dangling.id] is False
        assert member_flags[incomplete.id] is False

        plain_flags = flags(await list_policy_definitions(plain, team_id=team.id))
        assert not any(plain_flags.values())

        superuser_flags = flags(
            await list_policy_definitions(superuser, team_id=team.id)
        )
        assert all(superuser_flags.values())

        with pytest.raises(BusinessError) as outsider_denied:
            await list_policy_definitions(outsider, team_id=team.id)
        assert outsider_denied.value.msg_key == "tool_approval_policy_access_denied"

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Manager, superuser and cross-team scope authorization
# ---------------------------------------------------------------------------


def test_team_manager_requires_owner_or_admin_role(run_orm):
    async def scenario():
        owner = await _user("owner")
        plain = await _user("plain")
        team = await _team(owner)
        await _join(team, plain, "member")
        await _grant(plain, "tool:update")

        with pytest.raises(BusinessError) as denied:
            await create_policy_definition(
                plain, _team_payload(team, policy=_policy(ApprovalDecision.DENY))
            )
        assert denied.value.msg_key == "tool_approval_policy_access_denied"
        assert await ToolApprovalPolicyDefinition.all().count() == 0

    run_orm(scenario)


def test_superuser_bypasses_role_and_membership_checks(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        superuser = await _user("root", superuser=True)

        team_view = await create_policy_definition(
            superuser, _team_payload(team, policy=_policy(ApprovalDecision.DENY))
        )
        listed = await list_policy_definitions(superuser, team_id=team.id)
        assert [view.row.id for view in listed] == [team_view.row.id]
        assert listed[0].can_edit is True

        await update_policy_definition(
            superuser,
            team_view.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=_policy(ApprovalDecision.ALLOW), expected_version=1
            ),
        )

        await create_policy_definition(
            superuser,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.SITE,
                policy=_policy(ApprovalDecision.DENY),
            ),
        )
        preview = await get_effective_policy(
            superuser,
            team_id=team.id,
            tool_id=tool.id,
            operation="delete",
        )
        assert preview.can_edit_team is True
        assert preview.layer_can_edit == (True, True)
        assert preview.evaluation.decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_team_tool_must_exist_and_belong_or_be_shared(run_orm):
    async def scenario():
        owner = await _user("owner")
        other_owner = await _user("other-owner")
        team = await _team(owner)
        other_team = await _team(other_owner)
        await _grant(owner, "tool:update")
        foreign_tool = await _tool(other_team)

        with pytest.raises(BusinessError) as missing:
            await create_policy_definition(
                owner,
                _team_payload(
                    team,
                    tool_id=uuid4(),
                    policy=_policy(ApprovalDecision.DENY),
                ),
            )
        assert missing.value.msg_key == "tool_approval_policy_tool_invalid"

        with pytest.raises(BusinessError) as unshared:
            await create_policy_definition(
                owner,
                _team_payload(
                    team,
                    tool_id=foreign_tool.id,
                    policy=_policy(ApprovalDecision.DENY),
                ),
            )
        assert unshared.value.msg_key == "tool_approval_policy_tool_invalid"

        await ToolShare.create(
            id=uuid4(),
            tool_id=foreign_tool.id,
            shared_with_team_id=team.id,
            shared_by_id=other_owner.id,
        )
        shared = await create_policy_definition(
            owner,
            _team_payload(
                team,
                tool_id=foreign_tool.id,
                policy=_policy(ApprovalDecision.DENY),
            ),
        )
        assert shared.row.tool_id == foreign_tool.id

    run_orm(scenario)


def test_entrypoint_creation_requires_permission_and_membership(run_orm):
    async def scenario():
        owner = await _user("owner")
        creator = await _user("creator")
        outsider = await _user("outsider")
        team = await _team(owner)
        await _join(team, creator, "member")
        agent = await _agent(team, creator)

        payload = ToolApprovalPolicyCreateIn(
            scope=ToolApprovalPolicyScope.ENTRYPOINT,
            team_id=team.id,
            entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
            entrypoint_id=agent.id,
            policy=_policy(ApprovalDecision.DENY),
        )

        with pytest.raises(BusinessError) as no_permission:
            await create_policy_definition(creator, payload)
        assert no_permission.value.msg_key == "tool_approval_policy_access_denied"

        await _grant(outsider, "tool:update")
        with pytest.raises(BusinessError) as no_membership:
            await create_policy_definition(outsider, payload)
        assert no_membership.value.msg_key == "tool_approval_policy_access_denied"

        await _grant(creator, "tool:update")
        created = await create_policy_definition(creator, payload)
        assert created.row.entrypoint_id == agent.id

        layers = await load_effective_policy_layers(
            _context(
                team,
                entrypoint=ExecutionEntrypoint.AGENT_RUN,
                entrypoint_id=str(agent.id),
            ),
            await _tool(team),
        )
        assert [layer.source for layer in layers] == [PolicySource.ENTRYPOINT]

    run_orm(scenario)


def test_workflow_entrypoint_must_live_in_the_policy_team(run_orm):
    async def scenario():
        owner = await _user("owner")
        other_owner = await _user("other-owner")
        team = await _team(owner)
        other_team = await _team(other_owner)
        await _grant(owner, "tool:update")
        workflow = await _workflow(team, owner)
        foreign_workflow = await _workflow(other_team, other_owner)

        await create_policy_definition(
            owner,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.WORKFLOW,
                entrypoint_id=workflow.id,
                policy=_policy(ApprovalDecision.REQUIRE_APPROVAL),
            ),
        )

        for missing_id in (uuid4(), foreign_workflow.id):
            with pytest.raises(BusinessError) as invalid:
                await create_policy_definition(
                    owner,
                    ToolApprovalPolicyCreateIn(
                        scope=ToolApprovalPolicyScope.ENTRYPOINT,
                        team_id=team.id,
                        entrypoint_kind=ToolApprovalEntrypointKind.WORKFLOW,
                        entrypoint_id=missing_id,
                        policy=_policy(ApprovalDecision.DENY),
                    ),
                )
            assert invalid.value.msg_key == "tool_approval_policy_entrypoint_invalid"

    run_orm(scenario)


def test_team_policy_update_requires_admin_and_manage(run_orm):
    async def scenario():
        owner = await _user("owner")
        admin = await _user("admin")
        member = await _user("member")
        plain = await _user("plain")
        outsider = await _user("outsider")
        superuser = await _user("root", superuser=True)
        team = await _team(owner)
        await _join(team, admin, "admin")
        await _join(team, member, "member")
        await _join(team, plain, "member")
        await _team(outsider)
        for user in (owner, admin, member, outsider):
            await _grant(user, "tool:update")

        row = await create_policy_definition(
            owner, _team_payload(team, policy=_policy(ApprovalDecision.DENY))
        )
        new_policy = _policy(ApprovalDecision.ALLOW)

        with pytest.raises(BusinessError) as no_manage:
            await update_policy_definition(
                plain, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
            )
        assert no_manage.value.msg_key == "tool_approval_policy_access_denied"

        with pytest.raises(BusinessError) as not_member:
            await update_policy_definition(
                outsider, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
            )
        assert not_member.value.msg_key == "tool_approval_policy_access_denied"

        with pytest.raises(BusinessError) as not_admin:
            await update_policy_definition(
                member, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
            )
        assert not_admin.value.msg_key == "tool_approval_policy_access_denied"

        admin_update = await update_policy_definition(
            admin, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
        )
        assert admin_update.row.version == 2

        superuser_update = await update_policy_definition(
            superuser,
            row.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=_policy(ApprovalDecision.DENY), expected_version=2
            ),
        )
        assert superuser_update.row.version == 3

    run_orm(scenario)


def test_entrypoint_policy_update_requires_admin_or_owner(run_orm):
    async def scenario():
        owner = await _user("owner")
        creator = await _user("creator")
        member = await _user("member")
        team = await _team(owner)
        await _join(team, creator, "member")
        await _join(team, member, "member")
        for user in (owner, creator, member):
            await _grant(user, "tool:update")
        agent = await _agent(team, creator)

        row = await create_policy_definition(
            creator,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.ENTRYPOINT,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=agent.id,
                policy=_policy(ApprovalDecision.DENY),
            ),
        )
        new_policy = _policy(ApprovalDecision.ALLOW)

        with pytest.raises(BusinessError) as not_owner:
            await update_policy_definition(
                member, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
            )
        assert not_owner.value.msg_key == "tool_approval_policy_access_denied"

        owner_update = await update_policy_definition(
            owner, row.row.id, ToolApprovalPolicyUpdateIn(policy=new_policy)
        )
        assert owner_update.row.version == 2

        creator_update = await update_policy_definition(
            creator,
            row.row.id,
            ToolApprovalPolicyUpdateIn(
                policy=_policy(ApprovalDecision.DENY), expected_version=2
            ),
        )
        assert creator_update.row.version == 3

    run_orm(scenario)


# ---------------------------------------------------------------------------
# Policy precedence and fail-closed integrity
# ---------------------------------------------------------------------------


def test_merge_require_approval_unions_gates():
    admin_gate = ApprovalGate(
        kind=ApprovalGateKind.TEAM_ROLE,
        roles=("admin",),
        allow_self_approval=False,
    )
    user_gate = ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(uuid4(),))
    caller_gate = ApprovalGate(kind=ApprovalGateKind.CALLER)

    upper = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(admin_gate, user_gate),
    )
    lower = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(caller_gate, admin_gate),
    )

    merged = merge_tool_approval_policies(upper, lower)
    assert merged.default_decision == ApprovalDecision.REQUIRE_APPROVAL
    assert merged.gates == (admin_gate, user_gate, caller_gate)

    denied = merge_tool_approval_policies(
        upper, ToolApprovalPolicy(default_decision=ApprovalDecision.DENY)
    )
    assert denied.default_decision == ApprovalDecision.DENY
    assert denied.gates == ()


def test_tampered_policy_hash_fails_closed(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        policy = _policy(ApprovalDecision.DENY)
        await ToolApprovalPolicyDefinition.create(
            id=uuid4(),
            scope=ToolApprovalPolicyScope.TEAM,
            scope_key=build_scope_key(ToolApprovalPolicyScope.TEAM, team_id=team.id),
            team_id=team.id,
            policy=policy.model_dump(mode="json"),
            policy_hash="0" * 64,
            version=1,
        )

        layers = await load_effective_policy_layers(_context(team), tool)
        assert len(layers) == 1
        assert layers[0].label.endswith(":invalid")
        assert layers[0].policy.default_decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_preview_validates_entrypoint_and_computes_editability(run_orm):
    async def scenario():
        owner = await _user("owner")
        member = await _user("member")
        superuser = await _user("root", superuser=True)
        team = await _team(owner)
        await _join(team, member, "member")
        await _grant(owner, "tool:update")
        tool = await _tool(team)
        agent = await _agent(team, owner)

        await create_policy_definition(
            owner,
            _team_payload(team, policy=_policy(ApprovalDecision.REQUIRE_APPROVAL)),
        )

        with pytest.raises(BusinessError) as half_scope:
            await get_effective_policy(
                owner,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=None,
                tool_id=tool.id,
                operation="delete",
            )
        assert half_scope.value.msg_key == "tool_approval_policy_scope_invalid"

        with pytest.raises(BusinessError) as dangling:
            await get_effective_policy(
                owner,
                team_id=team.id,
                entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
                entrypoint_id=uuid4(),
                tool_id=tool.id,
                operation="delete",
            )
        assert dangling.value.msg_key == "tool_approval_policy_entrypoint_invalid"

        owner_view = await get_effective_policy(
            owner,
            team_id=team.id,
            tool_id=tool.id,
            operation="delete",
        )
        assert owner_view.layer_can_edit == (True,)
        assert owner_view.can_edit_team is True
        assert owner_view.evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL

        member_view = await get_effective_policy(
            member,
            team_id=team.id,
            tool_id=tool.id,
            operation="delete",
        )
        assert member_view.layer_can_edit == (False,)
        assert member_view.can_edit_team is False

        superuser_view = await get_effective_policy(
            superuser,
            team_id=team.id,
            tool_id=tool.id,
            operation="delete",
        )
        assert superuser_view.layer_can_edit == (True,)
        assert superuser_view.can_edit_team is True

        await create_policy_definition(
            superuser,
            ToolApprovalPolicyCreateIn(
                scope=ToolApprovalPolicyScope.SITE,
                policy=_policy(ApprovalDecision.DENY),
            ),
        )
        mixed = await get_effective_policy(
            owner,
            team_id=team.id,
            entrypoint_kind=ToolApprovalEntrypointKind.AGENT,
            entrypoint_id=agent.id,
            tool_id=tool.id,
            operation="delete",
            entrypoint_interactive=False,
        )
        assert mixed.layer_can_edit == (False, True)
        assert mixed.evaluation.decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_effective_preview_matches_the_actual_entrypoint(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        tool = await _tool(team)
        caller_gate = (ApprovalGate(kind=ApprovalGateKind.CALLER),)
        stored = ToolApprovalPolicy(
            default_decision=ApprovalDecision.REQUIRE_APPROVAL,
            gates=caller_gate,
            operation_overrides={
                "list:tools": ToolApprovalPolicy(
                    default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                    gates=caller_gate,
                )
            },
        )
        await Tool.filter(id=tool.id).update(
            type=ToolType.MCP,
            created_by_id=owner.id,
            approval_policy=stored.model_dump(mode="json"),
        )
        tool = await Tool.get(id=tool.id)
        await _grant(owner, "tool:update")
        await _grant(owner, "team:read")

        # Capability browsing is a direct call: the tool's operation default
        # never gates it, exactly like execute_stored_tool.
        direct = await get_effective_policy(
            owner, team_id=team.id, tool_id=tool.id, operation="tool:search"
        )
        assert direct.evaluation.decision == ApprovalDecision.ALLOW
        assert direct.evaluation.gates == ()

        explicit_test = await get_effective_policy(
            owner,
            team_id=team.id,
            tool_id=tool.id,
            operation="tool:search",
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
        )
        assert explicit_test.evaluation.decision == ApprovalDecision.ALLOW

        # An interactive agent call reaches the same layer the model call does.
        agent_call = await get_effective_policy(
            owner,
            team_id=team.id,
            tool_id=tool.id,
            operation="tool:search",
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        assert agent_call.evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL

        # Execution agrees with both previews, not just the API.
        from app.services.tool_execution import (
            PendingToolApproval,
            ToolCallContext,
            execute_stored_tool,
        )

        async def invoke(_parameters, _connection):
            return "ran"

        direct_call = await execute_stored_tool(
            tool,
            "tool:search",
            {},
            ToolCallContext(
                actor=owner,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.TOOL_TEST,
                interactive=True,
            ),
            invoke,
        )
        assert direct_call == "ran"

        agent_execution = await execute_stored_tool(
            tool,
            "tool:search",
            {},
            ToolCallContext(
                actor=owner,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                interactive=True,
            ),
            invoke,
        )
        assert isinstance(agent_execution, PendingToolApproval)

        # A non-interactive Agent entrypoint still applies the tool layer. A
        # caller gate becomes a configuration error (nobody can approve), so
        # both preview and execution fail closed instead of skipping policy.
        non_interactive = await get_effective_policy(
            owner,
            team_id=team.id,
            tool_id=tool.id,
            operation="tool:search",
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_interactive=False,
        )
        assert non_interactive.evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL
        assert (
            non_interactive.evaluation.configuration_error
            == "approval_audience_unavailable"
        )
        assert non_interactive.evaluation.is_allowed is False
        with pytest.raises(BusinessError) as fail_closed:
            await execute_stored_tool(
                tool,
                "tool:search",
                {},
                ToolCallContext(
                    actor=owner,
                    team_id=team.id,
                    entrypoint=ExecutionEntrypoint.CHAT,
                    entrypoint_id=str(uuid4()),
                    interactive=False,
                ),
                invoke,
            )
        assert fail_closed.value.msg_key == (
            "tool_approval_policy_configuration_required"
        )
        assert fail_closed.value.data == {"reason": "approval_audience_unavailable"}

        # Discovery honours its explicit one-level override.
        discovery_override = await get_effective_policy(
            owner, team_id=team.id, tool_id=tool.id, operation="list:tools"
        )
        assert (
            discovery_override.evaluation.decision == ApprovalDecision.REQUIRE_APPROVAL
        )

        # Content browsing is direct and has no discovery override.
        ignored_override = await get_effective_policy(
            owner, team_id=team.id, tool_id=tool.id, operation="read:resource"
        )
        assert ignored_override.evaluation.decision == ApprovalDecision.ALLOW

        # A discovery operation with no explicit override stays open.
        unconfigured_discovery = await get_effective_policy(
            owner, team_id=team.id, tool_id=tool.id, operation="list:resources"
        )
        assert unconfigured_discovery.evaluation.decision == ApprovalDecision.ALLOW

        # Stored layers still tighten every entrypoint, including browsing.
        await create_policy_definition(
            owner, _team_payload(team, policy=_policy(ApprovalDecision.DENY))
        )
        denied = await get_effective_policy(
            owner, team_id=team.id, tool_id=tool.id, operation="tool:search"
        )
        assert denied.evaluation.decision == ApprovalDecision.DENY

    run_orm(scenario)


def test_tool_layer_resolver_keeps_legacy_audiences_fail_closed():
    from app.services.tool_approval_policies import resolve_tool_layer_policy

    legacy = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(ApprovalGate(kind=ApprovalGateKind.TEAM_ROLE, roles=("member",)),),
    )

    resolved = resolve_tool_layer_policy(
        SimpleNamespace(
            type=ToolType.MCP,
            approval_policy=legacy.model_dump(mode="json"),
        ),
        operation="list:tools",
        entrypoint=ExecutionEntrypoint.TOOL_TEST,
    )

    assert resolved.default_decision == ApprovalDecision.REQUIRE_APPROVAL
    assert resolved.gates

    # Explicit policies apply to every tool type on Agent invocations,
    # including non-interactive API-key runs (which then fail closed).
    caller_policy = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
    )
    for tool_type in (ToolType.CUSTOM, ToolType.MCP):
        custom = resolve_tool_layer_policy(
            SimpleNamespace(
                type=tool_type,
                approval_policy=caller_policy.model_dump(mode="json"),
            ),
            operation="tool:search",
            entrypoint=ExecutionEntrypoint.API_KEY,
        )
        assert custom.default_decision == ApprovalDecision.REQUIRE_APPROVAL

    # No explicit policy means no added restriction for Agent calls.
    unconfigured = resolve_tool_layer_policy(
        SimpleNamespace(type=ToolType.CUSTOM, approval_policy={}),
        operation="tool:search",
        entrypoint=ExecutionEntrypoint.API_KEY,
    )
    assert unconfigured.default_decision == ApprovalDecision.ALLOW


def test_agent_call_predicate_normalizes_entrypoints_and_run_kinds():
    from app.schemas.tool_approval import ExecutionRunKind
    from app.services.tool_approval_policies import is_agent_tool_call

    assert is_agent_tool_call(ExecutionEntrypoint.CHAT) is True
    assert is_agent_tool_call("chat") is True
    assert is_agent_tool_call(ExecutionEntrypoint.API_KEY) is True
    assert is_agent_tool_call(ExecutionEntrypoint.NESTED_AGENT) is True
    assert is_agent_tool_call(ExecutionEntrypoint.SCHEDULE) is True
    assert is_agent_tool_call(ExecutionEntrypoint.EMBED) is True
    assert (
        is_agent_tool_call(
            ExecutionEntrypoint.CHAT,
            run_kind=ExecutionRunKind.WORKFLOW,
        )
        is False
    )
    assert is_agent_tool_call(ExecutionEntrypoint.CHAT, run_kind="workflow") is False
    assert is_agent_tool_call(ExecutionEntrypoint.TOOL_TEST) is False
    assert is_agent_tool_call(ExecutionEntrypoint.WORKFLOW) is False
    assert is_agent_tool_call(None) is False

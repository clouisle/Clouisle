"""Workflow access-policy endpoints against a real database."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.api.v1.endpoints import workflows as workflows_endpoint
from app.models.user import Team, TeamMember, User
from app.models.workflow import Workflow, WorkflowStatus, WorkflowVisibility
from app.schemas.response import BusinessError


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str, *, is_superuser: bool = False) -> User:
    created = await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:6]}",
        email=f"{label}_{uuid4().hex[:6]}@policy.test",
        hashed_password="x",
        is_superuser=is_superuser,
    )
    # The team guard reads global permission grants through ``user.roles``.
    return await User.get(id=created.id).prefetch_related("roles__permissions")


async def _grant(user: User, *codes: str) -> User:
    """Give ``user`` a role holding these global permission codes."""
    from app.models.user import Permission, Role

    role = await Role.create(name=f"role_{uuid4().hex[:8]}")
    for code in codes:
        permission = await Permission.get_or_create(code=code, scope="global")
        await role.permissions.add(permission[0])
    await user.roles.add(role)
    return await User.get(id=user.id).prefetch_related("roles__permissions")


async def _member(label: str, *codes: str, is_superuser: bool = False) -> User:
    """A user holding the given global permission codes."""
    return await _grant(
        await _user(label, is_superuser=is_superuser),
        "team:read",
        "workflow:read",
        "workflow:update",
        *codes,
    )


async def _team_with(owner: User, *members: tuple[User, str]) -> Team:
    team = await Team.create(id=uuid4(), name=f"policy_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    for user, role in members:
        await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role=role)
    return team


async def _workflow(team: Team, owner: User, **overrides) -> Workflow:
    fields = {
        "id": uuid4(),
        "team_id": team.id,
        "created_by_id": owner.id,
        "name": f"flow_{uuid4().hex[:6]}",
        "visibility": WorkflowVisibility.TEAM,
        "status": WorkflowStatus.PUBLISHED,
        "definition": {"nodes": [], "edges": [], "viewport": {}},
    }
    fields.update(overrides)
    return await Workflow.create(**fields)


@pytest.mark.asyncio
async def test_policy_starts_empty_and_inherits(monkeypatch):
    async with _database():
        owner = await _member("owner")
        team = await _team_with(owner)
        workflow = await _workflow(team, owner)

        response = await workflows_endpoint.get_workflow_access_policy(
            workflow_id=workflow.id, current_user=owner
        )

        assert response["data"]["policy"] == {"operations": {}}
        assert response["data"]["version"] == 1
        assert all(
            decision["source"] == "inherit"
            for decision in response["data"]["effective"].values()
        )


@pytest.mark.asyncio
async def test_policy_update_persists_audits_and_limits_run(monkeypatch):
    async with _database():
        owner = await _member("owner")
        member = await _member("member")
        team = await _team_with(owner, (member, "member"))
        workflow = await _workflow(team, owner)
        log = AsyncMock()
        monkeypatch.setattr(workflows_endpoint.AuditLogService, "log", log)

        response = await workflows_endpoint.update_workflow_access_policy(
            workflow_id=workflow.id,
            payload={
                "operations": {
                    "run": {
                        "decision": "allow",
                        "gates": [{"kind": "team_role", "roles": ["owner", "admin"]}],
                    }
                }
            },
            request=SimpleNamespace(),
            current_user=owner,
        )

        assert response["data"]["version"] == 2
        assert response["data"]["effective"]["run"]["allowed"] is True
        fresh = await Workflow.get(id=workflow.id)
        assert fresh.access_policy["operations"]["run"]["decision"] == "allow"
        log.assert_awaited_once()
        assert log.await_args.kwargs["action"] == "update_workflow_access_policy"

        # The owner passes the gate; a plain member is refused on run only.
        assert (
            await workflows_endpoint.check_workflow_access(
                workflow.id, owner, operation="run"
            )
        ).id == workflow.id
        with pytest.raises(BusinessError) as denied:
            await workflows_endpoint.check_workflow_access(
                workflow.id, member, operation="run"
            )
        assert denied.value.status_code == 404
        # Reads are still inherited, so the member can open the workflow.
        await workflows_endpoint.check_workflow_access(workflow.id, member)


@pytest.mark.asyncio
async def test_policy_deny_blocks_edits_but_superuser_can_still_manage(monkeypatch):
    async with _database():
        owner = await _member("owner")
        admin = await _member("admin")
        root = await _member("root", is_superuser=True)
        team = await _team_with(owner, (admin, "admin"))
        workflow = await _workflow(
            team,
            owner,
            access_policy={"operations": {"edit": {"decision": "deny"}}},
        )
        monkeypatch.setattr(workflows_endpoint.AuditLogService, "log", AsyncMock())

        with pytest.raises(BusinessError) as denied:
            await workflows_endpoint.check_workflow_access(
                workflow.id, admin, require_write=True
            )
        assert denied.value.status_code == 403

        # Managing the policy itself is not blocked by the policy.
        response = await workflows_endpoint.get_workflow_access_policy(
            workflow_id=workflow.id, current_user=admin
        )
        assert response["data"]["policy"]["operations"]["edit"]["decision"] == "deny"

        await workflows_endpoint.check_workflow_access(
            workflow.id, root, require_write=True
        )


@pytest.mark.asyncio
async def test_invalid_policy_is_rejected_without_saving(monkeypatch):
    async with _database():
        owner = await _member("owner")
        team = await _team_with(owner)
        workflow = await _workflow(team, owner)

        with pytest.raises(BusinessError) as invalid:
            await workflows_endpoint.update_workflow_access_policy(
                workflow_id=workflow.id,
                payload={"operations": {"run": {"decision": "maybe"}}},
                request=SimpleNamespace(),
                current_user=owner,
            )

        assert invalid.value.status_code == 400
        fresh = await Workflow.get(id=workflow.id)
        assert fresh.access_policy == {}
        assert fresh.access_policy_version == 1


@pytest.mark.asyncio
async def test_evaluate_previews_another_member_without_mutating(monkeypatch):
    async with _database():
        owner = await _member("owner")
        viewer = await _member("viewer")
        team = await _team_with(owner, (viewer, "viewer"))
        workflow = await _workflow(
            team,
            owner,
            access_policy={
                "operations": {
                    "run": {
                        "decision": "allow",
                        "gates": [{"kind": "team_role", "roles": ["owner"]}],
                    }
                }
            },
        )

        response = await workflows_endpoint.evaluate_workflow_access_policy(
            workflow_id=workflow.id,
            current_user=owner,
            user_id=viewer.id,
            api_key_id=None,
        )

        assert response["data"]["principal"]["team_role"] == "viewer"
        assert response["data"]["operations"]["run"]["allowed"] is False
        assert response["data"]["operations"]["view"]["source"] == "inherit"
        fresh = await Workflow.get(id=workflow.id)
        assert fresh.access_policy_version == 1

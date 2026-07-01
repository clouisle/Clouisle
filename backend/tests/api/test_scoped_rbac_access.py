from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.deps import check_scoped_permission
from app.api.team_access import check_team_access
from app.api.workflow_access import check_workflow_access
from app.models.workflow import WorkflowVisibility
from app.schemas.response import BusinessError


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _Query:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class _TeamModel:
    team = None

    @classmethod
    def filter(cls, **_kwargs):
        return _Query(cls.team)


class _TeamMemberModel:
    membership = None

    @classmethod
    def filter(cls, **_kwargs):
        return _Query(cls.membership)


@pytest.mark.anyio
async def test_team_member_cannot_use_team_admin_action(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    _TeamModel.team = team
    _TeamMemberModel.membership = SimpleNamespace(role="member")
    monkeypatch.setattr("app.api.team_access.Team", _TeamModel)
    monkeypatch.setattr("app.api.team_access.TeamMember", _TeamMemberModel)

    with pytest.raises(BusinessError) as error:
        await check_team_access(team.id, user, require_admin=True)

    assert error.value.msg_key == "team_admin_required"


@pytest.mark.anyio
async def test_team_admin_can_use_team_admin_action(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    _TeamModel.team = team
    _TeamMemberModel.membership = SimpleNamespace(role="admin")
    monkeypatch.setattr("app.api.team_access.Team", _TeamModel)
    monkeypatch.setattr("app.api.team_access.TeamMember", _TeamMemberModel)

    assert await check_team_access(team.id, user, require_admin=True) is team


class _WorkflowModel:
    workflow = None

    @classmethod
    def filter(cls, **_kwargs):
        return _Query(cls.workflow)


@pytest.mark.anyio
async def test_private_workflow_rejects_unrelated_user(monkeypatch):
    owner = SimpleNamespace(id=uuid4())
    other_user = SimpleNamespace(id=uuid4(), is_superuser=False)
    _WorkflowModel.workflow = SimpleNamespace(
        id=uuid4(),
        visibility=WorkflowVisibility.PRIVATE,
        created_by=owner,
        team=SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr("app.api.workflow_access.Workflow", _WorkflowModel)

    with pytest.raises(BusinessError) as error:
        await check_workflow_access(_WorkflowModel.workflow.id, other_user)

    assert error.value.msg_key == "workflow_access_denied"


@pytest.mark.anyio
async def test_team_workflow_write_delegates_to_team_admin_check(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(
        id=uuid4(),
        visibility=WorkflowVisibility.TEAM,
        created_by=None,
        team=team,
    )
    _WorkflowModel.workflow = workflow
    check_team = AsyncMock()
    monkeypatch.setattr("app.api.workflow_access.Workflow", _WorkflowModel)
    monkeypatch.setattr("app.api.workflow_access.check_team_access", check_team)

    assert (
        await check_workflow_access(workflow.id, user, require_write=True) is workflow
    )
    check_team.assert_any_await(team.id, user)
    check_team.assert_any_await(team.id, user, require_admin=True)


class _ScopedAssignmentModel:
    assignments = []

    @classmethod
    def filter(cls, **_kwargs):
        return _Query(cls.assignments)


@pytest.mark.anyio
async def test_team_scoped_role_cannot_satisfy_admin_permission(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        roles=[],
    )
    _ScopedAssignmentModel.assignments = [SimpleNamespace(role=_Role("admin:*", "*"))]
    monkeypatch.setattr("app.api.deps.ScopedRoleAssignment", _ScopedAssignmentModel)

    with pytest.raises(BusinessError) as error:
        await check_scoped_permission(user, "admin:dashboard:access", "team", uuid4())

    assert error.value.msg_key == "operation_not_permitted"


@pytest.mark.anyio
async def test_team_scoped_role_satisfies_non_admin_permission(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        roles=[],
    )
    _ScopedAssignmentModel.assignments = [
        SimpleNamespace(role=_Role("workflow:update"))
    ]
    monkeypatch.setattr("app.api.deps.ScopedRoleAssignment", _ScopedAssignmentModel)

    await check_scoped_permission(user, "workflow:update", "team", uuid4())


@pytest.mark.anyio
async def test_team_workflow_owner_can_write_without_team_admin(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(
        id=uuid4(),
        visibility=WorkflowVisibility.TEAM,
        created_by=user,
        team=team,
    )
    _WorkflowModel.workflow = workflow
    check_team = AsyncMock()
    monkeypatch.setattr("app.api.workflow_access.Workflow", _WorkflowModel)
    monkeypatch.setattr("app.api.workflow_access.check_team_access", check_team)

    assert (
        await check_workflow_access(workflow.id, user, require_write=True) is workflow
    )
    check_team.assert_awaited_once_with(team.id, user)

"""Visibility scoping for the global workflow run endpoints (YUN-153).

``GET /workflows/runs`` and ``GET /workflows/runs/stats`` previously scoped
only by team membership, so a team member could read run history, statuses,
durations and workflow names belonging to another member's PRIVATE workflow —
data that a direct ``GET /workflows/{id}`` would reject.

These tests assert the queryset filter matches ``check_workflow_access`` read
semantics: team/public workflows in the user's teams, own private workflows,
and creator-less legacy private workflows.
"""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from tortoise.expressions import Q

from app.api import workflow_access
from app.models.workflow import WorkflowVisibility


class _MembershipQuery:
    def __init__(self, team_ids):
        self.team_ids = team_ids

    async def values_list(self, *_args, **_kwargs):
        return self.team_ids


def _flatten(node) -> list[dict]:
    """Collect the leaf filter kwargs of a (possibly nested) Q tree."""
    if not node.children:
        return [dict(node.filters)]
    leaves: list[dict] = []
    for child in node.children:
        leaves.extend(_flatten(child))
    return leaves


@pytest.mark.anyio
async def test_visibility_filter_is_skipped_for_superusers(monkeypatch):
    membership = Mock()
    monkeypatch.setattr(workflow_access.TeamMember, "filter", membership)

    result = await workflow_access.workflow_read_visibility_filter(
        SimpleNamespace(id=uuid4(), is_superuser=True)
    )

    assert result is None
    membership.assert_not_called()


@pytest.mark.anyio
async def test_visibility_filter_scopes_to_teams_ownership_and_legacy(monkeypatch):
    user_id, team_id = uuid4(), uuid4()
    monkeypatch.setattr(
        workflow_access.TeamMember,
        "filter",
        lambda **_kwargs: _MembershipQuery([team_id]),
    )

    result = await workflow_access.workflow_read_visibility_filter(
        SimpleNamespace(id=user_id, is_superuser=False)
    )

    assert isinstance(result, Q)
    branches = _flatten(result)

    # Team/public workflows are readable only inside the user's own teams.
    assert {
        "team_id__in": [team_id],
        "visibility__in": [WorkflowVisibility.TEAM, WorkflowVisibility.PUBLIC],
    } in branches
    # Own private workflows stay readable regardless of team membership.
    assert {
        "created_by_id": user_id,
        "visibility": WorkflowVisibility.PRIVATE,
    } in branches
    # Creator-less legacy private workflows fall back to team membership,
    # matching check_workflow_access's `if not workflow.created_by` branch.
    assert {
        "team_id__in": [team_id],
        "created_by_id__isnull": True,
        "visibility": WorkflowVisibility.PRIVATE,
    } in branches

    # A foreign member's private workflow matches no branch: every branch
    # either demands ownership, a null creator, or non-private visibility.
    assert not any(
        branch.get("visibility") == WorkflowVisibility.PRIVATE
        and "created_by_id" not in branch
        and "created_by_id__isnull" not in branch
        for branch in branches
    )

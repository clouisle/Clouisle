from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.api.v1.endpoints.tools import list_tool_shares, share_tool
from app.models.tool import ToolVisibility as DBToolVisibility
from app.schemas.tool import ToolShareInput, ToolSharePermission


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


@pytest.mark.anyio
async def test_share_tool_creates_audits_and_serializes_share():
    tool_id, owner_team_id, target_team_id, user_id = (uuid4() for _ in range(4))
    tool = SimpleNamespace(
        id=tool_id,
        team_id=owner_team_id,
        name="custom",
        display_name="Custom",
        visibility=DBToolVisibility.TEAM,
    )
    user = SimpleNamespace(id=user_id)
    share = SimpleNamespace(
        id=uuid4(),
        tool_id=tool_id,
        tool=tool,
        shared_with_team_id=target_team_id,
        shared_with_team=SimpleNamespace(name="Target"),
        permission="read_execute",
        shared_by_id=user_id,
        shared_by=SimpleNamespace(username="alice"),
        shared_at=datetime.now(UTC),
        fetch_related=AsyncMock(),
    )

    with (
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=Query(tool)),
        patch(
            "app.api.v1.endpoints.tools.Team.filter",
            return_value=Query(SimpleNamespace(id=target_team_id)),
        ),
        patch("app.api.v1.endpoints.tools.ToolShare.filter", return_value=Query(None)),
        patch(
            "app.api.v1.endpoints.tools.ToolShare.create",
            new=AsyncMock(return_value=share),
        ) as create,
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.tools.AuditLogService.log", new=AsyncMock()
        ) as audit,
    ):
        response = await share_tool(
            tool_id,
            ToolShareInput(
                team_id=target_team_id,
                permission=ToolSharePermission.READ_EXECUTE,
            ),
            SimpleNamespace(),
            user,
        )

    create.assert_awaited_once_with(
        tool_id=tool_id,
        shared_with_team_id=target_team_id,
        permission=ToolSharePermission.READ_EXECUTE,
        shared_by_id=user_id,
    )
    share.fetch_related.assert_awaited_once()
    audit.assert_awaited_once()
    assert response["data"]["shared_by_name"] == "alice"
    assert response["data"]["shared_with_team_name"] == "Target"


@pytest.mark.anyio
async def test_list_tool_shares_serializes_missing_sharer():
    tool_id, owner_team_id, target_team_id = (uuid4() for _ in range(3))
    tool = SimpleNamespace(
        id=tool_id,
        team_id=owner_team_id,
        name="custom",
        display_name="Custom",
        visibility=DBToolVisibility.TEAM,
    )
    share = SimpleNamespace(
        id=uuid4(),
        tool_id=tool_id,
        tool=tool,
        shared_with_team_id=target_team_id,
        shared_with_team=SimpleNamespace(name="Target"),
        permission="read_only",
        shared_by_id=None,
        shared_by=None,
        shared_at=datetime.now(UTC),
    )

    with (
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=Query(tool)),
        patch(
            "app.api.v1.endpoints.tools.ToolShare.filter",
            return_value=Query([share]),
        ),
        patch(
            "app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()
        ) as access,
    ):
        response = await list_tool_shares(tool_id, SimpleNamespace())

    access.assert_awaited_once()
    assert response["data"]["total"] == 1
    assert response["data"]["shares"][0]["shared_by_name"] == ""

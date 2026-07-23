from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.tools import get_tool_config, list_tool_shares, share_tool
from app.schemas.response import BusinessError, ResponseCode
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


def config(team_id):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        tool_name="web_search",
        team_id=team_id,
        credentials={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
async def test_get_tool_config_creates_builtin_team_default():
    team_id = uuid4()
    created = config(team_id)
    user = SimpleNamespace()

    with (
        patch(
            "app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()
        ) as access,
        patch("app.models.tool_config.ToolConfig.filter", return_value=Query(None)),
        patch(
            "app.models.tool_config.ToolConfig.create",
            new=AsyncMock(return_value=created),
        ) as create,
        patch(
            "app.api.v1.endpoints.tools.tool_registry.get_tool",
            return_value=object(),
        ),
    ):
        response = await get_tool_config(
            "web_search", team_id=team_id, current_user=user
        )

    access.assert_awaited_once_with(team_id, user)
    create.assert_awaited_once_with(
        tool_name="web_search", team_id=team_id, credentials={}
    )
    assert response["data"]["tool_name"] == "web_search"

    global_config = config(None)
    with patch(
        "app.models.tool_config.ToolConfig.filter", return_value=Query(global_config)
    ):
        response = await get_tool_config(
            "web_search",
            team_id=None,
            current_user=SimpleNamespace(is_superuser=True),
        )

    assert response["data"]["team_id"] is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("team_id", "is_superuser"),
    [(uuid4(), False), (None, True), (None, False)],
)
async def test_get_tool_config_rejects_missing_or_unauthorized(team_id, is_superuser):
    with (
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.models.tool_config.ToolConfig.filter", return_value=Query(None)),
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        pytest.raises(BusinessError) as error,
    ):
        await get_tool_config(
            "missing",
            team_id=team_id,
            current_user=SimpleNamespace(is_superuser=is_superuser),
        )

    expected = (
        ResponseCode.PERMISSION_DENIED
        if team_id is None and not is_superuser
        else ResponseCode.NOT_FOUND
    )
    assert error.value.code == expected


@pytest.mark.anyio
async def test_share_tool_creates_audits_and_serializes_share():
    tool_id, owner_team_id, target_team_id, user_id = (uuid4() for _ in range(4))
    tool = SimpleNamespace(
        id=tool_id, team_id=owner_team_id, name="custom", display_name="Custom"
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
        id=tool_id, team_id=owner_team_id, name="custom", display_name="Custom"
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

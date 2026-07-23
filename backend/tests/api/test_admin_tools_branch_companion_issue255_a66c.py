from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools
from app.schemas.tool import ToolExecuteRequest


class _Query:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("team_config", "global_config", "expected_credentials"),
    [
        (SimpleNamespace(credentials={"token": "team"}), None, {"token": "team"}),
        (None, SimpleNamespace(credentials={"token": "global"}), {"token": "global"}),
        (None, None, {}),
    ],
)
async def test_builtin_tool_credential_fallbacks(
    team_config, global_config, expected_credentials
):
    query_results = [_Query(team_config), _Query(global_config)]
    execute = AsyncMock(return_value={"ok": True})

    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch(
            "app.models.tool_config.ToolConfig.filter",
            side_effect=query_results,
        ) as filter_config,
        patch.object(tools.tool_registry, "execute", execute),
    ):
        response = await tools.test_tool(
            ToolExecuteRequest(name="builtin", arguments={"x": 1}),
            team_id=uuid4(),
            current_user=SimpleNamespace(),
        )

    execute.assert_awaited_once_with(
        "builtin", {"x": 1}, credentials=expected_credentials
    )
    assert response["data"].success is True
    assert filter_config.call_count == (1 if team_config else 2)


@pytest.mark.anyio
async def test_builtin_tool_execution_failure_returns_resolved_error():
    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch("app.models.tool_config.ToolConfig.filter", return_value=_Query(None)),
        patch.object(
            tools.tool_registry,
            "execute",
            AsyncMock(side_effect=RuntimeError("provider secret")),
        ),
        patch.object(
            tools, "resolve_user_visible_error", Mock(return_value="safe failure")
        ) as resolve,
    ):
        response = await tools.test_tool(
            ToolExecuteRequest(name="builtin", arguments={}),
            current_user=SimpleNamespace(),
        )

    resolve.assert_called_once_with("provider secret")
    assert response["data"].success is False
    assert response["data"].error == "safe failure"

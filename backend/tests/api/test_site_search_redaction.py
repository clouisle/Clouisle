from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools as admin
from app.api.v1.endpoints import tools as platform
from app.models.tool_config import ToolConfig


class ConfigQuery:
    def __init__(self, rows):
        self.rows = rows

    async def all(self):
        return self.rows


@pytest.mark.anyio
@pytest.mark.parametrize("module", [admin, platform])
async def test_generic_config_list_does_not_expose_search_ciphertext_or_archive(
    module, monkeypatch
):
    now = datetime.now(UTC)
    rows = [
        SimpleNamespace(
            id=uuid4(),
            tool_name=name,
            team_id=None,
            credentials=credentials,
            created_at=now,
            updated_at=now,
        )
        for name, credentials in [
            (
                "web_search",
                {
                    "TAVILY_API_KEY": "enc:v1:private",
                    "_legacy_credentials": "enc:v1:archive",
                },
            ),
            ("weather", {"key": "unchanged-other-tool"}),
        ]
    ]
    monkeypatch.setattr(ToolConfig, "filter", lambda **kwargs: ConfigQuery(rows))
    response = await module.list_tool_configs(
        team_id=None, current_user=SimpleNamespace(is_superuser=True)
    )
    assert [item["tool_name"] for item in response["data"]] == ["weather"]
    assert response["data"][0]["credentials"] == {"key": "unchanged-other-tool"}

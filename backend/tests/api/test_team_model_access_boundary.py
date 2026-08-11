from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.team_models import get_team_available_models
from app.schemas.response import BusinessError


class AuthorizationQuery:
    def __init__(self, rows):
        self.rows = rows

    def prefetch_related(self, *_args):
        return self

    async def order_by(self, *_args):
        return self.rows


@pytest.mark.asyncio
async def test_available_models_denies_non_member_before_inventory_lookup():
    team = SimpleNamespace(id=uuid4())
    current_user = SimpleNamespace(is_superuser=False)
    team_filter = Mock()
    team_filter.return_value.first = AsyncMock(return_value=team)
    membership_filter = Mock()
    membership_filter.return_value.first = AsyncMock(return_value=None)

    with (
        patch("app.api.v1.endpoints.team_models.Team.filter", team_filter),
        patch("app.api.v1.endpoints.team_models.TeamMember.filter", membership_filter),
        patch("app.api.v1.endpoints.team_models.TeamModel.filter") as model_filter,
    ):
        with pytest.raises(BusinessError) as exc_info:
            await get_team_available_models(team.id, current_user=current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.msg_key == "not_team_member"
    model_filter.assert_not_called()


@pytest.mark.asyncio
async def test_available_models_returns_enabled_grants_to_member():
    team = SimpleNamespace(id=uuid4())
    current_user = SimpleNamespace(is_superuser=False)
    model = SimpleNamespace(
        id=uuid4(),
        name="Team model",
        provider="openai",
        provider_display_name=None,
        model_id="gpt-4.1",
        model_type="llm",
    )
    team_filter = Mock()
    team_filter.return_value.first = AsyncMock(return_value=team)
    membership_filter = Mock()
    membership_filter.return_value.first = AsyncMock(return_value=object())
    model_filter = Mock(return_value=AuthorizationQuery([SimpleNamespace(model=model)]))

    with (
        patch("app.api.v1.endpoints.team_models.Team.filter", team_filter),
        patch("app.api.v1.endpoints.team_models.TeamMember.filter", membership_filter),
        patch("app.api.v1.endpoints.team_models.TeamModel.filter", model_filter),
    ):
        response = await get_team_available_models(team.id, current_user=current_user)

    assert response["data"] == [
        {
            "id": model.id,
            "name": "Team model",
            "provider": "openai",
            "provider_display_name": None,
            "model_id": "gpt-4.1",
            "model_type": "llm",
        }
    ]
    model_filter.assert_called_once_with(
        team_id=team.id,
        is_enabled=True,
        model__is_enabled=True,
    )

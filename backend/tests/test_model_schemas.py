from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.model import (
    ModelBrief,
    ModelCreate,
    ModelProvider,
    ModelResponse,
    ModelType,
    ModelUpdate,
    TeamModelBatchCreate,
    TeamModelCreate,
    TeamModelQuotaStatus,
    TeamModelResponse,
)


def test_model_create_parses_enums_prices_and_defaults():
    model = ModelCreate(
        name="GPT",
        provider="openai",
        model_id="gpt-4o",
        model_type="chat",
        input_price="0.123456",
        output_price=Decimal("0.654321"),
    )

    assert model.provider is ModelProvider.OPENAI
    assert model.model_type is ModelType.CHAT
    assert model.input_price == Decimal("0.123456")
    assert model.output_price == Decimal("0.654321")
    assert model.is_enabled is True
    assert model.is_default is False
    assert model.sort_order == 0


@pytest.mark.parametrize(
    "schema,values",
    [
        (
            ModelCreate,
            {"name": "", "provider": "openai", "model_id": "gpt", "model_type": "chat"},
        ),
        (
            ModelCreate,
            {
                "name": "GPT",
                "provider": "unknown",
                "model_id": "gpt",
                "model_type": "chat",
            },
        ),
        (
            ModelCreate,
            {
                "name": "GPT",
                "provider": "openai",
                "model_id": "gpt",
                "model_type": "chat",
                "input_price": "-0.1",
            },
        ),
        (
            ModelCreate,
            {
                "name": "GPT",
                "provider": "openai",
                "model_id": "gpt",
                "model_type": "chat",
                "output_price": "0.1234567",
            },
        ),
        (ModelUpdate, {"context_length": 0}),
        (TeamModelCreate, {"model_id": uuid4(), "daily_token_limit": -1}),
        (TeamModelBatchCreate, {"model_ids": []}),
    ],
)
def test_model_schema_constraints_reject_invalid_values(schema, values):
    with pytest.raises(ValidationError):
        schema(**values)


def test_model_update_tracks_explicit_null_fields():
    omitted = ModelUpdate()
    clear_api_key = ModelUpdate(api_key=None)

    assert omitted.model_fields_set == set()
    assert clear_api_key.model_fields_set == {"api_key"}
    assert clear_api_key.api_key is None


def test_model_responses_read_attributes_and_keep_quota_defaults():
    model_id = uuid4()
    now = datetime(2026, 1, 1)
    response = ModelResponse.model_validate(
        SimpleNamespace(
            id=model_id,
            name="GPT",
            provider="openai",
            model_id="gpt-4o",
            model_type="chat",
            has_api_key=True,
            is_enabled=True,
            is_default=False,
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    team_response = TeamModelResponse.model_validate(
        SimpleNamespace(
            id=uuid4(),
            team_id=uuid4(),
            model_id=model_id,
            model=SimpleNamespace(
                id=model_id,
                name="GPT",
                provider="openai",
                model_id="gpt-4o",
                model_type="chat",
            ),
            is_enabled=True,
            priority=0,
            created_at=now,
            updated_at=now,
        )
    )
    quota = TeamModelQuotaStatus(
        model_id=model_id,
        model_name="GPT",
        model_type="chat",
        is_enabled=True,
    )

    assert response.id == model_id
    assert isinstance(team_response.model, ModelBrief)
    assert team_response.daily_tokens_used == 0
    assert quota.is_quota_exceeded is False
    assert quota.daily_token_percent is None

import pytest
from pydantic import ValidationError

from app.schemas.api_key import APIKeyCreate, APIKeyUpdate
from app.schemas.workflow import WorkflowUpdate


def test_api_key_create_accepts_limit_boundaries_and_defaults() -> None:
    request = APIKeyCreate(name="k" * 100, rate_limit=0)

    assert request.name == "k" * 100
    assert request.rate_limit == 0
    assert request.scopes == ["chat"]
    assert request.agent_ids == []
    assert request.workflow_ids == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "k" * 101},
        {"name": "valid", "rate_limit": -1},
    ],
)
def test_api_key_create_rejects_invalid_name_and_rate_limit(payload: dict) -> None:
    with pytest.raises(ValidationError):
        APIKeyCreate(**payload)


def test_api_key_update_keeps_fields_optional_but_rejects_negative_limit() -> None:
    assert APIKeyUpdate().model_dump(exclude_unset=True) == {}

    with pytest.raises(ValidationError):
        APIKeyUpdate(rate_limit=-1)


def test_workflow_update_run_page_config_none():
    update = WorkflowUpdate(run_page_config=None)
    assert update.run_page_config is None


def test_workflow_update_run_page_config_valid_modes():
    update = WorkflowUpdate(run_page_config={"presentation_mode": "simple"})
    assert update.run_page_config["presentation_mode"] == "simple"
    update = WorkflowUpdate(run_page_config={"presentation_mode": "result_first"})
    assert update.run_page_config["presentation_mode"] == "result_first"


def test_workflow_update_run_page_config_defaults_to_simple():
    update = WorkflowUpdate(run_page_config={"custom": True})
    assert update.run_page_config["presentation_mode"] == "simple"
    assert update.run_page_config["custom"] is True


def test_workflow_update_run_page_config_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        WorkflowUpdate(run_page_config={"presentation_mode": "fancy"})

"""Strict input validation for the site web search configuration API."""

import pytest
from pydantic import ValidationError

from app.schemas.web_search import (
    SECRET_MAX_LENGTH,
    WebSearchConfigUpdate,
    WebSearchTestInput,
)


def _config(**overrides):
    values = {
        "default_engine": "tavily",
        "tavily_enabled": True,
        "bocha_enabled": False,
    }
    values.update(overrides)
    return values


def test_config_update_forbids_unknown_fields_and_credentials():
    with pytest.raises(ValidationError):
        WebSearchConfigUpdate(**_config(team_id="team-1"))


@pytest.mark.parametrize("engine", ["auto", "searxng", "google", ""])
def test_config_update_rejects_unsupported_default_engines(engine):
    with pytest.raises(ValidationError):
        WebSearchConfigUpdate(**_config(default_engine=engine))


def test_config_update_strips_secret_and_treats_blank_as_clear():
    data = WebSearchConfigUpdate(
        **_config(tavily_api_key="  tvly-secret  ", bocha_api_key="   ")
    )

    assert data.tavily_api_key == "tvly-secret"
    assert data.bocha_api_key == ""


def test_config_update_bounds_secret_length():
    with pytest.raises(ValidationError):
        WebSearchConfigUpdate(**_config(tavily_api_key="x" * (SECRET_MAX_LENGTH + 1)))


def test_config_update_requires_explicit_flags():
    with pytest.raises(ValidationError):
        WebSearchConfigUpdate(default_engine="tavily")


def test_test_input_defaults_to_auto_and_strips_query():
    data = WebSearchTestInput(query="  site search status  ")

    assert data.engine == "auto"
    assert data.query == "site search status"


@pytest.mark.parametrize("query", ["", "   ", "x" * 1001])
def test_test_input_bounds_query(query):
    with pytest.raises(ValidationError):
        WebSearchTestInput(query=query)


@pytest.mark.parametrize("engine", ["auto", "tavily", "bocha"])
def test_test_input_accepts_only_site_engines(engine):
    assert WebSearchTestInput(query="q", engine=engine).engine == engine


@pytest.mark.parametrize("engine", ["searxng", "google"])
def test_test_input_rejects_other_engines(engine):
    with pytest.raises(ValidationError):
        WebSearchTestInput(query="q", engine=engine)


def test_test_input_forbids_extra_fields():
    with pytest.raises(ValidationError):
        WebSearchTestInput(query="q", base_url="https://example.test")

import pytest
from pydantic import ValidationError

from app.schemas.integration import IntegrationCreate, IntegrationUpdate


def integration_data(**overrides):
    return {
        "name": "company_sso-1",
        "provider_type": "oidc",
        "display_name": "Company SSO",
        "config": {},
        **overrides,
    }


@pytest.mark.parametrize(
    "icon_url",
    [None, "", "http://cdn.example/icon.svg", "https://cdn.example/icon.svg"],
)
def test_create_accepts_valid_name_and_icon_url(icon_url):
    integration = IntegrationCreate(**integration_data(icon_url=icon_url))
    assert integration.name == "company_sso-1"
    assert integration.icon_url == icon_url


@pytest.mark.parametrize(
    "name", ["", "1company", "Company", "company sso", "company.sso"]
)
@pytest.mark.parametrize("schema", [IntegrationCreate, IntegrationUpdate])
def test_integration_schemas_reject_invalid_names(schema, name):
    with pytest.raises(ValidationError):
        schema(**integration_data(name=name))


@pytest.mark.parametrize(
    "icon_url", ["/icon.svg", "ftp://cdn.example/icon.svg", "javascript:alert(1)"]
)
def test_update_rejects_non_http_icon_url(icon_url):
    with pytest.raises(ValidationError, match="sso_invalid_icon_url"):
        IntegrationUpdate(icon_url=icon_url)


@pytest.mark.parametrize(
    "data",
    [
        {"provider_type": "unknown"},
        {"provider_type": "feishu", "enabled_capabilities": ["user_login"]},
        {"enabled_capabilities": ["directory_sync"]},
        {"config": {"client_secret": "secret"}},
        {"credentials": {"unsupported": "secret"}},
    ],
)
def test_create_rejects_unsupported_capabilities_types_and_secret_fields(data):
    with pytest.raises(ValidationError):
        IntegrationCreate(**integration_data(**data))


def test_update_allows_omitted_name():
    assert IntegrationUpdate().name is None


def test_update_accepts_explicit_none_name_for_endpoint_validation():
    assert IntegrationUpdate(name=None).name is None


def test_login_policy_default_role_serializes_as_json_uuid():
    role_id = "550e8400-e29b-41d4-a716-446655440000"
    data = IntegrationCreate(
        **integration_data(login_config={"default_role_id": role_id})
    )
    assert data.model_dump(mode="json")["login_config"]["default_role_id"] == role_id

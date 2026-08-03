import pytest
from pydantic import ValidationError

from app.schemas.sso import SSOProviderCreate, SSOProviderUpdate


def provider_data(**overrides):
    return {
        "name": "company_sso-1",
        "protocol": "oidc",
        "display_name": "Company SSO",
        "config": {},
        **overrides,
    }


@pytest.mark.parametrize(
    "icon_url",
    [None, "", "http://cdn.example/icon.svg", "https://cdn.example/icon.svg"],
)
def test_create_accepts_valid_provider_name_and_icon_url(icon_url):
    provider = SSOProviderCreate(**provider_data(icon_url=icon_url))

    assert provider.name == "company_sso-1"
    assert provider.icon_url == icon_url


@pytest.mark.parametrize(
    "name", ["", "1company", "Company", "company sso", "company.sso"]
)
@pytest.mark.parametrize("schema", [SSOProviderCreate, SSOProviderUpdate])
def test_provider_schemas_reject_invalid_names(schema, name):
    with pytest.raises(ValidationError, match="sso_invalid_provider_name"):
        schema(**provider_data(name=name))


@pytest.mark.parametrize(
    "icon_url", ["/icon.svg", "ftp://cdn.example/icon.svg", "javascript:alert(1)"]
)
def test_update_rejects_non_http_icon_url(icon_url):
    with pytest.raises(ValidationError, match="sso_invalid_icon_url"):
        SSOProviderUpdate(icon_url=icon_url)


def test_update_allows_omitted_name():
    assert SSOProviderUpdate().name is None


def test_update_accepts_explicit_none_name():
    assert SSOProviderUpdate(name=None).name is None

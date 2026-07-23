from types import SimpleNamespace

import pytest

from app.schemas.response import BusinessError, ResponseCode
from app.services import sso as sso_service


class _ConnectionQuery:
    def prefetch_related(self, *_args: object) -> "_ConnectionQuery":
        return self

    async def first(self) -> None:
        return None


def test_get_provider_instance_rejects_unsupported_protocol() -> None:
    provider = SimpleNamespace(protocol="ldap")

    with pytest.raises(ValueError, match="Unsupported protocol: ldap"):
        sso_service.SSOService.get_provider_instance(provider)


@pytest.mark.asyncio
async def test_find_or_create_user_rejects_registration_when_signup_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object = None) -> object:
        return {"sso_match_by_email": False, "sso_auto_create_users": False}.get(
            key, default
        )

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    provider = SimpleNamespace(allow_signup=False)

    with pytest.raises(BusinessError) as exc_info:
        await sso_service.SSOService.find_or_create_user(
            provider=provider,
            provider_user_id="provider-user-id",
            user_info={"email": "alice@example.com"},
        )

    assert exc_info.value.code == ResponseCode.SSO_REGISTRATION_DISABLED
    assert exc_info.value.msg_key == "sso_registration_disabled"

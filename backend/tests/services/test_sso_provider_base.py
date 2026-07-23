from types import SimpleNamespace
from typing import Any

from app.sso.providers.base import BaseSSOProvider


class StubSSOProvider(BaseSSOProvider):
    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs: Any
    ) -> str:
        return redirect_uri

    async def handle_callback(
        self, callback_data: dict[str, Any], redirect_uri: str, **kwargs: Any
    ) -> dict[str, Any]:
        return callback_data


def make_provider(mapping: dict[str, str]) -> StubSSOProvider:
    provider = SimpleNamespace(config={"client_id": "test"}, attribute_mapping=mapping)
    return StubSSOProvider(provider)


def test_maps_dotted_and_jsonpath_attributes() -> None:
    provider = make_provider(
        {
            "email": "profile.email",
            "primary_email": "$.emails[0].value",
            "provider_user_id": "id",
        }
    )

    assert provider.config == {"client_id": "test"}
    assert provider.map_user_attributes(
        {
            "id": "user-1",
            "profile": {"email": "alice@example.com"},
            "emails": [{"value": "primary@example.com"}],
        }
    ) == {
        "email": "alice@example.com",
        "primary_email": "primary@example.com",
        "provider_user_id": "user-1",
    }


def test_omits_missing_falsey_and_broken_nested_attributes() -> None:
    provider = make_provider(
        {
            "missing": "profile.name",
            "empty": "profile.email",
            "broken": "subject.id",
            "no_match": "$.emails[0].value",
        }
    )

    assert (
        provider.map_user_attributes(
            {"profile": {"email": ""}, "subject": "not-a-dict", "emails": []}
        )
        == {}
    )


def test_invalid_jsonpath_is_ignored() -> None:
    provider = make_provider({"email": "$.["})

    assert provider.map_user_attributes({"email": "alice@example.com"}) == {}

from types import SimpleNamespace
from typing import Any

from app.sso.providers.base import BaseSSOProvider


class Provider(BaseSSOProvider):
    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs: Any
    ) -> str:
        return redirect_uri

    async def handle_callback(
        self, callback_data: dict[str, Any], redirect_uri: str, **kwargs: Any
    ) -> dict[str, Any]:
        return callback_data


def provider(mapping: dict[str, str]) -> Provider:
    return Provider(
        SimpleNamespace(config={"client_id": "test"}, attribute_mapping=mapping)
    )


def test_maps_truthy_nested_values_and_ignores_unusable_paths() -> None:
    instance = provider(
        {
            "email": "profile.email",
            "primary_email": "$.emails[0].value",
            "missing_jsonpath": "$.emails[1].value",
            "invalid_jsonpath": "$.[",
            "missing_nested": "profile.name",
            "broken_nested": "subject.id",
            "empty": "profile.empty",
        }
    )

    assert instance.config == {"client_id": "test"}
    assert instance.map_user_attributes(
        {
            "profile": {"email": "alice@example.com", "empty": ""},
            "emails": [{"value": "primary@example.com"}],
            "subject": "not-a-dict",
        }
    ) == {
        "email": "alice@example.com",
        "primary_email": "primary@example.com",
    }

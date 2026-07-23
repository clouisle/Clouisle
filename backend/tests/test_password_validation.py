import pytest

from app.core import password as password_module


@pytest.mark.asyncio
async def test_validate_password_accepts_exact_minimum_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object) -> object:
        return {
            "min_password_length": 8,
            "require_uppercase": True,
            "require_number": True,
            "require_special_char": True,
        }.get(key, default)

    monkeypatch.setattr(password_module.SiteSetting, "get_value", get_value)

    assert await password_module.validate_password("Abcdef1!") == (True, [])


@pytest.mark.asyncio
async def test_validate_password_collects_all_policy_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object) -> object:
        return {
            "min_password_length": 8,
            "require_uppercase": True,
            "require_number": True,
            "require_special_char": True,
        }.get(key, default)

    monkeypatch.setattr(password_module.SiteSetting, "get_value", get_value)

    assert await password_module.validate_password("short") == (
        False,
        [
            "password_min_length:8",
            "password_require_uppercase",
            "password_require_number",
            "password_require_special",
        ],
    )


@pytest.mark.asyncio
async def test_validate_password_rejects_recent_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.password_expiration import PasswordExpirationService

    async def get_value(key: str, default: object) -> object:
        return {
            "min_password_length": 8,
            "require_uppercase": True,
            "require_number": True,
            "require_special_char": False,
        }.get(key, default)

    async def check_password_history(user: object, new_password: str) -> bool:
        assert user is user_marker
        assert new_password == "Abcdef12"
        return True

    user_marker = object()
    monkeypatch.setattr(password_module.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        PasswordExpirationService, "check_password_history", check_password_history
    )

    assert await password_module.validate_password("Abcdef12", user_marker) == (
        False,
        ["password_recently_used"],
    )


def test_translate_password_validation_errors_formats_length_and_generic_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def translate(key: str, **kwargs: str) -> str:
        calls.append((key, kwargs))
        return f"{key}:{kwargs.get('length', '')}"

    monkeypatch.setattr(password_module, "t", translate)

    assert password_module.translate_password_validation_errors(
        ["password_min_length:12", "password_require_number"]
    ) == ["password_min_length:12", "password_require_number:"]
    assert calls == [
        ("password_min_length", {"length": "12"}),
        ("password_require_number", {}),
    ]


def test_get_password_requirements_sync_includes_only_enabled_rules() -> None:
    assert password_module.get_password_requirements_sync(12, False, True, True) == [
        "至少 12 个字符",
        "至少一个数字",
        "至少一个特殊字符",
    ]

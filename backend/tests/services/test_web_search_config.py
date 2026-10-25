"""Site-managed web search configuration storage and runtime resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.schemas.response import BusinessError
from app.schemas.web_search import WebSearchConfigUpdate
from app.services import web_search_config as subject


def _encrypted(value: str) -> str:
    return f"{subject.ENCRYPTED_PREFIX}{encrypt_secret(value)}"


class FakeRow:
    def __init__(self, credentials):
        self.credentials = credentials
        self.save_kwargs = None

    async def save(self, **kwargs):
        self.save_kwargs = kwargs


def _update(**overrides) -> WebSearchConfigUpdate:
    values = {
        "default_engine": "tavily",
        "tavily_enabled": True,
        "bocha_enabled": False,
    }
    values.update(overrides)
    return WebSearchConfigUpdate(**values)


def _install_save(monkeypatch, row, *, created=None):
    class Transaction:
        async def __aenter__(self):
            return SimpleNamespace(capabilities=SimpleNamespace(dialect="postgresql"))

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(subject, "in_transaction", lambda: Transaction())
    monkeypatch.setattr(subject, "_load_locked_config", AsyncMock(return_value=row))
    if row is None:
        fake_model = SimpleNamespace(create=AsyncMock(return_value=created))
        monkeypatch.setattr(subject, "ToolConfig", fake_model)
        return fake_model
    return None


@pytest.mark.anyio
async def test_save_preserves_omitted_ciphertext_and_reserved_fields(monkeypatch):
    tavily_ciphertext = _encrypted("tvly-old")
    legacy_ciphertext = _encrypted('[{"source": "team"}]')
    row = FakeRow(
        {
            "default_engine": "tavily",
            "tavily_enabled": "true",
            "bocha_enabled": "false",
            "TAVILY_API_KEY": tavily_ciphertext,
            "_legacy_credentials": legacy_ciphertext,
            "_site_config_version": "1",
            "custom_key": "kept",
        }
    )
    _install_save(monkeypatch, row)

    result = await subject.save_web_search_config(_update())

    assert row.credentials["TAVILY_API_KEY"] == tavily_ciphertext
    assert (
        decrypt_secret(
            row.credentials["TAVILY_API_KEY"][len(subject.ENCRYPTED_PREFIX) :]
        )
        == "tvly-old"
    )
    assert row.credentials["_legacy_credentials"] == legacy_ciphertext
    assert row.credentials["_site_config_version"] == subject.SITE_CONFIG_VERSION
    assert row.credentials["custom_key"] == "kept"
    assert row.save_kwargs is not None
    assert result.tavily_api_key_configured is True
    assert result.tavily_enabled is True
    assert result.legacy_credentials_present is True
    assert "tvly-old" not in result.model_dump_json()


@pytest.mark.anyio
async def test_save_replaces_secret_with_ciphertext(monkeypatch):
    row = FakeRow(
        {
            "default_engine": "tavily",
            "tavily_enabled": "true",
            "bocha_enabled": "false",
            "TAVILY_API_KEY": _encrypted("tvly-old"),
        }
    )
    _install_save(monkeypatch, row)

    await subject.save_web_search_config(_update(tavily_api_key="  tvly-new  "))

    stored = row.credentials["TAVILY_API_KEY"]
    assert stored.startswith(subject.ENCRYPTED_PREFIX)
    assert decrypt_secret(stored[len(subject.ENCRYPTED_PREFIX) :]) == "tvly-new"
    assert "tvly-new" not in stored.replace(subject.ENCRYPTED_PREFIX, "", 1)


@pytest.mark.anyio
async def test_save_clears_secret_with_empty_string(monkeypatch):
    row = FakeRow(
        {
            "default_engine": "bocha",
            "tavily_enabled": "true",
            "bocha_enabled": "true",
            "TAVILY_API_KEY": _encrypted("tvly-old"),
            "BOCHA_API_KEY": _encrypted("bocha-key"),
        }
    )
    _install_save(monkeypatch, row)

    result = await subject.save_web_search_config(
        _update(
            default_engine="bocha",
            tavily_enabled=False,
            bocha_enabled=True,
            tavily_api_key="",
        )
    )

    assert "TAVILY_API_KEY" not in row.credentials
    assert result.tavily_api_key_configured is False
    assert result.bocha_api_key_configured is True


@pytest.mark.anyio
async def test_save_allows_admin_shutoff(monkeypatch):
    row = FakeRow({"default_engine": "tavily"})
    _install_save(monkeypatch, row)

    result = await subject.save_web_search_config(
        _update(tavily_enabled=False, bocha_enabled=False)
    )

    assert row.credentials["tavily_enabled"] == "false"
    assert row.credentials["bocha_enabled"] == "false"
    assert result.tavily_enabled is False
    assert result.bocha_enabled is False


@pytest.mark.anyio
async def test_save_rejects_enabled_provider_without_secret(monkeypatch):
    row = FakeRow({"default_engine": "tavily"})
    _install_save(monkeypatch, row)

    with pytest.raises(BusinessError) as error:
        await subject.save_web_search_config(_update())

    assert error.value.msg_key == "web_search_engine_not_configured"
    assert error.value.kwargs == {"engine": "tavily"}
    assert row.save_kwargs is None


@pytest.mark.anyio
async def test_save_rejects_default_provider_that_is_disabled(monkeypatch):
    row = FakeRow({"default_engine": "tavily"})
    _install_save(monkeypatch, row)

    with pytest.raises(BusinessError) as error:
        await subject.save_web_search_config(
            _update(
                default_engine="tavily",
                tavily_enabled=False,
                bocha_enabled=True,
                bocha_api_key="bocha-key",
            )
        )

    assert error.value.msg_key == "web_search_default_engine_disabled"
    assert row.save_kwargs is None


def test_validate_consistency_rejects_unknown_default_engine():
    with pytest.raises(BusinessError) as error:
        subject._validate_consistency(
            {
                "default_engine": "auto",
                "tavily_enabled": "false",
                "bocha_enabled": "false",
            }
        )

    assert error.value.msg_key == "web_search_default_engine_invalid"


@pytest.mark.anyio
async def test_save_creates_the_singleton_row_when_absent(monkeypatch):
    created = FakeRow({})
    fake_model = _install_save(monkeypatch, None, created=created)

    result = await subject.save_web_search_config(_update(tavily_api_key="tvly-new"))

    fake_model.create.assert_awaited_once()
    assert fake_model.create.await_args.kwargs["tool_name"] == "web_search"
    assert fake_model.create.await_args.kwargs["team_id"] is None
    assert created.credentials["_site_config_version"] == "1"
    assert result.tavily_api_key_configured is True


@pytest.mark.anyio
async def test_get_config_without_a_row_reports_disabled_defaults(monkeypatch):
    monkeypatch.setattr(subject, "_get_global_config", AsyncMock(return_value=None))

    result = await subject.get_web_search_config()

    assert result.model_dump() == {
        "default_engine": "tavily",
        "tavily_enabled": False,
        "bocha_enabled": False,
        "tavily_api_key_configured": False,
        "bocha_api_key_configured": False,
        "legacy_credentials_present": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("credentials", "expected_engine"),
    [
        (None, "tavily"),
        ("not-a-dict", "tavily"),
        ({"default_engine": "searxng"}, "tavily"),
        ({"default_engine": 7}, "tavily"),
    ],
)
async def test_get_config_falls_back_for_unusable_stored_values(
    monkeypatch, credentials, expected_engine
):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(return_value=SimpleNamespace(credentials=credentials)),
    )

    result = await subject.get_web_search_config()

    assert result.default_engine == expected_engine
    assert result.tavily_enabled is False


@pytest.mark.anyio
async def test_get_config_never_decrypts_or_returns_secrets(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": " BOCHA ",
                    "tavily_enabled": True,
                    "bocha_enabled": "TRUE",
                    "TAVILY_API_KEY": "garbage-not-decryptable",
                    "BOCHA_API_KEY": _encrypted("bocha-secret"),
                    "_legacy_credentials": "archive",
                }
            )
        ),
    )

    result = await subject.get_web_search_config()

    assert result.default_engine == "bocha"
    assert result.tavily_enabled is True
    assert result.bocha_enabled is True
    assert result.tavily_api_key_configured is True
    assert result.bocha_api_key_configured is True
    assert result.legacy_credentials_present is True
    assert "bocha-secret" not in result.model_dump_json()


@pytest.mark.anyio
async def test_runtime_without_config_fails_safely(monkeypatch):
    monkeypatch.setattr(subject, "_get_global_config", AsyncMock(return_value=None))

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("auto")

    assert error.value.msg_key == "web_search_not_configured"


@pytest.mark.anyio
async def test_runtime_auto_uses_the_explicit_default_not_key_availability(
    monkeypatch,
):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "bocha",
                    "tavily_enabled": "true",
                    "bocha_enabled": "true",
                    "TAVILY_API_KEY": _encrypted("tvly-secret"),
                    "BOCHA_API_KEY": _encrypted("bocha-secret"),
                }
            )
        ),
    )

    engine, config = await subject.get_web_search_runtime("auto")

    assert engine == "bocha"
    assert config == {"BOCHA_API_KEY": "bocha-secret"}


@pytest.mark.anyio
async def test_runtime_only_decrypts_the_selected_provider(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "bocha",
                    "tavily_enabled": "true",
                    "bocha_enabled": "true",
                    # Unreadable Tavily material must not break a Bocha run.
                    "TAVILY_API_KEY": "legacy-plaintext",
                    "BOCHA_API_KEY": _encrypted("bocha-secret"),
                }
            )
        ),
    )

    assert await subject.get_web_search_runtime() == (
        "bocha",
        {"BOCHA_API_KEY": "bocha-secret"},
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("requested", "expected"), [("  Tavily ", "tavily"), (None, "tavily")]
)
async def test_runtime_normalizes_explicit_engine_requests(
    monkeypatch, requested, expected
):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "tavily",
                    "tavily_enabled": "true",
                    "TAVILY_API_KEY": _encrypted("tvly-secret"),
                }
            )
        ),
    )

    engine, config = await subject.get_web_search_runtime(requested)

    assert engine == expected
    assert config == {"TAVILY_API_KEY": "tvly-secret"}


@pytest.mark.anyio
async def test_runtime_rejects_corrupt_default_engine(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "tavily_enabled": "true",
                }
            )
        ),
    )

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("auto")

    assert error.value.msg_key == "web_search_default_engine_invalid"


@pytest.mark.anyio
async def test_runtime_rejects_unsupported_explicit_engine(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(return_value=SimpleNamespace(credentials={})),
    )

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("google")

    assert error.value.msg_key == "web_search_unsupported_engine"
    assert error.value.kwargs == {"search_engine": "google"}


@pytest.mark.anyio
async def test_runtime_rejects_disabled_provider(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "tavily",
                    "tavily_enabled": "false",
                }
            )
        ),
    )

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("tavily")

    assert error.value.msg_key == "web_search_engine_disabled"
    assert error.value.kwargs == {"engine": "tavily"}


@pytest.mark.anyio
async def test_runtime_rejects_enabled_provider_without_secret(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "tavily",
                    "tavily_enabled": "true",
                }
            )
        ),
    )

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("auto")

    assert error.value.msg_key == "web_search_engine_not_configured"
    assert error.value.kwargs == {"engine": "tavily"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "stored_secret",
    ["plain-legacy-key", "enc:v1:not-a-fernet-token"],
)
async def test_runtime_fails_safe_for_unreadable_credentials(
    monkeypatch, stored_secret
):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "tavily",
                    "tavily_enabled": "true",
                    "TAVILY_API_KEY": stored_secret,
                }
            )
        ),
    )

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("tavily")

    assert error.value.msg_key == "web_search_credentials_unreadable"
    assert stored_secret not in str(error.value)


class FakeQuery:
    def __init__(self, row):
        self.row = row
        self.lock_requested = False
        self.using = None

    def using_db(self, conn):
        self.using = conn
        return self

    def select_for_update(self):
        self.lock_requested = True
        return self

    async def first(self):
        return self.row


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("dialect", "locks"),
    [("postgresql", True), ("sqlite", False)],
)
async def test_load_locked_config_uses_dialect_appropriate_locking(
    monkeypatch, dialect, locks
):
    row = FakeRow({})
    query = FakeQuery(row)
    monkeypatch.setattr(
        subject, "ToolConfig", SimpleNamespace(filter=lambda **_kwargs: query)
    )
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect=dialect),
        execute_query=AsyncMock(),
    )

    assert await subject._load_locked_config(conn) is row
    assert query.lock_requested is locks
    assert conn.execute_query.await_count == (1 if locks else 0)
    if locks:
        assert str(subject.SAVE_LOCK_KEY) in conn.execute_query.await_args.args[0]

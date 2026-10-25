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
        "searxng_enabled": False,
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
        "searxng_enabled": False,
        "tavily_api_key_configured": False,
        "bocha_api_key_configured": False,
        "searxng_base_url": "",
        "searxng_auth_token_configured": False,
        "legacy_credentials_present": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("credentials", "expected_engine"),
    [
        (None, "tavily"),
        ("not-a-dict", "tavily"),
        ({"default_engine": "google"}, "tavily"),
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
                    "default_engine": "google",
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


SEARXNG_BASE = "https://search.example.test/searx"


def _install_searxng_validation(monkeypatch, *, error=None):
    validation = (
        AsyncMock(side_effect=error)
        if error is not None
        else AsyncMock(side_effect=lambda value: value)
    )
    monkeypatch.setattr(subject, "validate_searxng_base_url", validation)
    return validation


def _searxng_update(**overrides):
    values = {
        "default_engine": "searxng",
        "tavily_enabled": False,
        "bocha_enabled": False,
        "searxng_enabled": True,
        "searxng_base_url": SEARXNG_BASE,
    }
    values.update(overrides)
    return WebSearchConfigUpdate(**values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://search.example.test/searx/", SEARXNG_BASE),
        ("https://search.example.test", "https://search.example.test"),
        ("HTTPS://search.example.test/searx", SEARXNG_BASE),
        ("http://10.0.0.10:8080/searx", "http://10.0.0.10:8080/searx"),
    ],
)
def test_normalize_searxng_base_url_preserves_subpaths(raw, expected):
    assert subject.normalize_searxng_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ftp://search.example.test/searx",
        "https://user:pass@search.example.test/searx",
        "https://@search.example.test/searx",
        "https://search.example.test/searx\\evil",
        "https://search.example.test/searx\n/evil",
        "https://search.example.test/searx?token=x",
        "https://search.example.test/searx#frag",
        "https://search.example.test/search",
        "https://search.example.test/searx/search/",
        "https://search.example.test:bad/searx",
        "no-host",
    ],
)
def test_normalize_searxng_base_url_rejects_unsafe_shapes(raw):
    with pytest.raises(BusinessError) as error:
        subject.normalize_searxng_base_url(raw)
    assert error.value.msg_key == "web_search_searxng_base_url_invalid"


@pytest.mark.anyio
async def test_validate_searxng_base_url_delegates_to_ssrf_policy(monkeypatch):
    ensure = AsyncMock()
    monkeypatch.setattr(subject, "ensure_external_http_url_allowed", ensure)

    result = await subject.validate_searxng_base_url(f" {SEARXNG_BASE}/ ")

    assert result == SEARXNG_BASE
    ensure.assert_awaited_once_with(SEARXNG_BASE)


@pytest.mark.anyio
async def test_save_searxng_normalizes_and_stores_base_url(monkeypatch):
    row = FakeRow({})
    _install_save(monkeypatch, row)
    validation = _install_searxng_validation(monkeypatch)

    result = await subject.save_web_search_config(
        _searxng_update(searxng_base_url=f" {SEARXNG_BASE}/ ")
    )

    assert row.credentials["SEARXNG_BASE_URL"] == SEARXNG_BASE
    assert row.credentials["searxng_enabled"] == "true"
    assert "SEARXNG_AUTH_TOKEN" not in row.credentials
    validation.assert_awaited_once_with(SEARXNG_BASE)
    assert result.searxng_enabled is True
    assert result.searxng_base_url == SEARXNG_BASE
    assert result.searxng_auth_token_configured is False


@pytest.mark.anyio
async def test_save_searxng_preserves_omitted_base_and_token(monkeypatch):
    token_ciphertext = _encrypted("site-token")
    row = FakeRow(
        {
            "default_engine": "searxng",
            "tavily_enabled": "false",
            "bocha_enabled": "false",
            "searxng_enabled": "true",
            "SEARXNG_BASE_URL": SEARXNG_BASE,
            "SEARXNG_AUTH_TOKEN": token_ciphertext,
        }
    )
    _install_save(monkeypatch, row)
    validation = _install_searxng_validation(monkeypatch)

    result = await subject.save_web_search_config(
        _searxng_update(searxng_base_url=None, searxng_auth_token=None)
    )

    assert row.credentials["SEARXNG_BASE_URL"] == SEARXNG_BASE
    assert row.credentials["SEARXNG_AUTH_TOKEN"] == token_ciphertext
    validation.assert_awaited_once_with(SEARXNG_BASE)
    assert result.searxng_auth_token_configured is True


@pytest.mark.anyio
async def test_save_rejects_url_change_without_explicit_token_decision(monkeypatch):
    old_token = _encrypted("site-token")
    row = FakeRow(
        {
            "default_engine": "searxng",
            "searxng_enabled": "true",
            "SEARXNG_BASE_URL": SEARXNG_BASE,
            "SEARXNG_AUTH_TOKEN": old_token,
        }
    )
    _install_save(monkeypatch, row)
    _install_searxng_validation(monkeypatch)

    with pytest.raises(BusinessError) as error:
        await subject.save_web_search_config(
            _searxng_update(
                searxng_base_url="https://other.example.test/searx",
                searxng_auth_token=None,
            )
        )

    assert error.value.msg_key == "web_search_searxng_token_confirmation_required"
    assert row.save_kwargs is None
    assert row.credentials["SEARXNG_AUTH_TOKEN"] == old_token


@pytest.mark.anyio
async def test_save_allows_url_change_when_token_is_explicitly_cleared(monkeypatch):
    row = FakeRow(
        {
            "default_engine": "searxng",
            "searxng_enabled": "true",
            "SEARXNG_BASE_URL": SEARXNG_BASE,
            "SEARXNG_AUTH_TOKEN": _encrypted("site-token"),
        }
    )
    _install_save(monkeypatch, row)
    _install_searxng_validation(monkeypatch)

    result = await subject.save_web_search_config(
        _searxng_update(
            searxng_base_url="https://other.example.test/searx",
            searxng_auth_token="",
        )
    )

    assert row.credentials["SEARXNG_BASE_URL"] == "https://other.example.test/searx"
    assert "SEARXNG_AUTH_TOKEN" not in row.credentials
    assert result.searxng_base_url == "https://other.example.test/searx"


@pytest.mark.anyio
async def test_save_rejects_searxng_without_base_url(monkeypatch):
    row = FakeRow({})
    _install_save(monkeypatch, row)

    with pytest.raises(BusinessError) as error:
        await subject.save_web_search_config(_searxng_update(searxng_base_url=None))

    assert error.value.msg_key == "web_search_searxng_base_url_required"
    assert row.save_kwargs is None


@pytest.mark.anyio
async def test_save_rejects_plain_http_token_transport(monkeypatch):
    row = FakeRow({})
    _install_save(monkeypatch, row)

    with pytest.raises(BusinessError) as error:
        await subject.save_web_search_config(
            _searxng_update(
                searxng_base_url="http://search.example.test/searx",
                searxng_auth_token="site-token",
            )
        )

    assert error.value.msg_key == "web_search_searxng_https_required"
    assert row.save_kwargs is None


@pytest.mark.anyio
async def test_runtime_searxng_returns_base_and_decrypted_token(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                    "SEARXNG_BASE_URL": SEARXNG_BASE,
                    "SEARXNG_AUTH_TOKEN": _encrypted("site-token"),
                }
            )
        ),
    )
    validation = _install_searxng_validation(monkeypatch)

    engine, config = await subject.get_web_search_runtime("searxng")

    assert engine == "searxng"
    assert config == {
        "SEARXNG_BASE_URL": SEARXNG_BASE,
        "SEARXNG_AUTH_TOKEN": "site-token",
    }
    validation.assert_awaited_once_with(SEARXNG_BASE)


@pytest.mark.anyio
async def test_runtime_searxng_without_token_returns_only_base(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                    "SEARXNG_BASE_URL": SEARXNG_BASE,
                }
            )
        ),
    )
    _install_searxng_validation(monkeypatch)

    assert await subject.get_web_search_runtime() == (
        "searxng",
        {"SEARXNG_BASE_URL": SEARXNG_BASE},
    )


@pytest.mark.anyio
async def test_runtime_searxng_rejects_http_with_token(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                    "SEARXNG_BASE_URL": "http://search.example.test/searx",
                    "SEARXNG_AUTH_TOKEN": _encrypted("site-token"),
                }
            )
        ),
    )
    validation = _install_searxng_validation(monkeypatch)

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("searxng")

    assert error.value.msg_key == "web_search_searxng_https_required"
    validation.assert_not_awaited()


@pytest.mark.anyio
async def test_runtime_searxng_requires_base_url(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                }
            )
        ),
    )
    validation = _install_searxng_validation(monkeypatch)

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("auto")

    assert error.value.msg_key == "web_search_engine_not_configured"
    assert error.value.kwargs == {"engine": "searxng"}
    validation.assert_not_awaited()


@pytest.mark.anyio
async def test_runtime_searxng_revalidates_ssrf_on_every_request(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                    "SEARXNG_BASE_URL": SEARXNG_BASE,
                }
            )
        ),
    )
    blocked = BusinessError(
        msg_key="http_tool_url_host_not_allowed",
        host="search.example.test",
        reason="private address 10.0.0.10",
    )
    ensure = AsyncMock(side_effect=blocked)
    monkeypatch.setattr(subject, "ensure_external_http_url_allowed", ensure)

    for _request in range(2):
        with pytest.raises(BusinessError) as error:
            await subject.get_web_search_runtime("searxng")
        assert error.value.msg_key == "http_tool_url_host_not_allowed"

    assert ensure.await_count == 2


@pytest.mark.anyio
async def test_runtime_searxng_fails_safe_for_unreadable_token(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_get_global_config",
        AsyncMock(
            return_value=SimpleNamespace(
                credentials={
                    "default_engine": "searxng",
                    "searxng_enabled": "true",
                    "SEARXNG_BASE_URL": SEARXNG_BASE,
                    "SEARXNG_AUTH_TOKEN": "enc:v1:not-a-fernet-token",
                }
            )
        ),
    )
    _install_searxng_validation(monkeypatch)

    with pytest.raises(BusinessError) as error:
        await subject.get_web_search_runtime("searxng")

    assert error.value.msg_key == "web_search_credentials_unreadable"

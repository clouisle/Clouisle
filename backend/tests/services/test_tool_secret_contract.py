"""Contract tests for inline-secret rejection and export sanitization."""

from __future__ import annotations

from app.schemas.response import BusinessError
from app.services.tool_secret_contract import (
    enforce_tool_secret_contract,
    find_tool_secret_violations,
    sanitize_tool_configs_for_export,
)


def _rules(**payload) -> list[tuple[str, str]]:
    return [(item.path, item.rule) for item in find_tool_secret_violations(**payload)]


def test_inline_credentials_are_rejected_even_when_templated():
    assert _rules(credentials={"api_key": "sk-live"}) == [
        ("credentials.api_key", "inline_credentials")
    ]
    assert _rules(credentials={"api_key": "{{api_key}}"}) == [
        ("credentials.api_key", "inline_credentials")
    ]


def test_sensitive_headers_require_a_placeholder_and_declaration():
    assert _rules(
        http_config={"headers": {"Authorization": "Bearer sk-live"}},
        connection_fields=[{"name": "api_key"}],
    ) == [("http_config.headers.Authorization", "inline_secret")]

    assert (
        _rules(
            http_config={"headers": {"Authorization": "Bearer {{api_key}}"}},
            connection_fields=[{"name": "api_key"}],
        )
        == []
    )

    assert _rules(
        http_config={"headers": {"Authorization": "Bearer {{api_key}}"}},
    ) == [("http_config.headers.Authorization", "undeclared_connection_field")]


def test_nonsecret_headers_and_env_are_preserved():
    payload = {
        "http_config": {
            "url": "https://api.example.test",
            "headers": {"X-Trace": "trace-1", "Accept": "application/json"},
        },
        "mcp_config": {
            "env": {"LOG_LEVEL": "debug", "API_KEY": "{{api_key}}"},
            "headers": {"X-Client": "clouisle"},
        },
        "connection_fields": [{"name": "api_key", "label": "API key"}],
    }
    assert _rules(**payload) == []


def test_secret_mcp_env_requires_declared_connection_field():
    violations = _rules(
        mcp_config={"env": {"GITHUB_TOKEN": "ghp_live"}},
    )
    assert ("mcp_config.env.GITHUB_TOKEN", "inline_secret") in violations

    assert (
        _rules(
            mcp_config={"env": {"GITHUB_TOKEN": "{{github_token}}"}},
            connection_fields=[{"name": "github_token"}],
        )
        == []
    )


def test_credential_bearing_urls_are_rejected_but_plain_urls_pass():
    assert _rules(
        http_config={"url": "https://api.example.test/data?api_key=sk-live"}
    ) == [("http_config.url", "url_credentials")]
    assert (
        _rules(
            http_config={"url": "https://api.example.test/data"},
        )
        == []
    )


def test_connection_field_definitions_must_be_unique_and_valid():
    violations = _rules(
        connection_fields=[
            {"name": "api_key"},
            {"name": "api_key"},
            {"name": "1invalid"},
        ]
    )
    assert ("connection_fields[1].name", "duplicate_connection_field") in violations
    assert ("connection_fields[2].name", "invalid_connection_field") in violations


def test_enforce_raises_actionable_business_error():
    try:
        enforce_tool_secret_contract(credentials={"token": "secret"})
    except BusinessError as exc:
        assert exc.msg_key == "tool_secret_inline_not_allowed"
        assert exc.status_code == 400
        assert "credentials.token" in exc.kwargs["fields"]
    else:  # pragma: no cover
        raise AssertionError("inline credentials were accepted")


def test_export_sanitization_drops_literal_secrets_and_keeps_configuration():
    http, mcp = sanitize_tool_configs_for_export(
        http_config={
            "url": "https://api.example.test",
            "headers": {
                "Authorization": "Bearer sk-live",
                "X-Trace": "trace-1",
                "X-Api-Key": "{{api_key}}",
            },
            "oauth2": {
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "client_id": "public-client",
            },
        },
        mcp_config={
            "env": {"LOG_LEVEL": "debug", "GITHUB_TOKEN": "ghp_live"},
            "headers": [{"Authorization": "Bearer sk-live"}],
        },
    )

    assert http["headers"] == {"X-Trace": "trace-1", "X-Api-Key": "{{api_key}}"}
    assert http["oauth2"]["token_endpoint"] == "https://auth.example.test/token"
    assert mcp["env"] == {"LOG_LEVEL": "debug"}
    assert mcp["headers"] == [{}]

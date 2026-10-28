"""Input-boundary behavior for the tool write-time secret contract.

The module is pure, so every assertion goes through its public classifiers.
"""

from __future__ import annotations

from app.services.tool_secret_contract import (
    find_tool_secret_violations,
    sanitize_tool_configs_for_export,
)


def _rules(**payload) -> list[tuple[str, str]]:
    return [(item.path, item.rule) for item in find_tool_secret_violations(**payload)]


def test_names_without_alphanumerics_are_never_credentials():
    # A header/env name that normalizes to the empty string cannot be
    # classified, so it must not be rejected.
    assert _rules(http_config={"headers": {"---": "Bearer sk-live"}}) == []
    assert _rules(mcp_config={"env": {"  ": "literal"}}) == []


def test_url_credentials_cover_userinfo_and_fail_closed():
    assert _rules(http_config={"url": "https://user:secret@api.example.test/v1"}) == [
        ("http_config.url", "url_credentials")
    ]
    # A credential-looking *username* is a secret even without a password.
    assert _rules(http_config={"url": "https://api_key@api.example.test/v1"}) == [
        ("http_config.url", "url_credentials")
    ]
    assert _rules(http_config={"url": "https://service-account@api.example.test"}) == []
    # An unparseable URL is rejected rather than silently accepted.
    assert _rules(mcp_config={"url": "http://[::1"}) == [
        ("mcp_config.url", "url_credentials")
    ]


def test_literal_query_parameters_and_mcp_headers_are_inline_secrets():
    assert _rules(
        http_config={
            "query_params": {
                "api_key": "sk-live",
                "q": "hello",
                "token": "",
            }
        }
    ) == [("http_config.query_params.api_key", "inline_secret")]

    assert _rules(
        mcp_config={
            "headers": {
                "Authorization": "Bearer live",
                "X-Client": "clouisle",
                "X-Empty": "",
            }
        }
    ) == [("mcp_config.headers.Authorization", "inline_secret")]


def test_templated_query_and_header_values_must_be_declared():
    assert (
        _rules(
            http_config={"query_params": {"api_key": "{{api_key}}"}},
            connection_fields=[{"name": "api_key"}],
        )
        == []
    )
    assert _rules(mcp_config={"headers": {"X-Api-Key": "{{api_key}}"}}) == [
        ("mcp_config.headers.X-Api-Key", "undeclared_connection_field")
    ]


def test_connection_field_entries_that_cannot_be_declared_are_skipped():
    assert (
        _rules(
            connection_fields=[
                None,
                "api_key",
                {"name": ""},
                {"name": "api_key"},
            ]
        )
        == []
    )


def test_export_sanitization_drops_credential_bearing_urls_only():
    http, mcp = sanitize_tool_configs_for_export(
        http_config={"url": "https://user:secret@example.test/v1"},
        mcp_config={
            "url": "https://mcp.example.test/sse?api_key=sk-live",
            "headers": {"X-Trace": "trace-1"},
        },
    )

    assert "url" not in http
    assert "url" not in mcp
    assert mcp["headers"] == {"X-Trace": "trace-1"}

    http, mcp = sanitize_tool_configs_for_export(
        http_config={"url": "https://{{host}}/v1"},
        mcp_config={"url": "https://mcp.example.test/sse"},
    )

    assert http["url"] == "https://{{host}}/v1"
    assert mcp["url"] == "https://mcp.example.test/sse"

"""Server log forwarding and liveness pings (#499).

Covers the adapter half: the ``notifications/message`` hook forwards into the
application logger tagged with the session's subject, and the requested log
level is delivered by whichever mechanism the negotiated protocol version
supports. The subscription half lives in
``tests/services/test_mcp_subscriptions_listen.py``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _transport():
    yield "read-stream", "write-stream"


class _FakeSession:
    """Negotiated session stand-in recording what the adapter asked for."""

    protocol_version = "2026-07-28"
    server_capabilities: dict[str, object] = {"logging": {}}
    log_level_calls: list[str] = []
    fail_set_logging_level = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def initialize(self):
        return None

    async def set_logging_level(self, level, **kwargs) -> None:
        if type(self).fail_set_logging_level:
            raise RuntimeError("logging unsupported")
        type(self).log_level_calls.append(level)


class _LegacySession(_FakeSession):
    protocol_version = "2025-11-25"


class _LegacySessionWithoutLogging(_LegacySession):
    server_capabilities: dict[str, object] = {}


@pytest.fixture(autouse=True)
def _reset_session_records(monkeypatch):
    for session_class in (
        _FakeSession,
        _LegacySession,
        _LegacySessionWithoutLogging,
    ):
        session_class.log_level_calls = []
        session_class.fail_set_logging_level = False
    monkeypatch.setattr(mcp, "_SESSION_ACCEPTS_LOG_LEVEL", True)
    yield


@asynccontextmanager
async def _open(client: mcp.McpClient, monkeypatch, session_class):
    """Open the adapter's session context against a fake ``ClientSession``."""
    monkeypatch.setattr(client, "_transport", _transport)
    monkeypatch.setattr(mcp, "ClientSession", session_class)
    async with client._open(mcp._Deadline(5.0, "test")) as opened:
        yield opened


def _logging_callbacks(**logging_kwargs):
    return mcp.McpCallbacks(
        server_logging=mcp.McpServerLogging(**logging_kwargs),
    )


# ---------------------------------------------------------------------------
# Forwarding to the application logger
# ---------------------------------------------------------------------------


def _notification(level="error", logger_name="mcp.db", data="secret-value"):
    return types.LoggingMessageNotificationParams(
        level=level, logger=logger_name, data=data
    )


async def test_server_log_is_forwarded_with_its_subject_and_level(caplog):
    caplog.set_level(logging.WARNING, logger=mcp.logger.name)
    guard = mcp._CallbackGuard(_logging_callbacks(subject="tool:42"))

    await guard.server_log(_notification())

    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert record.mcp_server == "tool:42"
    assert record.mcp_server_log_level == "error"
    assert "mcp.db" in record.getMessage()
    # The payload is not part of a normal-level record.
    assert "secret-value" not in record.getMessage()


async def test_server_log_payload_is_debug_only_and_truncated(caplog):
    caplog.set_level(logging.DEBUG, logger=mcp.logger.name)
    guard = mcp._CallbackGuard(_logging_callbacks(subject="tool:7"))
    oversized = "x" * (mcp.MAX_SERVER_LOG_PAYLOAD_CHARS * 3)

    await guard.server_log(_notification(data=oversized))

    payload_records = [
        record for record in caplog.records if record.levelno == logging.DEBUG
    ]
    assert len(payload_records) == 1
    message = payload_records[0].getMessage()
    assert "tool:7" in message
    assert len(message) < mcp.MAX_SERVER_LOG_PAYLOAD_CHARS + 200

    caplog.clear()
    caplog.set_level(logging.INFO, logger=mcp.logger.name)
    await guard.server_log(_notification(data="payload-that-must-not-appear"))
    assert not any(record.levelno == logging.DEBUG for record in caplog.records)
    assert not any(
        "payload-that-must-not-appear" in record.getMessage()
        for record in caplog.records
    )


async def test_server_log_unknown_level_falls_back_to_info(caplog):
    caplog.set_level(logging.DEBUG, logger=mcp.logger.name)
    guard = mcp._CallbackGuard(_logging_callbacks())

    # An unnamed level reaches the adapter only from non-conforming servers, so
    # the forwarder must not crash on it.
    await guard.server_log(SimpleNamespace(level="verbose", logger=None, data=None))
    listed = [record for record in caplog.records if record.levelno == logging.INFO]
    assert listed and "verbose" in listed[-1].getMessage()

    caplog.clear()
    await guard.server_log(SimpleNamespace())
    fallback = [record for record in caplog.records if record.levelno == logging.INFO]
    assert fallback and "unlisted" in fallback[-1].getMessage()
    assert fallback[-1].mcp_server is None
    assert fallback[-1].mcp_server_log_level is None


async def test_a_broken_server_log_never_raises(caplog):
    caplog.set_level(logging.WARNING, logger=mcp.logger.name)
    guard = mcp._CallbackGuard(_logging_callbacks(subject="tool:9"))

    class _Exploding:
        @property
        def level(self):
            raise RuntimeError("unreadable notification")

    assert await guard.server_log(_Exploding()) is None
    assert any(
        "Forwarding an MCP server log notification failed" in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Opt-in level: protocol-version branch
# ---------------------------------------------------------------------------


async def test_server_logging_from_config_is_opt_in_and_validated(caplog):
    assert mcp.server_logging_from_config({}) is None
    assert mcp.server_logging_from_config({"server_log_level": None}) is None

    assert mcp.server_logging_from_config(
        {"server_log_level": " Debug "}, subject="tool:3"
    ) == mcp.McpServerLogging(level="debug", subject="tool:3")

    assert mcp.server_logging_from_config({"server_log_level": "loud"}) is None
    assert any(
        "Ignoring unknown MCP server_log_level" in record.getMessage()
        for record in caplog.records
    )


async def test_without_the_opt_in_nothing_is_registered_or_requested(
    monkeypatch,
):
    client = mcp.McpClient({})

    async with _open(client, monkeypatch, _FakeSession) as (session, _capabilities):
        assert session.kwargs["logging_callback"] is None
        assert "log_level" not in session.kwargs
    assert _FakeSession.log_level_calls == []


async def test_a_modern_session_carries_the_level_in_request_meta(monkeypatch):
    client = mcp.McpClient({}, callbacks=_logging_callbacks(level="debug"))

    async with _open(client, monkeypatch, _FakeSession) as (session, _capabilities):
        # mcp 2.x stamps this into every request's ``_meta`` for 2026-07-28.
        assert session.kwargs["log_level"] == "debug"
        assert callable(session.kwargs["logging_callback"])
    # logging/setLevel is deprecated at 2026-07-28 (SEP-2577): never sent.
    assert _FakeSession.log_level_calls == []


async def test_a_handshake_session_gets_the_explicit_logging_request(monkeypatch):
    client = mcp.McpClient({}, callbacks=_logging_callbacks(level="warning"))

    async with _open(client, monkeypatch, _LegacySession) as (_session, _caps):
        pass

    assert _LegacySession.log_level_calls == ["warning"]


async def test_a_server_without_the_logging_capability_is_not_asked(
    monkeypatch,
):
    client = mcp.McpClient({}, callbacks=_logging_callbacks())

    async with _open(client, monkeypatch, _LegacySessionWithoutLogging) as (
        _session,
        _caps,
    ):
        pass

    assert _LegacySessionWithoutLogging.log_level_calls == []


async def test_a_rejected_log_level_never_fails_the_session(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=mcp.logger.name)
    client = mcp.McpClient({}, callbacks=_logging_callbacks())
    monkeypatch.setattr(_LegacySession, "fail_set_logging_level", True)

    async with _open(client, monkeypatch, _LegacySession) as (session, _caps):
        assert session is not None

    assert any("rejected log level" in record.getMessage() for record in caplog.records)


async def test_an_sdk_without_the_log_level_argument_sends_no_such_kwarg(
    monkeypatch,
):
    # mcp 1.x has no per-request log-level default; it must not be passed.
    monkeypatch.setattr(mcp, "_SESSION_ACCEPTS_LOG_LEVEL", False)
    client = mcp.McpClient({}, callbacks=_logging_callbacks())

    async with _open(client, monkeypatch, _FakeSession) as (session, _caps):
        assert "log_level" not in session.kwargs
        assert callable(session.kwargs["logging_callback"])


async def test_log_level_meta_branch_follows_the_negotiated_version():
    assert mcp._log_level_uses_meta("2026-07-28") is True
    assert mcp._log_level_uses_meta("2025-11-25") is False
    assert mcp._log_level_uses_meta(None) is False
    assert mcp.LOG_LEVEL_META_MIN_PROTOCOL_VERSION == "2026-07-28"

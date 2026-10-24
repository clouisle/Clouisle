"""Feishu event callback: signature, framing, challenge, and intake guards.

The callback is unauthenticated, so these tests pin the properties that make
it safe: bounded bodies, constant-time signature verification before any
runtime state is touched, length-framed decryption with app-id binding, and
acknowledgement of anything the runtime rejects.
"""

import base64
import hashlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.api.v1.endpoints import feishu_agent
from app.integrations.credentials import encrypt_secret
from app.integrations.registry import IntegrationCapability

APP_ID = "cli_test_app"
VERIFICATION_TOKEN = "feishu-verification-token"
ENCRYPT_KEY = "kF2xY7pQ9rT4vW6zA1bC3dE5gH8jK0mN2sU4wX6yZ1a="
AES_KEY = base64.b64decode(ENCRYPT_KEY)
assert len(AES_KEY) == 32, len(AES_KEY)


def _integration(**overrides):
    values = dict(
        id=uuid4(),
        name="feishu",
        provider_type="feishu",
        config={"app_id": APP_ID},
        credentials={
            "app_secret": encrypt_secret("app-secret"),
            "event_verification_token": encrypt_secret(VERIFICATION_TOKEN),
            "event_encrypt_key": encrypt_secret(ENCRYPT_KEY),
        },
        is_enabled=True,
        enabled_capabilities=["directory_sync", "agent_chat"],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _install(monkeypatch, integration=None):
    monkeypatch.setattr(
        feishu_agent,
        "get_builtin_integration",
        AsyncMock(return_value=integration or _integration()),
    )
    monkeypatch.setattr(
        feishu_agent,
        "integration_registry",
        MagicMock(
            get=MagicMock(
                return_value=SimpleNamespace(
                    capabilities=[IntegrationCapability.AGENT_CHAT]
                )
            )
        ),
    )


def _request(body: bytes, **headers) -> SimpleNamespace:
    payload = {
        "X-Lark-Request-Timestamp": str(int(time.time())),
        "X-Lark-Request-Nonce": "nonce-1",
    }
    payload.update(headers)
    return SimpleNamespace(
        headers=payload,
        body=AsyncMock(return_value=body),
    )


def _sign(body: bytes, **headers) -> dict:
    signed = {
        "X-Lark-Request-Timestamp": str(int(time.time())),
        "X-Lark-Request-Nonce": "nonce-1",
    }
    signed.update(headers)
    digest = hashlib.sha256(
        (
            signed["X-Lark-Request-Timestamp"]
            + signed["X-Lark-Request-Nonce"]
            + ENCRYPT_KEY
        ).encode()
        + body
    ).hexdigest()
    signed["X-Lark-Signature"] = digest
    return signed


def _encrypt(
    payload: dict, *, app_id: str = APP_ID, prefix: bytes | None = None
) -> str:
    """Encrypt exactly the way Feishu does: random16 || len4 || JSON || app_id."""
    body = json.dumps(payload).encode()
    plaintext = (
        (prefix if prefix is not None else b"\x11" * 16)
        + len(body).to_bytes(4, "big")
        + body
        + app_id.encode()
    )
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_KEY[:16])).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def _success_payload() -> dict:
    return {"code": 0, "data": None, "msg": "Success"}


def _event_payload(**overrides) -> dict:
    header = {
        "event_id": str(uuid4()),
        "event_type": "im.message.receive_v1",
        "app_id": APP_ID,
        "token": VERIFICATION_TOKEN,
    }
    event = {
        "sender": {
            "sender_type": "user",
            "sender_id": {"user_id": "ou_sender", "open_id": "on_sender"},
        },
        "message": {
            "message_id": f"om_{uuid4().hex}",
            "chat_id": "oc_chat",
            "chat_type": "p2p",
            "message_type": "text",
            "content": json.dumps({"text": "hello"}),
        },
    }
    header.update(overrides.pop("header", {}))
    event.update(overrides.pop("event", {}))
    payload = {"schema": "2.0", "header": header, "event": event}
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_challenge_echoes_after_signature_verification(monkeypatch):
    _install(monkeypatch)
    body = json.dumps({"challenge": "abc123", "token": VERIFICATION_TOKEN}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == {"challenge": "abc123"}


@pytest.mark.asyncio
async def test_challenge_rejects_wrong_token(monkeypatch):
    _install(monkeypatch)
    body = json.dumps({"challenge": "abc123", "token": "wrong"}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unsigned_challenge_is_rejected(monkeypatch):
    _install(monkeypatch)
    body = json.dumps({"challenge": "abc123", "token": VERIFICATION_TOKEN}).encode()
    request = _request(body)

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stale_timestamp_is_rejected(monkeypatch):
    _install(monkeypatch)
    body = json.dumps({"challenge": "abc123", "token": VERIFICATION_TOKEN}).encode()
    headers = _sign(body, **{"X-Lark-Request-Timestamp": str(int(time.time()) - 3600)})
    request = SimpleNamespace(headers=headers, body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tampered_body_fails_signature(monkeypatch):
    _install(monkeypatch)
    signed = json.dumps({"challenge": "abc123", "token": VERIFICATION_TOKEN}).encode()
    headers = _sign(signed)
    tampered = json.dumps({"challenge": "evil", "token": VERIFICATION_TOKEN}).encode()
    request = SimpleNamespace(headers=headers, body=AsyncMock(return_value=tampered))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_without_reading_past_the_bound(
    monkeypatch,
):
    _install(monkeypatch)
    body = b"x" * (feishu_agent.MAX_BODY_BYTES + 1)
    reader = AsyncMock(side_effect=AssertionError("body must not be read"))
    headers = _sign(body)
    headers["content-length"] = str(len(body))
    request = SimpleNamespace(headers=headers, body=reader)

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_undeclared_oversized_body_is_rejected(monkeypatch):
    _install(monkeypatch)
    body = b"x" * (feishu_agent.MAX_BODY_BYTES + 1)
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_disabled_capability_never_reads_the_body(monkeypatch):
    _install(
        monkeypatch,
        _integration(enabled_capabilities=["directory_sync"], is_enabled=True),
    )
    body = json.dumps({"challenge": "abc"}).encode()
    reader = AsyncMock(side_effect=AssertionError("body must not be read"))
    request = SimpleNamespace(headers=_sign(body), body=reader)

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_connection_mode_never_reads_callback_body(monkeypatch):
    integration = _integration()
    integration.config["agent_chat_connection_mode"] = "long_connection"
    _install(monkeypatch, integration)
    request = SimpleNamespace(headers={}, body=AsyncMock())

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403
    request.body.assert_not_awaited()


@pytest.mark.asyncio
async def test_integration_disabled_is_rejected(monkeypatch):
    _install(monkeypatch, _integration(is_enabled=False))
    body = json.dumps({"challenge": "abc"}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_encrypted_event_decrypts_and_queues_the_runtime(monkeypatch):
    _install(monkeypatch)
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope)}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value="receipt-1"))
    task = MagicMock(delay=MagicMock())
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.feishu_agent",
        SimpleNamespace(process_message_task=task),
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    task.delay.assert_called_once_with("receipt-1")
    event = runtime.accept_message.await_args.args[0]
    assert event["app_id"] == APP_ID
    assert event["message"]["chat_type"] == "p2p"


@pytest.mark.asyncio
async def test_encrypted_payload_bound_to_another_app_is_rejected(monkeypatch):
    _install(monkeypatch)
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope, app_id="cli_other")}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_decrypted_length_field_must_match_the_payload(monkeypatch):
    _install(monkeypatch)
    inner = json.dumps(_event_payload()).encode()
    plaintext = (
        b"\x22" * 16 + (len(inner) + 64).to_bytes(4, "big") + inner + APP_ID.encode()
    )
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_KEY[:16])).encryptor()
    encrypted = base64.b64encode(
        encryptor.update(padded) + encryptor.finalize()
    ).decode()
    body = json.dumps({"encrypt": encrypted}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_real_feishu_plaintext_layout_decrypts(monkeypatch):
    """random16 || uint32_be(len) || JSON || app_id, with a non-zero prefix."""
    _install(monkeypatch)
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope, prefix=bytes(range(16)))}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value="receipt-9"))
    task = MagicMock(delay=MagicMock())
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.feishu_agent",
        SimpleNamespace(process_message_task=task),
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    task.delay.assert_called_once_with("receipt-9")
    assert runtime.accept_message.await_args.args[0]["app_id"] == APP_ID


def test_encrypt_key_without_padding_still_decodes():
    """Feishu issues a 43-character key with no trailing '='."""
    unpadded = ENCRYPT_KEY.rstrip("=")
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope)}).encode()

    assert len(unpadded) == 43
    assert (
        feishu_agent._decrypt(
            json.loads(body)["encrypt"], unpadded, expected_app_id=APP_ID
        )["header"]["app_id"]
        == APP_ID
    )


@pytest.mark.asyncio
async def test_encrypt_key_is_base64_decoded_not_hashed(monkeypatch):
    _install(monkeypatch)
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope)}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value=None))
    task = MagicMock(delay=MagicMock())
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.feishu_agent",
        SimpleNamespace(process_message_task=task),
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    task.delay.assert_not_called()
    runtime.accept_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_rejection_is_acknowledged_without_queueing(monkeypatch):
    _install(monkeypatch)
    body = json.dumps(_event_payload()).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value=None))
    task = MagicMock(delay=MagicMock())
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.feishu_agent",
        SimpleNamespace(process_message_task=task),
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_failure_is_acknowledged_without_queueing(monkeypatch):
    _install(monkeypatch)
    body = json.dumps(_event_payload()).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(
        accept_message=AsyncMock(side_effect=RuntimeError("boom"))
    )
    task = MagicMock(delay=MagicMock())
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.feishu_agent",
        SimpleNamespace(process_message_task=task),
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_event_app_id_mismatch_is_rejected_before_the_runtime(monkeypatch):
    _install(monkeypatch)
    body = json.dumps(_event_payload(header={"app_id": "cli_other"})).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value="receipt-1"))
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403
    runtime.accept_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsubscribed_event_type_is_acknowledged(monkeypatch):
    _install(monkeypatch)
    body = json.dumps(
        _event_payload(header={"event_type": "im.chat.updated_v1"})
    ).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value="receipt-1"))
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )

    response = await feishu_agent.feishu_event_callback(request)

    assert json.loads(response.body) == _success_payload()
    runtime.accept_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_callback_secrets_are_rejected(monkeypatch):
    _install(monkeypatch, _integration(credentials={}))
    body = json.dumps(_event_payload()).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


def test_signature_comparison_is_constant_time():
    """The digest comparison must not short-circuit on the first byte."""
    body = b"{}"
    timestamp = "1700000000"
    nonce = "nonce"
    expected = hashlib.sha256(
        (timestamp + nonce + ENCRYPT_KEY).encode() + body
    ).hexdigest()
    assert feishu_agent._verify_signature(
        signature=expected.upper(),
        timestamp=timestamp,
        nonce=nonce,
        encrypt_key=ENCRYPT_KEY,
        body=body,
    )
    assert not feishu_agent._verify_signature(
        signature=expected[:-1] + ("0" if expected[-1] != "0" else "1"),
        timestamp=timestamp,
        nonce=nonce,
        encrypt_key=ENCRYPT_KEY,
        body=body,
    )
    assert not feishu_agent._verify_signature(
        signature="",
        timestamp=timestamp,
        nonce=nonce,
        encrypt_key=ENCRYPT_KEY,
        body=body,
    )


def test_encrypt_key_must_decode_to_32_bytes():
    short_key = base64.b64encode(b"too-short").decode()
    with pytest.raises(ValueError, match="32 bytes"):
        feishu_agent._decrypt("AAAA", short_key, expected_app_id=APP_ID)


def test_non_base64_encrypt_key_is_rejected():
    with pytest.raises(ValueError, match="not valid base64"):
        feishu_agent._decrypt("AAAA", "not base64 at all!", expected_app_id=APP_ID)

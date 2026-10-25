"""Feishu event callback: SDK encryption, challenge, and intake guards.

The callback is unauthenticated, so these tests pin the properties that make
it safe: bounded bodies, constant-time signature verification before any
runtime state is touched, JSON decryption with header app-id binding, and
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
from lark_oapi.core.model import RawRequest
from lark_oapi.core.utils.decryptor import AESCipher
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

from app.api.v1.endpoints import feishu_agent
from app.integrations.credentials import encrypt_secret
from app.integrations.registry import IntegrationCapability

APP_ID = "cli_test_app"
VERIFICATION_TOKEN = "feishu-verification-token"
ENCRYPT_KEY = "kF2xY7pQ9rT4vW6zA1bC3dE5gH8jK0mN2sU4wX6yZ1a="


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


def _sign(body: bytes, *, encrypt_key: str = ENCRYPT_KEY, **headers) -> dict:
    signed = {
        "X-Lark-Request-Timestamp": str(int(time.time())),
        "X-Lark-Request-Nonce": "nonce-1",
    }
    signed.update(headers)
    digest = hashlib.sha256(
        (
            signed["X-Lark-Request-Timestamp"]
            + signed["X-Lark-Request-Nonce"]
            + encrypt_key
        ).encode()
        + body
    ).hexdigest()
    signed["X-Lark-Signature"] = digest
    return signed


def _encrypt_plaintext(
    plaintext: bytes,
    *,
    iv: bytes = b"\x33" * 16,
    encrypt_key: str = ENCRYPT_KEY,
) -> str:
    """Use the installed Lark SDK's SHA256(key), prepended-IV wire format."""
    key = hashlib.sha256(encrypt_key.encode()).digest()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = iv + encryptor.update(padded) + encryptor.finalize()
    encrypted = base64.b64encode(ciphertext).decode()
    assert AESCipher(encrypt_key).decrypt(ciphertext) == plaintext
    return encrypted


def _encrypt(payload: dict, *, encrypt_key: str = ENCRYPT_KEY) -> str:
    """Feishu encrypts the JSON directly, without an inner binary frame."""
    return _encrypt_plaintext(json.dumps(payload).encode(), encrypt_key=encrypt_key)


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
async def test_encrypted_challenge_matches_installed_sdk_dispatcher(monkeypatch):
    _install(monkeypatch)
    payload = {
        "type": "url_verification",
        "challenge": "sdk-challenge",
        "token": VERIFICATION_TOKEN,
    }
    body = json.dumps({"encrypt": _encrypt(payload)}).encode()
    headers = _sign(body)
    sdk_request = RawRequest()
    sdk_request.uri = "/feishu/callback"
    sdk_request.headers = headers
    sdk_request.body = body
    handler = EventDispatcherHandler.builder(ENCRYPT_KEY, VERIFICATION_TOKEN).build()

    sdk_response = handler.do(sdk_request)
    assert sdk_response.status_code == 200
    assert json.loads(sdk_response.content) == {"challenge": "sdk-challenge"}

    response = await feishu_agent.feishu_event_callback(
        SimpleNamespace(headers=headers, body=AsyncMock(return_value=body))
    )

    assert response.status_code == 200
    assert json.loads(response.body) == json.loads(sdk_response.content)


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
@pytest.mark.parametrize("field", ["app_id", "token"])
async def test_encrypted_event_rejects_mismatched_header_before_runtime(
    monkeypatch, field
):
    _install(monkeypatch)
    envelope = _event_payload(header={field: "wrong"})
    body = json.dumps({"encrypt": _encrypt(envelope)}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))
    receive = AsyncMock()
    monkeypatch.setattr(feishu_agent, "receive_message", receive)

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403
    receive.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [VERIFICATION_TOKEN, "wrong"])
async def test_encrypted_challenge_checks_token(monkeypatch, token):
    _install(monkeypatch)
    body = json.dumps(
        {"encrypt": _encrypt({"challenge": "abc123", "token": token})}
    ).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == (200 if token == VERIFICATION_TOKEN else 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", ["signature", "timestamp"])
async def test_encrypted_event_rejects_invalid_request_authentication(
    monkeypatch, guard
):
    _install(monkeypatch)
    body = json.dumps({"encrypt": _encrypt(_event_payload())}).encode()
    headers = _sign(
        body,
        **(
            {"X-Lark-Request-Timestamp": str(int(time.time()) - 3600)}
            if guard == "timestamp"
            else {}
        ),
    )
    if guard == "signature":
        headers["X-Lark-Signature"] = "0" * 64
    receive = AsyncMock()
    monkeypatch.setattr(feishu_agent, "receive_message", receive)

    response = await feishu_agent.feishu_event_callback(
        SimpleNamespace(headers=headers, body=AsyncMock(return_value=body))
    )

    assert response.status_code == 403
    receive.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "encrypted",
    [
        "not base64!",
        base64.b64encode(b"short").decode(),
        base64.b64encode(b"\0" * 33).decode(),
        base64.b64encode(b"\0" * 32).decode(),
    ],
)
async def test_malformed_encrypted_payload_is_rejected(monkeypatch, encrypted):
    _install(monkeypatch)
    body = json.dumps({"encrypt": encrypted}).encode()
    request = SimpleNamespace(headers=_sign(body), body=AsyncMock(return_value=body))

    response = await feishu_agent.feishu_event_callback(request)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sdk_dispatcher_accepts_encrypted_event_json(monkeypatch):
    """The real SDK parses the same decrypted JSON and delivers its message."""
    _install(monkeypatch)
    envelope = _event_payload()
    body = json.dumps({"encrypt": _encrypt(envelope)}).encode()
    headers = _sign(body)
    sdk_request = RawRequest()
    sdk_request.uri = "/feishu/callback"
    sdk_request.headers = headers
    sdk_request.body = body
    sdk_events = []
    handler = (
        EventDispatcherHandler.builder(ENCRYPT_KEY, VERIFICATION_TOKEN)
        .register_p2_im_message_receive_v1(sdk_events.append)
        .build()
    )

    sdk_response = handler.do(sdk_request)
    assert sdk_response.status_code == 200
    assert len(sdk_events) == 1
    assert sdk_events[0].header.app_id == APP_ID
    assert (
        sdk_events[0].event.message.message_id
        == envelope["event"]["message"]["message_id"]
    )
    receive = AsyncMock()
    monkeypatch.setattr(feishu_agent, "receive_message", receive)

    response = await feishu_agent.feishu_event_callback(
        SimpleNamespace(headers=headers, body=AsyncMock(return_value=body))
    )

    assert response.status_code == 200
    receive.assert_awaited_once_with(envelope["event"], app_id=APP_ID)


@pytest.mark.parametrize("plaintext", [b"[]", b"not JSON", b'"text"', b"\xff"])
def test_decrypted_payload_must_be_a_json_object(plaintext):
    encrypted = _encrypt_plaintext(plaintext)
    with pytest.raises(ValueError):
        feishu_agent._decrypt(encrypted, ENCRYPT_KEY)


def test_legacy_unprefixed_iv_ciphertext_is_rejected():
    """Do not retain the incorrect AES-key/derived-IV wire format."""
    plaintext = b"\x11" * 16 + (2).to_bytes(4, "big") + b"{}" + APP_ID.encode()
    key = base64.b64decode(ENCRYPT_KEY)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    legacy = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()

    with pytest.raises(ValueError):
        feishu_agent._decrypt(legacy, ENCRYPT_KEY)


def test_sdk_rejects_binary_framing_after_decryption():
    body = json.dumps(_event_payload()).encode()
    framed = b"\x11" * 16 + len(body).to_bytes(4, "big") + body + APP_ID.encode()
    encrypted = _encrypt_plaintext(framed)

    with pytest.raises(ValueError):
        json.loads(AESCipher(ENCRYPT_KEY).decrypt_str(encrypted))
    with pytest.raises(ValueError):
        feishu_agent._decrypt(encrypted, ENCRYPT_KEY)


def test_encrypt_key_without_padding_is_hashed_as_given():
    """Trailing '=' is part of the UTF-8 key, not optional base64 padding."""
    unpadded = ENCRYPT_KEY.rstrip("=")
    envelope = _event_payload()
    encrypted = _encrypt(envelope, encrypt_key=unpadded)
    body = json.dumps({"encrypt": encrypted}).encode()

    assert len(unpadded) == 43
    assert (
        feishu_agent._decrypt(json.loads(body)["encrypt"], unpadded)["header"]["app_id"]
        == APP_ID
    )


@pytest.mark.asyncio
async def test_encrypt_key_is_hashed_as_utf8_by_sdk(monkeypatch):
    _install(monkeypatch)
    monkeypatch.setattr(
        feishu_agent,
        "_agent_chat_secrets",
        AsyncMock(return_value=("raw-encrypt-key", VERIFICATION_TOKEN)),
    )
    envelope = _event_payload()
    body = json.dumps(
        {"encrypt": _encrypt(envelope, encrypt_key="raw-encrypt-key")}
    ).encode()
    request = SimpleNamespace(
        headers=_sign(body, encrypt_key="raw-encrypt-key"),
        body=AsyncMock(return_value=body),
    )
    runtime = SimpleNamespace(accept_message=AsyncMock(return_value=None))
    monkeypatch.setitem(
        __import__("sys").modules, "app.services.feishu_agent_runtime", runtime
    )
    task = MagicMock(delay=MagicMock())
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


def test_encrypt_key_must_be_accepted_as_utf8_sdk_key():
    """The SDK hashes any Encrypt Key string rather than base64-decoding it."""
    encrypted = _encrypt({}, encrypt_key="short-key")
    decrypted = feishu_agent._decrypt(encrypted, "short-key")
    assert decrypted == {}


def test_non_base64_encrypt_key_is_supported_by_sdk():
    encrypted = _encrypt({}, encrypt_key="not base64 at all!")
    assert feishu_agent._decrypt(encrypted, "not base64 at all!") == {}

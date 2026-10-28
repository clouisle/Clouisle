"""Per-execution credential handoff for sandbox snippet jobs.

Connection secrets are resolved in the API/Agent process but executed in a
separate Sandbox Worker. Sandbox jobs are serialized into durable Celery
messages, so *plaintext* secrets must never enter ``SandboxJob.metadata`` or
the process environment.

The API process therefore attaches a versioned Fernet envelope produced by
:func:`app.core.tool_secrets.encrypt_tool_secret` under
``job.metadata["credentials_envelope"]``. That is the same tool-secret keyring
used for stored connection values; no second crypto scheme exists.

Just before launching the snippet, the Sandbox Worker decrypts the envelope,
writes a random mode-0600 JSON file inside the job's private workspace ``tmp``
directory, and points the wrapper at it via ``CLOUISLE_CREDENTIALS_FILE``. The
wrapper reads and immediately unlinks the file, removes the pointer from its
own environment, and exposes a ``credentials`` mapping to user code. The
manager also unlinks the file in a ``finally`` block.

Isolation properties:

* one file per execution with a random name; the wrapper unlinks it before
  user code starts and the manager unlinks it again in ``finally``. A worker
  killed between file write and wrapper read can leave a mode-0600 file in the
  workspace ``tmp`` directory; standalone jobs are deleted as a whole. Code
  tools currently submit standalone jobs (no ``session_id``), so persistent
  session workspaces do not receive this handoff today.
* the pointer variable is reserved and assigned after ``job.env`` is merged,
  so a tool definition cannot spoof it, and credential values are never merged
  into the ambient process environment;
* a failed decryption/file write fails the job closed instead of running code
  without the connection it was configured for;
* consecutive executions with different connections cannot observe each
  other's mappings.
* the envelope is not a cryptographic one-time token: a durable Celery message
  keeps its ciphertext until consumed by the existing sandbox execution claim.
  Replay protection is the sandbox task claim/terminal-state fencing, not
  encryption semantics.

Secrets are available to the code by design; code can print or persist what it
was given. Output/log scrubbing is intentionally not promised.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.tool_secrets import (
    ToolSecretError,
    decrypt_tool_secret,
    encrypt_tool_secret,
)

#: Metadata key carrying the encrypted envelope from the API to the worker.
#: It is ciphertext, never a decryptable handle with external state.
CREDENTIALS_METADATA_KEY = "credentials_envelope"

#: Environment variable pointing the snippet wrapper at its credential file.
#: Reserved: user-provided job env cannot override it.
CREDENTIALS_ENV_VAR = "CLOUISLE_CREDENTIALS_FILE"

#: Workspace tmp prefix used for per-execution credential files.
CREDENTIAL_FILE_PREFIX = ".clouisle-credentials-"

MAX_CREDENTIAL_FIELDS = 50
MAX_CREDENTIAL_VALUE_LENGTH = 8192
MAX_CREDENTIAL_PAYLOAD_BYTES = 512 * 1024

_CREDENTIAL_PURPOSE = "sandbox_code_snippet"


class SandboxCredentialError(RuntimeError):
    """Credentials are missing, malformed or cannot be decrypted.

    Messages never include secret values.
    """


def _normalize_credentials(secrets: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for name, value in secrets.items():
        key = str(name)
        if not key or len(key) > 128:
            raise SandboxCredentialError("invalid credential field name")
        if value is None:
            continue
        if not isinstance(value, str):
            raise SandboxCredentialError("credential values must be strings")
        if len(value) > MAX_CREDENTIAL_VALUE_LENGTH:
            raise SandboxCredentialError("credential value exceeds the size limit")
        normalized[key] = value
    if len(normalized) > MAX_CREDENTIAL_FIELDS:
        raise SandboxCredentialError("too many credential fields")
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_CREDENTIAL_PAYLOAD_BYTES:
        raise SandboxCredentialError("credential payload exceeds the size limit")
    return normalized


def encrypt_sandbox_credentials(secrets: Mapping[str, Any], *, job_id: str) -> str:
    """Encrypt selected connection fields for one sandbox job payload.

    The plaintext payload is bound to ``job_id`` and a fixed purpose so a
    ciphertext copied into another job's metadata is rejected instead of
    silently granting that job the original connection identity.
    """
    normalized = _normalize_credentials(secrets)
    if not normalized:
        raise SandboxCredentialError("cannot attach empty credentials")
    bound_job_id = str(job_id)
    if not bound_job_id or len(bound_job_id) > 128:
        raise SandboxCredentialError("invalid sandbox job id for credentials")
    payload = json.dumps(
        {
            "purpose": _CREDENTIAL_PURPOSE,
            "job_id": bound_job_id,
            "fields": normalized,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        return encrypt_tool_secret(payload)
    except ToolSecretError as exc:
        raise SandboxCredentialError(
            "tool secret keyring cannot encrypt sandbox credentials"
        ) from exc


def decrypt_sandbox_credentials(envelope: str, *, job_id: str) -> dict[str, str]:
    """Decrypt a job's credential envelope in the Sandbox Worker.

    Fails closed when the envelope is malformed, was produced for a different
    job, or carries an unexpected purpose.
    """
    if not envelope or not isinstance(envelope, str):
        raise SandboxCredentialError("sandbox credential envelope is invalid")
    try:
        decoded = json.loads(decrypt_tool_secret(envelope))
    except (ToolSecretError, ValueError) as exc:
        raise SandboxCredentialError("sandbox credentials cannot be decrypted") from exc
    if not isinstance(decoded, dict):
        raise SandboxCredentialError("sandbox credentials payload is invalid")
    if decoded.get("purpose") != _CREDENTIAL_PURPOSE:
        raise SandboxCredentialError("sandbox credential envelope purpose mismatch")
    if str(decoded.get("job_id")) != str(job_id):
        raise SandboxCredentialError("sandbox credential envelope job mismatch")
    fields = decoded.get("fields")
    if not isinstance(fields, dict):
        raise SandboxCredentialError("sandbox credentials payload is invalid")
    return {str(key): str(value) for key, value in fields.items()}


def credential_file_path(workspace_tmp_dir: Path) -> Path:
    """Return a new, traversal-free credential file path inside the tmp dir."""
    return Path(workspace_tmp_dir) / f"{CREDENTIAL_FILE_PREFIX}{uuid4().hex}.json"


def write_credentials_file(path: Path, secrets: Mapping[str, str]) -> None:
    """Write a fresh mode-0600 JSON credential file for one execution."""
    payload = json.dumps(
        dict(secrets), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


__all__ = [
    "CREDENTIALS_ENV_VAR",
    "CREDENTIALS_METADATA_KEY",
    "CREDENTIAL_FILE_PREFIX",
    "SandboxCredentialError",
    "credential_file_path",
    "decrypt_sandbox_credentials",
    "encrypt_sandbox_credentials",
    "write_credentials_file",
]

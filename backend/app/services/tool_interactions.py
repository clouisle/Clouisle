"""Durable truth for server-initiated MCP interactions.

The live MCP worker owns the JSON-RPC request; this service owns the *human
decision* about it. A worker creates one row, waits on it with a bounded
budget, and the row is answered by an authorized member of its explicit
audience through ``/run-interactions``.

Durability rules enforced here:

* The database row is the only truth. Waiting polls the row (with an
  in-process wake-up for the same process); a response never "continues" a
  dead JSON-RPC call.
* Every transition out of ``pending`` is conditional (`status=pending`) and
  terminal. A response cannot revive ``expired``, ``cancelled`` or
  ``connection_lost``.
* Accepted elicitation content is encrypted with the platform Fernet key;
  payload previews stay display-safe and bounded.
* Form schemas that ask for credentials are rejected before a human sees them,
  and responses are validated against the stored schema — a client cannot add
  fields or change the request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.timezone import now_utc
from app.core.tool_secrets import (
    ToolSecretError,
    decrypt_tool_secret,
    encrypt_tool_secret,
)
from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionRequest,
    InteractionStatus,
)
from app.models.user import TeamMember, User
from app.schemas.response import BusinessError, ResponseCode

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 64 * 1024
MAX_SCHEMA_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_PREVIEW_MESSAGES = 20
MAX_STRING_VALUE = 4096
MAX_SCHEMA_PROPERTIES = 50
MAX_AUDIENCE_USERS = 50
MAX_AUDIENCE_ROLES = 10
MAX_LIST_SCAN = 500
MIN_TTL_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.25

_SENSITIVE_FIELD = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "credential",
    "authorization",
    "bearer",
    "cookie",
    "credit_card",
    "card_number",
    "cvv",
)
_ALLOWED_FORM_TYPES = {"string", "number", "integer", "boolean", "array"}
_ALLOWED_ARRAY_ITEMS = {"string"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _error(
    code: ResponseCode,
    message: str,
    *,
    msg_key: str,
    status_code: int,
) -> BusinessError:
    return BusinessError(
        code=code, msg=message, msg_key=msg_key, status_code=status_code
    )


def not_found() -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_NOT_FOUND,
        "Run interaction not found",
        msg_key="run_interaction_not_found",
        status_code=404,
    )


def access_denied() -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_ACCESS_DENIED,
        "You are not an authorized responder for this interaction",
        msg_key="run_interaction_access_denied",
        status_code=403,
    )


def _not_pending(status: InteractionStatus) -> BusinessError:
    if status == InteractionStatus.EXPIRED:
        return _error(
            ResponseCode.TOOL_INTERACTION_EXPIRED,
            "This interaction expired before it was answered",
            msg_key="run_interaction_expired",
            status_code=409,
        )
    if status == InteractionStatus.CONNECTION_LOST:
        return _error(
            ResponseCode.TOOL_INTERACTION_CONNECTION_LOST,
            "The MCP session that asked ended; start a new tool execution",
            msg_key="run_interaction_connection_lost",
            status_code=409,
        )
    return _error(
        ResponseCode.TOOL_INTERACTION_NOT_PENDING,
        "This interaction is no longer pending",
        msg_key="run_interaction_not_pending",
        status_code=409,
    )


def _invalid_response(message: str = "Invalid interaction response") -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_INVALID_RESPONSE,
        message,
        msg_key="run_interaction_invalid_response",
        status_code=422,
    )


def _schema_invalid(
    message: str = "Response does not match the requested schema",
) -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
        message,
        msg_key="run_interaction_schema_invalid",
        status_code=422,
    )


def _secret_rejected() -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_SECRET_FIELD_REJECTED,
        "Interactions may not request or submit credentials",
        msg_key="run_interaction_secret_field_rejected",
        status_code=422,
    )


def _too_large() -> BusinessError:
    return _error(
        ResponseCode.TOOL_INTERACTION_CONTENT_TOO_LARGE,
        "Interaction payload is too large",
        msg_key="run_interaction_content_too_large",
        status_code=413,
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_expired(value: datetime | None, now: datetime) -> bool:
    deadline = _as_utc(value)
    return deadline is not None and deadline <= now


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def contains_sensitive_name(value: str) -> bool:
    lowered = value.lower().replace("-", "_")
    return any(marker in lowered for marker in _SENSITIVE_FIELD)


def schema_requests_secrets(schema: Any) -> bool:
    """Whether a flat MCP form schema asks for a credential-like field."""
    if not isinstance(schema, Mapping):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return False
    for name, definition in properties.items():
        haystack = [str(name)]
        if isinstance(definition, Mapping):
            for key in ("title", "description", "format"):
                value = definition.get(key)
                if isinstance(value, str):
                    haystack.append(value)
        if any(contains_sensitive_name(item) for item in haystack):
            return True
    return False


def _normalize_audience(
    user_ids: Iterable[Any], roles: Iterable[Any] = ()
) -> dict[str, list[str]]:
    users: list[str] = []
    for raw in user_ids:
        value = str(raw)
        if value and value not in users:
            users.append(value)
    normalized_roles: list[str] = []
    for raw in roles:
        value = str(raw).strip()
        if value and value not in normalized_roles:
            normalized_roles.append(value)
    return {
        "user_ids": users[:MAX_AUDIENCE_USERS],
        "roles": normalized_roles[:MAX_AUDIENCE_ROLES],
    }


async def _role_map(user: User) -> dict[str, str]:
    rows = await TeamMember.filter(user_id=user.id).values("team_id", "role")
    return {str(row["team_id"]): str(row["role"]) for row in rows}


def audience_matches(
    interaction: InteractionRequest,
    user: User,
    roles: Mapping[str, str] | None = None,
) -> bool:
    """Explicit-audience check; run/tool read permission is not enough."""
    if not getattr(user, "is_active", True):
        return False
    audience = interaction.audience or {}
    if not isinstance(audience, Mapping):
        return False
    if str(user.id) in {str(item) for item in audience.get("user_ids") or []}:
        return True
    wanted_roles = {str(item) for item in audience.get("roles") or []}
    if wanted_roles and roles and interaction.team_id is not None:
        role = roles.get(str(interaction.team_id))
        if role is not None and role in wanted_roles:
            return True
    return False


async def _signal(interaction_id: UUID) -> None:
    event = _WAITERS.get(interaction_id)
    if event is not None:
        event.set()


_WAITERS: dict[UUID, asyncio.Event] = {}


def _waiter_event(interaction_id: UUID) -> asyncio.Event:
    event = _WAITERS.get(interaction_id)
    if event is None:
        event = asyncio.Event()
        _WAITERS[interaction_id] = event
    return event


def _drop_waiter(interaction_id: UUID, event: asyncio.Event) -> None:
    if _WAITERS.get(interaction_id) is event:
        _WAITERS.pop(interaction_id, None)


# ---------------------------------------------------------------------------
# Creation & bounded waiting
# ---------------------------------------------------------------------------


async def create_interaction(
    *,
    kind: InteractionKind,
    actor: User,
    team_id: UUID | None,
    payload: dict[str, Any],
    audience: Mapping[str, Sequence[str]],
    ttl_seconds: float,
    run_kind: str | None = None,
    run_id: UUID | None = None,
    execution_id: UUID | None = None,
    session_key: str | None = None,
    tool_id: UUID | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> InteractionRequest:
    """Persist one pending interaction with a hard answer deadline."""
    if (
        not isinstance(payload, dict)
        or _utf8_size(_canonical_json(payload)) > MAX_PAYLOAD_BYTES
    ):
        raise _too_large()
    ttl = max(MIN_TTL_SECONDS, float(ttl_seconds))
    deadline = now_utc() + timedelta(seconds=ttl)
    normalized_audience = _normalize_audience(
        audience.get("user_ids") or (), audience.get("roles") or ()
    )
    if not normalized_audience["user_ids"] and not normalized_audience["roles"]:
        # No addressee means nobody could ever answer: do not create a row
        # that looks answerable. Callers translate this into a protocol
        # decline/cancel.
        raise access_denied()
    interaction = InteractionRequest(
        id=uuid4(),
        kind=kind,
        status=InteractionStatus.PENDING,
        run_kind=run_kind,
        run_id=run_id,
        execution_id=execution_id,
        session_key=session_key,
        tool_id=tool_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        team_id=team_id,
        actor_user_id=actor.id,
        payload=payload,
        audience=normalized_audience,
        expires_at=deadline,
    )
    await interaction.save()
    if session_key:
        # The managed-session runtime owns the key; tell it a row now exists
        # so its close path knows it must terminate rows. Lazy import avoids a
        # module cycle (the runtime imports this service for that close).
        try:
            from app.services import mcp_session_runtime

            mcp_session_runtime.note_interaction_created(session_key)
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Unable to register interaction %s with its managed session",
                interaction.id,
                exc_info=True,
            )
    logger.info(
        "Created %s interaction %s for execution=%s run=%s",
        kind.value,
        interaction.id,
        execution_id,
        run_id,
    )
    return interaction


async def _reload(interaction_id: UUID) -> InteractionRequest:
    interaction = await InteractionRequest.filter(id=interaction_id).first()
    if interaction is None:
        raise not_found()
    return interaction


async def _terminate_if_pending(
    interaction_id: UUID, status: InteractionStatus
) -> InteractionRequest:
    now = now_utc()
    await InteractionRequest.filter(
        id=interaction_id, status=InteractionStatus.PENDING
    ).update(status=status, updated_at=now)
    await _signal(interaction_id)
    return await _reload(interaction_id)


async def wait_for_response(
    interaction_id: UUID,
    *,
    deadline_seconds: float,
    session_check: Any | None = None,
) -> InteractionRequest:
    """Wait for a human answer, the deadline, or live-session loss.

    ``session_check`` is an optional zero-argument callable returning a
    terminal :class:`InteractionStatus` (or ``None``) for the owning MCP
    session. The returned row is terminal: ``responded``, ``expired``,
    ``cancelled`` or ``connection_lost``. Nothing here replays a tool call.
    """
    loop = asyncio.get_running_loop()
    expires = loop.time() + max(float(deadline_seconds), MIN_TTL_SECONDS)
    event = _waiter_event(interaction_id)
    try:
        while True:
            interaction = await _reload(interaction_id)
            if interaction.status != InteractionStatus.PENDING:
                return interaction

            session_status = None
            if session_check is not None:
                try:
                    session_status = session_check()
                except Exception:  # pragma: no cover - defensive
                    session_status = InteractionStatus.CONNECTION_LOST
            if session_status is not None:
                return await _terminate_if_pending(interaction_id, session_status)

            now = now_utc()
            if _is_expired(interaction.expires_at, now):
                return await _terminate_if_pending(
                    interaction_id, InteractionStatus.EXPIRED
                )

            remaining = expires - loop.time()
            if remaining <= 0:
                return await _terminate_if_pending(
                    interaction_id, InteractionStatus.EXPIRED
                )

            event.clear()
            try:
                await asyncio.wait_for(
                    event.wait(), timeout=min(POLL_INTERVAL_SECONDS, remaining)
                )
            except TimeoutError:
                pass
    finally:
        _drop_waiter(interaction_id, event)


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------


def _schema_properties(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise _schema_invalid()
    if _utf8_size(_canonical_json(dict(schema))) > MAX_SCHEMA_BYTES:
        raise _too_large()
    if schema.get("type") != "object":
        raise _schema_invalid()
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        raise _schema_invalid()
    if len(properties) > MAX_SCHEMA_PROPERTIES:
        raise _too_large()
    if schema.get("additionalProperties") not in (None, False):
        raise _schema_invalid()
    return dict(properties)


def _validate_value(name: str, definition: Any, value: Any) -> Any:
    if contains_sensitive_name(name):
        raise _secret_rejected()
    if not isinstance(definition, Mapping):
        raise _schema_invalid()
    declared = definition.get("type")
    if declared not in _ALLOWED_FORM_TYPES:
        raise _schema_invalid(f"Unsupported field type for {name!r}")
    if isinstance(definition.get("format"), str) and definition["format"].lower() in {
        "password",
        "secret",
    }:
        raise _secret_rejected()

    if declared == "string":
        if not isinstance(value, str):
            raise _schema_invalid(f"Field {name!r} must be a string")
        max_length = _clamp_int(
            definition.get("maxLength"),
            default=MAX_STRING_VALUE,
            minimum=1,
            maximum=MAX_STRING_VALUE,
        )
        if len(value) > max_length:
            raise _schema_invalid(f"Field {name!r} is too long")
    elif declared == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _schema_invalid(f"Field {name!r} must be an integer")
    elif declared == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _schema_invalid(f"Field {name!r} must be a number")
        if isinstance(value, float) and not math.isfinite(value):
            raise _schema_invalid(f"Field {name!r} must be finite")
    elif declared == "boolean":
        if not isinstance(value, bool):
            raise _schema_invalid(f"Field {name!r} must be a boolean")
    elif declared == "array":
        items = definition.get("items")
        if (
            not isinstance(items, Mapping)
            or items.get("type") not in _ALLOWED_ARRAY_ITEMS
        ):
            raise _schema_invalid(f"Field {name!r} has an unsupported array item type")
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise _schema_invalid(f"Field {name!r} must be a list of strings")
        if len(value) > 100:
            raise _schema_invalid(f"Field {name!r} has too many items")

    enum = definition.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or value not in enum:
            raise _schema_invalid(f"Field {name!r} is not an allowed value")
    return value


def form_schema_supported(schema: Any) -> bool:
    """Whether the flat schema is one this platform can collect faithfully.

    Unsupported shapes (nested objects, non-string arrays, wrong top-level
    type) are declined before a row is created, so a human never sees a form
    that cannot be accepted.
    """
    try:
        properties = _schema_properties(schema)
    except BusinessError:
        return False
    for definition in properties.values():
        if not isinstance(definition, Mapping):
            return False
        if definition.get("type") not in _ALLOWED_FORM_TYPES:
            return False
        if definition.get("type") == "array":
            items = definition.get("items")
            if (
                not isinstance(items, Mapping)
                or items.get("type") not in _ALLOWED_ARRAY_ITEMS
            ):
                return False
        if isinstance(definition.get("format"), str) and definition[
            "format"
        ].lower() in {
            "password",
            "secret",
        }:
            return False
    required = schema.get("required") or []
    if not isinstance(required, list):
        return False
    return all(str(item) in properties for item in required)


def validate_form_content(schema: Any, content: Any) -> dict[str, Any]:
    """Validate a form acceptance against the stored flat JSON schema.

    Unknown fields, missing required fields, wrong primitives, non-finite
    numbers and credential-like names are rejected rather than coerced.
    """
    properties = _schema_properties(schema)
    if not isinstance(content, Mapping):
        raise _schema_invalid()
    if _utf8_size(_canonical_json(dict(content))) > MAX_RESPONSE_BYTES:
        raise _too_large()
    required = schema.get("required") or []
    if not isinstance(required, list):
        raise _schema_invalid()
    normalized: dict[str, Any] = {}
    for name in content:
        if str(name) not in properties:
            raise _schema_invalid(f"Unknown field {name!r}")
        normalized[str(name)] = _validate_value(
            str(name), properties[str(name)], content[name]
        )
    for name in required:
        if str(name) not in normalized:
            raise _schema_invalid(f"Missing required field {name!r}")
    return normalized


def _resolve_response_content(
    interaction: InteractionRequest,
    action: InteractionOutcome,
    content: Any,
) -> dict[str, Any] | None:
    if interaction.kind == InteractionKind.SAMPLING:
        if content is not None:
            raise _invalid_response("Sampling approval cannot carry content")
        return None

    payload = interaction.payload or {}
    mode = payload.get("mode") or "form"
    if mode == "url":
        if content is not None:
            raise _invalid_response("URL elicitation cannot carry content")
        return None
    if action == InteractionOutcome.ACCEPT:
        if content is None:
            raise _invalid_response("Accepting a form requires content")
        return validate_form_content(payload.get("requested_schema"), content)
    if content is not None:
        raise _invalid_response("Declining or cancelling cannot carry content")
    return None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def _response_digest(action: InteractionOutcome, content: Any) -> str:
    return _sha256(_canonical_json({"action": action.value, "content": content}))


def _normalize_action(action: Any) -> InteractionOutcome:
    try:
        return InteractionOutcome(str(action))
    except ValueError as exc:
        raise _invalid_response("Unknown interaction action") from exc


def _normalize_idempotency_key(value: Any) -> str:
    if not isinstance(value, str):
        raise _invalid_response("An idempotency key is required")
    key = value.strip()
    if not 8 <= len(key) <= 100:
        raise _invalid_response("The idempotency key must be 8-100 characters")
    return key


async def respond_to_interaction(
    interaction_id: UUID,
    user: User,
    *,
    action: Any,
    content: Any = None,
    idempotency_key: str,
) -> InteractionRequest:
    """Record one authorized, idempotent answer to a pending interaction."""
    normalized_action = _normalize_action(action)
    key = _normalize_idempotency_key(idempotency_key)

    initial = await _reload(interaction_id)
    if not audience_matches(initial, user, await _role_map(user)):
        raise access_denied()

    normalized_content = _resolve_response_content(initial, normalized_action, content)
    digest = _response_digest(normalized_action, normalized_content)

    current = await _reload(interaction_id)
    if current.status == InteractionStatus.PENDING and _is_expired(
        current.expires_at, now_utc()
    ):
        current = await _terminate_if_pending(interaction_id, InteractionStatus.EXPIRED)

    if current.status == InteractionStatus.RESPONDED:
        if current.response_idempotency_key == key:
            if current.response_digest == digest:
                return current
            raise _error(
                ResponseCode.TOOL_INTERACTION_IDEMPOTENCY_CONFLICT,
                "Idempotency key was reused for a different response",
                msg_key="run_interaction_invalid_response",
                status_code=409,
            )
        raise _not_pending(current.status)
    if current.status != InteractionStatus.PENDING:
        raise _not_pending(current.status)

    cipher = (
        encrypt_tool_secret(_canonical_json(normalized_content))
        if normalized_content is not None
        else None
    )
    now = now_utc()
    responded = await InteractionRequest.filter(
        id=interaction_id, status=InteractionStatus.PENDING
    ).update(
        status=InteractionStatus.RESPONDED,
        outcome=normalized_action,
        response_cipher=cipher,
        response_digest=digest,
        responded_by_id=user.id,
        responded_at=now,
        response_idempotency_key=key,
        answered_via="api",
        updated_at=now,
    )
    if not responded:
        # A concurrent decision won. Re-read and honour idempotent replay.
        latest = await _reload(interaction_id)
        if (
            latest.status == InteractionStatus.RESPONDED
            and latest.response_idempotency_key == key
            and latest.response_digest == digest
        ):
            return latest
        raise _not_pending(latest.status)

    await _signal(interaction_id)
    logger.info(
        "Interaction %s answered %s by user %s",
        interaction_id,
        normalized_action.value,
        user.id,
    )
    return await _reload(interaction_id)


def load_response_content(interaction: InteractionRequest) -> dict[str, Any] | None:
    """Decrypt an accepted form answer for its audience-only DTO."""
    if not interaction.response_cipher:
        return None
    try:
        raw = decrypt_tool_secret(interaction.response_cipher)
        value = json.loads(raw)
    except (ToolSecretError, json.JSONDecodeError):
        logger.warning(
            "Interaction %s response content cannot be decrypted", interaction.id
        )
        return None
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------------------
# Queries, expiry and terminal fan-out
# ---------------------------------------------------------------------------


async def expire_stale_interactions(limit: int = 200) -> int:
    """Mark pending rows whose hard deadline passed as ``expired``.

    Safe to run repeatedly from the existing maintenance sweep: only rows that
    are still ``pending`` are touched, and a later response cannot revive them.
    """
    now = now_utc()
    ids = await (
        InteractionRequest.filter(status=InteractionStatus.PENDING, expires_at__lte=now)
        .limit(limit)
        .values_list("id", flat=True)
    )
    if not ids:
        return 0
    updated = await InteractionRequest.filter(
        id__in=list(ids), status=InteractionStatus.PENDING
    ).update(status=InteractionStatus.EXPIRED, updated_at=now)
    if updated:
        logger.info("Expired %s stale run interaction(s)", updated)
    return int(updated)


async def _close_pending(
    *,
    status: InteractionStatus,
    session_key: str | None = None,
    execution_id: UUID | None = None,
    run_kind: str | None = None,
    run_id: UUID | None = None,
) -> int:
    if status == InteractionStatus.PENDING:
        raise ValueError("close status must be terminal")
    filters: dict[str, Any] = {"status": InteractionStatus.PENDING}
    if session_key is not None:
        filters["session_key"] = session_key
    elif execution_id is not None:
        filters["execution_id"] = execution_id
    elif run_kind is not None and run_id is not None:
        filters["run_kind"] = run_kind
        filters["run_id"] = run_id
    else:
        raise ValueError("a session, execution or run selector is required")
    ids = await (
        InteractionRequest.filter(**filters)
        .limit(MAX_LIST_SCAN)
        .values_list("id", flat=True)
    )
    if not ids:
        return 0
    updated = await InteractionRequest.filter(
        id__in=list(ids), status=InteractionStatus.PENDING
    ).update(status=status, updated_at=now_utc())
    for interaction_id in ids:
        await _signal(interaction_id)
    if updated:
        logger.info(
            "Closed %s pending interaction(s) as %s (%s)",
            updated,
            status.value,
            session_key or execution_id or run_id,
        )
    return int(updated)


async def close_pending_for_session(
    session_key: str, status: InteractionStatus = InteractionStatus.CONNECTION_LOST
) -> int:
    """Terminal fan-out when an owned MCP session ends with pending requests."""
    return await _close_pending(status=status, session_key=session_key)


async def close_interaction(
    interaction_id: UUID, status: InteractionStatus = InteractionStatus.CANCELLED
) -> InteractionRequest:
    """Terminally close one pending row (for example on caller cancellation)."""
    if status == InteractionStatus.PENDING:
        raise ValueError("close status must be terminal")
    return await _terminate_if_pending(interaction_id, status)


async def close_pending_for_execution(
    execution_id: UUID, status: InteractionStatus = InteractionStatus.CONNECTION_LOST
) -> int:
    return await _close_pending(status=status, execution_id=execution_id)


async def close_pending_for_run(
    run_kind: str, run_id: UUID, status: InteractionStatus = InteractionStatus.CANCELLED
) -> int:
    return await _close_pending(status=status, run_kind=run_kind, run_id=run_id)


async def get_interaction_for_user(
    interaction_id: UUID, user: User
) -> InteractionRequest:
    interaction = await _reload(interaction_id)
    if not audience_matches(interaction, user, await _role_map(user)):
        raise access_denied()
    if interaction.status == InteractionStatus.PENDING and _is_expired(
        interaction.expires_at, now_utc()
    ):
        interaction = await _terminate_if_pending(
            interaction_id, InteractionStatus.EXPIRED
        )
    return interaction


async def list_interactions_for_user(
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    kind: InteractionKind | None = None,
    status: InteractionStatus = InteractionStatus.PENDING,
    run_id: UUID | None = None,
) -> tuple[list[InteractionRequest], int]:
    """Pending (or terminal) interactions whose explicit audience includes ``user``."""
    if status == InteractionStatus.PENDING:
        await expire_stale_interactions()

    filters: dict[str, Any] = {"status": status}
    if kind is not None:
        filters["kind"] = kind
    if run_id is not None:
        filters["run_id"] = run_id
    rows = (
        await InteractionRequest.filter(**filters)
        .order_by("-created_at")
        .limit(MAX_LIST_SCAN)
    )
    roles = await _role_map(user)
    authorized = [row for row in rows if audience_matches(row, user, roles)]
    total = len(authorized)
    start = (page - 1) * page_size
    return authorized[start : start + page_size], total


__all__ = [
    "MAX_PAYLOAD_BYTES",
    "MAX_RESPONSE_BYTES",
    "audience_matches",
    "close_interaction",
    "close_pending_for_execution",
    "close_pending_for_run",
    "close_pending_for_session",
    "contains_sensitive_name",
    "create_interaction",
    "expire_stale_interactions",
    "form_schema_supported",
    "get_interaction_for_user",
    "list_interactions_for_user",
    "load_response_content",
    "respond_to_interaction",
    "schema_requests_secrets",
    "validate_form_content",
    "wait_for_response",
]

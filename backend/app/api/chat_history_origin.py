"""History-origin separation for end-user Agent chat.

One Agent conversation belongs to exactly one chat surface:

* the platform Agent Chat (JWT) - ``api_key_id`` is null;
* one API key (direct Agent API or embed) - ``api_key_id`` is that key.

Neither surface may read, continue or edit the other's history, and one key
never reaches another key's history even when both belong to the same user.
Records written before origin tracking existed have no ``api_key_id`` and are
the owner's own history. ``api_key_origin_unknown`` therefore exists only for
databases that ran the retired classification; nothing sets it any more, and a
row carrying it belongs to no chat surface while the Agent orchestration logs
still list it for its owner.

The conversation is the source of truth. ``AgentRun.api_key_id`` is checked as
well so a run whose credential disagrees with its conversation is resolved
closed instead of picking a side.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.response import BusinessError, ResponseCode


def history_origin_filter(api_key: Any = None) -> dict[str, Any]:
    """Query kwargs selecting the conversations of one chat surface."""
    if api_key is None:
        return {"api_key_id__isnull": True, "api_key_origin_unknown": False}
    key_id = getattr(api_key, "id", None)
    if key_id is None:
        # Fail closed: an unidentified credential must never fall back to the
        # platform (null key) history.
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="invalid_api_key",
            status_code=401,
        )
    return {"api_key_id": key_id, "api_key_origin_unknown": False}


def conversation_matches_origin(conversation: Any, api_key: Any = None) -> bool:
    """True when ``conversation`` belongs to the requesting chat surface."""
    if getattr(conversation, "api_key_origin_unknown", False):
        return False
    stored = getattr(conversation, "api_key_id", None)
    if api_key is None:
        return stored is None
    key_id = getattr(api_key, "id", None)
    if key_id is None:
        return False
    return stored is not None and str(stored) == str(key_id)


def _run_api_key_id(run: Any) -> UUID | None:
    """Credential a run was submitted with, from the row or its payload.

    The explicit column wins; runs written before the column existed carry the
    same evidence in the payload written by the submitting surface.
    """
    stored = getattr(run, "api_key_id", None)
    if stored is not None:
        return stored
    payload = getattr(run, "worker_payload", None)
    if not isinstance(payload, dict):
        return None
    raw = payload.get("api_key_id")
    if not raw and payload.get("tool_entrypoint") == "api_key":
        raw = payload.get("tool_entrypoint_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def run_matches_origin(run: Any, api_key: Any = None) -> bool:
    """True when ``run`` was submitted by the requesting chat surface.

    A run with no credential evidence is a platform-chat run, so it is never
    readable by an API key: absence of binding is not proof of ownership.
    """
    run_key_id = _run_api_key_id(run)
    if api_key is None:
        return run_key_id is None
    key_id = getattr(api_key, "id", None)
    if key_id is None or not getattr(api_key, "is_active", True):
        return False
    return run_key_id is not None and str(run_key_id) == str(key_id)

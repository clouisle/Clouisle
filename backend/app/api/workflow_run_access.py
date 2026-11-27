"""Run-history isolation for workflow runs.

A workflow run records the credential that created it, so the same workflow is
read through two deliberately different scopes:

- **User history** (``/workflows/{id}/runs/mine``) is the caller's own history.
  It only contains runs the caller started from the app, because API-key and
  embed traffic belongs to the integration that produced it, not to the key
  owner's personal list.
- **Integration history** (the same routes authenticated by an API key) contains
  exactly the runs that credential created: not a second key of the same owner
  and not the owner's app sessions.

Orchestration logs (``GET /workflows/runs``, ``GET /workflows/{id}/runs``, run
detail and node detail) are intentionally *not* isolated: they are the debugging
view of everything a workflow executed and stay gated by the existing workflow
log permissions. ``api_key_origin_unknown`` rows are visible there but excluded
from both histories, because no credential can prove it owns them.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.api import deps
from app.core.timezone import now_utc
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode

#: Permission an app session needs to read its own run history.
RUN_HISTORY_PERMISSION = "workflow:run"


def split_run_principal(auth_result: Any) -> tuple[User, APIKey | None]:
    """Accept the dual-auth dependency tuple and direct-user calls.

    ``deps.get_current_user_or_api_key`` resolves to ``(user, api_key)`` with
    ``api_key is None`` for a JWT session. Endpoint tests and internal callers
    pass the user alone, which means the same thing.
    """
    if isinstance(auth_result, tuple) and len(auth_result) == 2:
        return auth_result
    return auth_result, None


async def get_run_history_principal(
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> tuple[User, APIKey | None]:
    """Dual auth for run history that keeps the app session's permission gate.

    An API key acts with its own scope (the key's workflows and its owner's
    access) exactly like the workflow execution surfaces, while a JWT session
    still needs the global ``workflow:run`` permission it has always needed.
    """
    user, api_key = split_run_principal(auth_result)
    if api_key is None and not user.is_active:
        await deps.get_current_active_user(user)
    if api_key is None and not deps.user_has_global_permission(
        user, RUN_HISTORY_PERMISSION
    ):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="operation_not_permitted",
            status_code=403,
            permission=RUN_HISTORY_PERMISSION,
        )
    return user, api_key


def credential_is_usable(api_key: Any) -> bool:
    """Whether an in-memory key may still act on its own runs."""
    if getattr(api_key, "id", None) is None:
        return False
    if not getattr(api_key, "is_active", True):
        return False
    expires_at = getattr(api_key, "expires_at", None)
    return expires_at is None or expires_at > now_utc()


def session_run_filter(user: User) -> dict[str, Any]:
    """Filter kwargs for runs a user started from the app itself.

    API-key and embed runs are excluded even when the key belongs to the
    caller: they are the integration's history, not the user's. Legacy runs
    carry no key, so they stay in this view; ``api_key_origin_unknown`` only
    appears in databases that ran the retired classification, where those rows
    are deliberately kept out of personal history.
    """
    return {
        "triggered_by_id": user.id,
        "api_key_id__isnull": True,
        "api_key_origin_unknown": False,
    }


def api_key_run_filter(api_key: Any) -> dict[str, Any] | None:
    """Filter kwargs for runs one exact credential created; ``None`` = no rows.

    Binding needs the stored key id, so a revoked/expired key and an
    ``api_key_origin_unknown`` row can never match.
    """
    if not credential_is_usable(api_key):
        return None
    return {
        "triggered_by_id": api_key.user_id,
        "api_key_id": api_key.id,
        "api_key_origin_unknown": False,
    }


def run_history_filter(user: User, api_key: Any | None) -> dict[str, Any] | None:
    """Filter kwargs for the caller's own run history; ``None`` = no rows."""
    if api_key is None:
        return session_run_filter(user)
    return api_key_run_filter(api_key)


def api_key_may_read_run(run: Any, api_key: Any) -> bool:
    """Whether this exact credential, never merely its owner, created ``run``.

    Startup migration recovers known legacy origins into the stored column.
    No binding (including a web run) is never authorization for an API key.
    """
    if not credential_is_usable(api_key):
        return False
    key_owner_id = getattr(api_key, "user_id", None)
    run_owner_id = getattr(run, "triggered_by_id", None)
    if run_owner_id is None or str(run_owner_id) != str(key_owner_id):
        return False
    if getattr(run, "api_key_origin_unknown", False):
        return False
    return getattr(run, "api_key_id", None) == api_key.id


def run_not_found_error() -> BusinessError:
    """Uniform 404 for a run outside the caller's history.

    Deliberately indistinguishable from a missing run: whether another
    credential's run exists is not disclosed.
    """
    return BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="workflow_run_not_found",
        status_code=404,
    )


__all__ = [
    "RUN_HISTORY_PERMISSION",
    "api_key_may_read_run",
    "api_key_run_filter",
    "credential_is_usable",
    "get_run_history_principal",
    "run_history_filter",
    "run_not_found_error",
    "session_run_filter",
    "split_run_principal",
]

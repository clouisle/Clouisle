"""Authorization for protected generated assets."""

from __future__ import annotations


from app.api.conversation_access import can_access_conversation
from app.api.deps import check_api_key_agent_access, check_api_key_workflow_access
from app.models.agent import Conversation
from app.models.api_key import APIKey
from app.models.asset import Asset, AssetScopeRef, AssetScopeType, AssetStatus
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.schemas.response import BusinessError, ResponseCode


PROTECTED_FILE_CATEGORIES = frozenset(
    {"sandbox-artifacts", "generated-images", "generated-videos"}
)


async def authorize_protected_asset(
    storage_key: str,
    *,
    authenticated: tuple[User, APIKey | None] | None,
) -> Asset:
    """Authorize a protected file through its conversation or workflow scope."""
    if authenticated is None:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="not_authenticated",
            status_code=401,
        )

    user, api_key = authenticated
    asset = await Asset.filter(
        storage_key=storage_key,
        status=AssetStatus.AVAILABLE,
    ).first()
    if asset is None:
        raise _not_found()

    refs = await AssetScopeRef.filter(asset_id=asset.id)
    if not refs:
        raise _not_found()

    for ref in refs:
        if ref.scope_type == AssetScopeType.CONVERSATION:
            conversation = (
                await Conversation.filter(id=ref.scope_id)
                .prefetch_related("agent")
                .first()
            )
            if conversation is None or not await can_access_conversation(
                conversation, user
            ):
                continue
            try:
                await check_api_key_agent_access(api_key, conversation.agent_id)
            except BusinessError as error:
                if error.msg_key != "api_key_no_agent_access":
                    raise
                continue
            return asset

        if ref.scope_type == AssetScopeType.WORKFLOW_RUN:
            run = (
                await WorkflowRun.filter(id=ref.scope_id)
                .prefetch_related("workflow")
                .first()
            )
            if run is None or run.workflow_id is None:
                continue
            if not await _can_access_workflow_run(run, user):
                continue
            try:
                await check_api_key_workflow_access(api_key, run.workflow_id)
            except BusinessError as error:
                if error.msg_key != "api_key_no_workflow_access":
                    raise
                continue
            return asset

    raise BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="access_denied",
        status_code=403,
    )


async def _can_access_workflow_run(run: WorkflowRun, user: User) -> bool:
    from app.api.workflow_access import check_workflow_access

    if run.triggered_by_id == user.id or user.is_superuser:
        return True
    try:
        await check_workflow_access(run.workflow_id, user)
    except BusinessError:
        return False
    return True


def _not_found() -> BusinessError:
    return BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="file_not_found",
        status_code=404,
    )

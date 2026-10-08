"""Authorization for protected generated assets."""

from __future__ import annotations
from uuid import UUID


from app.api.conversation_access import can_access_conversation
from app.api.deps import check_api_key_agent_access, check_api_key_workflow_access
from app.models.agent import Conversation
from app.models.api_key import APIKey
from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetStatus,
)
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.schemas.response import BusinessError, ResponseCode


PROTECTED_FILE_CATEGORIES = frozenset(
    {"agent-attachments", "sandbox-artifacts", "generated-images", "generated-videos"}
)


async def authorize_asset_for_scope(
    asset_id: UUID,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None = None,
    expected_team_id: UUID | None = None,
) -> Asset:
    """Authorize an Asset against its owner/team and execution scope."""
    team_id = await _authorized_scope_team_id(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        api_key=api_key,
        expected_team_id=expected_team_id,
    )
    from app.services.asset import asset_service

    return await asset_service.get_authorized(
        asset_id,
        team_id=team_id,
        user_id=user.id if user is not None else None,
    )


async def resolve_authorized_asset_ref(
    ref: str,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None = None,
    expected_team_id: UUID | None = None,
) -> Asset:
    """Resolve a scope-local ref after authorizing its conversation or run."""
    team_id = await _authorized_scope_team_id(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        api_key=api_key,
        expected_team_id=expected_team_id,
    )
    from app.services.asset import asset_service

    return await asset_service.resolve_ref(
        scope_type=scope_type,
        scope_id=scope_id,
        ref=ref,
        team_id=team_id,
        user_id=user.id if user is not None else None,
    )


async def _authorized_scope_team_id(
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None,
    expected_team_id: UUID | None,
) -> UUID | None:
    if scope_type == AssetScopeType.CONVERSATION:
        conversation = (
            await Conversation.filter(id=scope_id).prefetch_related("agent").first()
        )
        if conversation is None or conversation.agent is None:
            raise _not_found()
        if user is None or not await can_access_conversation(conversation, user):
            raise _access_denied()
        try:
            await check_api_key_agent_access(api_key, conversation.agent_id)
        except BusinessError as error:
            if error.msg_key == "api_key_no_agent_access":
                raise _access_denied() from error
            raise
        team_id = conversation.agent.team_id
    elif scope_type == AssetScopeType.WORKFLOW_RUN:
        run = await WorkflowRun.filter(id=scope_id).prefetch_related("workflow").first()
        if run is None or run.workflow is None or run.workflow_id is None:
            raise _not_found()
        if user is not None and not await _can_access_workflow_run(run, user):
            raise _access_denied()
        try:
            await check_api_key_workflow_access(api_key, run.workflow_id)
        except BusinessError as error:
            if error.msg_key == "api_key_no_workflow_access":
                raise _access_denied() from error
            raise
        team_id = run.workflow.team_id
    else:
        raise _not_found()

    if expected_team_id is not None and team_id != expected_team_id:
        raise _access_denied()
    return team_id


def _access_denied() -> BusinessError:
    return BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="access_denied",
        status_code=403,
    )


async def authorize_protected_asset(
    storage_key: str,
    *,
    authenticated: tuple[User, APIKey | None] | None,
) -> Asset:
    """Authorize a protected file through any valid Asset scope."""
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
        if user.is_superuser or (
            api_key is None and getattr(asset, "created_by_id", None) == user.id
        ):
            return asset
        raise _not_found()

    for ref in refs:
        try:
            await authorize_asset_for_scope(
                asset.id,
                scope_type=ref.scope_type,
                scope_id=ref.scope_id,
                user=user,
                api_key=api_key,
            )
        except BusinessError as error:
            if error.status_code in (403, 404):
                continue
            raise
        return asset

    raise _access_denied()


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

"""System-superuser administration of Feishu Wiki to KB synchronization."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.api import deps
from app.models.feishu_knowledge import FeishuKnowledgeSource
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseStatus
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services import feishu_knowledge as service

router = APIRouter()


async def require_superuser(
    current_user: User = Depends(deps.get_current_active_user),
) -> User:
    if not current_user.is_superuser:
        raise BusinessError(
            code=ResponseCode.INSUFFICIENT_PRIVILEGES,
            msg_key="insufficient_privileges",
            status_code=403,
        )
    return current_user


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_base_id: UUID
    space_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=100)
    interval_minutes: int = Field(default=60, ge=1, le=43200)
    is_enabled: bool = True

    @field_validator("space_id", "name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    interval_minutes: int | None = Field(default=None, ge=1, le=43200)
    is_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Must not be blank")
        return value.strip() if value else value


def busy_error() -> BusinessError:
    return BusinessError(
        code=ResponseCode.BAD_REQUEST,
        msg_key="feishu_knowledge_source_busy",
        status_code=409,
    )


@router.get("/spaces", response_model=Response[list[dict[str, str]]])
async def list_spaces(current_user: User = Depends(require_superuser)) -> Any:
    try:
        client = await service.configured_client()
        return success(data=await client.list_wiki_spaces())
    except BusinessError:
        raise
    except Exception as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=service.public_error(exc),
            status_code=502,
        ) from exc


@router.get("/targets", response_model=Response[list[dict[str, str]]])
async def list_targets(current_user: User = Depends(require_superuser)) -> Any:
    targets = (
        await KnowledgeBase.filter(status=KnowledgeBaseStatus.ACTIVE.value)
        .prefetch_related("team")
        .order_by("name")
    )
    return success(
        data=[
            {"id": str(kb.id), "name": kb.name, "team_name": kb.team.name}
            for kb in targets
            if not kb.team.is_deleted
        ]
    )


@router.get("/sources", response_model=Response[list[dict[str, Any]]])
async def list_sources(current_user: User = Depends(require_superuser)) -> Any:
    sources = await FeishuKnowledgeSource.all().prefetch_related("knowledge_base")
    return success(data=[service.source_output(source) for source in sources])


@router.post("/sources", response_model=Response[dict[str, Any]])
async def create_source(
    data: SourceCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
) -> Any:
    client = await service.configured_client()
    # Reject mistyped/non-readable spaces before persisting an unusable source.
    try:
        spaces = await client.list_wiki_spaces()
    except Exception as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=service.public_error(exc),
            status_code=502,
        ) from exc
    if data.space_id not in {space["space_id"] for space in spaces}:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_knowledge_space_unavailable"
        )
    try:
        async with in_transaction() as connection:
            kb = (
                await KnowledgeBase.filter(
                    id=data.knowledge_base_id,
                    status=KnowledgeBaseStatus.ACTIVE.value,
                    team__is_deleted=False,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if not kb:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="feishu_knowledge_target_unavailable",
                )
            source = await FeishuKnowledgeSource.create(
                **data.model_dump(),
                created_by_id=current_user.id,
                using_db=connection,
                last_result={
                    "space_name": next(
                        space["name"]
                        for space in spaces
                        if space["space_id"] == data.space_id
                    )
                },
            )
    except IntegrityError as exc:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS,
            msg_key="feishu_knowledge_source_exists",
            status_code=409,
        ) from exc
    await AuditLogService.log(
        user=current_user,
        action="create_feishu_knowledge_source",
        resource_type="feishu_knowledge_source",
        resource_id=source.id,
        resource_name=source.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "knowledge_base_id": str(source.knowledge_base_id),
            "space_id": source.space_id,
        },
    )
    return success(data=service.source_output(await service.get_source(source.id)))


@router.put("/sources/{source_id}", response_model=Response[dict[str, Any]])
async def update_source(
    source_id: UUID,
    data: SourceUpdate,
    request: Request,
    current_user: User = Depends(require_superuser),
) -> Any:
    try:
        async with service.source_lock(source_id):
            source = await service.get_source(source_id)
            values = data.model_dump(exclude_none=True, exclude_unset=True)
            for key, value in values.items():
                setattr(source, key, value)
            if values.get("is_enabled") is False:
                source.dispatch_token = None
                source.lease_expires_at = None
                source.status = "idle"
            if "interval_minutes" in values or values.get("is_enabled"):
                source.next_sync_at = service.utcnow()
            await source.save()
    except service.SourceBusyError as exc:
        raise busy_error() from exc
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_knowledge_source",
        resource_type="feishu_knowledge_source",
        resource_id=source.id,
        resource_name=source.name,
        operation="update",
        status="success",
        request=request,
        metadata=values,
    )
    return success(data=service.source_output(source))


@router.post("/sources/{source_id}/sync", response_model=Response[dict[str, Any]])
async def sync_source(
    source_id: UUID,
    request: Request,
    current_user: User = Depends(require_superuser),
) -> Any:
    try:
        source = await service.queue_source(source_id)
    except service.SourceBusyError as exc:
        raise busy_error() from exc
    await AuditLogService.log(
        user=current_user,
        action="sync_feishu_knowledge_source",
        resource_type="feishu_knowledge_source",
        resource_id=source.id,
        resource_name=source.name,
        operation="update",
        status="success",
        request=request,
    )
    return success(data=service.source_output(source))


@router.delete("/sources/{source_id}", response_model=Response[dict[str, str]])
async def delete_source(
    source_id: UUID,
    request: Request,
    current_user: User = Depends(require_superuser),
) -> Any:
    source = await service.get_source(source_id)
    try:
        await service.delete_source(source_id)
    except service.SourceBusyError as exc:
        raise busy_error() from exc
    await AuditLogService.log(
        user=current_user,
        action="delete_feishu_knowledge_source",
        resource_type="feishu_knowledge_source",
        resource_id=source.id,
        resource_name=source.name,
        operation="delete",
        status="success",
        request=request,
    )
    return success(data={"id": str(source_id)})

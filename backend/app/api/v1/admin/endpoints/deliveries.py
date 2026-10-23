"""Administrator view of durable messaging integration deliveries.

The queue itself is provider-neutral; this read-only endpoint exposes delivery
outcomes so an operator can explain a message or artifact that never reached
the chat. Message text, provider resource keys and credentials are never
returned.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import PermissionChecker
from app.models.integration_delivery import IntegrationDelivery
from app.models.user import User
from app.schemas.response import Response, success

router = APIRouter()

DeliveryStatus = Literal[
    "pending", "sending", "sent", "error", "unavailable", "unknown"
]


class DeliveryOut(BaseModel):
    id: str
    provider_type: str
    run_id: str | None
    user_id: str | None
    agent_id: str | None
    chat_id: str | None
    message_id: str | None
    event_key: str
    sequence: int
    kind: str
    filename: str | None
    content_type: str | None
    size: int | None
    media_type: str | None
    status: str
    error: str | None
    error_detail: str | None
    has_media_key: bool
    created_at: datetime
    updated_at: datetime


class DeliveryPage(BaseModel):
    items: list[DeliveryOut]
    total: int
    limit: int
    offset: int


@router.get("", response_model=Response[DeliveryPage])
async def list_deliveries(
    provider_type: list[Literal["feishu", "wechat"]] | None = Query(None),
    status: list[DeliveryStatus] | None = Query(None),
    run_id: UUID | None = None,
    filename: str | None = Query(None, min_length=1, max_length=500),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
) -> Any:
    query = IntegrationDelivery.all()
    if provider_type:
        query = query.filter(provider_type__in=provider_type)
    if status:
        query = query.filter(status__in=status)
    if run_id:
        query = query.filter(run_id=run_id)
    if filename:
        query = query.filter(filename__icontains=filename.strip())

    total = await query.count()
    rows = await query.order_by("-created_at", "-id").offset(offset).limit(limit)
    return success(
        data=DeliveryPage(
            items=[
                DeliveryOut(
                    id=str(row.id),
                    provider_type=row.provider_type,
                    run_id=str(row.run_id) if row.run_id else None,
                    user_id=str(row.user_id) if row.user_id else None,
                    agent_id=str(row.agent_id) if row.agent_id else None,
                    chat_id=row.chat_id,
                    message_id=row.message_id,
                    event_key=row.event_key,
                    sequence=row.sequence,
                    kind=row.kind,
                    filename=row.filename,
                    content_type=row.content_type,
                    size=row.size,
                    media_type=row.media_type,
                    status=row.status,
                    error=row.error,
                    error_detail=row.error_detail,
                    has_media_key=bool(row.media_key),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    )

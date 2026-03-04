from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from tortoise.expressions import Q

from app.api import deps
from app.core.i18n import t
from app.models.memory import MemoryEntity, MemoryRelation
from app.models.user import User
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService

router = APIRouter()


class MemoryEntityUpdate(BaseModel):
    """Schema for updating memory entity"""

    description: Optional[str] = None
    properties: Optional[dict[str, Any]] = None


async def serialize_entity_with_user(entity: MemoryEntity) -> dict:
    """Serialize entity with user info"""
    # Fetch user if not prefetched
    if hasattr(entity, "_fetched_relations") and "user" in entity._fetched_relations:
        user = entity.user
    else:
        user = await entity.user

    # Count relations
    outgoing_count = await entity.outgoing_relations.all().count()
    incoming_count = await entity.incoming_relations.all().count()

    return {
        "id": str(entity.id),
        "user_id": str(entity.user_id),
        "user_name": user.username,
        "user_avatar_url": user.avatar_url,
        "name": entity.name,
        "entity_type": entity.entity_type,
        "description": entity.description,
        "properties": entity.properties,
        "access_count": entity.access_count,
        "last_accessed_at": entity.last_accessed_at.isoformat()
        if entity.last_accessed_at
        else None,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
        "outgoing_relations_count": outgoing_count,
        "incoming_relations_count": incoming_count,
    }


async def serialize_relation_with_entities(relation: MemoryRelation) -> dict:
    """Serialize relation with entity names"""
    # Fetch entities if not prefetched
    if (
        hasattr(relation, "_fetched_relations")
        and "source_entity" in relation._fetched_relations
    ):
        source_entity = relation.source_entity
    else:
        source_entity = await relation.source_entity

    if (
        hasattr(relation, "_fetched_relations")
        and "target_entity" in relation._fetched_relations
    ):
        target_entity = relation.target_entity
    else:
        target_entity = await relation.target_entity

    return {
        "id": str(relation.id),
        "user_id": str(relation.user_id),
        "source_entity_id": str(relation.source_entity_id),
        "source_entity_name": source_entity.name,
        "target_entity_id": str(relation.target_entity_id),
        "target_entity_name": target_entity.name,
        "relation_type": relation.relation_type,
        "description": relation.description,
        "properties": relation.properties,
        "created_at": relation.created_at.isoformat(),
    }


@router.get("/entities", response_model=Response[PageData[dict]])
async def list_entities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = None,
    entity_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(deps.PermissionChecker("memory:read")),
) -> Any:
    """
    List all memory entities (admin only).
    Supports filtering by user, entity type, and search.
    """
    # Build query
    query = MemoryEntity.all()

    if user_id:
        query = query.filter(user_id=user_id)

    if entity_type:
        query = query.filter(entity_type=entity_type)

    if search:
        query = query.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    # Get total count
    total = await query.count()

    # Get paginated results with user prefetch
    entities = (
        await query.prefetch_related("user")
        .order_by("-created_at")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    # Serialize entities
    items = []
    for entity in entities:
        items.append(await serialize_entity_with_user(entity))

    return success(
        data=PageData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/entities/stats", response_model=Response[dict])
async def get_stats(
    current_user: User = Depends(deps.PermissionChecker("memory:read")),
) -> Any:
    """
    Get memory statistics (admin only).
    Returns total entities, relations, and breakdowns by type and user.
    """
    # Total counts
    total_entities = await MemoryEntity.all().count()
    total_relations = await MemoryRelation.all().count()

    # By type
    by_type: dict[str, int] = {}
    type_results = (
        await MemoryEntity.all()
        .group_by("entity_type")
        .values("entity_type", count="id")
    )
    for result in type_results:
        by_type[result["entity_type"]] = result["count"]

    # By user (top 10)
    by_user: dict[str, int] = {}
    user_results = (
        await MemoryEntity.all().group_by("user_id").values("user_id", count="id")
    )
    # Sort by count and limit to 10
    sorted_results = sorted(user_results, key=lambda x: x["count"], reverse=True)[:10]
    for result in sorted_results:
        user = await User.get(id=result["user_id"])
        by_user[user.username] = result["count"]

    return success(
        data={
            "total_entities": total_entities,
            "total_relations": total_relations,
            "by_type": by_type,
            "by_user": by_user,
        }
    )


@router.get("/entities/{entity_id}", response_model=Response[dict])
async def get_entity(
    entity_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("memory:read")),
) -> Any:
    """
    Get single memory entity with relations (admin only).
    """
    entity = await MemoryEntity.filter(id=entity_id).prefetch_related("user").first()
    if not entity:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_entity_not_found",
        )

    # Get relations
    outgoing_relations = await entity.outgoing_relations.all().prefetch_related(
        "target_entity"
    )
    incoming_relations = await entity.incoming_relations.all().prefetch_related(
        "source_entity"
    )

    # Serialize
    entity_data = await serialize_entity_with_user(entity)
    entity_data["outgoing_relations"] = [
        await serialize_relation_with_entities(rel) for rel in outgoing_relations
    ]
    entity_data["incoming_relations"] = [
        await serialize_relation_with_entities(rel) for rel in incoming_relations
    ]

    return success(data=entity_data)


@router.put("/entities/{entity_id}", response_model=Response[dict])
async def update_entity(
    entity_id: UUID,
    data: MemoryEntityUpdate,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("memory:update")),
) -> Any:
    """
    Update memory entity (admin only).
    Only description and properties can be updated.
    """
    entity = await MemoryEntity.filter(id=entity_id).prefetch_related("user").first()
    if not entity:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_entity_not_found",
        )

    # Store old values for audit
    old_values = {
        "description": entity.description,
        "properties": entity.properties,
    }

    # Update fields
    if data.description is not None:
        entity.description = data.description
    if data.properties is not None:
        entity.properties = data.properties

    await entity.save()

    # Audit log
    await AuditLogService.log(
        user=current_user,
        action="update_memory_entity",
        resource_type="memory_entity",
        resource_id=entity_id,
        resource_name=entity.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": old_values,
            "after": {
                "description": entity.description,
                "properties": entity.properties,
            },
        },
        metadata={
            "entity_type": entity.entity_type,
            "owner_user_id": str(entity.user_id),
        },
    )

    return success(
        data=await serialize_entity_with_user(entity),
        msg=t("memory_entity_updated"),
    )


@router.delete("/entities/{entity_id}", response_model=Response[None])
async def delete_entity(
    entity_id: UUID,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("memory:delete")),
) -> Any:
    """
    Delete memory entity (admin only).
    Cascades to all relations.
    """
    entity = await MemoryEntity.filter(id=entity_id).prefetch_related("user").first()
    if not entity:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_entity_not_found",
        )

    entity_name = entity.name
    entity_type = entity.entity_type
    owner_user_id = str(entity.user_id)

    # Delete entity (cascades to relations)
    await entity.delete()

    # Audit log
    await AuditLogService.log(
        user=current_user,
        action="delete_memory_entity",
        resource_type="memory_entity",
        resource_id=entity_id,
        resource_name=entity_name,
        operation="delete",
        status="success",
        request=request,
        metadata={
            "entity_type": entity_type,
            "owner_user_id": owner_user_id,
        },
    )

    return success(msg=t("memory_entity_deleted"))


@router.get("/relations", response_model=Response[PageData[dict]])
async def list_relations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = None,
    relation_type: Optional[str] = None,
    current_user: User = Depends(deps.PermissionChecker("memory:read")),
) -> Any:
    """
    List all memory relations (admin only).
    Supports filtering by user and relation type.
    """
    # Build query
    query = MemoryRelation.all()

    if user_id:
        query = query.filter(user_id=user_id)

    if relation_type:
        query = query.filter(relation_type=relation_type)

    # Get total count
    total = await query.count()

    # Get paginated results with entity prefetch
    relations = (
        await query.prefetch_related("source_entity", "target_entity")
        .order_by("-created_at")
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    # Serialize relations
    items = []
    for relation in relations:
        items.append(await serialize_relation_with_entities(relation))

    return success(
        data=PageData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.delete("/relations/{relation_id}", response_model=Response[None])
async def delete_relation(
    relation_id: UUID,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("memory:delete")),
) -> Any:
    """
    Delete memory relation (admin only).
    """
    relation = (
        await MemoryRelation.filter(id=relation_id)
        .prefetch_related("source_entity", "target_entity")
        .first()
    )
    if not relation:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_relation_not_found",
        )

    source_name = relation.source_entity.name
    target_name = relation.target_entity.name
    relation_type = relation.relation_type
    owner_user_id = str(relation.user_id)

    # Delete relation
    await relation.delete()

    # Audit log
    await AuditLogService.log(
        user=current_user,
        action="delete_memory_relation",
        resource_type="memory_relation",
        resource_id=relation_id,
        resource_name=f"{source_name} -> {target_name}",
        operation="delete",
        status="success",
        request=request,
        metadata={
            "relation_type": relation_type,
            "source_entity": source_name,
            "target_entity": target_name,
            "owner_user_id": owner_user_id,
        },
    )

    return success(msg=t("memory_relation_deleted"))

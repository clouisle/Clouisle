"""
Memory API endpoints.
Provides CRUD operations for user memory entities and relations.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_current_user
from app.core.i18n import t
from app.models.user import User
from app.models.memory import MemoryEntity, MemoryRelation, EntityType, RelationType
from app.schemas.response import success, ResponseCode, BusinessError
from app.schemas.memory import (
    CreateEntityRequest,
    UpdateEntityRequest,
    CreateRelationRequest,
    EntityResponse,
    RelationResponse,
    EntityListResponse,
    MemoryGraphResponse,
)
from app.services.memory import MemoryService
from app.services.audit_log import AuditLogService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/entities", summary="List user's memory entities")
async def list_entities(
    current_user: User = Depends(get_current_user),
    entity_type: EntityType | None = Query(None, description="Filter by entity type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """List user's memory entities with optional filters."""
    query = MemoryEntity.filter(user_id=current_user.id)

    if entity_type:
        query = query.filter(entity_type=entity_type)

    # Get total count
    total = await query.count()

    # Get paginated results
    entities = await query.offset((page - 1) * page_size).limit(page_size).all()

    return success(
        EntityListResponse(
            items=[EntityResponse.model_validate(e) for e in entities],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/entities", summary="Create a memory entity")
async def create_entity(
    request: Request,
    body: CreateEntityRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new memory entity manually."""
    try:
        entity = await MemoryService.create_entity(
            user_id=current_user.id,
            name=body.name,
            entity_type=body.entity_type,
            description=body.description,
            properties=body.properties,
        )

        await AuditLogService.log(
            user=current_user,
            action="create_memory_entity",
            resource_type="memory_entity",
            resource_id=entity.id,
            resource_name=entity.name,
            operation="create",
            status="success",
            request=request,
            metadata={"entity_type": body.entity_type.value},
        )

        return success(EntityResponse.model_validate(entity))
    except Exception as e:
        logger.error(f"Failed to create entity: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="memory_entity_create_failed",
        )


@router.get("/entities/{entity_id}", summary="Get entity details")
async def get_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """Get memory entity details with relations."""
    entity = await MemoryEntity.filter(
        id=entity_id,
        user_id=current_user.id,
    ).first()

    if not entity:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_entity_not_found",
        )

    # Get relations
    outgoing = await MemoryRelation.filter(
        source_entity_id=entity_id,
        user_id=current_user.id,
    ).all()

    incoming = await MemoryRelation.filter(
        target_entity_id=entity_id,
        user_id=current_user.id,
    ).all()

    return success(
        {
            "entity": EntityResponse.model_validate(entity),
            "outgoing_relations": [
                RelationResponse.model_validate(r) for r in outgoing
            ],
            "incoming_relations": [
                RelationResponse.model_validate(r) for r in incoming
            ],
        }
    )


@router.put("/entities/{entity_id}", summary="Update entity")
async def update_entity(
    entity_id: UUID,
    request: Request,
    body: UpdateEntityRequest,
    current_user: User = Depends(get_current_user),
):
    """Update a memory entity."""
    try:
        # Check ownership
        entity = await MemoryEntity.filter(
            id=entity_id,
            user_id=current_user.id,
        ).first()

        if not entity:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="memory_entity_not_found",
            )

        # Update fields
        if body.name is not None:
            entity.name = body.name
        if body.description is not None:
            entity.description = body.description
        if body.properties is not None:
            entity.properties = {**entity.properties, **body.properties}

        await entity.save()

        # Update embedding if content changed
        if body.name or body.description:
            await MemoryService._update_entity_embedding(entity)

        await AuditLogService.log(
            user=current_user,
            action="update_memory_entity",
            resource_type="memory_entity",
            resource_id=entity.id,
            resource_name=entity.name,
            operation="update",
            status="success",
            request=request,
        )

        return success(EntityResponse.model_validate(entity))
    except BusinessError:
        raise
    except Exception as e:
        logger.error(f"Failed to update entity: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="memory_entity_update_failed",
        )


@router.delete("/entities/{entity_id}", summary="Delete entity")
async def delete_entity(
    entity_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Delete a memory entity and its relations."""
    try:
        # Capture entity name before deletion
        entity = await MemoryEntity.filter(
            id=entity_id, user_id=current_user.id
        ).first()
        entity_name = entity.name if entity else str(entity_id)

        await MemoryService.delete_entity(
            user_id=current_user.id,
            entity_id=entity_id,
        )

        await AuditLogService.log(
            user=current_user,
            action="delete_memory_entity",
            resource_type="memory_entity",
            resource_id=entity_id,
            resource_name=entity_name,
            operation="delete",
            status="success",
            request=request,
        )

        return success(
            {"message": t("memory_entity_deleted")},
            msg_key="memory_entity_deleted",
        )
    except ValueError:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_entity_not_found",
        )
    except Exception as e:
        logger.error(f"Failed to delete entity: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="memory_entity_delete_failed",
        )


@router.get("/relations", summary="List user's memory relations")
async def list_relations(
    current_user: User = Depends(get_current_user),
    entity_id: UUID | None = Query(
        None, description="Filter by entity ID (source or target)"
    ),
    relation_type: RelationType | None = Query(
        None, description="Filter by relation type"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """List user's memory relations with optional filters."""
    query = MemoryRelation.filter(user_id=current_user.id)

    if entity_id:
        # Find relations where entity is source or target
        from tortoise.expressions import Q

        query = query.filter(
            Q(source_entity_id=entity_id) | Q(target_entity_id=entity_id)
        )

    if relation_type:
        query = query.filter(relation_type=relation_type)

    # Get total count
    total = await query.count()

    # Get paginated results
    relations = await query.offset((page - 1) * page_size).limit(page_size).all()

    return success(
        {
            "items": [RelationResponse.model_validate(r) for r in relations],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/relations", summary="Create a memory relation")
async def create_relation(
    request: Request,
    body: CreateRelationRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new memory relation manually."""
    try:
        relation = await MemoryService.create_relation(
            user_id=current_user.id,
            source_entity_id=body.source_entity_id,
            target_entity_id=body.target_entity_id,
            relation_type=body.relation_type,
            description=body.description,
            properties=body.properties,
        )

        await AuditLogService.log(
            user=current_user,
            action="create_memory_relation",
            resource_type="memory_relation",
            resource_id=relation.id,
            resource_name=str(relation.id),
            operation="create",
            status="success",
            request=request,
            metadata={
                "source_entity_id": str(body.source_entity_id),
                "target_entity_id": str(body.target_entity_id),
                "relation_type": body.relation_type.value,
            },
        )

        return success(RelationResponse.model_validate(relation))
    except ValueError as e:
        msg_key = str(e)
        if msg_key in {
            "memory_source_entity_not_found",
            "memory_target_entity_not_found",
        }:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key=msg_key,
            )
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="memory_relation_create_failed",
        )
    except Exception as e:
        logger.error(f"Failed to create relation: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="memory_relation_create_failed",
        )


@router.delete("/relations/{relation_id}", summary="Delete relation")
async def delete_relation(
    relation_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Delete a memory relation."""
    try:
        await MemoryService.delete_relation(
            user_id=current_user.id,
            relation_id=relation_id,
        )

        await AuditLogService.log(
            user=current_user,
            action="delete_memory_relation",
            resource_type="memory_relation",
            resource_id=relation_id,
            resource_name=str(relation_id),
            operation="delete",
            status="success",
            request=request,
        )

        return success(
            {"message": t("memory_relation_deleted")},
            msg_key="memory_relation_deleted",
        )
    except ValueError:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="memory_relation_not_found",
        )
    except Exception as e:
        logger.error(f"Failed to delete relation: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="memory_relation_delete_failed",
        )


@router.get("/graph", summary="Get user's memory graph")
async def get_memory_graph(
    current_user: User = Depends(get_current_user),
    entity_ids: list[UUID] | None = Query(None, description="Filter by entity IDs"),
    max_depth: int = Query(1, ge=1, le=3, description="Graph traversal depth"),
):
    """Get user's memory graph for visualization."""
    if entity_ids:
        # Get subgraph around specific entities
        subgraph = await MemoryService.get_entity_subgraph(
            user_id=current_user.id,
            entity_ids=entity_ids,
            max_depth=max_depth,
        )
        entities = subgraph["entities"]
        relations = subgraph["relations"]
    else:
        # Get all entities and relations
        entities = await MemoryEntity.filter(user_id=current_user.id).all()
        relations = await MemoryRelation.filter(user_id=current_user.id).all()

    return success(
        MemoryGraphResponse(
            entities=[EntityResponse.model_validate(e) for e in entities],
            relations=[RelationResponse.model_validate(r) for r in relations],
        )
    )

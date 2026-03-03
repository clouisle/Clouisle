"""
Pydantic schemas for memory API.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.memory import EntityType, RelationType


# Request schemas
class CreateEntityRequest(BaseModel):
    """Request to create a memory entity."""

    name: str = Field(..., max_length=255, description="Entity name")
    entity_type: EntityType = Field(..., description="Entity type")
    description: str | None = Field(None, description="Entity description")
    properties: dict = Field(default_factory=dict, description="Additional properties")


class UpdateEntityRequest(BaseModel):
    """Request to update a memory entity."""

    name: str | None = Field(None, max_length=255, description="Entity name")
    description: str | None = Field(None, description="Entity description")
    properties: dict | None = Field(None, description="Properties to update")


class CreateRelationRequest(BaseModel):
    """Request to create a memory relation."""

    source_entity_id: UUID = Field(..., description="Source entity ID")
    target_entity_id: UUID = Field(..., description="Target entity ID")
    relation_type: RelationType = Field(..., description="Relation type")
    description: str | None = Field(None, description="Relation description")
    properties: dict = Field(default_factory=dict, description="Additional properties")


# Response schemas
class EntityResponse(BaseModel):
    """Memory entity response."""

    id: UUID
    user_id: UUID
    name: str
    entity_type: EntityType
    description: str | None
    properties: dict
    source_conversation_id: UUID | None
    source_message_id: UUID | None
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RelationResponse(BaseModel):
    """Memory relation response."""

    id: UUID
    user_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: RelationType
    description: str | None
    properties: dict
    source_conversation_id: UUID | None
    source_message_id: UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EntityWithRelationsResponse(BaseModel):
    """Entity with its relations."""

    entity: EntityResponse
    outgoing_relations: list[RelationResponse]
    incoming_relations: list[RelationResponse]


class MemoryGraphResponse(BaseModel):
    """Memory graph response."""

    entities: list[EntityResponse]
    relations: list[RelationResponse]


class EntityListResponse(BaseModel):
    """List of entities with pagination."""

    items: list[EntityResponse]
    total: int
    page: int
    page_size: int

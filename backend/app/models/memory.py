"""
Memory models for user memory graph.
Supports entity-relation graph structure for GraphRAG-ready architecture.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import User


class EntityType(str, Enum):
    """Entity types in memory graph"""

    PERSON = "person"  # User themselves or people they mention
    PREFERENCE = "preference"  # User preferences
    SKILL = "skill"  # Skills, technologies
    PROJECT = "project"  # Projects, work
    GOAL = "goal"  # Goals, objectives
    FACT = "fact"  # General facts
    CONCEPT = "concept"  # Abstract concepts
    ORGANIZATION = "organization"  # Companies, teams
    LOCATION = "location"  # Places
    CUSTOM = "custom"  # Other


class RelationType(str, Enum):
    """Relation types between entities"""

    PREFERS = "prefers"  # User prefers X
    WORKS_ON = "works_on"  # User works on X
    KNOWS = "knows"  # User knows X
    USES = "uses"  # User uses X
    WORKS_AT = "works_at"  # User works at X
    LOCATED_IN = "located_in"  # User/entity located in X
    HAS_GOAL = "has_goal"  # User has goal X
    RELATED_TO = "related_to"  # Generic relation
    PART_OF = "part_of"  # X is part of Y


class MemoryEntity(models.Model):
    """
    Entity in user's memory graph.
    Represents a node in the knowledge graph.
    """

    id = fields.UUIDField(pk=True)

    # User association
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User",
        related_name="memory_entities",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    # Entity content
    name = fields.CharField(
        max_length=255, description="Entity name (e.g., 'Python', 'E-commerce Project')"
    )
    entity_type = fields.CharEnumField(EntityType, default=EntityType.CUSTOM)
    description = fields.TextField(
        null=True, description="Detailed description"
    )

    # Metadata
    properties: dict = fields.JSONField(
        default=dict,
        description="Additional properties (e.g., {'level': 'expert', 'years': 5})",
    )  # type: ignore[assignment]

    # Source tracking
    source_conversation_id = fields.UUIDField(null=True)
    source_message_id = fields.UUIDField(null=True)

    # Vector embedding (stored in Qdrant)
    embedding_id = fields.CharField(max_length=100, null=True)
    embedding_model_id = fields.CharField(max_length=255, null=True, description="Embedding model identifier (e.g., 'bce-embedding-base_v1')")

    # Usage tracking
    access_count = fields.IntField(default=0)
    last_accessed_at = fields.DatetimeField(null=True)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Relations
    outgoing_relations: fields.ReverseRelation[MemoryRelation]
    incoming_relations: fields.ReverseRelation[MemoryRelation]

    class Meta:
        table = "memory_entities"
        unique_together = (("user_id", "name", "entity_type"),)
        indexes = [
            ("user_id", "entity_type"),
            ("user_id", "name"),
        ]

    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class MemoryRelation(models.Model):
    """
    Relation between entities in user's memory graph.
    Represents an edge in the knowledge graph.
    """

    id = fields.UUIDField(pk=True)

    # User association
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User",
        related_name="memory_relations",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    # Graph structure
    source_entity: fields.ForeignKeyRelation[MemoryEntity] = fields.ForeignKeyField(
        "models.MemoryEntity",
        related_name="outgoing_relations",
        on_delete=fields.CASCADE,
    )
    source_entity_id: UUID  # type: ignore[assignment]

    target_entity: fields.ForeignKeyRelation[MemoryEntity] = fields.ForeignKeyField(
        "models.MemoryEntity",
        related_name="incoming_relations",
        on_delete=fields.CASCADE,
    )
    target_entity_id: UUID  # type: ignore[assignment]

    relation_type = fields.CharEnumField(RelationType)

    # Relation metadata
    description = fields.TextField(null=True, description="Relation description")
    properties: dict = fields.JSONField(
        default=dict,
        description="Additional properties (e.g., {'since': '2024', 'confidence': 0.9})",
    )  # type: ignore[assignment]

    # Source tracking
    source_conversation_id = fields.UUIDField(null=True)
    source_message_id = fields.UUIDField(null=True)

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "memory_relations"
        unique_together = (
            (
                "user_id",
                "source_entity_id",
                "target_entity_id",
                "relation_type",
            ),
        )
        indexes = [
            ("user_id", "source_entity_id"),
            ("user_id", "target_entity_id"),
            ("user_id", "relation_type"),
        ]

    def __str__(self):
        return f"{self.source_entity_id} --[{self.relation_type}]--> {self.target_entity_id}"

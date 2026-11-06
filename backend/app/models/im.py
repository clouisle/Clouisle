from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User


class ImConversationType(str, Enum):
    DIRECT = "direct"
    SYSTEM = "system"


class ImMessageType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    CARD = "card"
    SYSTEM_NOTICE = "system_notice"
    # Any attachment (image or document); the client renders by content_type.
    FILE = "file"


class ImMessageStatus(str, Enum):
    NORMAL = "normal"
    RECALLED = "recalled"
    DELETED = "deleted"


class ImConversation(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)

    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="im_conversations",
        on_delete=fields.CASCADE,
    )
    team_id: UUID  # type: ignore[assignment]

    type = fields.CharEnumField(
        ImConversationType, max_length=20, default=ImConversationType.DIRECT
    )

    user1: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="im_conversations_as_user1",
        null=True,
        on_delete=fields.CASCADE,
    )
    user1_id: UUID | None  # type: ignore[assignment]

    user2: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="im_conversations_as_user2",
        null=True,
        on_delete=fields.CASCADE,
    )
    user2_id: UUID | None  # type: ignore[assignment]

    last_message_content = fields.TextField(null=True)
    last_message_at = fields.DatetimeField(null=True)
    latest_seq = fields.BigIntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "im_conversations"
        unique_together = (("team", "type", "user1", "user2"),)
        indexes = [
            ("team_id", "updated_at"),
            ("user1_id", "updated_at"),
            ("user2_id", "updated_at"),
        ]


class ImConversationParticipant(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)

    conversation: fields.ForeignKeyRelation["ImConversation"] = fields.ForeignKeyField(
        "models.ImConversation",
        related_name="participants",
        on_delete=fields.CASCADE,
    )
    conversation_id: UUID  # type: ignore[assignment]

    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="im_participations",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    last_read_seq = fields.BigIntField(default=0)
    is_pinned = fields.BooleanField(default=False)
    is_muted = fields.BooleanField(default=False)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "im_conversation_participants"
        unique_together = (("conversation", "user"),)
        indexes = [
            ("user_id", "is_pinned", "updated_at"),
            ("conversation_id", "user_id"),
        ]


class ImMessage(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)

    conversation: fields.ForeignKeyRelation["ImConversation"] = fields.ForeignKeyField(
        "models.ImConversation",
        related_name="messages",
        on_delete=fields.CASCADE,
    )
    conversation_id: UUID  # type: ignore[assignment]

    sender: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="im_messages_sent",
        null=True,
        on_delete=fields.SET_NULL,
    )
    sender_id: UUID | None  # type: ignore[assignment]

    client_msg_id = fields.CharField(max_length=64, null=True, index=True)
    seq = fields.BigIntField()

    msg_type = fields.CharEnumField(
        ImMessageType, max_length=30, default=ImMessageType.TEXT
    )
    content = fields.TextField()
    payload: dict | None = fields.JSONField(null=True)  # type: ignore[assignment]
    asset_id: UUID | None = fields.UUIDField(null=True)  # type: ignore[assignment]
    status = fields.CharEnumField(
        ImMessageStatus, max_length=20, default=ImMessageStatus.NORMAL
    )

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "im_messages"
        unique_together = (("conversation", "seq"),)
        indexes = [
            ("conversation_id", "seq"),
            ("conversation_id", "created_at"),
            ("client_msg_id",),
        ]

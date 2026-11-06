from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.im import ImMessageType

# 客户端可发送的消息类型：card / system_notice 只能由服务端内部生成，
# 否则客户端可伪造审批卡片等系统消息。
_CLIENT_MSG_TYPES = {
    ImMessageType.TEXT,
    ImMessageType.MARKDOWN,
    ImMessageType.FILE,
}


class DirectConversationCreate(BaseModel):
    team_id: UUID = Field(..., description="团队 ID")
    target_user_id: UUID = Field(..., description="聊天对象用户 ID")


class SendMessageRequest(BaseModel):
    content: str = Field(
        default="", max_length=10000, description="消息文本内容（附件消息为空）"
    )
    client_msg_id: str | None = Field(
        None, max_length=64, description="客户端生成的消息防重 ID"
    )
    msg_type: ImMessageType = Field(
        default=ImMessageType.TEXT,
        description="消息类型（客户端仅支持 text / markdown / file）",
    )
    payload: dict[str, Any] | None = Field(
        None, description="富交互结构体（如审批卡片状态等）"
    )
    asset_id: UUID | None = Field(None, description="图片/文件消息引用的资产 ID")

    @field_validator("msg_type")
    @classmethod
    def _validate_msg_type(cls, value: ImMessageType) -> ImMessageType:
        if value not in _CLIENT_MSG_TYPES:
            raise ValueError("msg_type must be one of text, markdown, file")
        return value

    @model_validator(mode="after")
    def _validate_attachment(self) -> SendMessageRequest:
        if self.msg_type == ImMessageType.FILE:
            if self.asset_id is None or self.content.strip():
                raise ValueError("file messages require an asset_id and empty content")
        elif self.asset_id is not None or not self.content.strip():
            raise ValueError("text messages require non-empty content and no asset_id")
        return self


class MarkReadRequest(BaseModel):
    up_to_seq: int | None = Field(
        None, ge=1, description="标记已读到的消息序列号，默认标记至最新"
    )


class ImPeerOut(BaseModel):
    id: str
    username: str
    full_name: str
    avatar_url: str | None = None


class ImConversationOut(BaseModel):
    id: str
    type: str
    team_id: str
    is_pinned: bool = False
    is_muted: bool = False
    last_read_seq: int = 0
    latest_seq: int = 0
    unread_count: int = 0
    last_message_content: str | None = None
    last_message_at: str | None = None
    peer: ImPeerOut | None = None
    created_at: str
    updated_at: str


class ImAttachmentOut(BaseModel):
    asset_id: str
    filename: str
    size: int
    content_type: str
    url: str


class ImMessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str | None = None
    client_msg_id: str | None = None
    seq: int
    msg_type: str
    content: str
    payload: dict[str, Any] | None = None
    status: str
    created_at: str
    attachment: ImAttachmentOut | None = None


class ImMessageListOut(BaseModel):
    messages: list[ImMessageOut]
    has_more: bool


class ImUnreadCountOut(BaseModel):
    total: int


class ImSearchResultOut(BaseModel):
    message_id: str
    conversation_id: str
    seq: int
    content: str
    msg_type: str
    conversation_type: str
    created_at: str
    peer: ImPeerOut | None = None

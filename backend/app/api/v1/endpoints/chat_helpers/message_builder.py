"""
Message building utilities for chat.
"""

from app.models.agent import Agent, Conversation, Message
from app.llm.types import LLMMessage, ContentPart, ImageContent
from .config import build_system_prompt_with_language


async def build_messages(
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    file_content: str | None = None,
    file_urls: list[dict] | None = None,
    user_locale: str | None = None,
) -> list[LLMMessage]:
    """Build messages for LLM including system prompt and history."""
    messages = []

    # Add system prompt with language instruction
    system_prompt = build_system_prompt_with_language(
        agent.system_prompt or "", user_locale
    )
    if system_prompt:
        messages.append(LLMMessage(role="system", content=system_prompt))

    # Add conversation history
    history_messages = await Message.filter(
        conversation_id=conversation.id, is_active=True
    ).order_by("created_at").all()

    for msg in history_messages:
        messages.append(
            LLMMessage(
                role=msg.role.value,
                content=msg.content,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                tool_name=msg.tool_name,
            )
        )

    # Add current user message
    if file_urls:
        # Build vision content with text and images
        content_parts = [ContentPart(type="text", text=user_message)]
        for file_url in file_urls:
            content_parts.append(
                ContentPart(
                    type="image",
                    image=ImageContent(
                        url=file_url["url"],
                        detail=file_url.get("detail", "auto"),
                    ),
                )
            )
        messages.append(LLMMessage(role="user", content=content_parts))
    elif file_content:
        # Add file content as context
        full_message = f"{user_message}\n\n[File Content]\n{file_content}"
        messages.append(LLMMessage(role="user", content=full_message))
    else:
        messages.append(LLMMessage(role="user", content=user_message))

    return messages

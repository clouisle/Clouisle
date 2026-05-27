from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from tortoise.expressions import Q

from app.models.agent import (
    ConversationSessionMemory,
    ConversationSessionMemoryStatus,
    Message,
)


def get_version_root_id(message: Message) -> UUID:
    return message.parent_id or message.id


async def get_message_version_group(message: Message) -> list[Message]:
    root_id = get_version_root_id(message)
    versions = await Message.filter(Q(id=root_id) | Q(parent_id=root_id)).all()
    versions.sort(key=lambda item: item.version_number)
    return versions


async def get_version_count(message: Message) -> int:
    root_id = get_version_root_id(message)
    return await Message.filter(Q(id=root_id) | Q(parent_id=root_id)).count()


def _is_canonical_visible(message: Message) -> bool:
    return message.round_id is None or message.is_round_canonical


async def get_active_canonical_path(conversation_id: UUID) -> list[Message]:
    messages = await Message.filter(
        conversation_id=conversation_id,
        is_active=True,
    ).order_by("created_at", "id")
    return [message for message in messages if _is_canonical_visible(message)]


async def get_visible_conversation_messages(
    conversation_id: UUID,
    *,
    before_created_at=None,
    exclude_message_ids: Iterable[UUID] | None = None,
) -> list[Message]:
    query = Message.filter(conversation_id=conversation_id, is_active=True)
    if before_created_at is not None:
        query = query.filter(created_at__lt=before_created_at)
    if exclude_message_ids:
        query = query.exclude(id__in=list(exclude_message_ids))
    return await query.order_by("created_at", "id")


async def get_last_active_canonical_message(conversation_id: UUID) -> Message | None:
    path = await get_active_canonical_path(conversation_id)
    return path[-1] if path else None


async def get_prefix_path_before(message: Message) -> list[Message]:
    if message.branch_parent_id:
        all_messages = await Message.filter(
            conversation_id=message.conversation_id
        ).all()
        message_by_id = {item.id: item for item in all_messages}
        prefix: list[Message] = []
        current_id = message.branch_parent_id
        seen: set[UUID] = set()

        while current_id and current_id not in seen:
            current = message_by_id.get(current_id)
            if not current:
                break
            seen.add(current_id)
            if _is_canonical_visible(current):
                prefix.append(current)
            current_id = current.branch_parent_id

        if prefix:
            prefix.reverse()
            return prefix

    path = await get_active_canonical_path(message.conversation_id)
    return [item for item in path if item.created_at < message.created_at]


async def _select_descendant_child(parent: Message) -> Message | None:
    children = await Message.filter(
        conversation_id=parent.conversation_id,
        branch_parent_id=parent.id,
    ).order_by("-is_active", "-created_at", "-id")
    for child in children:
        if _is_canonical_visible(child):
            return child
    return None


async def find_descendant_branch_from(message: Message) -> list[Message]:
    branch = [message]
    current = message
    seen = {message.id}
    while True:
        child = await _select_descendant_child(current)
        if not child or child.id in seen:
            break
        branch.append(child)
        seen.add(child.id)
        current = child
    return branch


async def activate_conversation_branch(
    conversation_id: UUID,
    canonical_path: Iterable[Message],
) -> None:
    canonical_ids = [message.id for message in canonical_path]
    round_ids = [
        message.round_id for message in canonical_path if message.round_id is not None
    ]

    active_ids = set(canonical_ids)
    if round_ids:
        round_steps = await Message.filter(
            conversation_id=conversation_id,
            round_id__in=round_ids,
            is_round_canonical=False,
        ).all()
        active_ids.update(message.id for message in round_steps)

    await Message.filter(conversation_id=conversation_id).update(is_active=False)
    if active_ids:
        await Message.filter(id__in=list(active_ids)).update(is_active=True)


async def is_message_on_active_branch(
    conversation_id: UUID,
    message_id: UUID,
    *,
    before_created_at=None,
) -> bool:
    query = Message.filter(
        conversation_id=conversation_id,
        id=message_id,
        is_active=True,
    )
    if before_created_at is not None:
        query = query.filter(created_at__lt=before_created_at)
    return await query.exists()


async def stale_session_memory_if_source_outside_active_branch(
    conversation_id: UUID,
) -> None:
    snapshot = await ConversationSessionMemory.filter(
        conversation_id=conversation_id,
        status=ConversationSessionMemoryStatus.READY,
    ).first()
    if not snapshot or not snapshot.source_message_id:
        return
    if await is_message_on_active_branch(conversation_id, snapshot.source_message_id):
        return
    snapshot.status = ConversationSessionMemoryStatus.STALE
    await snapshot.save(update_fields=["status", "updated_at"])

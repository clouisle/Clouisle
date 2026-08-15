from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.models.agent import (
    Conversation,
    ConversationSessionMemory,
    ConversationSessionMemoryStatus,
    Message,
    MessageRole,
    MessageRoundRole,
)


def get_version_root_id(message: Message) -> UUID:
    return message.parent_id or message.id


async def get_message_version_group(message: Message) -> list[Message]:
    root_id = get_version_root_id(message)
    versions = await _version_group_query(root_id).all()
    versions.sort(key=lambda item: item.version_number)
    return versions


async def get_version_count(message: Message) -> int:
    root_id = get_version_root_id(message)
    return await _version_group_query(root_id).count()


def _version_group_query(root_id: UUID):
    """Messages that are real versions of a group: the root plus canonical
    children. Excludes round steps (tool calls/results) that carry
    parent_id=root, which would otherwise inflate version counts."""
    return Message.filter(
        Q(id=root_id) | Q(parent_id=root_id),
        Q(round_id__isnull=True) | Q(is_round_canonical=True),
    )


def _is_canonical_visible(message: Message) -> bool:
    return message.round_id is None or message.is_round_canonical


# Chain walks only inspect these fields; trimming the queries avoids reading
# large `content`/`jsonb` columns for every message in a conversation.
_CHAIN_WALK_FIELDS = (
    "id",
    "parent_id",
    "branch_parent_id",
    "round_id",
    "round_role",
    "is_round_canonical",
    "is_active",
    "version_number",
    "created_at",
)


def _descendant_sort_key(message: Message):
    """Match the old SQL ordering (-is_active, -created_at, -id): active first,
    then NEWEST, then descending id tiebreak."""
    return (
        -int(message.is_active),
        -message.created_at.timestamp(),
        -message.id.int,
    )


def _pick_descendant_child(
    children: list[Message], *, skip_group_root: UUID | None
) -> Message | None:
    for child in children:
        if not _is_canonical_visible(child):
            continue
        if skip_group_root is not None and child.parent_id == skip_group_root:
            # A version sibling of the branch root (e.g. the edited copy of a
            # user message). Its subtree belongs to a different version, so the
            # branch ends before it.
            continue
        return child
    return None


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
    limit: int | None = None,
) -> list[Message]:
    query = Message.filter(conversation_id=conversation_id, is_active=True)
    if before_created_at is not None:
        query = query.filter(created_at__lt=before_created_at)
    if exclude_message_ids:
        query = query.exclude(id__in=list(exclude_message_ids))
    if limit is None:
        return await query.order_by("created_at", "id")

    messages = await query.order_by("-created_at", "-id").limit(limit * 8)
    visible = [message for message in messages if _is_canonical_visible(message)]
    visible = visible[:limit]
    visible.reverse()
    return visible


async def get_visible_conversation_messages_after(
    conversation_id: UUID,
    *,
    after_message_id: UUID,
    before_created_at=None,
    exclude_message_ids: Iterable[UUID] | None = None,
) -> list[Message] | None:
    """Load visible active-branch messages strictly after a checkpoint watermark."""
    anchor = await Message.filter(
        conversation_id=conversation_id,
        id=after_message_id,
        is_active=True,
    ).first()
    if not anchor:
        return None
    if before_created_at is not None and anchor.created_at >= before_created_at:
        return []

    query = Message.filter(
        conversation_id=conversation_id,
        is_active=True,
        created_at__gte=anchor.created_at,
    )
    if before_created_at is not None:
        query = query.filter(created_at__lt=before_created_at)
    if exclude_message_ids:
        query = query.exclude(id__in=list(exclude_message_ids))

    messages = await query.order_by("created_at", "id")
    for index, message in enumerate(messages):
        if message.id == after_message_id:
            return messages[index + 1 :]
    return None


async def get_last_active_canonical_message(conversation_id: UUID) -> Message | None:
    path = await get_active_canonical_path(conversation_id)
    return path[-1] if path else None


async def get_prefix_path_before(
    message: Message, *, limit: int | None = None, trimmed: bool = True
) -> list[Message]:
    if message.branch_parent_id and limit is None:
        query = Message.filter(conversation_id=message.conversation_id)
        all_messages = await (
            query.only(*_CHAIN_WALK_FIELDS) if trimmed else query
        ).all()
        message_by_id = {item.id: item for item in all_messages}
        prefix: list[Message] = []
        current_id: UUID | None = message.branch_parent_id
        seen: set[UUID] = set()

        while current_id and current_id not in seen:
            current = message_by_id.get(current_id)
            if not current:
                break
            seen.add(current_id)
            # Skip deactivated links (superseded versions / abandoned replies)
            # but keep walking their parent so older history survives.
            if _is_canonical_visible(current) and current.is_active:
                prefix.append(current)
            current_id = current.branch_parent_id

        if prefix:
            prefix.reverse()
            # Legacy conversations can contain a non-empty but truncated parent
            # chain. Preserve the active canonical history before the oldest
            # linked message instead of treating that partial chain as complete.
            oldest_created_at = prefix[0].created_at
            earlier_candidates = [
                item
                for item in all_messages
                if item.id not in seen
                and _is_canonical_visible(item)
                and item.created_at < oldest_created_at
            ]
            earlier_prefix = [item for item in earlier_candidates if item.is_active]

            # A previous faulty switch may already have deactivated that history.
            # Recover the newest pre-gap branch through its remaining parent links.
            if not earlier_prefix and earlier_candidates:
                current = max(
                    earlier_candidates,
                    key=lambda item: (item.created_at, str(item.id)),
                )
                recovered: list[Message] = []
                recovered_seen = set(seen)
                while current.id not in recovered_seen:
                    recovered_seen.add(current.id)
                    recovered.append(current)
                    if current.branch_parent_id is None:
                        break
                    parent = message_by_id.get(current.branch_parent_id)
                    if parent is None or not _is_canonical_visible(parent):
                        break
                    current = parent
                recovered.reverse()
                earlier_prefix = recovered

            earlier_prefix.sort(key=lambda item: (item.created_at, str(item.id)))
            return [*earlier_prefix, *prefix]

        path = await get_active_canonical_path(message.conversation_id)
        return [item for item in path if item.created_at < message.created_at]

    if message.branch_parent_id and limit is not None:
        prefix = []
        current_id = message.branch_parent_id
        seen = set()
        scan_limit = limit * 8

        while current_id and current_id not in seen and len(seen) < scan_limit:
            query = Message.filter(
                conversation_id=message.conversation_id,
                id=current_id,
            )
            current = await (
                query.only(*_CHAIN_WALK_FIELDS) if trimmed else query
            ).first()
            if not current:
                break
            seen.add(current_id)
            if _is_canonical_visible(current) and current.is_active:
                prefix.append(current)
                if len(prefix) == limit:
                    break
            current_id = current.branch_parent_id

        if prefix:
            prefix.reverse()
            if len(prefix) < limit:
                full_prefix = await get_prefix_path_before(message, trimmed=trimmed)
                return full_prefix[-limit:]
            return prefix

    return await get_visible_conversation_messages(
        message.conversation_id,
        before_created_at=message.created_at,
        limit=limit,
    )


async def _select_descendant_child(
    parent: Message, *, skip_group_root: UUID | None = None
) -> Message | None:
    children = (
        await Message.filter(
            conversation_id=parent.conversation_id,
            branch_parent_id=parent.id,
        )
        .only(*_CHAIN_WALK_FIELDS)
        .order_by("-is_active", "-created_at", "-id")
    )
    return _pick_descendant_child(children, skip_group_root=skip_group_root)


async def find_descendant_branch_from(message: Message) -> list[Message]:
    root_id = get_version_root_id(message)
    # One query instead of one per branch hop (N+1).
    messages = (
        await Message.filter(conversation_id=message.conversation_id)
        .only(*_CHAIN_WALK_FIELDS)
        .all()
    )
    children_by_parent: dict[UUID, list[Message]] = {}
    for item in messages:
        children_by_parent.setdefault(item.branch_parent_id, []).append(item)

    branch = [message]
    current = message
    seen = {message.id}
    while True:
        children = sorted(
            children_by_parent.get(current.id, []), key=_descendant_sort_key
        )
        child = _pick_descendant_child(children, skip_group_root=root_id)
        if not child or child.id in seen:
            break
        branch.append(child)
        seen.add(child.id)
        current = child
    return branch


async def activate_conversation_branch(
    conversation_id: UUID,
    canonical_path: Iterable[Message],
    *,
    using_db: BaseDBAsyncClient | None = None,
) -> None:
    if using_db is None:
        # Serialize concurrent branch-state transitions: the read of
        # current_active and the deactivate/activate updates below must not
        # interleave with another activation that read the same set, or two
        # competing version switches could leave both alternatives active.
        async with in_transaction() as conn:
            await (
                Conversation.filter(id=conversation_id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            await activate_conversation_branch(
                conversation_id, canonical_path, using_db=conn
            )
        return
    # Version-group invariant: members of one version group are alternatives,
    # so a path may never activate more than one of them. If a polluted branch
    # chain contributed both an old version and its replacement, keep the
    # newest version and drop the old one together with its round's canonical
    # messages (the old reply), so superseded turns cannot resurface.
    newest_by_root: dict[UUID, Message] = {}
    dropped_round_ids: set[UUID] = set()
    for message in canonical_path:
        root = get_version_root_id(message)
        current = newest_by_root.get(root)
        if current is None or message.version_number > current.version_number:
            if current is not None and current.round_id:
                dropped_round_ids.add(current.round_id)
            newest_by_root[root] = message
        elif message.round_id:
            dropped_round_ids.add(message.round_id)

    kept_ids = {message.id for message in newest_by_root.values()}
    canonical_path = [
        message
        for message in canonical_path
        if message.id in kept_ids
        and (
            message.round_id is None
            or message.round_id not in dropped_round_ids
            # The kept user version shares its round with the dropped old
            # assistant reply - never take the user message down with it.
            or message.round_role == MessageRoundRole.USER_INPUT
            or getattr(message, "role", None) in (MessageRole.USER, "user")
        )
    ]

    canonical_ids = [message.id for message in canonical_path]
    # Only activate round steps that belong to an assistant-final message in the
    # path. The user message shares its round with the (now-deactivated) old
    # assistant reply; including that round would re-activate the previous
    # version's tool calls/results as residue.
    round_ids = [
        message.round_id
        for message in canonical_path
        if message.round_id is not None
        and message.round_role == MessageRoundRole.ASSISTANT_FINAL
    ]

    active_ids = set(canonical_ids)
    if round_ids:
        round_steps = (
            await Message.filter(
                conversation_id=conversation_id,
                round_id__in=round_ids,
                is_round_canonical=False,
            )
            .using_db(using_db)
            .all()
        )
        active_ids.update(message.id for message in round_steps)

    # Difference-set activation: only touch messages whose state actually
    # changes instead of rewriting the whole conversation on every call.
    current_active = {
        message.id
        for message in await Message.filter(
            conversation_id=conversation_id, is_active=True
        )
        .only("id")
        .using_db(using_db)
        .all()
    }

    deactivate_ids = current_active - active_ids
    if deactivate_ids:
        await (
            Message.filter(id__in=list(deactivate_ids))
            .using_db(using_db)
            .update(is_active=False)
        )
    activate_ids = active_ids - current_active
    if activate_ids:
        await (
            Message.filter(id__in=list(activate_ids))
            .using_db(using_db)
            .update(is_active=True)
        )


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

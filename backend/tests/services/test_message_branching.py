from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.models.agent import ConversationSessionMemoryStatus
from app.services import message_branching as branching


def message(**overrides):
    values = {
        "id": uuid4(),
        "parent_id": None,
        "branch_parent_id": None,
        "conversation_id": uuid4(),
        "round_id": None,
        "round_role": None,
        "is_round_canonical": True,
        "is_active": True,
        "version_number": 1,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def query(**methods):
    value = MagicMock()
    for name, result in methods.items():
        setattr(value, name, AsyncMock(return_value=result))
    value.filter.return_value = value
    value.exclude.return_value = value
    value.order_by.return_value = methods.get("order_by", value)
    value.using_db.return_value = value
    value.only.return_value = value
    return value


def test_get_version_root_id_uses_parent_or_self():
    root_id = uuid4()
    assert branching.get_version_root_id(message(parent_id=root_id)) == root_id

    standalone = message()
    assert branching.get_version_root_id(standalone) == standalone.id


@pytest.mark.anyio
async def test_version_group_is_sorted_and_counted():
    root = message(version_number=1)
    later = message(parent_id=root.id, version_number=3)
    middle = message(parent_id=root.id, version_number=2)
    group_query = query(all=[later, root, middle])
    count_query = query(count=3)

    with patch.object(
        branching.Message, "filter", side_effect=[group_query, count_query]
    ) as message_filter:
        assert await branching.get_message_version_group(middle) == [
            root,
            middle,
            later,
        ]
        assert await branching.get_version_count(middle) == 3

    assert message_filter.call_count == 2
    group_query.all.assert_awaited_once()
    count_query.count.assert_awaited_once()


@pytest.mark.anyio
async def test_active_canonical_path_filters_round_steps():
    visible = message()
    canonical_round = message(round_id=uuid4(), is_round_canonical=True)
    hidden_round_step = message(
        round_id=canonical_round.round_id, is_round_canonical=False
    )
    orm = query(order_by=[visible, hidden_round_step, canonical_round])

    with patch.object(branching.Message, "filter", return_value=orm) as message_filter:
        result = await branching.get_active_canonical_path(visible.conversation_id)

    assert result == [visible, canonical_round]
    message_filter.assert_called_once_with(
        conversation_id=visible.conversation_id, is_active=True
    )
    orm.order_by.assert_called_once_with("created_at", "id")


@pytest.mark.anyio
async def test_visible_messages_applies_optional_filters_and_exclusions():
    conversation_id = uuid4()
    cutoff = datetime.now(UTC)
    excluded = [uuid4(), uuid4()]
    expected = [message(conversation_id=conversation_id)]
    orm = query(order_by=expected)

    with patch.object(branching.Message, "filter", return_value=orm):
        result = await branching.get_visible_conversation_messages(
            conversation_id,
            before_created_at=cutoff,
            exclude_message_ids=excluded,
        )

    assert result == expected
    orm.filter.assert_called_once_with(created_at__lt=cutoff)
    orm.exclude.assert_called_once_with(id__in=excluded)
    orm.order_by.assert_called_once_with("created_at", "id")


@pytest.mark.anyio
async def test_visible_messages_skips_empty_optional_filters():
    orm = query(order_by=[])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.get_visible_conversation_messages(uuid4()) == []

    orm.filter.assert_not_called()
    orm.exclude.assert_not_called()


@pytest.mark.anyio
async def test_visible_messages_after_keeps_active_tool_steps():
    conversation_id = uuid4()
    anchor = message(conversation_id=conversation_id)
    tool_step = message(
        conversation_id=conversation_id,
        round_id=uuid4(),
        is_round_canonical=False,
        created_at=anchor.created_at + timedelta(seconds=1),
    )
    follow_up = message(
        conversation_id=conversation_id,
        created_at=anchor.created_at + timedelta(seconds=2),
    )
    anchor_query = query(first=anchor)
    tail_query = query(order_by=[anchor, tool_step, follow_up])

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[anchor_query, tail_query],
    ):
        result = await branching.get_visible_conversation_messages_after(
            conversation_id,
            after_message_id=anchor.id,
        )

    assert result == [tool_step, follow_up]


@pytest.mark.anyio
async def test_last_active_canonical_message_handles_empty_and_nonempty_paths():
    last = message()
    with patch.object(
        branching,
        "get_active_canonical_path",
        new=AsyncMock(side_effect=[[], [message(), last]]),
    ):
        assert await branching.get_last_active_canonical_message(uuid4()) is None
        assert await branching.get_last_active_canonical_message(uuid4()) is last


@pytest.mark.anyio
async def test_prefix_path_follows_branch_parents_and_ignores_hidden_steps():
    conversation_id = uuid4()
    first = message(conversation_id=conversation_id)
    hidden = message(
        conversation_id=conversation_id,
        branch_parent_id=first.id,
        round_id=uuid4(),
        is_round_canonical=False,
    )
    target = message(
        conversation_id=conversation_id,
        branch_parent_id=hidden.id,
        created_at=first.created_at + timedelta(seconds=2),
    )
    orm = query(all=[first, hidden, target])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.get_prefix_path_before(target) == [first]


@pytest.mark.anyio
async def test_prefix_path_skips_deactivated_links_keeps_active_ancestors():
    """A polluted chain link (a deactivated superseded version, e.g. the old
    reply a user-message edit replaced) must not leak into the prefix, while
    older ACTIVE history behind it is still preserved."""
    conversation_id = uuid4()
    first = message(conversation_id=conversation_id)
    superseded_reply = message(
        conversation_id=conversation_id,
        branch_parent_id=first.id,
        is_active=False,
        created_at=first.created_at + timedelta(seconds=1),
    )
    edited_user = message(
        conversation_id=conversation_id,
        branch_parent_id=superseded_reply.id,
        created_at=first.created_at + timedelta(seconds=2),
    )
    target = message(
        conversation_id=conversation_id,
        branch_parent_id=edited_user.id,
        created_at=first.created_at + timedelta(seconds=3),
    )
    orm = query(all=[first, superseded_reply, edited_user, target])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.get_prefix_path_before(target) == [first, edited_user]


@pytest.mark.anyio
async def test_limited_prefix_skips_deactivated_links():
    conversation_id = uuid4()
    first = message(conversation_id=conversation_id)
    superseded_reply = message(
        conversation_id=conversation_id,
        branch_parent_id=first.id,
        is_active=False,
        created_at=first.created_at + timedelta(seconds=1),
    )
    target = message(
        conversation_id=conversation_id,
        branch_parent_id=superseded_reply.id,
        created_at=first.created_at + timedelta(seconds=2),
    )
    first_orm = query(first=superseded_reply)
    second_orm = query(first=first)

    with patch.object(branching.Message, "filter", side_effect=[first_orm, second_orm]):
        assert await branching.get_prefix_path_before(target, limit=1) == [first]


@pytest.mark.anyio
@pytest.mark.parametrize("history_is_active", [True, False])
async def test_prefix_path_preserves_history_before_legacy_chain_gap(
    history_is_active,
):
    conversation_id = uuid4()
    first_user = message(
        conversation_id=conversation_id,
        is_active=history_is_active,
    )
    first_assistant = message(
        conversation_id=conversation_id,
        branch_parent_id=first_user.id,
        is_active=history_is_active,
        created_at=first_user.created_at + timedelta(seconds=1),
    )
    latest_user = message(
        conversation_id=conversation_id,
        branch_parent_id=None,
        created_at=first_user.created_at + timedelta(seconds=2),
    )
    target_version = message(
        conversation_id=conversation_id,
        branch_parent_id=latest_user.id,
        created_at=first_user.created_at + timedelta(seconds=3),
    )
    orm = query(all=[first_user, first_assistant, latest_user, target_version])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.get_prefix_path_before(target_version) == [
            first_user,
            first_assistant,
            latest_user,
        ]


@pytest.mark.anyio
async def test_limited_prefix_recovers_history_after_chain_gap():
    conversation_id = uuid4()
    first_user = message(conversation_id=conversation_id, is_active=False)
    first_assistant = message(
        conversation_id=conversation_id,
        branch_parent_id=first_user.id,
        is_active=False,
        created_at=first_user.created_at + timedelta(seconds=1),
    )
    latest_user = message(
        conversation_id=conversation_id,
        branch_parent_id=None,
        created_at=first_user.created_at + timedelta(seconds=2),
    )
    target_version = message(
        conversation_id=conversation_id,
        branch_parent_id=latest_user.id,
        created_at=first_user.created_at + timedelta(seconds=3),
    )
    message_filter = MagicMock(
        side_effect=[
            query(first=latest_user),
            query(all=[first_user, first_assistant, latest_user, target_version]),
        ]
    )

    with patch.object(branching.Message, "filter", message_filter):
        assert await branching.get_prefix_path_before(target_version, limit=3) == [
            first_user,
            first_assistant,
            latest_user,
        ]


@pytest.mark.anyio
async def test_prefix_path_stops_at_cycle_and_falls_back_when_unresolved():
    conversation_id = uuid4()
    parent = message(conversation_id=conversation_id)
    parent.branch_parent_id = parent.id
    cyclic_target = message(conversation_id=conversation_id, branch_parent_id=parent.id)
    unresolved = message(conversation_id=conversation_id, branch_parent_id=uuid4())
    older = message(
        conversation_id=conversation_id,
        created_at=unresolved.created_at - timedelta(seconds=1),
    )
    newer = message(
        conversation_id=conversation_id,
        created_at=unresolved.created_at + timedelta(seconds=1),
    )

    with (
        patch.object(
            branching.Message,
            "filter",
            side_effect=[query(all=[parent, cyclic_target]), query(all=[unresolved])],
        ),
        patch.object(
            branching,
            "get_active_canonical_path",
            new=AsyncMock(return_value=[older, unresolved, newer]),
        ) as active_path,
    ):
        assert await branching.get_prefix_path_before(cyclic_target) == [parent]
        assert await branching.get_prefix_path_before(unresolved) == [older]

    active_path.assert_awaited_once_with(conversation_id)


@pytest.mark.anyio
async def test_descendant_branch_picks_newest_child_when_all_inactive():
    """After switching to an old version, both replies of a message are
    inactive; switching back must pick the NEWEST reply (old SQL ordering
    -created_at), not the oldest."""
    v2 = message()
    old_reply = message(
        conversation_id=v2.conversation_id,
        branch_parent_id=v2.id,
        is_active=False,
        created_at=v2.created_at + timedelta(seconds=1),
    )
    new_reply = message(
        conversation_id=v2.conversation_id,
        branch_parent_id=v2.id,
        is_active=False,
        created_at=v2.created_at + timedelta(seconds=60),
    )
    orm = query(all=[v2, old_reply, new_reply])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.find_descendant_branch_from(v2) == [v2, new_reply]


@pytest.mark.anyio
async def test_find_descendant_branch_selects_visible_children_and_stops_on_cycle():
    root = message()
    child = message(conversation_id=root.conversation_id, branch_parent_id=root.id)
    orm = query(all=[root, child])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.find_descendant_branch_from(root) == [root, child]

    orm.only.assert_called_once()
    # A self-loop must terminate via the visited set.
    root.branch_parent_id = root.id
    loop_orm = query(all=[root])
    with patch.object(branching.Message, "filter", return_value=loop_orm):
        assert await branching.find_descendant_branch_from(root) == [root]


@pytest.mark.anyio
async def test_select_descendant_child_skips_hidden_children():
    parent = message()
    hidden = message(round_id=uuid4(), is_round_canonical=False)
    visible = message()
    orm = query(order_by=[hidden, visible])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching._select_descendant_child(parent) is visible


@pytest.mark.anyio
async def test_select_descendant_child_skips_version_sibling_of_branch_root():
    parent = message()
    sibling = message(parent_id=parent.id)
    continuation = message()
    orm = query(order_by=[sibling, continuation])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert (
            await branching._select_descendant_child(parent, skip_group_root=parent.id)
            is continuation
        )


@pytest.mark.anyio
async def test_descendant_branch_stops_at_version_sibling():
    """Switching to an old version must not pull in the edited version's
    subtree even when the branch chain is polluted (old reply -> edited
    version)."""
    root = message()
    old_reply = message(
        conversation_id=root.conversation_id,
        branch_parent_id=root.id,
        created_at=root.created_at + timedelta(seconds=1),
    )
    edited_version = message(
        conversation_id=root.conversation_id,
        parent_id=root.id,
        branch_parent_id=old_reply.id,
        created_at=root.created_at + timedelta(seconds=2),
    )
    filter_mock = MagicMock()
    orm = query(all=[root, old_reply, edited_version])
    filter_mock.return_value = orm

    with patch.object(branching.Message, "filter", filter_mock):
        assert await branching.find_descendant_branch_from(root) == [root, old_reply]


@pytest.mark.anyio
async def test_activate_branch_dedups_version_groups_keeping_newest():
    """A polluted path containing both an old version and its replacement must
    activate only the newest version, dropping the old one and its round's
    reply (the superseded turn cannot resurface)."""
    conversation_id = uuid4()
    db = MagicMock()
    old_round = uuid4()
    new_round = uuid4()
    v1 = message(
        conversation_id=conversation_id,
        version_number=1,
        round_id=old_round,
        round_role=branching.MessageRoundRole.USER_INPUT,
    )
    old_reply = message(
        conversation_id=conversation_id,
        round_id=old_round,
        round_role=branching.MessageRoundRole.ASSISTANT_FINAL,
    )
    v2 = message(
        conversation_id=conversation_id,
        parent_id=v1.id,
        version_number=2,
        round_id=new_round,
        round_role=branching.MessageRoundRole.USER_INPUT,
    )
    new_reply = message(
        conversation_id=conversation_id,
        branch_parent_id=v2.id,
        round_id=new_round,
        round_role=branching.MessageRoundRole.ASSISTANT_FINAL,
    )
    round_query = query(all=[])
    active_query = query(all=[v1, old_reply])
    deactivate_query = query(update=1)
    activate_query = query(update=1)

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[round_query, active_query, deactivate_query, activate_query],
    ) as message_filter:
        await branching.activate_conversation_branch(
            conversation_id,
            [v1, old_reply, v2, new_reply],
            using_db=db,
        )

    # v1 + old_reply (active before) are deactivated.
    assert set(message_filter.call_args_list[2].kwargs["id__in"]) == {
        v1.id,
        old_reply.id,
    }
    deactivate_query.update.assert_awaited_once_with(is_active=False)
    # Only the newest version (v2) and its reply are activated.
    assert set(message_filter.call_args_list[3].kwargs["id__in"]) == {
        v2.id,
        new_reply.id,
    }
    activate_query.update.assert_awaited_once_with(is_active=True)
    # The round-steps query only covers the kept assistant-final round.
    assert message_filter.call_args_list[0].kwargs["round_id__in"] == [new_round]


@pytest.mark.anyio
async def test_activate_branch_persists_canonical_round_steps_and_deactivates_others():
    conversation_id = uuid4()
    db = MagicMock()
    round_id = uuid4()
    canonical = message(
        conversation_id=conversation_id,
        round_id=round_id,
        round_role=branching.MessageRoundRole.ASSISTANT_FINAL,
    )
    plain = message(conversation_id=conversation_id)
    round_step = message(
        conversation_id=conversation_id,
        round_id=round_id,
        is_round_canonical=False,
    )
    stray = message(conversation_id=conversation_id)
    round_query = query(all=[round_step])
    active_query = query(all=[plain, round_step, stray])
    deactivate_query = query(update=1)
    activate_query = query(update=1)

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[round_query, active_query, deactivate_query, activate_query],
    ) as message_filter:
        await branching.activate_conversation_branch(
            conversation_id, [plain, canonical], using_db=db
        )

    assert message_filter.call_args_list[:2] == [
        call(
            conversation_id=conversation_id,
            round_id__in=[round_id],
            is_round_canonical=False,
        ),
        call(conversation_id=conversation_id, is_active=True),
    ]
    active_query.only.assert_called_once_with("id")
    # Only the stray message is deactivated (it was active but is not in the
    # new path); only the canonical message is activated.
    assert set(message_filter.call_args_list[2].kwargs["id__in"]) == {stray.id}
    deactivate_query.update.assert_awaited_once_with(is_active=False)
    assert set(message_filter.call_args_list[3].kwargs["id__in"]) == {canonical.id}
    activate_query.update.assert_awaited_once_with(is_active=True)
    round_query.using_db.assert_called_once_with(db)


@pytest.mark.anyio
async def test_activate_empty_branch_only_deactivates_messages():
    conversation_id = uuid4()
    active = [
        message(conversation_id=conversation_id),
        message(conversation_id=conversation_id),
    ]
    active_query = query(all=active)
    deactivate_query = query(update=2)

    # Bare call (no using_db): the function must serialize itself by locking
    # the conversation row inside a transaction before touching message state.
    lock_query = MagicMock()
    lock_query.using_db.return_value = lock_query
    lock_query.select_for_update.return_value = lock_query
    lock_query.first = AsyncMock(return_value=None)

    class _Transaction:
        async def __aenter__(self) -> SimpleNamespace:
            return SimpleNamespace()

        async def __aexit__(self, *args) -> bool:
            return False

    with (
        patch.object(
            branching.Message,
            "filter",
            side_effect=[active_query, deactivate_query],
        ) as message_filter,
        patch.object(
            branching.Conversation, "filter", return_value=lock_query
        ) as conversation_filter,
        patch.object(branching, "in_transaction", return_value=_Transaction()),
    ):
        await branching.activate_conversation_branch(conversation_id, [])

    conversation_filter.assert_called_once_with(id=conversation_id)
    lock_query.select_for_update.assert_called_once_with()
    lock_query.first.assert_awaited_once_with()
    assert message_filter.call_args_list[0] == call(
        conversation_id=conversation_id, is_active=True
    )
    assert set(message_filter.call_args_list[1].kwargs["id__in"]) == {
        active[0].id,
        active[1].id,
    }
    deactivate_query.update.assert_awaited_once_with(is_active=False)


@pytest.mark.anyio
async def test_activate_branch_noop_when_state_unchanged():
    """Idempotency: when the path already equals the active set, no UPDATEs
    should be issued at all."""
    conversation_id = uuid4()
    db = MagicMock()
    canonical = message(
        conversation_id=conversation_id,
        round_role=branching.MessageRoundRole.ASSISTANT_FINAL,
    )
    active_query = query(all=[canonical])

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[active_query],
    ) as message_filter:
        await branching.activate_conversation_branch(
            conversation_id, [canonical], using_db=db
        )

    message_filter.assert_called_once()
    assert message_filter.call_args_list[0] == call(
        conversation_id=conversation_id, is_active=True
    )


@pytest.mark.anyio
async def test_is_message_on_active_branch_applies_cutoff():
    cutoff = datetime.now(UTC)
    orm = query(exists=True)
    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching.is_message_on_active_branch(
            uuid4(), uuid4(), before_created_at=cutoff
        )

    orm.filter.assert_called_once_with(created_at__lt=cutoff)
    orm.exists.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("snapshot", [None, SimpleNamespace(source_message_id=None)])
async def test_stale_session_memory_ignores_missing_sources(snapshot):
    orm = query(first=snapshot)
    with (
        patch.object(branching.ConversationSessionMemory, "filter", return_value=orm),
        patch.object(
            branching, "is_message_on_active_branch", new=AsyncMock()
        ) as is_active,
    ):
        await branching.stale_session_memory_if_source_outside_active_branch(uuid4())

    is_active.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("is_active", [True, False])
async def test_stale_session_memory_transitions_only_outside_active_branch(is_active):
    conversation_id = uuid4()
    snapshot = SimpleNamespace(source_message_id=uuid4(), save=AsyncMock())
    orm = query(first=snapshot)
    with (
        patch.object(branching.ConversationSessionMemory, "filter", return_value=orm),
        patch.object(
            branching,
            "is_message_on_active_branch",
            new=AsyncMock(return_value=is_active),
        ),
    ):
        await branching.stale_session_memory_if_source_outside_active_branch(
            conversation_id
        )

    if is_active:
        assert not hasattr(snapshot, "status")
        snapshot.save.assert_not_awaited()
    else:
        assert snapshot.status == ConversationSessionMemoryStatus.STALE
        snapshot.save.assert_awaited_once_with(update_fields=["status", "updated_at"])


@pytest.mark.anyio
async def test_activate_branch_excludes_user_message_round_steps():
    """Regenerate residue fix: the user message shares its round with the
    deactivated old assistant reply. Activating the new path must NOT
    re-activate the old round's tool steps - only the assistant-final
    round's steps belong on the active branch."""
    from app.models.agent import MessageRoundRole

    conversation_id = uuid4()
    user_round = uuid4()
    new_round = uuid4()
    user_msg = message(
        conversation_id=conversation_id,
        round_id=user_round,
        round_role=MessageRoundRole.USER_INPUT,
    )
    new_assistant = message(
        conversation_id=conversation_id,
        round_id=new_round,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
    )
    old_reply = message(conversation_id=conversation_id)
    steps_query = query(all=[])
    active_query = query(all=[user_msg, old_reply])
    deactivate_query = query(update=1)
    activate_ids = query(update=1)

    lock_query = MagicMock()
    lock_query.using_db.return_value = lock_query
    lock_query.select_for_update.return_value = lock_query
    lock_query.first = AsyncMock(return_value=None)

    class _Transaction:
        async def __aenter__(self) -> SimpleNamespace:
            return SimpleNamespace()

        async def __aexit__(self, *args) -> bool:
            return False

    with (
        patch.object(
            branching.Message,
            "filter",
            side_effect=[steps_query, active_query, deactivate_query, activate_ids],
        ) as message_filter,
        patch.object(branching.Conversation, "filter", return_value=lock_query),
        patch.object(branching, "in_transaction", return_value=_Transaction()),
    ):
        await branching.activate_conversation_branch(
            conversation_id, [user_msg, new_assistant]
        )

    # round_steps query must only include the assistant-final round,
    # NOT the user message's round (which shares the old reply's tool steps)
    round_steps_call = message_filter.call_args_list[0]
    assert round_steps_call.kwargs["round_id__in"] == [new_round]
    assert user_round not in round_steps_call.kwargs["round_id__in"]

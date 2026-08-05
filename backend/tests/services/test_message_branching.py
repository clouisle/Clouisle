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
async def test_find_descendant_branch_selects_visible_children_and_stops_on_cycle():
    root = message()
    child = message(conversation_id=root.conversation_id, branch_parent_id=root.id)
    with patch.object(
        branching,
        "_select_descendant_child",
        new=AsyncMock(side_effect=[child, root]),
    ):
        assert await branching.find_descendant_branch_from(root) == [root, child]


@pytest.mark.anyio
async def test_select_descendant_child_skips_hidden_children():
    parent = message()
    hidden = message(round_id=uuid4(), is_round_canonical=False)
    visible = message()
    orm = query(order_by=[hidden, visible])

    with patch.object(branching.Message, "filter", return_value=orm):
        assert await branching._select_descendant_child(parent) is visible


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
    round_query = query(all=[round_step])
    deactivate_query = query(update=5)
    activate_query = query(update=3)

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[round_query, deactivate_query, activate_query],
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
        call(conversation_id=conversation_id),
    ]
    assert set(message_filter.call_args_list[2].kwargs["id__in"]) == {
        plain.id,
        canonical.id,
        round_step.id,
    }
    round_query.using_db.assert_called_once_with(db)
    deactivate_query.update.assert_awaited_once_with(is_active=False)
    activate_query.update.assert_awaited_once_with(is_active=True)


@pytest.mark.anyio
async def test_activate_empty_branch_only_deactivates_messages():
    deactivate_query = query(update=2)
    with patch.object(
        branching.Message, "filter", return_value=deactivate_query
    ) as message_filter:
        await branching.activate_conversation_branch(uuid4(), [])

    message_filter.assert_called_once()
    deactivate_query.update.assert_awaited_once_with(is_active=False)


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
    steps_query = query(all=[])
    deactivate_all = query(update=1)
    activate_ids = query(update=1)

    with patch.object(
        branching.Message,
        "filter",
        side_effect=[steps_query, deactivate_all, activate_ids],
    ) as message_filter:
        await branching.activate_conversation_branch(
            conversation_id, [user_msg, new_assistant]
        )

    # round_steps query must only include the assistant-final round,
    # NOT the user message's round (which shares the old reply's tool steps)
    round_steps_call = message_filter.call_args_list[0]
    assert round_steps_call.kwargs["round_id__in"] == [new_round]
    assert user_round not in round_steps_call.kwargs["round_id__in"]

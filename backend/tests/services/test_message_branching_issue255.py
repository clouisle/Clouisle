from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.agent import ConversationSessionMemoryStatus
from app.services import message_branching as branching


class Query:
    def __init__(self, items=(), *, count=0, exists=False, first=None):
        self.items = list(items)
        self.count_value = count
        self.exists_value = exists
        self.first_value = first
        self.filters = []
        self.excludes = []
        self.ordering = None
        self.db = None
        self.update = AsyncMock()

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def exclude(self, **kwargs):
        self.excludes.append(kwargs)
        return self

    def order_by(self, *fields):
        self.ordering = fields
        return self

    def only(self, *fields):
        self.only_fields = fields
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def using_db(self, db):
        self.db = db
        return self

    async def all(self):
        return self.items

    async def count(self):
        return self.count_value

    async def exists(self):
        return self.exists_value

    async def first(self):
        return self.first_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


def message(**overrides):
    values = {
        "id": uuid4(),
        "parent_id": None,
        "conversation_id": uuid4(),
        "version_number": 1,
        "round_id": None,
        "round_role": None,
        "is_round_canonical": True,
        "is_active": True,
        "created_at": datetime(2026, 1, 1),
        "branch_parent_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_version_group_count_and_canonical_visibility(monkeypatch):
    root = message(version_number=2)
    older = message(parent_id=root.id, version_number=1)
    group_query = Query([root, older])
    count_query = Query(count=2)
    monkeypatch.setattr(
        branching.Message, "filter", MagicMock(side_effect=[group_query, count_query])
    )

    assert branching.get_version_root_id(root) == root.id
    assert branching.get_version_root_id(older) == root.id
    assert await branching.get_message_version_group(root) == [older, root]
    assert await branching.get_version_count(older) == 2
    assert branching._is_canonical_visible(message(round_id=None))
    assert not branching._is_canonical_visible(
        message(round_id=uuid4(), is_round_canonical=False)
    )


@pytest.mark.anyio
async def test_visible_queries_apply_optional_filters(monkeypatch):
    hidden = message(round_id=uuid4(), is_round_canonical=False)
    visible = message()
    active_query = Query([hidden, visible])
    visible_query = Query([visible])
    monkeypatch.setattr(
        branching.Message,
        "filter",
        MagicMock(side_effect=[active_query, visible_query]),
    )

    assert await branching.get_active_canonical_path(visible.conversation_id) == [
        visible
    ]
    before = datetime(2026, 1, 2)
    excluded = [uuid4()]
    assert await branching.get_visible_conversation_messages(
        visible.conversation_id,
        before_created_at=before,
        exclude_message_ids=excluded,
    ) == [visible]
    assert visible_query.filters[-1][1] == {"created_at__lt": before}
    assert visible_query.excludes == [{"id__in": excluded}]
    assert visible_query.ordering == ("created_at", "id")

    bounded_query = Query([hidden, visible])
    monkeypatch.setattr(
        branching.Message, "filter", MagicMock(return_value=bounded_query)
    )
    assert await branching.get_visible_conversation_messages(
        visible.conversation_id, limit=1
    ) == [visible]
    assert bounded_query.ordering == ("-created_at", "-id")
    assert bounded_query.limit_value == 8


@pytest.mark.anyio
async def test_last_active_message_handles_empty_and_nonempty(monkeypatch):
    item = message()
    paths = AsyncMock(side_effect=[[item], []])
    monkeypatch.setattr(branching, "get_active_canonical_path", paths)

    assert (
        await branching.get_last_active_canonical_message(item.conversation_id) is item
    )
    assert (
        await branching.get_last_active_canonical_message(item.conversation_id) is None
    )


@pytest.mark.anyio
async def test_prefix_follows_branch_parents_and_skips_noncanonical(monkeypatch):
    conversation_id = uuid4()
    first = message(conversation_id=conversation_id)
    hidden = message(
        conversation_id=conversation_id,
        branch_parent_id=first.id,
        round_id=uuid4(),
        is_round_canonical=False,
    )
    target = message(conversation_id=conversation_id, branch_parent_id=hidden.id)
    monkeypatch.setattr(
        branching.Message, "filter", MagicMock(return_value=Query([first, hidden]))
    )

    assert await branching.get_prefix_path_before(target) == [first]


@pytest.mark.anyio
async def test_prefix_falls_back_when_branch_chain_is_missing(monkeypatch):
    target = message(branch_parent_id=uuid4(), created_at=datetime(2026, 1, 3))
    older = message(created_at=target.created_at - timedelta(days=1))
    newer = message(created_at=target.created_at + timedelta(days=1))
    monkeypatch.setattr(branching.Message, "filter", MagicMock(return_value=Query([])))
    monkeypatch.setattr(
        branching, "get_active_canonical_path", AsyncMock(return_value=[older, newer])
    )

    assert await branching.get_prefix_path_before(target) == [older]


@pytest.mark.anyio
async def test_descendant_selector_returns_none_without_visible_child(monkeypatch):
    hidden = message(round_id=uuid4(), is_round_canonical=False)
    monkeypatch.setattr(
        branching.Message, "filter", MagicMock(return_value=Query([hidden]))
    )

    assert await branching._select_descendant_child(message()) is None


@pytest.mark.anyio
async def test_descendant_branch_skips_hidden_and_stops_on_cycle(monkeypatch):
    root = message()
    hidden = message(round_id=uuid4(), is_round_canonical=False)
    child = message(branch_parent_id=root.id)
    queries = [Query([hidden, child]), Query([root])]
    monkeypatch.setattr(branching.Message, "filter", MagicMock(side_effect=queries))

    assert await branching.find_descendant_branch_from(root) == [root, child]
    # The old SQL ordering (-is_active, -created_at, -id) is preserved by the
    # in-memory descendant sort key: active beats inactive, newest beats older.
    active_newer = message(branch_parent_id=root.id, created_at=datetime(2026, 1, 3))
    inactive_older = message(
        branch_parent_id=root.id,
        is_active=False,
        created_at=datetime(2026, 1, 2),
    )
    assert branching._descendant_sort_key(
        active_newer
    ) < branching._descendant_sort_key(inactive_older)
    assert branching._descendant_sort_key(
        inactive_older
    ) < branching._descendant_sort_key(
        message(
            branch_parent_id=root.id,
            is_active=False,
            created_at=datetime(2026, 1, 1),
        )
    )


@pytest.mark.anyio
async def test_activate_branch_includes_noncanonical_round_steps(monkeypatch):
    conversation_id = uuid4()
    round_id = uuid4()
    canonical = message(
        conversation_id=conversation_id,
        round_id=round_id,
        round_role=branching.MessageRoundRole.ASSISTANT_FINAL,
    )
    round_step = message(
        conversation_id=conversation_id,
        round_id=round_id,
        is_round_canonical=False,
    )
    round_query = Query([round_step])
    stray = message(conversation_id=conversation_id)
    active_query = Query([stray])
    deactivate_query = Query()
    activate_query = Query()
    monkeypatch.setattr(
        branching.Message,
        "filter",
        MagicMock(
            side_effect=[round_query, active_query, deactivate_query, activate_query]
        ),
    )
    db = object()

    await branching.activate_conversation_branch(
        conversation_id, [canonical], using_db=db
    )

    assert round_query.db is db
    deactivate_query.update.assert_awaited_once_with(is_active=False)
    activate_query.update.assert_awaited_once_with(is_active=True)
    active_ids = branching.Message.filter.call_args_list[-1].kwargs["id__in"]
    assert set(active_ids) == {canonical.id, round_step.id}


@pytest.mark.anyio
async def test_active_check_and_session_memory_staleness(monkeypatch):
    active_query = Query(exists=True)
    monkeypatch.setattr(
        branching.Message, "filter", MagicMock(return_value=active_query)
    )
    before = datetime(2026, 1, 2)
    assert await branching.is_message_on_active_branch(
        uuid4(), uuid4(), before_created_at=before
    )
    assert active_query.filters[-1][1] == {"created_at__lt": before}

    snapshot = SimpleNamespace(
        source_message_id=uuid4(),
        status=ConversationSessionMemoryStatus.READY,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        branching.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=Query(first=snapshot)),
    )
    monkeypatch.setattr(
        branching, "is_message_on_active_branch", AsyncMock(return_value=False)
    )

    await branching.stale_session_memory_if_source_outside_active_branch(uuid4())

    assert snapshot.status == ConversationSessionMemoryStatus.STALE
    snapshot.save.assert_awaited_once_with(update_fields=["status", "updated_at"])

    snapshot.save.reset_mock()
    snapshot.status = ConversationSessionMemoryStatus.READY
    branching.is_message_on_active_branch.return_value = True
    await branching.stale_session_memory_if_source_outside_active_branch(uuid4())
    assert snapshot.status == ConversationSessionMemoryStatus.READY
    snapshot.save.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("snapshot", [None, SimpleNamespace(source_message_id=None)])
async def test_session_memory_staleness_ignores_missing_source(monkeypatch, snapshot):
    monkeypatch.setattr(
        branching.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=Query(first=snapshot)),
    )
    active_check = AsyncMock()
    monkeypatch.setattr(branching, "is_message_on_active_branch", active_check)

    await branching.stale_session_memory_if_source_outside_active_branch(uuid4())

    active_check.assert_not_awaited()

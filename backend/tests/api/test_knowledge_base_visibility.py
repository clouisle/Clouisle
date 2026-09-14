import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.api.v1.endpoints import knowledge_bases
from app.models.knowledge_base import KnowledgeBaseVisibility
from app.schemas.response import BusinessError, ResponseCode


class DummyQuery:
    def __init__(
        self, item=None, items=None, exists_val=False, values_list_result=None
    ):
        self._item = item
        self._items = items or []
        self._exists_val = exists_val
        self._values_list_result = (
            values_list_result if values_list_result is not None else []
        )

    def prefetch_related(self, *args, **kwargs):
        return self

    async def first(self):
        return self._item

    async def all(self):
        return self._items

    async def exists(self):
        return self._exists_val

    def values_list(self, *args, **kwargs):
        return self

    def __await__(self):
        async def _resolve():
            return self._values_list_result

        return _resolve().__await__()


@pytest.mark.anyio
async def test_check_kb_access_private_kb_owner_and_non_owner():
    kb_id = uuid4()
    owner_id = uuid4()
    other_user_id = uuid4()
    team_id = uuid4()

    owner = type("User", (), {"id": owner_id, "is_superuser": False})()
    other_user = type("User", (), {"id": other_user_id, "is_superuser": False})()
    superuser = type("User", (), {"id": uuid4(), "is_superuser": True})()

    private_kb = type(
        "KnowledgeBase",
        (),
        {
            "id": kb_id,
            "name": "Private KB",
            "team_id": team_id,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
            "created_by": type("User", (), {"id": owner_id})(),
            "created_by_id": owner_id,
        },
    )()

    with patch.object(
        knowledge_bases.KnowledgeBase,
        "filter",
        return_value=DummyQuery(item=private_kb),
    ):
        # 1. Superuser can access
        assert await knowledge_bases.check_kb_access(kb_id, superuser) == private_kb

        # 2. Owner can access
        assert await knowledge_bases.check_kb_access(kb_id, owner) == private_kb

        # 3. Non-owner gets KB_ACCESS_DENIED (403)
        with pytest.raises(BusinessError) as exc_info:
            await knowledge_bases.check_kb_access(kb_id, other_user)
        assert exc_info.value.code == ResponseCode.KB_ACCESS_DENIED
        assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_share_private_kb_is_rejected():
    kb_id = uuid4()
    owner_id = uuid4()
    team_id = uuid4()
    target_team_id = uuid4()

    owner = type("User", (), {"id": owner_id, "is_superuser": False})()
    private_kb = type(
        "KnowledgeBase",
        (),
        {
            "id": kb_id,
            "name": "Private KB",
            "team_id": team_id,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
            "created_by": type("User", (), {"id": owner_id})(),
        },
    )()

    share_in = knowledge_bases.KnowledgeBaseShareInput(team_id=target_team_id)
    req = type("Request", (), {})()
    with (
        patch.object(
            knowledge_bases.KnowledgeBase,
            "filter",
            return_value=DummyQuery(item=private_kb),
        ),
        patch.object(knowledge_bases, "check_team_access", AsyncMock()),
        patch.object(
            knowledge_bases.Team,
            "filter",
            return_value=DummyQuery(item=type("Team", (), {"id": target_team_id})()),
        ),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await knowledge_bases.share_knowledge_base(
                kb_id=kb_id,
                share_data=share_in,
                request=req,
                current_user=owner,
            )
        assert exc_info.value.code == ResponseCode.BAD_REQUEST
        assert exc_info.value.msg_key == "private_kb_cannot_be_shared"


@pytest.mark.anyio
async def test_kb_read_visibility_filter_covers_scope_and_owner_variants(monkeypatch):
    team_id = uuid4()
    member_team_id = uuid4()
    user = type("User", (), {"id": uuid4(), "is_superuser": False})()
    no_id_user = type("User", (), {"id": None, "is_superuser": False})()

    superuser = type("User", (), {"id": uuid4(), "is_superuser": True})()
    scoped = await knowledge_bases.kb_read_visibility_filter(superuser, team_id)
    assert scoped.filters == {"team_id": team_id}
    unscoped = await knowledge_bases.kb_read_visibility_filter(superuser)
    assert unscoped.filters == {}

    membership_filter = DummyQuery(values_list_result=[member_team_id])
    monkeypatch.setattr(
        knowledge_bases.TeamMember,
        "filter",
        lambda **_kwargs: membership_filter,
    )
    explicit = await knowledge_bases.kb_read_visibility_filter(user, team_id)

    def leaf_filters(expression):
        if not expression.children:
            return [expression.filters]
        return [
            filters for child in expression.children for filters in leaf_filters(child)
        ]

    assert leaf_filters(explicit) == [
        {
            "team_id__in": [team_id],
            "visibility__in": [
                KnowledgeBaseVisibility.TEAM.value,
                KnowledgeBaseVisibility.PUBLIC.value,
            ],
        },
        {
            "team_id__in": [team_id],
            "created_by_id": user.id,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
        },
        {
            "team_id__in": [team_id],
            "created_by_id__isnull": True,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
        },
    ]
    unscoped_user = await knowledge_bases.kb_read_visibility_filter(user)
    assert leaf_filters(unscoped_user)[0]["team_id__in"] == [member_team_id]

    no_owner = await knowledge_bases.kb_read_visibility_filter(no_id_user, team_id)
    assert leaf_filters(no_owner)[1] == {"pk__in": []}


@pytest.mark.anyio
async def test_private_kb_owner_and_legacy_access_enforce_write_scope(monkeypatch):
    team_id = uuid4()
    owner = type("User", (), {"id": uuid4(), "is_superuser": False})()
    owner_kb = type(
        "KnowledgeBase",
        (),
        {
            "id": uuid4(),
            "team_id": team_id,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
            "created_by": owner,
        },
    )()
    legacy_kb = type(
        "KnowledgeBase",
        (),
        {
            "id": uuid4(),
            "team_id": team_id,
            "visibility": KnowledgeBaseVisibility.PRIVATE.value,
            "created_by": None,
        },
    )()
    check_team = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "check_team_access", check_team)
    query = DummyQuery(item=owner_kb)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: query
    )

    assert (
        await knowledge_bases.check_kb_access(
            owner_kb.id, owner, require_write=True, allow_owner_write=False
        )
        is owner_kb
    )
    check_team.assert_awaited_once_with(team_id, owner, require_admin=True)

    query._item = legacy_kb
    check_team.reset_mock()
    assert (
        await knowledge_bases.check_kb_access(
            legacy_kb.id, owner, require_write=True, allow_owner_write=False
        )
        is legacy_kb
    )
    assert check_team.await_args_list[0].kwargs == {}
    assert check_team.await_args_list[1].kwargs == {"require_admin": True}

    check_team.reset_mock()
    assert (
        await knowledge_bases.check_kb_access(legacy_kb.id, owner, require_write=False)
        is legacy_kb
    )
    check_team.assert_awaited_once_with(team_id, owner)


@pytest.mark.anyio
async def test_admin_team_access_and_action_permission_paths(monkeypatch):
    team_id = uuid4()
    admin_user = type("User", (), {"id": uuid4(), "is_superuser": False, "roles": []})()
    token = knowledge_bases._kb_access_mode.set("admin")
    try:
        monkeypatch.setattr(
            knowledge_bases.Team,
            "filter",
            lambda **_kwargs: DummyQuery(item=None),
        )
        with pytest.raises(BusinessError) as missing:
            await knowledge_bases.check_team_access(team_id, admin_user)
        assert missing.value.code == ResponseCode.TEAM_NOT_FOUND
    finally:
        knowledge_bases._kb_access_mode.reset(token)

    role = type(
        "Role",
        (),
        {"permissions": [type("Permission", (), {"code": "kb:read"})()]},
    )()
    permitted_user = type(
        "User",
        (),
        {"id": uuid4(), "is_superuser": False, "roles": [role]},
    )()
    action_token = knowledge_bases._kb_access_mode.set("platform")
    try:
        knowledge_bases._require_kb_action(permitted_user, "read")
    finally:
        knowledge_bases._kb_access_mode.reset(action_token)

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

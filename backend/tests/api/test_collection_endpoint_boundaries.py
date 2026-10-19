from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import feishu_knowledge
from app.api.v1.endpoints import wechat_knowledge
from app.schemas.response import BusinessError, ResponseCode
from app.services import wechat_connection


@pytest.mark.asyncio
async def test_wechat_binding_is_owner_scoped(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    identifier = uuid4()
    query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(
        wechat_knowledge.WeChatKnowledgeBinding, "filter", MagicMock(return_value=query)
    )

    with pytest.raises(BusinessError) as exc_info:
        await wechat_knowledge.owned_binding(identifier, user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.msg_key == "wechat_binding_not_found"
    wechat_knowledge.WeChatKnowledgeBinding.filter.assert_called_once_with(
        id=identifier, user_id=user.id
    )


@pytest.mark.asyncio
async def test_wechat_collection_rejects_unavailable_target_and_model(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    kb_id = uuid4()
    monkeypatch.setattr(
        wechat_knowledge,
        "check_binding_target",
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="kb_not_found",
                status_code=404,
            )
        ),
    )
    with pytest.raises(BusinessError) as exc_info:
        await wechat_knowledge.models(kb_id, user)
    assert exc_info.value.msg_key == "kb_not_found"

    kb = SimpleNamespace()
    monkeypatch.setattr(
        wechat_connection,
        "available_models",
        AsyncMock(return_value={"vision": [], "stt": []}),
    )
    with pytest.raises(BusinessError) as exc_info:
        await wechat_knowledge.validate_models(kb, uuid4(), None)
    assert exc_info.value.msg_key == "wechat_model_unavailable"


@pytest.mark.asyncio
async def test_wechat_purpose_rejects_invalid_target_and_model(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    binding = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        wechat_knowledge, "owned_binding", AsyncMock(return_value=binding)
    )
    monkeypatch.setattr(
        wechat_knowledge.WeChatKnowledgeCollection,
        "filter",
        MagicMock(return_value=SimpleNamespace(first=AsyncMock(return_value=None))),
    )
    monkeypatch.setattr(
        wechat_knowledge,
        "check_binding_target",
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.VALIDATION_ERROR, msg_key="wechat_kb_inactive"
            )
        ),
    )
    with pytest.raises(BusinessError) as exc_info:
        await wechat_knowledge.update_purpose(
            binding.id,
            wechat_knowledge.PurposeInput(
                purpose="knowledge_collection", knowledge_base_id=uuid4()
            ),
            user,
        )
    assert exc_info.value.msg_key == "wechat_kb_inactive"

    monkeypatch.setattr(
        wechat_knowledge,
        "check_binding_target",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        wechat_knowledge,
        "validate_models",
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.VALIDATION_ERROR, msg_key="wechat_model_unavailable"
            )
        ),
    )
    with pytest.raises(BusinessError) as exc_info:
        await wechat_knowledge.update_purpose(
            binding.id,
            wechat_knowledge.PurposeInput(
                purpose="knowledge_collection",
                knowledge_base_id=uuid4(),
                vision_model_id=uuid4(),
            ),
            user,
        )
    assert exc_info.value.msg_key == "wechat_model_unavailable"


@pytest.mark.asyncio
async def test_feishu_superuser_guard_denies_regular_user():
    with pytest.raises(BusinessError) as exc_info:
        await feishu_knowledge.require_superuser(SimpleNamespace(is_superuser=False))
    assert exc_info.value.code == ResponseCode.INSUFFICIENT_PRIVILEGES
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_feishu_create_rejects_unknown_space_before_database(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=True)
    client = SimpleNamespace(list_wiki_spaces=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        feishu_knowledge.service, "configured_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        feishu_knowledge,
        "in_transaction",
        MagicMock(side_effect=AssertionError("must not query database")),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu_knowledge.create_source(
            feishu_knowledge.SourceCreate(
                knowledge_base_id=uuid4(), space_id="missing", name="KB"
            ),
            MagicMock(),
            user,
        )
    assert exc_info.value.msg_key == "feishu_knowledge_space_unavailable"


@pytest.mark.asyncio
async def test_feishu_create_rejects_unavailable_target(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=True)
    space = {"space_id": "space-1", "name": "Wiki"}
    client = SimpleNamespace(list_wiki_spaces=AsyncMock(return_value=[space]))
    monkeypatch.setattr(
        feishu_knowledge.service, "configured_client", AsyncMock(return_value=client)
    )
    connection = object()

    class Transaction:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(feishu_knowledge, "in_transaction", Transaction)
    query = MagicMock()
    query.using_db.return_value = query
    query.select_for_update.return_value = query
    query.first = AsyncMock(return_value=None)
    monkeypatch.setattr(
        feishu_knowledge.KnowledgeBase, "filter", MagicMock(return_value=query)
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu_knowledge.create_source(
            feishu_knowledge.SourceCreate(
                knowledge_base_id=uuid4(), space_id="space-1", name="KB"
            ),
            MagicMock(),
            user,
        )
    assert exc_info.value.msg_key == "feishu_knowledge_target_unavailable"


@pytest.mark.asyncio
async def test_target_picker_hides_readable_but_not_writable_knowledge_bases(
    monkeypatch,
):
    from app.api.v1.endpoints import knowledge_bases
    from app.schemas.response import success

    user = SimpleNamespace(id=uuid4())
    writable = SimpleNamespace(
        id=uuid4(), name="Writable", team=SimpleNamespace(name="Team")
    )
    readonly = SimpleNamespace(
        id=uuid4(), name="Read only", team=SimpleNamespace(name="Team")
    )

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def prefetch_related(self, *args):
            return self

        def order_by(self, *args):
            return self

        def __await__(self):
            async def rows():
                return [readonly, writable]

            return rows().__await__()

    monkeypatch.setattr(
        wechat_knowledge.KnowledgeBase, "filter", MagicMock(return_value=Query())
    )
    monkeypatch.setattr(
        knowledge_bases, "kb_read_visibility_filter", AsyncMock(return_value=None)
    )

    async def authorize(identifier, actor):
        if identifier == readonly.id:
            raise BusinessError(code=403, msg_key="permission_denied", status_code=403)
        return writable

    monkeypatch.setattr(wechat_knowledge, "check_binding_target", authorize)
    before = knowledge_bases._kb_access_mode.get()
    result = await wechat_knowledge.targets(user)
    assert result == success(
        data=[{"id": str(writable.id), "name": "Writable", "team_name": "Team"}]
    )
    assert knowledge_bases._kb_access_mode.get() == before

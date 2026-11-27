from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.asset import AssetScopeType, AssetStatus
from app.schemas.response import BusinessError, ResponseCode
from app.services import asset_access


@pytest.mark.asyncio
async def test_protected_asset_requires_authentication():
    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "generated-images/2026/09/image.png", authenticated=None
        )

    assert error.value.code == ResponseCode.UNAUTHORIZED
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_protected_asset_hides_missing_or_unscoped_records(monkeypatch):
    asset_query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(asset_access.Asset, "filter", lambda **_: asset_query)
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])

    with pytest.raises(BusinessError) as missing:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/missing.txt",
            authenticated=(user, None),
        )
    assert missing.value.status_code == 404

    asset_query.first.return_value = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=[])
    )
    with pytest.raises(BusinessError) as unscoped:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/legacy.txt",
            authenticated=(user, None),
        )
    assert unscoped.value.status_code == 404


@pytest.mark.asyncio
async def test_protected_asset_allows_creator_for_legacy_unscoped_record(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    asset = SimpleNamespace(id=uuid4(), created_by_id=user.id)
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=[])
    )

    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/legacy.txt",
        authenticated=(user, None),
    )

    assert result is asset


@pytest.mark.asyncio
async def test_protected_asset_denies_user_without_scope_access(monkeypatch):
    asset_id = uuid4()
    conversation_id = uuid4()
    asset = SimpleNamespace(id=asset_id)
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(
                    return_value=SimpleNamespace(
                        id=conversation_id,
                        user_id=uuid4(),
                        api_key_id=None,
                        api_key_origin_unknown=False,
                        agent_id=uuid4(),
                        agent=SimpleNamespace(team_id=uuid4()),
                    )
                )
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=False)
    )

    with pytest.raises(BusinessError) as denied:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/private.txt",
            authenticated=(SimpleNamespace(id=uuid4()), None),
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_conversation_asset_uses_canonical_api_key_scope_check(monkeypatch):
    asset_id = uuid4()
    agent_id = uuid4()
    conversation_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(
        id=conversation_id,
        user_id=uuid4(),
        agent_id=agent_id,
        agent=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                )
            ]
        ),
    )
    get_authorized = AsyncMock(return_value=asset)
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", get_authorized
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    check_agent = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)

    user = SimpleNamespace(id=conversation.user_id, is_superuser=False, roles=[])
    api_key = SimpleNamespace(id=uuid4())
    conversation.api_key_id = api_key.id
    conversation.api_key_origin_unknown = False
    result = await asset_access.authorize_protected_asset(
        "generated-images/2026/09/image.png", authenticated=(user, api_key)
    )

    assert result is asset
    check_agent.assert_awaited_once_with(api_key, agent_id)

    check_agent.side_effect = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="api_key_no_agent_access",
        status_code=403,
    )
    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "generated-images/2026/09/image.png", authenticated=(user, api_key)
        )
    assert error.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_sandbox_artifact_key_identity_matrix(monkeypatch):
    owner_id, agent_id, conversation_id, asset_id, key_id = (uuid4() for _ in range(5))
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(
        id=conversation_id,
        user_id=owner_id,
        agent_id=agent_id,
        agent=SimpleNamespace(team_id=uuid4()),
        api_key_id=key_id,
        api_key_origin_unknown=False,
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    scope_type=AssetScopeType.CONVERSATION, scope_id=conversation_id
                )
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", AsyncMock(return_value=asset)
    )
    owner = SimpleNamespace(id=owner_id, is_superuser=False, roles=[])
    path = "sandbox-artifacts/2026/09/output.txt"
    assert (
        await asset_access.authorize_protected_asset(
            path, authenticated=(owner, SimpleNamespace(id=key_id))
        )
        is asset
    )
    for auth in [
        (owner, SimpleNamespace(id=uuid4())),
        (owner, None),
        (SimpleNamespace(id=uuid4(), is_superuser=True), SimpleNamespace(id=key_id)),
    ]:
        with pytest.raises(BusinessError) as denied:
            await asset_access.authorize_protected_asset(path, authenticated=auth)
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_workflow_asset_requires_workflow_access_and_api_key_scope(monkeypatch):
    asset_id = uuid4()
    workflow_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user_id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                )
            ]
        ),
    )
    get_authorized = AsyncMock(return_value=asset)
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", get_authorized
    )
    monkeypatch.setattr(
        asset_access.WorkflowRun,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=run)
            )
        ),
    )
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    user = SimpleNamespace(id=user_id, is_superuser=False, roles=[])
    api_key = SimpleNamespace(id=uuid4())
    run.api_key_id = api_key.id
    run.api_key_origin_unknown = False
    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/result.txt", authenticated=(user, api_key)
    )

    assert result is asset
    check_workflow.assert_awaited_once_with(api_key, workflow_id)


@pytest.mark.asyncio
async def test_api_key_denied_conversation_ref_continues_to_workflow_run_ref(
    monkeypatch,
):
    asset_id = uuid4()
    conversation_id = uuid4()
    workflow_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(
        id=conversation_id, agent_id=uuid4(), agent=SimpleNamespace(team_id=uuid4())
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user_id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                ),
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                ),
            ]
        ),
    )
    get_authorized = AsyncMock(return_value=asset)
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", get_authorized
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access.WorkflowRun,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=run)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    check_agent = AsyncMock(
        side_effect=BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="api_key_no_agent_access",
            status_code=403,
        )
    )
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    api_key = SimpleNamespace(id=uuid4())
    conversation.user_id = user_id
    conversation.api_key_id = run.api_key_id = api_key.id
    conversation.api_key_origin_unknown = run.api_key_origin_unknown = False
    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/shared.txt",
        authenticated=(
            SimpleNamespace(id=user_id, is_superuser=False, roles=[]),
            api_key,
        ),
    )

    assert result is asset
    check_agent.assert_awaited_once_with(api_key, conversation.agent_id)
    check_workflow.assert_awaited_once_with(api_key, workflow_id)


@pytest.mark.asyncio
async def test_unexpected_conversation_api_key_error_is_reraised(monkeypatch):
    asset_id = uuid4()
    conversation_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(
        id=conversation_id,
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                ),
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    unexpected = BusinessError(
        code=ResponseCode.INTERNAL_ERROR,
        msg_key="scope_check_failed",
        status_code=500,
    )
    api_key = SimpleNamespace(id=uuid4())
    conversation.user_id = user_id
    conversation.api_key_id = api_key.id
    conversation.api_key_origin_unknown = False
    check_agent = AsyncMock(side_effect=unexpected)
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/shared.txt",
            authenticated=(
                SimpleNamespace(id=user_id, is_superuser=False, roles=[]),
                api_key,
            ),
        )

    assert error.value is unexpected
    check_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_conversation_ref_checks_scope_before_asset_lookup(monkeypatch):
    conversation_id = uuid4()
    agent_id = uuid4()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    api_key = SimpleNamespace(id=uuid4())
    conversation = SimpleNamespace(
        id=conversation_id,
        user_id=user.id,
        api_key_id=api_key.id,
        api_key_origin_unknown=False,
        agent_id=agent_id,
        agent=SimpleNamespace(team_id=team_id),
    )
    first = SimpleNamespace(first=AsyncMock(return_value=conversation))
    query = SimpleNamespace(prefetch_related=lambda *_: first)
    monkeypatch.setattr(asset_access.Conversation, "filter", lambda **_: query)
    can_access = AsyncMock(return_value=True)
    check_api_key = AsyncMock()
    resolve_ref = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(asset_access, "can_access_conversation", can_access)
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_api_key)
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)
    links = SimpleNamespace(exists=AsyncMock(return_value=False))
    monkeypatch.setattr("app.models.asset.MessageAsset.filter", lambda **_: links)

    asset = await asset_access.resolve_authorized_asset_ref(
        "a1b2",
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
        user=user,
        api_key=api_key,
        expected_team_id=team_id,
    )

    assert asset.id == resolve_ref.return_value.id
    can_access.assert_awaited_once_with(conversation, user)
    check_api_key.assert_awaited_once_with(api_key, agent_id)
    resolve_ref.assert_awaited_once_with(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
        ref="a1b2",
        team_id=team_id,
        user_id=user.id,
    )


@pytest.mark.asyncio
async def test_resolve_conversation_ref_denies_inactive_branch(monkeypatch):
    conversation_id = uuid4()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    conversation = SimpleNamespace(
        id=conversation_id,
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=team_id),
    )
    first = SimpleNamespace(first=AsyncMock(return_value=conversation))
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(prefetch_related=lambda *_: first),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        asset_access, "check_api_key_agent_access", AsyncMock(return_value=None)
    )
    asset = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        "app.services.asset.asset_service.resolve_ref",
        AsyncMock(return_value=asset),
    )
    active = SimpleNamespace(exists=AsyncMock(return_value=False))
    links = SimpleNamespace(
        exists=AsyncMock(return_value=True),
        filter=MagicMock(return_value=active),
    )
    monkeypatch.setattr("app.models.asset.MessageAsset.filter", lambda **_: links)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation_id,
            user=user,
            expected_team_id=team_id,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_conversation_ref_denies_before_asset_lookup(monkeypatch):
    conversation_id = uuid4()
    conversation = SimpleNamespace(
        id=conversation_id,
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=uuid4()),
    )
    first = SimpleNamespace(first=AsyncMock(return_value=conversation))
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(prefetch_related=lambda *_: first),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=False)
    )
    check_api_key = AsyncMock()
    resolve_ref = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_api_key)
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation_id,
            user=SimpleNamespace(id=uuid4(), is_superuser=False, roles=[]),
        )

    assert error.value.status_code == 403
    check_api_key.assert_not_awaited()
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_conversation_ref_denies_expected_team_mismatch(monkeypatch):
    conversation_id = uuid4()
    actual_team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    conversation = SimpleNamespace(
        id=conversation_id,
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=actual_team_id),
    )
    first = SimpleNamespace(first=AsyncMock(return_value=conversation))
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(prefetch_related=lambda *_: first),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    resolve_ref = AsyncMock()
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation_id,
            user=user,
            expected_team_id=uuid4(),
        )

    assert error.value.status_code == 403
    resolve_ref.assert_not_awaited()


def _set_workflow_run_query(monkeypatch, run):
    first = SimpleNamespace(first=AsyncMock(return_value=run))
    monkeypatch.setattr(
        asset_access.WorkflowRun,
        "filter",
        lambda **_: SimpleNamespace(prefetch_related=lambda *_: first),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_workflow_access", [True, False])
async def test_workflow_asset_ref_checks_non_creator_access(
    monkeypatch, has_workflow_access
):
    workflow_id = uuid4()
    run_id = uuid4()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=uuid4(),
        workflow=SimpleNamespace(team_id=team_id),
    )
    asset = SimpleNamespace(id=uuid4())
    _set_workflow_run_query(monkeypatch, run)
    check_workflow = AsyncMock(
        side_effect=None
        if has_workflow_access
        else BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="workflow_access_denied",
            status_code=403,
        )
    )
    check_api_key = AsyncMock()
    resolve_ref = AsyncMock(return_value=asset)
    monkeypatch.setattr("app.api.workflow_access.check_workflow_access", check_workflow)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_api_key)
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    if has_workflow_access:
        result = await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=run_id,
            user=user,
            expected_team_id=team_id,
        )
        assert result is asset
        resolve_ref.assert_awaited_once()
    else:
        with pytest.raises(BusinessError) as error:
            await asset_access.resolve_authorized_asset_ref(
                "a1b2",
                scope_type=AssetScopeType.WORKFLOW_RUN,
                scope_id=run_id,
                user=user,
                expected_team_id=team_id,
            )
        assert error.value.status_code == 403
        resolve_ref.assert_not_awaited()

    check_workflow.assert_awaited_once_with(workflow_id, user)
    if has_workflow_access:
        check_api_key.assert_awaited_once_with(None, workflow_id)
    else:
        check_api_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_asset_ref_denies_api_key_without_workflow_access(monkeypatch):
    workflow_id = uuid4()
    run_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user.id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    api_key = SimpleNamespace(id=uuid4())
    run.api_key_id = api_key.id
    run.api_key_origin_unknown = False
    _set_workflow_run_query(monkeypatch, run)
    denied = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="api_key_no_workflow_access",
        status_code=403,
    )
    check_api_key = AsyncMock(side_effect=denied)
    resolve_ref = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_api_key)
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=run_id,
            user=user,
            api_key=api_key,
        )

    assert error.value.status_code == 403
    assert error.value.msg_key == "access_denied"
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_asset_ref_returns_not_found_for_missing_run(monkeypatch):
    _set_workflow_run_query(monkeypatch, None)
    resolve_ref = AsyncMock()
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4(), is_superuser=False, roles=[]),
        )

    assert error.value.status_code == 404
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_conversation_asset_ref_returns_not_found_without_agent(monkeypatch):
    conversation = SimpleNamespace(agent=None)
    first = SimpleNamespace(first=AsyncMock(return_value=conversation))
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(prefetch_related=lambda *_: first),
    )
    resolve_ref = AsyncMock()
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4(), is_superuser=False, roles=[]),
        )

    assert error.value.status_code == 404
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_asset_scope_returns_not_found_without_lookup(monkeypatch):
    resolve_ref = AsyncMock()
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type="unknown",
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4(), is_superuser=False, roles=[]),
        )

    assert error.value.status_code == 404
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_ref_reraises_unexpected_api_key_errors(monkeypatch):
    workflow_id = uuid4()
    run_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user.id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    api_key = SimpleNamespace(id=uuid4())
    run.api_key_id = api_key.id
    run.api_key_origin_unknown = False
    _set_workflow_run_query(monkeypatch, run)
    unexpected = BusinessError(
        code=ResponseCode.INTERNAL_ERROR,
        msg_key="scope_check_failed",
        status_code=500,
    )
    check_api_key = AsyncMock(side_effect=unexpected)
    resolve_ref = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_api_key)
    monkeypatch.setattr("app.services.asset.asset_service.resolve_ref", resolve_ref)

    with pytest.raises(BusinessError) as error:
        await asset_access.resolve_authorized_asset_ref(
            "a1b2",
            scope_type=AssetScopeType.WORKFLOW_RUN,
            scope_id=run_id,
            user=user,
            api_key=api_key,
        )

    assert error.value is unexpected
    resolve_ref.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_type", [AssetScopeType.CONVERSATION, AssetScopeType.WORKFLOW_RUN]
)
@pytest.mark.parametrize(
    "origin,credential,allowed",
    [
        ("web", "web", True),
        ("web", "key", False),
        ("key", "web", False),
        ("key", "key", True),
        ("key", "other-key", False),
        ("key", "other-user", False),
        ("unknown", "web", False),
        ("unknown", "key", False),
    ],
)
async def test_protected_history_asset_enforces_credential_origin(
    monkeypatch, scope_type, origin, credential, allowed
):
    owner_id, key_id, scope_id, team_id = [uuid4() for _ in range(4)]
    user = SimpleNamespace(
        id=uuid4() if credential == "other-user" else owner_id,
        is_superuser=False,
    )
    key = (
        None
        if credential == "web"
        else SimpleNamespace(id=uuid4() if credential == "other-key" else key_id)
    )
    record = SimpleNamespace(
        user_id=owner_id,
        triggered_by_id=owner_id,
        api_key_id=key_id if origin == "key" else None,
        api_key_origin_unknown=origin == "unknown",
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=team_id),
        workflow_id=uuid4(),
        workflow=SimpleNamespace(team_id=team_id),
    )
    asset = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=record)
            )
        ),
    )
    _set_workflow_run_query(monkeypatch, record)
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[SimpleNamespace(scope_type=scope_type, scope_id=scope_id)]
        ),
    )
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", AsyncMock())
    get_asset = AsyncMock(return_value=asset)
    monkeypatch.setattr("app.services.asset.asset_service.get_authorized", get_asset)
    if allowed:
        assert (
            await asset_access.authorize_protected_asset(
                "file", authenticated=(user, key)
            )
            is asset
        )
    else:
        with pytest.raises(BusinessError) as denied:
            await asset_access.authorize_protected_asset(
                "file", authenticated=(user, key)
            )
        assert denied.value.status_code == 403
        get_asset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_raw_asset_id_cannot_rebind_a_file_from_another_history(
    monkeypatch, same_key
):
    user = SimpleNamespace(id=uuid4())
    key = SimpleNamespace(id=uuid4())
    target_id, source_id, asset_id, team_id = [uuid4() for _ in range(4)]
    asset = SimpleNamespace(id=asset_id)
    records = {
        scope_id: SimpleNamespace(
            user_id=user.id,
            agent_id=uuid4(),
            agent=SimpleNamespace(team_id=team_id),
            api_key_id=key.id if scope_id == target_id or same_key else uuid4(),
            api_key_origin_unknown=False,
        )
        for scope_id in (target_id, source_id)
    }
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda *, id: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=records[id])
            ),
        ),
    )
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    scope_type=AssetScopeType.CONVERSATION, scope_id=source_id
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", AsyncMock(return_value=asset)
    )
    result = asset_access.authorize_asset_for_scope(
        asset_id,
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=target_id,
        user=user,
        api_key=key,
        enforce_history_origin=True,
    )
    if same_key:
        assert await result is asset
    else:
        with pytest.raises(BusinessError) as denied:
            await result
        assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["web", "key", "missing-key", "unknown"])
async def test_worker_asset_import_uses_target_history_origin(monkeypatch, origin):
    user = SimpleNamespace(id=uuid4())
    key = SimpleNamespace(id=uuid4(), user_id=user.id)
    target_id, source_id = uuid4(), uuid4()
    asset = SimpleNamespace(id=uuid4())
    refs = [SimpleNamespace(scope_type=AssetScopeType.CONVERSATION, scope_id=source_id)]
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=refs)
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "get_or_none",
        AsyncMock(
            return_value=SimpleNamespace(
                api_key_id=None if origin == "web" else key.id,
                api_key_origin_unknown=origin == "unknown",
            )
        ),
    )
    monkeypatch.setattr(
        asset_access.APIKey,
        "get_or_none",
        AsyncMock(return_value=key if origin == "key" else None),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(asset_access, "_authorize_via_ref", authorize)
    result = asset_access.authorize_history_asset_import(
        asset, scope_type=AssetScopeType.CONVERSATION, scope_id=target_id, user=user
    )
    if origin in ("web", "key"):
        await result
        authorize.assert_awaited_once_with(
            asset, refs, user=user, api_key=key if origin == "key" else None
        )
    else:
        with pytest.raises(BusinessError):
            await result
        authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_log_asset_requires_permission_and_conversation_binding(
    monkeypatch,
):
    conversation_id, agent_id, user_id = [uuid4() for _ in range(3)]
    user = SimpleNamespace(id=user_id, is_active=True, is_superuser=False, roles=[])
    asset = SimpleNamespace(id=uuid4())
    load = AsyncMock(return_value=SimpleNamespace(agent_id=agent_id))
    monkeypatch.setattr(asset_access.Conversation, "get_or_none", load)
    check_agent = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.agents.check_agent_access", check_agent)
    monkeypatch.setattr(
        asset_access.Asset, "get_or_none", AsyncMock(return_value=asset)
    )
    exists = AsyncMock(return_value=False)
    links = MagicMock(return_value=SimpleNamespace(exists=exists))
    monkeypatch.setattr(asset_access.AssetScopeRef, "filter", links)
    authorize = AsyncMock(return_value=asset)
    monkeypatch.setattr(asset_access, "authorize_asset_for_scope", authorize)

    with pytest.raises(BusinessError) as no_permission:
        await asset_access.authorize_agent_log_asset(
            "file", conversation_id=conversation_id, user=user
        )
    assert no_permission.value.status_code == 403
    load.assert_not_awaited()

    user.roles = [
        SimpleNamespace(permissions=[SimpleNamespace(code="conversation:read")])
    ]
    with pytest.raises(BusinessError) as unlinked:
        await asset_access.authorize_agent_log_asset(
            "file", conversation_id=conversation_id, user=user
        )
    assert unlinked.value.status_code == 404
    authorize.assert_not_awaited()

    exists.return_value = True
    assert (
        await asset_access.authorize_agent_log_asset(
            "file", conversation_id=conversation_id, user=user
        )
        is asset
    )
    load.assert_awaited_with(id=conversation_id, user=user)
    check_agent.assert_awaited_with(agent_id, user)
    links.assert_called_with(
        asset_id=asset.id,
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
    )


@pytest.mark.asyncio
async def test_raw_asset_id_without_scope_refs_stays_authorized(monkeypatch):
    """A generated asset that is not bound to any scope has nothing to rebind."""
    asset = SimpleNamespace(id=uuid4())
    team_id = uuid4()
    conversation = SimpleNamespace(
        user_id=uuid4(),
        agent_id=uuid4(),
        agent=SimpleNamespace(team_id=team_id),
        api_key_id=None,
        api_key_origin_unknown=False,
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.services.asset.asset_service.get_authorized", AsyncMock(return_value=asset)
    )

    assert (
        await asset_access.authorize_asset_for_scope(
            asset.id,
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=conversation.user_id),
            expected_team_id=team_id,
            enforce_history_origin=True,
        )
        is asset
    )


@pytest.mark.asyncio
async def test_worker_import_checks_the_workflow_run_history_origin(monkeypatch):
    """A run-scoped URL import is authorized as that run's credential."""
    user = SimpleNamespace(id=uuid4())
    asset = SimpleNamespace(id=uuid4())
    target_run, source_run = uuid4(), uuid4()
    refs = [
        SimpleNamespace(scope_type=AssetScopeType.WORKFLOW_RUN, scope_id=source_run)
    ]
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=refs)
    )
    load_run = AsyncMock(
        return_value=SimpleNamespace(api_key_id=None, api_key_origin_unknown=False)
    )
    monkeypatch.setattr(asset_access.WorkflowRun, "get_or_none", load_run)
    authorize = AsyncMock()
    monkeypatch.setattr(asset_access, "_authorize_via_ref", authorize)

    await asset_access.authorize_history_asset_import(
        asset,
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=target_run,
        user=user,
    )

    load_run.assert_awaited_once_with(id=target_run)
    authorize.assert_awaited_once_with(asset, refs, user=user, api_key=None)


@pytest.mark.asyncio
async def test_worker_import_rejects_a_scope_it_cannot_classify(monkeypatch):
    """Only history-bearing scopes may receive an already-bound asset."""
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    scope_type=AssetScopeType.CONVERSATION, scope_id=uuid4()
                )
            ]
        ),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(asset_access, "_authorize_via_ref", authorize)

    with pytest.raises(BusinessError) as denied:
        await asset_access.authorize_history_asset_import(
            SimpleNamespace(id=uuid4()),
            scope_type=AssetScopeType.IM_CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4()),
        )

    assert denied.value.status_code == 403
    authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_im_conversation_scope_rejects_api_keys_before_any_lookup(monkeypatch):
    """Direct-message files are a user surface: an API key never reaches them."""
    conversation_filter = MagicMock(side_effect=AssertionError("no lookup expected"))
    monkeypatch.setattr("app.models.im.ImConversation.filter", conversation_filter)

    with pytest.raises(BusinessError) as denied:
        await asset_access.authorize_asset_scope(
            scope_type=AssetScopeType.IM_CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4()),
            api_key=SimpleNamespace(id=uuid4()),
        )

    assert denied.value.status_code == 403
    conversation_filter.assert_not_called()


@pytest.mark.asyncio
async def test_im_conversation_scope_hides_a_missing_conversation(monkeypatch):
    monkeypatch.setattr(
        "app.models.im.ImConversation.filter",
        MagicMock(return_value=SimpleNamespace(first=AsyncMock(return_value=None))),
    )

    with pytest.raises(BusinessError) as missing:
        await asset_access.authorize_asset_scope(
            scope_type=AssetScopeType.IM_CONVERSATION,
            scope_id=uuid4(),
            user=SimpleNamespace(id=uuid4(), is_superuser=False),
        )

    assert missing.value.code == ResponseCode.NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conversation",
    [None, SimpleNamespace(agent_id=None)],
)
async def test_agent_log_asset_hides_a_conversation_without_an_agent(
    monkeypatch, conversation
):
    """A logged conversation must still resolve its Agent before any file read."""
    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        roles=[
            SimpleNamespace(permissions=[SimpleNamespace(code="conversation:read")])
        ],
    )
    load = AsyncMock(return_value=conversation)
    monkeypatch.setattr(asset_access.Conversation, "get_or_none", load)
    check_agent = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.agents.check_agent_access", check_agent)
    asset_lookup = AsyncMock()
    monkeypatch.setattr(asset_access.Asset, "get_or_none", asset_lookup)

    with pytest.raises(BusinessError) as missing:
        await asset_access.authorize_agent_log_asset(
            "file", conversation_id=uuid4(), user=user
        )

    assert missing.value.code == ResponseCode.NOT_FOUND
    check_agent.assert_not_awaited()
    asset_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_run_without_a_workflow_is_not_accepted_as_access(monkeypatch):
    """A run whose workflow relation is gone grants nobody log-level access."""
    from app.api import workflow_access

    run = SimpleNamespace(triggered_by_id=uuid4(), workflow_id=None)
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    check = AsyncMock()
    monkeypatch.setattr(workflow_access, "check_workflow_access", check)

    assert await asset_access._can_access_workflow_run(run, user) is False
    check.assert_not_awaited()

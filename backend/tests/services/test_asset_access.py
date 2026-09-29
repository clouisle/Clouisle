from types import SimpleNamespace
from unittest.mock import AsyncMock
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

    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    api_key = SimpleNamespace()
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
    api_key = SimpleNamespace()
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

    api_key = SimpleNamespace()
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
    check_agent = AsyncMock(side_effect=unexpected)
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/shared.txt",
            authenticated=(
                SimpleNamespace(id=user_id, is_superuser=False, roles=[]),
                SimpleNamespace(),
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
    api_key = SimpleNamespace()
    conversation = SimpleNamespace(
        id=conversation_id,
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
            api_key=SimpleNamespace(),
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
            api_key=SimpleNamespace(),
        )

    assert error.value is unexpected
    resolve_ref.assert_not_awaited()

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import feishu
from app.core.i18n import t as translate
from app.integrations.feishu import (
    FeishuAPIError,
    FeishuDirectoryUser,
    FeishuSecretError,
)
from app.schemas.response import BusinessError, ResponseCode


def _client(**overrides):
    client = SimpleNamespace(list_users=AsyncMock(), list_departments=AsyncMock())
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


@pytest.mark.asyncio
async def test_sync_reports_feishu_rejection_reason_without_internal_details(
    monkeypatch,
):
    monkeypatch.setattr(
        feishu.SiteSetting,
        "get_value",
        AsyncMock(return_value=["dept-a"]),
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(
                    side_effect=FeishuAPIError(
                        "Feishu API HTTP 400 (code 41050): no user authority error",
                        detail='{"code":41050,"msg":"no user authority error"}',
                    )
                )
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    error = exc_info.value
    assert error.code == ResponseCode.BAD_REQUEST
    assert error.msg_key == "feishu_api_error"
    assert "41050" in error.kwargs["error"]
    assert "no user authority error" in error.kwargs["error"]
    # The rendered message is what the admin sees in the integrations page.
    assert len(translate("feishu_api_error", lang="en", **error.kwargs)) < 200


@pytest.mark.asyncio
async def test_sync_reports_undecryptable_secret_as_actionable_config_error(
    monkeypatch,
):
    monkeypatch.setattr(
        feishu.SiteSetting, "get_value", AsyncMock(return_value=["dept-a"])
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            side_effect=FeishuSecretError(
                "Stored Feishu app secret cannot be decrypted"
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "feishu_secret_undecryptable"


@pytest.mark.asyncio
async def test_sync_keeps_unexpected_failures_generic(monkeypatch):
    monkeypatch.setattr(
        feishu.SiteSetting, "get_value", AsyncMock(return_value=["dept-a"])
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(side_effect=RuntimeError("db down"))
            )
        ),
    )

    with pytest.raises(BusinessError) as exc_info:
        await feishu.sync_contacts(
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.UNKNOWN_ERROR
    assert exc_info.value.msg_key == "internal_error"


@pytest.mark.asyncio
async def test_sync_returns_synced_counts(monkeypatch):
    members = [
        FeishuDirectoryUser(
            user_id="u1",
            open_id="o1",
            union_id=None,
            name="Ada",
            email="ada@example.com",
            avatar_url=None,
        )
    ]
    monkeypatch.setattr(
        feishu.SiteSetting, "get_value", AsyncMock(return_value=["dept-a"])
    )
    monkeypatch.setattr(
        feishu,
        "_configured_client",
        AsyncMock(
            return_value=_client(
                list_users=AsyncMock(return_value=members),
                list_departments=AsyncMock(
                    return_value=[
                        SimpleNamespace(
                            department_id="0",
                            name="Acme Inc.",
                            children=[
                                SimpleNamespace(department_id="dept-a", children=[])
                            ],
                        )
                    ]
                ),
            )
        ),
    )
    synced = SimpleNamespace(created=1, updated=2, skipped=3)
    monkeypatch.setattr(feishu, "sync_directory_users", AsyncMock(return_value=synced))
    monkeypatch.setattr(feishu, "sync_department_teams", AsyncMock(return_value=2))
    response = await feishu.sync_contacts(
        request=MagicMock(),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"] == {
        "created": 1,
        "updated": 2,
        "skipped": 3,
        "teams_created": 2,
    }


@pytest.mark.asyncio
async def test_company_department_scope_syncs_company_and_descendant_teams(monkeypatch):
    members = [
        FeishuDirectoryUser(
            user_id="u1",
            open_id="o1",
            union_id=None,
            name="Ada",
            email=None,
            avatar_url=None,
            department_ids=frozenset({"dept-a"}),
        )
    ]
    company = SimpleNamespace(
        department_id="0",
        name="Company",
        children=[
            SimpleNamespace(department_id="dept-a", name="Engineering", children=[])
        ],
    )
    client = _client(
        list_users=AsyncMock(return_value=members),
        list_departments=AsyncMock(return_value=[company]),
    )
    monkeypatch.setattr(feishu.SiteSetting, "get_value", AsyncMock(return_value=["0"]))
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        feishu,
        "sync_directory_users",
        AsyncMock(return_value=SimpleNamespace(created=1, updated=0, skipped=0)),
    )
    sync_teams = AsyncMock(return_value=2)
    monkeypatch.setattr(feishu, "sync_department_teams", sync_teams)

    response = await feishu.sync_contacts(
        request=MagicMock(), current_user=SimpleNamespace(id=uuid4())
    )

    assert response["data"]["teams_created"] == 2
    assert [
        department.department_id for department in sync_teams.await_args.args[0]
    ] == ["0", "dept-a"]
    assert sync_teams.await_args.args[1] == members
    assert client.list_users.await_args.args[0] == ["0", "dept-a"]


@pytest.mark.asyncio
async def test_department_scope_accepts_company_root_id(monkeypatch):
    client = _client(
        list_departments=AsyncMock(
            return_value=[SimpleNamespace(department_id="dept-a", children=[])]
        )
    )
    monkeypatch.setattr(feishu, "_configured_client", AsyncMock(return_value=client))
    monkeypatch.setattr(feishu.SiteSetting, "set_value", AsyncMock())
    monkeypatch.setattr(feishu.AuditLogService, "log", AsyncMock())

    response = await feishu.update_department_scope(
        request=MagicMock(),
        data=feishu.FeishuDepartmentScopeUpdate(department_ids=["0"]),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert response["data"] == {"department_ids": ["0"]}

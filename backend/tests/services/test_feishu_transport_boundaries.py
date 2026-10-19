from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations import feishu
from app.integrations.credentials import encrypt_secret


@pytest.fixture
def transport_client(monkeypatch):
    original = httpx.AsyncClient

    def install(handler):
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            feishu.httpx,
            "AsyncClient",
            lambda **kwargs: original(transport=transport, **kwargs),
        )
        monkeypatch.setattr(feishu.asyncio, "sleep", AsyncMock())
        return feishu.FeishuClient("app-id", encrypt_secret("never-display-secret"))

    return install


def token_response(request):
    if request.url.path.endswith("/internal"):
        return httpx.Response(
            200, json={"code": 0, "tenant_access_token": "tenant-token"}
        )
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=["not", "an", "object"]),
        httpx.Response(200, json={"code": 0, "data": {"items": "invalid"}}),
        httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": "yes"}}),
    ],
)
async def test_wiki_malformed_page_responses_abort_scan(transport_client, response):
    def handler(request):
        return token_response(request) or response

    with pytest.raises(feishu.FeishuAPIError):
        await transport_client(handler).list_wiki_spaces()


@pytest.mark.asyncio
@pytest.mark.parametrize("page_token", [None, "", "first"])
async def test_wiki_pagination_must_advance(transport_client, page_token):
    calls = 0

    def handler(request):
        nonlocal calls
        auth = token_response(request)
        if auth:
            return auth
        calls += 1
        token = "first" if calls == 1 or page_token == "first" else page_token
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": token},
            },
        )

    with pytest.raises(feishu.FeishuAPIError, match="did not advance"):
        await transport_client(handler).list_wiki_spaces()


@pytest.mark.asyncio
async def test_wiki_permission_denial_is_classified_and_scopes_are_validated(
    transport_client,
):
    def handler(request):
        auth = token_response(request)
        if auth:
            return auth
        return httpx.Response(
            403,
            json={
                "code": 99991672,
                "msg": "sensitive provider diagnostic",
                "error": {
                    "permission_violations": [
                        {"subject": "wiki:space:retrieve"},
                        {"subject": "Bearer secret-token"},
                    ]
                },
            },
        )

    with pytest.raises(feishu.FeishuAPIError) as raised:
        await transport_client(handler).list_wiki_spaces()
    assert raised.value.permission_denied is False
    assert raised.value.required_scopes == ("wiki:space:retrieve",)
    from app.services.feishu_knowledge import public_error

    message = public_error(raised.value)
    assert "sensitive provider diagnostic" not in message
    assert "never-display-secret" not in message


@pytest.mark.asyncio
async def test_wiki_node_permission_error_marks_denied_subtree(transport_client):
    def handler(request):
        auth = token_response(request)
        if auth:
            return auth
        return httpx.Response(403, json={"code": 131006, "msg": "denied"})

    with pytest.raises(feishu.FeishuAPIError) as raised:
        await transport_client(handler).list_wiki_nodes("space")
    assert raised.value.permission_denied
    assert raised.value.resource_scope == "wiki_space"


@pytest.mark.asyncio
async def test_directory_pagination_stops_when_more_has_no_token(transport_client):
    requests = []

    def handler(request):
        requests.append(request)
        auth = token_response(request)
        if auth:
            return auth
        if request.url.path.endswith("/tenant/query"):
            return httpx.Response(
                200, json={"code": 0, "data": {"tenant": {"name": "Org"}}}
            )
        return httpx.Response(
            200, json={"code": 0, "data": {"items": [], "has_more": True}}
        )

    # Directory APIs tolerate an absent cursor by stopping rather than looping forever.
    result = await transport_client(handler).list_departments()
    assert result[0].name == "Org"
    assert sum(request.url.path.endswith("/children") for request in requests) == 1


@pytest.mark.asyncio
async def test_transport_error_does_not_expose_app_secret(transport_client):
    def handler(request):
        auth = token_response(request)
        if auth:
            return auth
        return httpx.Response(500, text="provider echoed never-display-secret")

    with pytest.raises(feishu.FeishuAPIError) as raised:
        await transport_client(handler).list_wiki_spaces()
    assert "never-display-secret" not in str(raised.value)
    assert "never-display-secret" in (raised.value.detail or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        {},
        {"node_token": "n"},
        {"node_token": "n", "obj_token": "d", "obj_type": "docx"},
        {"node_token": "n", "obj_token": "d", "obj_type": "docx", "has_child": "false"},
    ],
)
async def test_invalid_wiki_node_never_looks_like_complete_inventory(
    transport_client, item
):
    def handler(request):
        return token_response(request) or httpx.Response(
            200, json={"code": 0, "data": {"items": [item], "has_more": False}}
        )

    with pytest.raises(feishu.FeishuAPIError):
        await transport_client(handler).list_wiki_nodes("space")


@pytest.mark.asyncio
@pytest.mark.parametrize("item", [{}, {"space_id": ""}, {"space_id": 123}, None])
async def test_invalid_wiki_space_identity_aborts_inventory(transport_client, item):
    def handler(request):
        return token_response(request) or httpx.Response(
            200, json={"code": 0, "data": {"items": [item], "has_more": False}}
        )

    with pytest.raises(feishu.FeishuAPIError):
        await transport_client(handler).list_wiki_spaces()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "items",
    [
        [None],
        [{}],
        [{"open_id": "", "user_id": "id", "name": "Name"}],
        [{"open_id": "open", "user_id": "id", "name": ""}],
    ],
)
async def test_directory_skips_unidentifiable_entries(transport_client, items):
    def handler(request):
        return token_response(request) or httpx.Response(
            200, json={"code": 0, "data": {"items": items, "has_more": False}}
        )

    assert await transport_client(handler).list_users(["department"]) == []


@pytest.mark.asyncio
async def test_directory_missing_user_id_aborts_instead_of_creating_wrong_identity(
    transport_client,
):
    def handler(request):
        return token_response(request) or httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [{"open_id": "open", "name": "Name"}],
                    "has_more": False,
                },
            },
        )

    with pytest.raises(feishu.FeishuAPIError, match="user_id"):
        await transport_client(handler).list_users(["department"])


@pytest.mark.asyncio
async def test_directory_user_pagination_merges_departments_and_normalizes_fields(
    transport_client,
):
    requests = []

    def handler(request):
        auth = token_response(request)
        if auth:
            return auth
        requests.append(request)
        if request.url.params.get("department_id") == "dept-a":
            if request.url.params.get("page_token"):
                return httpx.Response(
                    200,
                    json={"code": 0, "data": {"items": [], "has_more": False}},
                )
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "user_id": "user-1",
                                "open_id": "open-1",
                                "name": "Ada",
                                "email": " ADA@EXAMPLE.COM ",
                                "avatar": {"avatar_240": "https://img.example/a"},
                                "department_ids": ["dept-a", 8, ""],
                            }
                        ],
                        "has_more": True,
                        "page_token": "page-2",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "user_id": "user-1",
                            "open_id": "open-1",
                            "name": "Ada Lovelace",
                            "union_id": "union-1",
                            "email": "ada@example.com",
                            "avatar": {
                                "avatar_240": "",
                                "avatar_72": "https://img.example/a-small",
                            },
                            "department_ids": ["dept-b"],
                        }
                    ],
                    "has_more": False,
                },
            },
        )

    users = await transport_client(handler).list_users(["dept-a", "dept-b"])

    assert len(users) == 1
    assert users[0].name == "Ada Lovelace"
    assert users[0].email == "ada@example.com"
    assert users[0].union_id == "union-1"
    assert users[0].avatar_url == "https://img.example/a-small"
    assert users[0].department_ids == frozenset({"dept-a", "dept-b"})
    assert requests[1].url.params["page_token"] == "page-2"
    assert requests[2].url.params["department_id"] == "dept-b"


@pytest.mark.asyncio
async def test_department_tree_handles_missing_parent_and_skips_malformed_rows(
    transport_client,
):
    def handler(request):
        auth = token_response(request)
        if auth:
            return auth
        if request.url.path.endswith("/tenant/query"):
            return httpx.Response(
                200, json={"code": 0, "data": {"tenant": {"name": "  Acme  "}}}
            )
        if request.url.path.endswith("/0/children"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            None,
                            {"open_department_id": "bad", "name": 3},
                            {
                                "open_department_id": "dept-a",
                                "name": "Engineering",
                                "parent_department_id": "missing-parent",
                            },
                        ],
                        "has_more": False,
                    },
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {"items": []}})

    root = (await transport_client(handler).list_departments())[0]

    assert root.name == "Acme"
    assert [
        (child.department_id, child.parent_department_id) for child in root.children
    ] == [("dept-a", "missing-parent")]

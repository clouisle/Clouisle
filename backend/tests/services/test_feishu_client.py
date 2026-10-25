import httpx
import pytest

from app.integrations import feishu


@pytest.mark.asyncio
async def test_list_users_uses_documented_department_query_and_deduplicates(
    monkeypatch,
):
    responses = [
        (200, {"code": 0, "tenant_access_token": "token"}),
        (
            200,
            {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "user_id": "u1",
                            "open_id": "o1",
                            "name": "Ada",
                            "email": " ADA@example.com ",
                            "department_ids": ["dept-a", "dept-shared"],
                        }
                    ],
                    "has_more": False,
                },
            },
        ),
        (
            200,
            {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "user_id": "u1",
                            "open_id": "o1",
                            "name": "Ada",
                            "email": "ada@example.com",
                            "department_ids": ["dept-b", "dept-shared"],
                        },
                        {"user_id": "u2", "open_id": "o2", "name": "Lin"},
                    ],
                    "has_more": False,
                },
            },
        ),
    ]
    requests = []

    async def handler(request):
        requests.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body, request=request)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class ClientFactory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original_client(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", ClientFactory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"
    users = await client.list_users(["dept-a", "dept-b"])

    assert [(user.user_id, user.email, user.department_ids) for user in users] == [
        ("u1", "ada@example.com", frozenset({"dept-a", "dept-b", "dept-shared"})),
        ("u2", None, frozenset({"dept-b"})),
    ]
    user_requests = [
        request
        for request in requests
        if request.url.path.endswith("/find_by_department")
    ]
    assert [request.url.params["department_id"] for request in user_requests] == [
        "dept-a",
        "dept-b",
    ]
    assert all(
        request.url.params["department_id_type"] == "open_department_id"
        for request in user_requests
    )
    assert all(
        request.url.params["user_id_type"] == "user_id" for request in user_requests
    )
    assert all(request.url.params["page_size"] == "50" for request in user_requests)
    assert all(
        request.headers["Authorization"] == "Bearer token" for request in user_requests
    )


@pytest.mark.asyncio
async def test_missing_user_id_raises_actionable_permission_error(monkeypatch):
    responses = [
        (200, {"code": 0, "tenant_access_token": "token"}),
        (
            200,
            {
                "code": 0,
                "data": {
                    "items": [{"open_id": "o1", "name": "Ada"}],
                    "has_more": False,
                },
            },
        ),
    ]

    async def handler(request):
        status, body = responses.pop(0)
        return httpx.Response(status, json=body, request=request)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    class ClientFactory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original_client(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", ClientFactory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"

    with pytest.raises(
        feishu.FeishuAPIError, match="contact:user.employee_id:readonly"
    ):
        await client.list_users(["dept-a"])


@pytest.mark.asyncio
async def test_http_error_stays_short_for_ui_and_keeps_raw_detail_for_logs(monkeypatch):
    body = {
        "code": 41050,
        "msg": "no user authority error",
        "error": {
            "troubleshooter": "https://open.feishu.cn/search?from=openapi&log_id=abc",
            "log_id": "abc",
        },
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json=body, request=request)
    )
    original_client = httpx.AsyncClient

    class ClientFactory:
        def __init__(self, **_kwargs):
            self.client = original_client(transport=transport, base_url=feishu.API_BASE)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", ClientFactory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"
    with pytest.raises(feishu.FeishuAPIError) as exc_info:
        await client.list_users(["dept-a"])

    assert len(str(exc_info.value)) < 200
    assert "41050" in str(exc_info.value)
    assert "no user authority error" in str(exc_info.value)
    assert "troubleshooter" not in str(exc_info.value)
    assert "troubleshooter" in exc_info.value.detail
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_long_feishu_message_is_truncated_to_a_displayable_length(monkeypatch):
    body = {"code": 99991672, "msg": "x" * 500}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json=body, request=request)
    )
    original_client = httpx.AsyncClient

    class ClientFactory:
        def __init__(self, **_kwargs):
            self.client = original_client(transport=transport, base_url=feishu.API_BASE)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", ClientFactory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"

    with pytest.raises(feishu.FeishuAPIError) as exc_info:
        await client.list_users(["dept-a"])

    assert len(str(exc_info.value)) < 200
    assert "99991672" in str(exc_info.value)
    assert len(exc_info.value.detail) <= 1024


@pytest.mark.asyncio
async def test_list_departments_includes_company_root_node_and_attaches_children(
    monkeypatch,
):
    responses = [
        (200, {"code": 0, "tenant_access_token": "token"}),
        (200, {"code": 0, "data": {"tenant": {"name": "Acme Inc."}}}),
        (
            200,
            {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "open_department_id": "dept-a",
                            "name": "Engineering",
                            "parent_department_id": "0",
                        }
                    ],
                    "has_more": False,
                },
            },
        ),
        (
            200,
            {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "open_department_id": "dept-b",
                            "name": "Platform",
                            "parent_department_id": "dept-a",
                        }
                    ],
                    "has_more": False,
                },
            },
        ),
        (200, {"code": 0, "data": {"items": [], "has_more": False}}),
    ]
    requests = []

    async def handler(request):
        requests.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body, request=request)

    original_client = httpx.AsyncClient

    class ClientFactory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original_client(
                transport=httpx.MockTransport(handler), **kwargs
            )

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", ClientFactory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id = "app"
    client.app_secret = "secret"

    [company] = await client.list_departments()

    assert (company.department_id, company.name) == ("0", "Acme Inc.")
    assert (company.children[0].department_id, company.children[0].name) == (
        "dept-a",
        "Engineering",
    )
    assert (
        company.children[0].children[0].department_id,
        company.children[0].children[0].name,
    ) == ("dept-b", "Platform")
    tenant_requests = [
        request
        for request in requests
        if request.url.path == "/open-apis/tenant/v2/tenant/query"
    ]
    assert len(tenant_requests) == 1
    assert tenant_requests[0].headers["Authorization"] == "Bearer token"


@pytest.mark.asyncio
async def test_malformed_token_and_directory_responses_are_rejected(monkeypatch):
    from app.integrations import feishu

    responses = [
        {"code": 0},
        {"code": 0, "tenant_access_token": "token"},
        {"code": 0, "data": {"tenant": {"name": "   "}}},
    ]

    def handler(request):
        return httpx.Response(200, json=responses.pop(0), request=request)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Factory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", Factory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id, client.app_secret = "app", "secret"
    with pytest.raises(feishu.FeishuAPIError, match="access token"):
        await client.check_connection()

    with pytest.raises(feishu.FeishuAPIError, match="tenant name"):
        await client.list_departments()


def test_scope_extraction_ignores_bad_violations_and_uses_path_fallback():
    assert feishu._required_scopes(
        {"code": 99991672, "error": {"permission_violations": "invalid"}},
        "/wiki/v2/spaces",
    ) == ("wiki:space:retrieve", "wiki:wiki:readonly", "wiki:wiki")
    assert (
        feishu._required_scopes(
            {
                "code": 99991672,
                "error": {"permission_violations": [None, {"subject": "bad"}]},
            },
            "/unknown",
        )
        == ()
    )


@pytest.mark.asyncio
async def test_message_without_link_omits_card_button(monkeypatch):
    from app.integrations import feishu
    import json

    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("tenant_access_token/internal"):
            body = {"code": 0, "tenant_access_token": "token"}
        else:
            body = {"code": 0}
        return httpx.Response(200, json=body, request=request)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Factory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", Factory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id, client.app_secret = "app", "secret"
    await client.send_user_message("user", "Title", "body")
    payload = json.loads(requests[-1].content)
    card = json.loads(payload["content"])
    assert card["body"]["elements"] == [{"tag": "markdown", "content": "body"}]


@pytest.mark.asyncio
async def test_directory_and_wiki_malformed_payloads_fail_closed(monkeypatch):
    from app.integrations import feishu

    responses = []

    def handler(request):
        body = responses.pop(0)
        return httpx.Response(200, json=body, request=request)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Factory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", Factory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id, client.app_secret = "app", "secret"
    client._knowledge_request_at = 0

    responses.extend(
        [
            {"code": 0, "tenant_access_token": "token"},
            {"code": 0, "data": {"tenant": {"name": "Acme"}}},
            {"code": 0, "data": None},
        ]
    )
    with pytest.raises(feishu.FeishuAPIError, match="department response"):
        await client.list_departments()

    responses.extend(
        [
            {"code": 0, "tenant_access_token": "token"},
            {"code": 0, "data": {"items": [{"name": "missing id"}], "has_more": False}},
        ]
    )
    with pytest.raises(feishu.FeishuAPIError, match="without an ID"):
        await client.list_wiki_spaces()

    responses.extend(
        [
            {"code": 0, "tenant_access_token": "token"},
            {
                "code": 0,
                "data": {
                    "items": [{"node_token": "n", "has_child": False}],
                    "has_more": False,
                },
            },
        ]
    )
    with pytest.raises(feishu.FeishuAPIError, match="without its object"):
        await client.list_wiki_nodes("space")


def test_login_body_rejects_non_object_response():
    request = httpx.Request("POST", "https://example.com/login")
    with pytest.raises(feishu.FeishuAPIError, match="unexpected body"):
        feishu._login_body(
            httpx.Response(200, json=["unexpected"], request=request), "login"
        )


@pytest.mark.asyncio
async def test_error_without_message_uses_request_path(monkeypatch):
    from app.integrations import feishu

    def handler(request):
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "token"}, request=request
            )
        return httpx.Response(400, json={"code": 123}, request=request)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Factory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", Factory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id, client.app_secret = "app", "secret"
    with pytest.raises(feishu.FeishuAPIError, match="HTTP 400"):
        await client.list_users(["dept"])


@pytest.mark.asyncio
async def test_user_and_wiki_pagination_validate_payload_and_duplicate_nodes(
    monkeypatch,
):
    from app.integrations import feishu

    responses = []

    def handler(request):
        return httpx.Response(200, json=responses.pop(0), request=request)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class Factory:
        def __init__(self, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("follow_redirects", None)
            kwargs.pop("trust_env", None)
            self.client = original(transport=transport, **kwargs)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    monkeypatch.setattr(feishu.httpx, "AsyncClient", Factory)
    client = feishu.FeishuClient.__new__(feishu.FeishuClient)
    client.app_id, client.app_secret = "app", "secret"
    client._knowledge_request_at = 0
    responses.extend(
        [
            {"code": 0, "tenant_access_token": "token"},
            {"code": 0, "data": None},
        ]
    )
    with pytest.raises(feishu.FeishuAPIError, match="user response"):
        await client.list_users(["dept"])

    responses.extend(
        [
            {"code": 0, "tenant_access_token": "token"},
            {
                "code": 0,
                "data": {
                    "items": [
                        {
                            "node_token": "n",
                            "obj_token": "o",
                            "obj_type": "doc",
                            "has_child": False,
                        },
                        {
                            "node_token": "n",
                            "obj_token": "o",
                            "obj_type": "doc",
                            "has_child": False,
                        },
                    ],
                    "has_more": False,
                },
            },
        ]
    )
    with pytest.raises(feishu.FeishuAPIError, match="repeated node"):
        await client.list_wiki_nodes("space")

"""Feishu Open Platform client for administrator-driven directory sync."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any
from urllib.parse import quote

import httpx

from app.integrations.credentials import decrypt_secret

API_BASE = "https://open.feishu.cn/open-apis"
TIMEOUT = httpx.Timeout(20.0, connect=5.0)
PAGE_SIZE = 50

# User-authorized (web login) endpoints. Overridable per integration so a
# deployment can point at a Lark tenant or a test double.
DEFAULT_AUTHORIZATION_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
DEFAULT_TOKEN_URL = "https://accounts.feishu.cn/oauth/v3/token"
DEFAULT_USERINFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
# `user_info` needs no scope for identity, but the email field requires this one.
DEFAULT_LOGIN_SCOPES = "contact:user.base:readonly contact:user.email:readonly"


@dataclass
class FeishuDepartment:
    department_id: str
    name: str
    parent_department_id: str | None
    children: list["FeishuDepartment"] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "department_id": self.department_id,
            "name": self.name,
            "parent_department_id": self.parent_department_id,
            "children": [child.as_dict() for child in self.children],
        }


@dataclass(frozen=True)
class FeishuDirectoryUser:
    user_id: str
    open_id: str
    union_id: str | None
    name: str
    email: str | None
    avatar_url: str | None
    department_ids: frozenset[str] = frozenset()


class FeishuAPIError(ValueError):
    """The Feishu Open Platform rejected an API request.

    `message` stays short enough for the administrator UI to display; `detail`
    carries the raw response for server logs.
    """

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.detail = detail


def _short(value: object, limit: int = 120) -> str:
    text = str(value).strip().replace("\n", " ")
    return text[:limit]


def _error_message(response: httpx.Response) -> tuple[str, str]:
    """Build a displayable message plus a log-only detail from a Feishu error response."""
    raw = response.text[:1024]
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = body.get("code")
        msg = body.get("msg")
        if msg:
            return (
                f"Feishu API HTTP {response.status_code} (code {code}): {_short(msg)}",
                raw,
            )
    return (
        f"Feishu API HTTP {response.status_code} for {response.request.url.path}",
        raw,
    )


class FeishuClient:
    def __init__(self, app_id: str, encrypted_app_secret: str):
        self.app_id = app_id.strip()
        self.app_secret = decrypt_secret(encrypted_app_secret)

    async def _request(
        self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        response = await client.request(method, path, **kwargs)
        if response.status_code >= 400:
            message, detail = _error_message(response)
            raise FeishuAPIError(message, detail=detail)
        try:
            body = response.json()
        except ValueError as exc:
            raise FeishuAPIError(
                f"Feishu API HTTP {response.status_code} returned a non-JSON body",
                detail=response.text[:1024],
            ) from exc
        if not isinstance(body, dict) or body.get("code") != 0:
            code = body.get("code") if isinstance(body, dict) else "invalid response"
            msg = body.get("msg", "") if isinstance(body, dict) else ""
            raise FeishuAPIError(
                f"Feishu API error {code}: {_short(msg)}",
                detail=str(body)[:1024],
            )
        return body

    async def _token(self, client: httpx.AsyncClient) -> str:
        body = await self._request(
            client,
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = body.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuAPIError("Feishu did not return a tenant access token")
        return token

    async def check_connection(self) -> None:
        """Verify app credentials by requesting a tenant access token."""
        async with httpx.AsyncClient(
            base_url=API_BASE,
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            await self._token(client)

    async def send_user_message(
        self,
        feishu_user_id: str,
        title: str,
        content: str,
        link_url: str | None = None,
        link_label: str | None = None,
    ) -> None:
        """Send a direct message, using a native card button for optional links."""
        card: dict[str, Any] = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "body": {
                "elements": [
                    {"tag": "markdown", "content": content},
                ]
            },
        }
        if link_url:
            card["body"]["elements"].append(
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": link_label or "View details",
                    },
                    "type": "primary",
                    "url": link_url,
                }
            )

        async with httpx.AsyncClient(
            base_url=API_BASE,
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            token = await self._token(client)
            await self._request(
                client,
                "POST",
                "/im/v1/messages",
                params={"receive_id_type": "user_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": feishu_user_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False),
                },
            )

    async def list_departments(self) -> list[FeishuDepartment]:
        async with httpx.AsyncClient(
            base_url=API_BASE,
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            token = await self._token(client)
            headers = {"Authorization": f"Bearer {token}"}
            tenant_body = await self._request(
                client,
                "GET",
                "/tenant/v2/tenant/query",
                headers=headers,
            )
            tenant_data = tenant_body.get("data")
            tenant = (
                tenant_data.get("tenant") if isinstance(tenant_data, dict) else None
            )
            tenant_name = tenant.get("name") if isinstance(tenant, dict) else None
            company_name = (
                tenant_name.strip()
                if isinstance(tenant_name, str) and tenant_name.strip()
                else None
            )
            if company_name is None:
                raise FeishuAPIError("Feishu did not return the tenant name")
            departments: dict[str, FeishuDepartment] = {}
            pending = ["0"]
            while pending:
                parent_id = pending.pop()
                page_token: str | None = None
                while True:
                    params: dict[str, Any] = {
                        "department_id_type": "open_department_id",
                        "page_size": PAGE_SIZE,
                        "fetch_child": "false",
                    }
                    if page_token:
                        params["page_token"] = page_token
                    body = await self._request(
                        client,
                        "GET",
                        f"/contact/v3/departments/{quote(parent_id, safe='')}/children",
                        headers=headers,
                        params=params,
                    )
                    payload = body.get("data")
                    if not isinstance(payload, dict):
                        raise FeishuAPIError("Invalid Feishu department response")
                    for item in payload.get("items", []):
                        if not isinstance(item, dict):
                            continue
                        department_id = item.get("open_department_id")
                        name = item.get("name")
                        if (
                            not isinstance(department_id, str)
                            or not department_id
                            or not isinstance(name, str)
                        ):
                            continue
                        parent = item.get("parent_department_id")
                        department = FeishuDepartment(
                            department_id=department_id,
                            name=name,
                            parent_department_id=parent
                            if isinstance(parent, str) and parent
                            else parent_id,
                        )
                        departments[department_id] = department
                        pending.append(department_id)
                    page_token = payload.get("page_token")
                    if not payload.get("has_more") or not page_token:
                        break
            roots: list[FeishuDepartment] = []
            for department in departments.values():
                parent = departments.get(department.parent_department_id or "")
                if parent:
                    parent.children.append(department)
                else:
                    roots.append(department)
            return [FeishuDepartment("0", company_name, None, roots)]

    async def list_users(self, department_ids: list[str]) -> list[FeishuDirectoryUser]:
        async with httpx.AsyncClient(
            base_url=API_BASE,
            timeout=TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            token = await self._token(client)
            headers = {"Authorization": f"Bearer {token}"}
            users: dict[str, FeishuDirectoryUser] = {}
            for department_id in department_ids:
                page_token: str | None = None
                while True:
                    params: dict[str, Any] = {
                        "department_id_type": "open_department_id",
                        "user_id_type": "user_id",
                        "department_id": department_id,
                        "page_size": PAGE_SIZE,
                    }
                    if page_token:
                        params["page_token"] = page_token
                    body = await self._request(
                        client,
                        "GET",
                        "/contact/v3/users/find_by_department",
                        headers=headers,
                        params=params,
                    )
                    payload = body.get("data")
                    if not isinstance(payload, dict):
                        raise FeishuAPIError("Invalid Feishu user response")
                    for item in payload.get("items", []):
                        if not isinstance(item, dict):
                            continue
                        user_id, open_id, name = (
                            item.get("user_id"),
                            item.get("open_id"),
                            item.get("name"),
                        )
                        if not isinstance(open_id, str) or not open_id:
                            continue
                        if not isinstance(user_id, str) or not user_id:
                            raise FeishuAPIError(
                                "Feishu returned no user_id; grant "
                                "'contact:user.employee_id:readonly' to read user IDs"
                            )
                        if not isinstance(name, str) or not name:
                            continue
                        avatar = item.get("avatar")
                        avatar_url = None
                        if isinstance(avatar, dict):
                            avatar_url = next(
                                (
                                    avatar[key]
                                    for key in (
                                        "avatar_240",
                                        "avatar_72",
                                        "avatar_40",
                                        "avatar_origin",
                                    )
                                    if isinstance(avatar.get(key), str) and avatar[key]
                                ),
                                None,
                            )
                        email = item.get("email")
                        raw_department_ids = item.get("department_ids")
                        member_department_ids = (
                            frozenset(
                                value
                                for value in raw_department_ids
                                if isinstance(value, str) and value
                            )
                            if isinstance(raw_department_ids, list)
                            else frozenset()
                        )
                        existing = users.get(user_id)
                        users[user_id] = FeishuDirectoryUser(
                            user_id=user_id,
                            open_id=open_id,
                            union_id=item.get("union_id")
                            if isinstance(item.get("union_id"), str)
                            else None,
                            name=name,
                            email=email.strip().lower()
                            if isinstance(email, str) and email.strip()
                            else None,
                            avatar_url=avatar_url,
                            department_ids=(
                                existing.department_ids if existing else frozenset()
                            )
                            | member_department_ids
                            | {department_id},
                        )
                    page_token = payload.get("page_token")
                    if not payload.get("has_more") or not page_token:
                        break
            return list(users.values())


# --- User-authorized web login ------------------------------------------------


def build_authorization_url(
    *,
    app_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: str = DEFAULT_LOGIN_SCOPES,
    authorization_url: str = DEFAULT_AUTHORIZATION_URL,
) -> str:
    """Authorization page the browser is redirected to; Feishu returns `code`."""
    query = httpx.QueryParams(
        {
            "client_id": app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{authorization_url}?{query}"


def _login_body(response: httpx.Response, operation: str) -> dict[str, Any]:
    if response.status_code >= 400:
        message, detail = _error_message(response)
        raise FeishuAPIError(f"{operation} failed: {message}", detail=detail)
    try:
        body = response.json()
    except ValueError as exc:
        raise FeishuAPIError(
            f"Feishu {operation} returned a non-JSON body",
            detail=response.text[:1024],
        ) from exc
    if not isinstance(body, dict):
        raise FeishuAPIError(
            f"Feishu {operation} returned an unexpected body", detail=str(body)[:1024]
        )
    code = body.get("code")
    if code not in (0, None):
        reason = (
            body.get("error_description") or body.get("msg") or body.get("error") or ""
        )
        raise FeishuAPIError(
            f"Feishu {operation} error {code}: {_short(reason)}",
            detail=str(body)[:1024],
        )
    return body


async def exchange_user_access_token(
    *,
    token_url: str,
    app_id: str,
    app_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> str:
    """Trade the authorization code for a `user_access_token`."""
    async with httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=False, trust_env=False
    ) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": app_id,
                "client_secret": app_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )

    body = _login_body(response, "token exchange")
    # `accounts.feishu.cn/oauth/v3/token` returns `access_token` at the top level;
    # the older `authen/v1/access_token` nests the token under `data`.
    candidates = [body.get("access_token")]
    nested = body.get("data")
    if isinstance(nested, dict):
        candidates += [nested.get("access_token"), nested.get("user_access_token")]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    raise FeishuAPIError(
        "Feishu did not return a user access token", detail=str(body)[:1024]
    )


async def fetch_user_info(
    *, userinfo_url: str, user_access_token: str
) -> dict[str, Any]:
    """User profile authorized by `user_access_token`."""
    async with httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=False, trust_env=False
    ) as client:
        response = await client.get(
            userinfo_url,
            headers={
                "Authorization": f"Bearer {user_access_token}",
                "Accept": "application/json",
            },
        )

    body = _login_body(response, "user info")
    data = body.get("data")
    return data if isinstance(data, dict) else body

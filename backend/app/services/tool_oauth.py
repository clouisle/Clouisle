"""OAuth 2.0 authorization-code + PKCE for tool connections.

Two provider shapes are supported:

* **MCP** — discovery via RFC 9728 protected-resource metadata and RFC 8414 /
  OpenID authorization-server metadata, with optional RFC 7591 dynamic client
  registration when the tool has no pre-registered ``client_id``.
* **HTTP** — an explicitly configured ``Tool.http_config["oauth2"]`` provider.

Security properties enforced here:

* PKCE S256 is mandatory; the verifier is stored encrypted with the shared
  integration credential helper.
* ``state`` is stored only as a SHA-256 digest, bound to the logged-in user and
  one connection, expires after ten minutes and is consumed atomically.
* Every discovery/token/userinfo URL is checked by the centralized SSRF guard;
  redirects are never followed and response bodies are size-bounded.
* Provider client secrets are tool-administrator managed. A personal user can
  start a flow for their own connection but cannot overwrite a shared provider
  credential.
* Refresh tokens are rotated under a database row lock. A refresh never bumps
  ``secret_version`` unless the external account subject changes; the first
  authorization bumps it exactly once.
* Refresh responses may not widen scopes beyond the previously granted set.
* Access/refresh tokens live only in ``ToolConnection.encrypted_config``
  reserved fields and never in logs or API responses.

The public token entry point requires a :class:`ResolvedConnection` produced by
:class:`ToolConnectionService`; there is deliberately no ``UUID -> token``
public method that could be called for another user's connection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets as py_secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import httpx
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core.config import settings
from app.core.network_security import ensure_external_http_url_allowed
from app.core.timezone import now_utc
from app.core.tool_secrets import (
    ToolSecretError,
    decrypt_tool_secret,
    encrypt_tool_secret,
)
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionStatus,
)
from app.models.tool_oauth import (
    ToolOAuthClientAuthMethod,
    ToolOAuthFlow,
    ToolOAuthProvider,
    ToolOAuthProviderKind,
)
from app.models.user import TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_oauth import (
    HttpOAuth2Config,
    McpOAuthConfig,
    OAuthConnectionStatusOut,
    OAuthDisconnectOut,
    OAuthStartOut,
    RESERVED_AUTHORIZATION_PARAMS,
    RESERVED_TOKEN_PARAMS,
    validate_redirect_path,
)
from app.services.tool_connections import (
    ResolvedConnection,
    ToolConnectionService,
)

logger = logging.getLogger(__name__)

CALLBACK_PATH = "/api/v1/tool-oauth/callback"
STATE_TTL = timedelta(minutes=10)
EXPIRY_SKEW_SECONDS = 60
DEFAULT_TOKEN_LIFETIME_SECONDS = 3600
MAX_HTTP_RESPONSE_BYTES = 256 * 1024
MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
MAX_ACCESS_TOKEN_LENGTH = 16 * 1024
MAX_REFRESH_TOKEN_LENGTH = 16 * 1024
MAX_CLIENT_SECRET_LENGTH = 8192
HTTP_TIMEOUT_SECONDS = 15.0
HTTP_CONNECT_TIMEOUT_SECONDS = 5.0
REVOCATION_TIMEOUT_SECONDS = 3.0
FLOW_RETENTION = timedelta(hours=24)
CLIENT_NAME = "Clouisle"

# Reserved ToolConnection.encrypted_config fields. Values are strings because
# the connection secret container only accepts non-empty strings.
CONNECTION_ACCESS_TOKEN = "oauth_access_token"
CONNECTION_REFRESH_TOKEN = "oauth_refresh_token"
CONNECTION_EXPIRES_AT = "oauth_expires_at"
CONNECTION_SCOPE = "oauth_scope"
CONNECTION_TOKEN_TYPE = "oauth_token_type"
CONNECTION_PROVIDER_ID = "oauth_provider_id"
CONNECTION_ACCOUNT_SUBJECT = "oauth_account_subject"
RESERVED_CONNECTION_KEYS = frozenset(
    {
        CONNECTION_ACCESS_TOKEN,
        CONNECTION_REFRESH_TOKEN,
        CONNECTION_EXPIRES_AT,
        CONNECTION_SCOPE,
        CONNECTION_TOKEN_TYPE,
        CONNECTION_PROVIDER_ID,
        CONNECTION_ACCOUNT_SUBJECT,
    }
)
DISCONNECT_CLEARED_KEYS = (
    CONNECTION_ACCESS_TOKEN,
    CONNECTION_REFRESH_TOKEN,
    CONNECTION_EXPIRES_AT,
    CONNECTION_SCOPE,
    CONNECTION_TOKEN_TYPE,
    CONNECTION_ACCOUNT_SUBJECT,
)

_SAFE_ERROR_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_REDIRECT_ERROR_KEYS = frozenset(
    {
        "tool_oauth_state_invalid",
        "tool_oauth_expired",
        "tool_oauth_provider_error",
        "tool_oauth_exchange_failed",
        "tool_oauth_reauth_required",
        "tool_oauth_config_invalid",
        "tool_oauth_discovery_failed",
        "tool_oauth_scope_escalation",
        "tool_oauth_version_conflict",
        "tool_oauth_callback_failed",
    }
)


class _OAuthEndpointError(Exception):
    """Sanitized failure from an OAuth HTTP endpoint."""

    def __init__(
        self,
        error: str,
        *,
        description: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.description = description
        self.status = status


@dataclass(frozen=True, slots=True)
class _OAuthTokens:
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    scope: tuple[str, ...]
    id_token: str | None


@dataclass(frozen=True, slots=True)
class _ProviderSetup:
    provider: ToolOAuthProvider
    scopes: tuple[str, ...]
    resource: str | None
    authorization_params: Mapping[str, str]
    token_params: Mapping[str, str]


def _utcnow() -> datetime:
    return now_utc()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fail(
    code: ResponseCode,
    msg_key: str,
    *,
    status_code: int = 400,
    **kwargs: Any,
) -> None:
    raise BusinessError(code=code, msg_key=msg_key, status_code=status_code, **kwargs)


def _callback_url() -> str:
    """Server-configured public callback URI (never derived from a request)."""
    base = (settings.PUBLIC_API_URL or settings.API_BASE_URL or "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        _fail(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            "tool_oauth_config_invalid",
            status_code=500,
        )
    if not parsed.hostname:
        _fail(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            "tool_oauth_config_invalid",
            status_code=500,
        )
    return f"{base}{CALLBACK_PATH}"


async def _frontend_url() -> str:
    from app.models.site_setting import SiteSetting

    try:
        site_url = await SiteSetting.get_value("site_url", "")
    except Exception:  # pragma: no cover - configuration read failure
        site_url = ""
    return (site_url or settings.FRONTEND_URL).rstrip("/")


async def _frontend_redirect(
    *,
    redirect_path: str | None,
    error_key: str | None = None,
    connection_id: UUID | None = None,
) -> str:
    base = await _frontend_url()
    try:
        path = validate_redirect_path(redirect_path) or "/app"
    except ValueError:
        path = "/app"
    query: dict[str, str] = {}
    if error_key:
        slug = (
            error_key
            if _SAFE_ERROR_SLUG_PATTERN.fullmatch(error_key)
            and error_key in _REDIRECT_ERROR_KEYS
            else "tool_oauth_callback_failed"
        )
        # The backend message catalog uses tool_oauth_* ids, while the browser
        # contract exposes stable oauth_* slugs; never expose internal names.
        if slug.startswith("tool_oauth_"):
            slug = slug[len("tool_") :]
        query["oauth"] = "error"
        query["error"] = slug
    else:
        query["oauth"] = "success"
    if connection_id is not None:
        query["connection_id"] = str(connection_id)
    separator = "&" if "?" in path else "?"
    return f"{base}{path}{separator}{urlencode(query)}"


def _hash_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _pkce_pair() -> tuple[str, str]:
    verifier = py_secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _merge_query(url: str, params: Mapping[str, str]) -> str:
    parsed = urlsplit(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(params)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(existing), "")
    )


def _normalize_scope_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates = value.split()
    elif isinstance(value, Sequence):
        candidates = [str(item) for item in value]
    else:
        return ()
    cleaned: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or len(normalized) > 200 or " " in normalized:
            continue
        cleaned.append(normalized)
    return tuple(dict.fromkeys(cleaned))


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _as_utc(parsed)


def _parse_expires_in(value: Any) -> int:
    if value is None:
        return DEFAULT_TOKEN_LIFETIME_SECONDS
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise _OAuthEndpointError("invalid_expires_in") from None
    if seconds <= 0:
        raise _OAuthEndpointError("invalid_expires_in")
    try:
        _utcnow() + timedelta(seconds=seconds)
    except (OverflowError, ValueError):
        raise _OAuthEndpointError("invalid_expires_in") from None
    return seconds


def _sanitize_token_type(value: Any) -> str:
    if value is None:
        return "Bearer"
    token_type = str(value).strip()
    if token_type.lower() != "bearer":
        # This adapter only knows how to present Bearer credentials. DPoP or
        # other schemes fail explicitly instead of being sent as Bearer.
        raise _OAuthEndpointError("unsupported_token_type")
    return "Bearer"


def _bearer_resource_metadata(header: str | None) -> str | None:
    """Return the ``resource_metadata`` URL from the first Bearer challenge.

    Only the RFC 9728 ``Bearer resource_metadata="..."`` parameter is accepted;
    unknown schemes/parameters are ignored rather than guessed.
    """
    if not header:
        return None
    match = re.search(r"(?i)\bbearer\b", header)
    if not match:
        return None
    parameter = re.search(
        r'(?i)\bresource_metadata\s*=\s*"([^"]{1,2000})"',
        header[match.end() :],
    )
    return parameter.group(1) if parameter else None


def _sanitize_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "registration_endpoint",
        "userinfo_endpoint",
        "scopes_supported",
        "code_challenge_methods_supported",
        "token_endpoint_auth_methods_supported",
        "grant_types_supported",
        "response_types_supported",
    )
    result: dict[str, Any] = {}
    for key in allowed:
        value = data.get(key)
        if isinstance(value, str) and len(value) <= 2000:
            result[key] = value
        elif isinstance(value, list):
            result[key] = [
                str(item)[:200] for item in value[:50] if isinstance(item, str)
            ]
    return result


def _require_https_endpoint(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 2000:
        raise _OAuthEndpointError("invalid_endpoint")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise _OAuthEndpointError("invalid_endpoint")
    return value


def _decode_id_token_claims(id_token: str | None) -> dict[str, Any]:
    """Decode claims for display/identity comparison only.

    Signatures are deliberately not verified here: the token arrived directly
    from the token endpoint over TLS, and this data is never used to authorize
    a Clouisle action. It is used to detect external-account changes and to
    show a human-readable account label.
    """
    if not id_token or len(id_token) > 32768:
        return {}
    parts = id_token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _identity_from_claims(claims: Mapping[str, Any]) -> tuple[str | None, str | None]:
    subject = claims.get("sub")
    subject = subject if isinstance(subject, str) and subject else None
    for key in ("email", "preferred_username", "name"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return subject, value[:150]
    return subject, None


class ToolOAuthService:
    """Authorization-code flow, token storage and locked refresh rotation."""

    # ------------------------------------------------------------------
    # Public start / status / callback
    # ------------------------------------------------------------------

    @classmethod
    async def start_authorization(
        cls,
        *,
        actor: User,
        connection_id: UUID,
        redirect_path: str | None = None,
        client_secret: str | None = None,
    ) -> OAuthStartOut:
        """Create a one-time flow and return the authorization URL.

        The caller must manage the connection. Tool write access is additionally
        required to change a provider client secret; a personal user can never
        overwrite the shared provider credential.
        """
        from app.api.v1.endpoints.tools import (
            check_tool_access,
            check_tool_write_access,
        )

        await ToolConnectionService.assert_manage_access(
            actor=actor, connection_id=connection_id
        )
        connection = await ToolConnection.filter(id=connection_id).first()
        if connection is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                "tool_connection_not_found",
                status_code=404,
            )
        if connection.status == ToolConnectionStatus.REVOKED:
            _fail(
                ResponseCode.TOOL_CONNECTION_INACTIVE,
                "tool_connection_inactive",
                status_code=409,
            )
        if connection.tool_id is None:
            _fail(
                ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
                "tool_oauth_not_supported",
                status_code=400,
            )
        try:
            redirect_path = validate_redirect_path(redirect_path)
        except ValueError:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )
        tool = await Tool.filter(id=connection.tool_id).first()
        if tool is None:
            _fail(
                ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
                "tool_oauth_not_supported",
                status_code=400,
            )
        await check_tool_access(tool, actor)

        try:
            config = ToolConnectionService._decrypt_config(connection)
        except BusinessError:
            config = {}
        if (
            not config.get(CONNECTION_ACCESS_TOKEN)
            and connection.status == ToolConnectionStatus.ACTIVE
        ):
            # A connection with no token is not usable yet; make that explicit
            # while the flow is pending instead of leaving it "active".
            connection.status = ToolConnectionStatus.REAUTH_REQUIRED
            await connection.save(update_fields=["status", "updated_at"])

        if client_secret is not None:
            if not client_secret or len(client_secret) > MAX_CLIENT_SECRET_LENGTH:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_config_invalid",
                    status_code=400,
                )
            await check_tool_write_access(tool, actor)

        kind = cls._provider_kind(tool)
        redirect_uri = _callback_url()
        setup = await cls._ensure_provider(
            tool=tool,
            kind=kind,
            redirect_uri=redirect_uri,
            client_secret=client_secret,
        )

        state = py_secrets.token_urlsafe(48)
        verifier, challenge = _pkce_pair()
        expires_at = _utcnow() + STATE_TTL

        flow = ToolOAuthFlow(
            state_hash=_hash_state(state),
            user_id=actor.id,
            team_id=connection.team_id,
            tool_id=tool.id,
            connection_id=connection.id,
            provider_id=setup.provider.id,
            provider_kind=kind,
            redirect_uri=redirect_uri,
            redirect_path=redirect_path,
            scopes=list(setup.scopes),
            resource=setup.resource,
            code_verifier_encrypted=encrypt_tool_secret(verifier),
            expected_secret_version=connection.secret_version,
            expires_at=expires_at,
        )
        await flow.save()

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": setup.provider.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if setup.scopes:
            params["scope"] = " ".join(setup.scopes)
        if kind == ToolOAuthProviderKind.MCP and setup.resource:
            params["resource"] = setup.resource
        params.update(
            {
                key: value
                for key, value in setup.authorization_params.items()
                if key not in RESERVED_AUTHORIZATION_PARAMS
            }
        )
        authorization_url = _merge_query(setup.provider.authorization_endpoint, params)
        return OAuthStartOut(
            authorization_url=authorization_url,
            state=state,
            expires_at=expires_at,
            provider_kind=kind,
            connection_id=connection.id,
        )

    @classmethod
    async def handle_callback(
        cls,
        *,
        state: str | None,
        code: str | None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> str:
        """Consume a flow, exchange the code, store tokens, return a redirect URL.

        Every failure is turned into a frontend redirect; the browser callback
        never exposes raw provider errors or tokens.
        """
        flow: ToolOAuthFlow | None = None
        try:
            flow = await cls._consume_flow(state)
        except BusinessError as exc:
            return await _frontend_redirect(redirect_path=None, error_key=exc.msg_key)

        try:
            if error:
                logger.warning("OAuth provider returned error code %s", error[:100])
                return await _frontend_redirect(
                    redirect_path=flow.redirect_path,
                    error_key="tool_oauth_provider_error",
                    connection_id=flow.connection_id,
                )
            await cls._validate_flow_actor(flow)
            if not code or len(code) > 4096:
                _fail(
                    ResponseCode.TOOL_OAUTH_EXCHANGE_FAILED,
                    "tool_oauth_exchange_failed",
                    status_code=400,
                )

            provider = await ToolOAuthProvider.filter(id=flow.provider_id).first()
            connection = await ToolConnection.filter(id=flow.connection_id).first()
            if (
                provider is None
                or connection is None
                or connection.status == ToolConnectionStatus.REVOKED
                or connection.tool_id != flow.tool_id
            ):
                _fail(
                    ResponseCode.TOOL_CONNECTION_INACTIVE,
                    "tool_connection_inactive",
                    status_code=409,
                )
            if connection.secret_version != flow.expected_secret_version:
                # Do not spend a one-time authorization code against a
                # connection that changed after the user started the flow.
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_oauth_version_conflict",
                    status_code=409,
                )

            try:
                verifier = decrypt_tool_secret(flow.code_verifier_encrypted)
            except ToolSecretError:
                _fail(
                    ResponseCode.TOOL_OAUTH_STATE_INVALID,
                    "tool_oauth_state_invalid",
                    status_code=409,
                )

            token_data: dict[str, str] = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": flow.redirect_uri,
                "client_id": provider.client_id,
                "code_verifier": verifier,
            }
            if provider.provider_kind == ToolOAuthProviderKind.MCP and flow.resource:
                token_data["resource"] = flow.resource
            token_data.update(
                {
                    key: value
                    for key, value in (provider.token_params or {}).items()
                    if key not in RESERVED_TOKEN_PARAMS
                }
            )
            tokens = await cls._request_token(provider, token_data)
            await cls._store_tokens(
                connection_id=connection.id,
                provider=provider,
                tokens=tokens,
                expected_secret_version=flow.expected_secret_version,
                allowed_scopes=set(flow.scopes),
                bump_version=True,
                allow_userinfo=True,
            )
            return await _frontend_redirect(
                redirect_path=flow.redirect_path,
                connection_id=connection.id,
            )
        except BusinessError as exc:
            logger.warning(
                "OAuth callback failed for flow %s: %s",
                flow.id if flow else None,
                exc.msg_key,
            )
            if flow is not None:
                await cls._drop_tokens_for_failed_reauth(flow.connection_id)
            return await _frontend_redirect(
                redirect_path=flow.redirect_path if flow else None,
                error_key=exc.msg_key if flow else "tool_oauth_callback_failed",
                connection_id=flow.connection_id if flow else None,
            )
        except _OAuthEndpointError as exc:
            logger.warning(
                "OAuth token exchange failed for flow %s: %s",
                flow.id if flow else None,
                exc.error,
            )
            if flow is not None:
                await cls._drop_tokens_for_failed_reauth(flow.connection_id)
            return await _frontend_redirect(
                redirect_path=flow.redirect_path if flow else None,
                error_key=(
                    "tool_oauth_config_invalid"
                    if exc.error == "unsupported_token_type"
                    else "tool_oauth_exchange_failed"
                ),
                connection_id=flow.connection_id if flow else None,
            )
        except Exception:
            logger.exception(
                "OAuth callback failed for flow %s",
                flow.id if flow else None,
            )
            return await _frontend_redirect(
                redirect_path=flow.redirect_path if flow else None,
                error_key="tool_oauth_callback_failed",
                connection_id=flow.connection_id if flow else None,
            )

    @classmethod
    async def get_status(
        cls,
        *,
        actor: User,
        connection_id: UUID,
        team_id: UUID | None = None,
    ) -> OAuthConnectionStatusOut:
        """Secret-free OAuth status for a connection the caller may read."""
        await ToolConnectionService.get_connection(
            actor=actor, connection_id=connection_id, team_id=team_id
        )
        connection = await ToolConnection.filter(id=connection_id).first()
        if connection is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                "tool_connection_not_found",
                status_code=404,
            )
        try:
            config = ToolConnectionService._decrypt_config(connection)
        except BusinessError:
            config = {}

        provider: ToolOAuthProvider | None = None
        provider_id = config.get(CONNECTION_PROVIDER_ID)
        if provider_id:
            try:
                provider = await ToolOAuthProvider.filter(id=UUID(provider_id)).first()
            except ValueError:
                provider = None
        if provider is None and connection.tool_id is not None:
            provider = (
                await ToolOAuthProvider.filter(tool_id=connection.tool_id)
                .order_by("-updated_at")
                .first()
            )

        tool = (
            await Tool.filter(id=connection.tool_id).first()
            if connection.tool_id
            else None
        )
        kind = cls._provider_kind(tool) if tool is not None else None

        access_token = config.get(CONNECTION_ACCESS_TOKEN)
        refresh_token = config.get(CONNECTION_REFRESH_TOKEN)
        expires_at = _parse_expiry(config.get(CONNECTION_EXPIRES_AT))
        scope_values = config.get(CONNECTION_SCOPE, "").split()
        scopes = scope_values or list(provider.scopes if provider else [])
        expired = expires_at is not None and expires_at <= _utcnow()
        needs_reauth = bool(
            connection.status == ToolConnectionStatus.REAUTH_REQUIRED
            or not access_token
            or (expired and not refresh_token)
        )
        return OAuthConnectionStatusOut(
            connection_id=connection.id,
            provider_kind=kind,
            provider_configured=provider is not None,
            authorized=bool(access_token),
            needs_reauth=needs_reauth,
            status=(
                connection.status.value
                if isinstance(connection.status, ToolConnectionStatus)
                else str(connection.status)
            ),
            account_label=connection.account_label,
            scopes=scopes,
            expires_at=expires_at,
            client_id=provider.client_id if provider else None,
        )

    # ------------------------------------------------------------------
    # Disconnect / cleanup
    # ------------------------------------------------------------------

    @classmethod
    async def disconnect(
        cls,
        *,
        actor: User,
        connection_id: UUID,
    ) -> OAuthDisconnectOut:
        """Best-effort remote revocation, then always clear local tokens.

        A missing provider revocation endpoint never blocks the local revoke and
        is reported as ``unsupported``; a failed remote call is reported as
        ``failed``. Neither claims the remote token was revoked.
        """
        await ToolConnectionService.assert_manage_access(
            actor=actor, connection_id=connection_id
        )
        connection = await ToolConnection.filter(id=connection_id).first()
        if connection is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                "tool_connection_not_found",
                status_code=404,
            )
        try:
            config = ToolConnectionService._decrypt_config(connection)
        except BusinessError:
            config = {}

        provider = await cls._provider_for_connection(connection, config)
        refresh_token = config.get(CONNECTION_REFRESH_TOKEN)
        access_token = config.get(CONNECTION_ACCESS_TOKEN)
        remote_revocation = "unsupported"
        token = refresh_token or access_token
        if provider is not None and token:
            remote_revocation = await cls._revoke_remote_token(
                provider,
                token,
                "refresh_token" if refresh_token else "access_token",
            )

        async with in_transaction() as db:
            locked = (
                await ToolConnection.filter(id=connection_id)
                .using_db(db)
                .select_for_update()
                .first()
            )
            if locked is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                    "tool_connection_not_found",
                    status_code=404,
                )
            try:
                current = ToolConnectionService._decrypt_config(locked)
            except BusinessError:
                current = {}
            changed = any(key in current for key in DISCONNECT_CLEARED_KEYS)
            for key in DISCONNECT_CLEARED_KEYS:
                current.pop(key, None)
            encrypted, fields = ToolConnectionService._encrypt_config(current)
            locked.encrypted_config = encrypted
            locked.secret_fields = fields
            if locked.status != ToolConnectionStatus.REVOKED:
                locked.status = ToolConnectionStatus.REAUTH_REQUIRED
            if changed:
                locked.secret_version += 1
            await locked.save(
                using_db=db,
                update_fields=[
                    "encrypted_config",
                    "secret_fields",
                    "status",
                    "secret_version",
                    "updated_at",
                ],
            )
            needs_reauth = locked.status != ToolConnectionStatus.REVOKED

        return OAuthDisconnectOut(
            connection_id=connection_id,
            local_revoked=True,
            remote_revocation=remote_revocation,
            needs_reauth=needs_reauth,
        )

    @classmethod
    async def _revoke_remote_token(
        cls,
        provider: ToolOAuthProvider,
        token: str,
        token_type_hint: str,
    ) -> str:
        endpoint = provider.revocation_endpoint
        if not endpoint:
            return "unsupported"
        try:
            await ensure_external_http_url_allowed(endpoint)
            auth_headers, auth_fields = cls._client_auth(provider)
            data = {
                "token": token,
                "token_type_hint": token_type_hint,
                **auth_fields,
            }
            timeout = httpx.Timeout(
                REVOCATION_TIMEOUT_SECONDS,
                connect=min(2.0, REVOCATION_TIMEOUT_SECONDS),
            )
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False
            ) as client:
                response = await client.post(
                    endpoint,
                    data=data,
                    headers={"Accept": "application/json", **auth_headers},
                )
            return "revoked" if 200 <= response.status_code < 300 else "failed"
        except Exception:
            logger.warning(
                "OAuth provider revocation failed (%s)",
                urlsplit(endpoint).hostname,
            )
            return "failed"

    @classmethod
    async def cleanup_expired_flows(cls, *, limit: int = 500) -> int:
        """Delete expired/consumed flows older than the retention window."""
        cutoff = _utcnow() - FLOW_RETENTION
        flow_ids = await (
            ToolOAuthFlow.filter(Q(expires_at__lt=cutoff) | Q(consumed_at__lt=cutoff))
            .limit(limit)
            .values_list("id", flat=True)
        )
        if not flow_ids:
            return 0
        deleted = await ToolOAuthFlow.filter(id__in=list(flow_ids)).delete()
        return int(deleted or 0)

    # ------------------------------------------------------------------
    # Execution-facing token access
    # ------------------------------------------------------------------

    @classmethod
    async def get_access_token(
        cls,
        resolved: ResolvedConnection,
        *,
        force: bool = False,
        expiry_skew_seconds: int = EXPIRY_SKEW_SECONDS,
    ) -> str:
        """Return a usable access token for an already-resolved connection.

        Call only with a :class:`ResolvedConnection` returned by
        :meth:`ToolConnectionService.resolve_connection`; the expected
        ``secret_version`` is re-checked under the refresh lock. There is no
        public UUID-only variant.
        """
        return await cls._access_token_for_resolved(
            resolved,
            force=force,
            expiry_skew_seconds=expiry_skew_seconds,
        )

    @classmethod
    async def get_authorization_header(
        cls,
        resolved: ResolvedConnection,
        *,
        force: bool = False,
    ) -> str:
        """Build an ``Authorization`` header value for an already-resolved connection."""
        token = await cls.get_access_token(resolved, force=force)
        return f"Bearer {token}"

    # ------------------------------------------------------------------
    # Provider discovery / configuration
    # ------------------------------------------------------------------

    @staticmethod
    def _provider_kind(tool: Tool) -> ToolOAuthProviderKind:
        if tool.type == ToolType.MCP:
            return ToolOAuthProviderKind.MCP
        if tool.type == ToolType.CUSTOM and tool.custom_type == CustomToolType.HTTP:
            return ToolOAuthProviderKind.HTTP
        _fail(
            ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
            "tool_oauth_not_supported",
            status_code=400,
        )
        raise AssertionError("unreachable")

    @classmethod
    async def _ensure_provider(
        cls,
        *,
        tool: Tool,
        kind: ToolOAuthProviderKind,
        redirect_uri: str,
        client_secret: str | None,
    ) -> _ProviderSetup:
        try:
            if kind == ToolOAuthProviderKind.MCP:
                return await cls._ensure_mcp_provider(
                    tool=tool,
                    redirect_uri=redirect_uri,
                    client_secret=client_secret,
                )
            return await cls._ensure_http_provider(
                tool=tool,
                redirect_uri=redirect_uri,
                client_secret=client_secret,
            )
        except _OAuthEndpointError as exc:
            logger.warning(
                "OAuth provider setup failed for tool %s: %s",
                tool.id,
                exc.error,
            )
            _fail(
                ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                "tool_oauth_discovery_failed",
                status_code=400,
            )
            raise AssertionError("unreachable")

    @classmethod
    async def _ensure_http_provider(
        cls,
        *,
        tool: Tool,
        redirect_uri: str,
        client_secret: str | None,
    ) -> _ProviderSetup:
        raw = (tool.http_config or {}).get("oauth2")
        if not isinstance(raw, Mapping):
            _fail(
                ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
                "tool_oauth_not_supported",
                status_code=400,
            )
        try:
            config = HttpOAuth2Config.model_validate(dict(raw))
        except Exception:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )

        authorization_endpoint = _require_https_endpoint(config.authorization_endpoint)
        token_endpoint = _require_https_endpoint(config.token_endpoint)
        await ensure_external_http_url_allowed(authorization_endpoint)
        await ensure_external_http_url_allowed(token_endpoint)

        parsed = urlsplit(config.authorization_endpoint)
        authorization_server = (
            config.issuer or f"{parsed.scheme}://{parsed.netloc}"
        ).rstrip("/")
        cls._validate_authorization_server(authorization_server)

        method = config.token_endpoint_auth_method
        existing = await ToolOAuthProvider.filter(
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            authorization_server=authorization_server,
        ).first()
        client_id_changed = bool(existing and existing.client_id != config.client_id)

        if client_secret is not None and method == ToolOAuthClientAuthMethod.NONE:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )
        has_secret = bool(
            client_secret
            or (existing and existing.client_secret_encrypted and not client_id_changed)
        )
        if method != ToolOAuthClientAuthMethod.NONE and not has_secret:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_client_secret_required",
                status_code=409,
            )

        provider = existing or ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            authorization_server=authorization_server,
        )
        provider.issuer = authorization_server
        provider.resource = None
        provider.authorization_endpoint = authorization_endpoint
        provider.token_endpoint = token_endpoint
        provider.registration_endpoint = None
        provider.userinfo_endpoint = None
        revocation_endpoint = config.revocation_endpoint
        if revocation_endpoint is not None:
            revocation_endpoint = _require_https_endpoint(revocation_endpoint)
            await ensure_external_http_url_allowed(revocation_endpoint)
        provider.revocation_endpoint = revocation_endpoint
        provider.client_id = config.client_id
        provider.token_endpoint_auth_method = method
        provider.scopes = list(config.scopes)
        provider.code_challenge_methods = ["S256"]
        provider.authorization_params = dict(config.extra_authorization_params)
        provider.token_params = dict(config.extra_token_params)
        provider.metadata = {
            "source": "configured",
            "issuer": authorization_server,
            "authorization_endpoint": authorization_endpoint,
            "token_endpoint": token_endpoint,
        }
        if client_secret:
            provider.client_secret_encrypted = encrypt_tool_secret(client_secret)
        elif method == ToolOAuthClientAuthMethod.NONE or client_id_changed:
            provider.client_secret_encrypted = ""
        provider = await cls._save_provider(provider)
        return _ProviderSetup(
            provider=provider,
            scopes=tuple(config.scopes),
            resource=None,
            authorization_params=dict(config.extra_authorization_params),
            token_params=dict(config.extra_token_params),
        )

    @classmethod
    async def _ensure_mcp_provider(
        cls,
        *,
        tool: Tool,
        redirect_uri: str,
        client_secret: str | None,
    ) -> _ProviderSetup:
        mcp_config = tool.mcp_config or {}
        transport = str(mcp_config.get("transport", "stdio"))
        mcp_url = mcp_config.get("url")
        if transport not in {"sse", "http"} or not isinstance(mcp_url, str):
            _fail(
                ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
                "tool_oauth_not_supported",
                status_code=400,
            )
        mcp_url = _require_https_endpoint(mcp_url)
        await ensure_external_http_url_allowed(mcp_url)

        try:
            config = McpOAuthConfig.model_validate(dict(mcp_config.get("oauth") or {}))
        except Exception:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )

        resource = config.resource or mcp_url
        issuer = config.authorization_server
        prm_scopes: list[str] = []
        if issuer is None:
            prm = await cls._protected_resource_metadata(mcp_url)
            servers = prm.get("authorization_servers")
            if not isinstance(servers, list) or not servers:
                _fail(
                    ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                    "tool_oauth_discovery_failed",
                    status_code=400,
                )
            issuer = servers[0] if isinstance(servers[0], str) else None
            if not issuer:
                _fail(
                    ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                    "tool_oauth_discovery_failed",
                    status_code=400,
                )
            raw_resource = prm.get("resource")
            if isinstance(raw_resource, str) and raw_resource:
                resource = raw_resource
            raw_scopes = prm.get("scopes_supported")
            if isinstance(raw_scopes, list):
                prm_scopes = [
                    scope
                    for scope in raw_scopes
                    if isinstance(scope, str) and 0 < len(scope) <= 200
                ][:50]

        issuer = _require_https_endpoint(issuer).rstrip("/")
        cls._validate_authorization_server(issuer)
        await ensure_external_http_url_allowed(issuer)

        metadata = await cls._authorization_server_metadata(issuer)
        authorization_endpoint = _require_https_endpoint(
            metadata.get("authorization_endpoint")
        )
        token_endpoint = _require_https_endpoint(metadata.get("token_endpoint"))
        registration_endpoint = metadata.get("registration_endpoint")
        if registration_endpoint is not None:
            registration_endpoint = _require_https_endpoint(registration_endpoint)
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if userinfo_endpoint is not None:
            userinfo_endpoint = _require_https_endpoint(userinfo_endpoint)
        revocation_endpoint = metadata.get("revocation_endpoint")
        if revocation_endpoint is not None:
            revocation_endpoint = _require_https_endpoint(revocation_endpoint)
        await ensure_external_http_url_allowed(authorization_endpoint)
        await ensure_external_http_url_allowed(token_endpoint)

        challenge_methods = metadata.get("code_challenge_methods_supported")
        if challenge_methods is not None and not isinstance(challenge_methods, list):
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )
        if isinstance(challenge_methods, list) and challenge_methods:
            if "S256" not in challenge_methods:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_pkce_unsupported",
                    status_code=400,
                )
        else:
            challenge_methods = ["S256"]

        scopes = tuple(config.scopes) or tuple(prm_scopes)
        existing = await ToolOAuthProvider.filter(
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.MCP,
            authorization_server=issuer,
        ).first()

        client_id = config.client_id or (existing.client_id if existing else None)
        method = config.token_endpoint_auth_method
        encrypted_secret = existing.client_secret_encrypted if existing else ""
        client_id_changed = bool(
            existing
            and config.client_id is not None
            and existing.client_id != config.client_id
        )
        if client_id is None:
            if not config.use_dcr or not registration_endpoint:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_client_registration_required",
                    status_code=409,
                )
            client_id, registered_secret = await cls._register_client(
                registration_endpoint=registration_endpoint,
                redirect_uri=redirect_uri,
                scopes=scopes,
            )
            method = (
                ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC
                if registered_secret
                else ToolOAuthClientAuthMethod.NONE
            )
            encrypted_secret = (
                encrypt_tool_secret(registered_secret) if registered_secret else ""
            )
        else:
            if client_secret is not None and method == ToolOAuthClientAuthMethod.NONE:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_config_invalid",
                    status_code=400,
                )
            if client_secret:
                encrypted_secret = encrypt_tool_secret(client_secret)
            elif client_id_changed or method == ToolOAuthClientAuthMethod.NONE:
                encrypted_secret = ""
            if method != ToolOAuthClientAuthMethod.NONE and not encrypted_secret:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_client_secret_required",
                    status_code=409,
                )

        provider = existing or ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.MCP,
            authorization_server=issuer,
        )
        provider.issuer = issuer
        provider.resource = resource
        provider.authorization_endpoint = authorization_endpoint
        provider.token_endpoint = token_endpoint
        provider.registration_endpoint = registration_endpoint
        provider.userinfo_endpoint = userinfo_endpoint
        provider.revocation_endpoint = revocation_endpoint
        provider.client_id = client_id
        provider.client_secret_encrypted = encrypted_secret
        provider.token_endpoint_auth_method = method
        provider.scopes = list(scopes)
        provider.code_challenge_methods = [str(item) for item in challenge_methods]
        provider.authorization_params = dict(config.extra_authorization_params)
        provider.token_params = dict(config.extra_token_params)
        provider.metadata = _sanitize_metadata(metadata)
        provider = await cls._save_provider(provider)
        return _ProviderSetup(
            provider=provider,
            scopes=scopes,
            resource=resource,
            authorization_params=dict(config.extra_authorization_params),
            token_params=dict(config.extra_token_params),
        )

    @staticmethod
    def _validate_authorization_server(value: str) -> None:
        if not value or len(value) > 500:
            _fail(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                "tool_oauth_config_invalid",
                status_code=400,
            )

    @classmethod
    async def _save_provider(cls, provider: ToolOAuthProvider) -> ToolOAuthProvider:
        try:
            await provider.save()
            return provider
        except IntegrityError:
            existing = await ToolOAuthProvider.filter(
                tool_id=provider.tool_id,
                provider_kind=provider.provider_kind,
                authorization_server=provider.authorization_server,
            ).first()
            if existing is None:
                raise
            return existing

    @classmethod
    async def _protected_resource_metadata(cls, mcp_url: str) -> dict[str, Any]:
        # RFC 9728: a 401 Bearer challenge names the authoritative metadata URL.
        header_url = await cls._probe_resource_metadata_url(mcp_url)
        if header_url:
            data = await cls._try_json(header_url)
            if data is not None:
                return data
            logger.warning(
                "resource_metadata URL from WWW-Authenticate was unusable; "
                "falling back to well-known discovery"
            )

        parsed = urlsplit(mcp_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/")
        candidates: list[str] = []
        if path:
            candidates.append(f"{origin}/.well-known/oauth-protected-resource{path}")
        candidates.append(f"{origin}/.well-known/oauth-protected-resource")
        for url in candidates:
            data = await cls._try_json(url)
            if data is not None:
                return data
        _fail(
            ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
            "tool_oauth_discovery_failed",
            status_code=400,
        )
        raise AssertionError("unreachable")

    @classmethod
    async def _probe_resource_metadata_url(cls, mcp_url: str) -> str | None:
        """Probe the MCP endpoint for a 401 Bearer challenge.

        A GET is attempted first; Streamable HTTP servers commonly require POST,
        so a minimal unauthenticated ``initialize`` follows. No parameter other
        than ``resource_metadata`` is interpreted, and the returned URL must be
        HTTPS and pass the centralized SSRF check when fetched.
        """
        await ensure_external_http_url_allowed(mcp_url)
        timeout = httpx.Timeout(
            HTTP_CONNECT_TIMEOUT_SECONDS,
            connect=HTTP_CONNECT_TIMEOUT_SECONDS,
        )
        initialize = {
            "jsonrpc": "2.0",
            "id": "oauth-discovery-probe",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": "1"},
            },
        }
        attempts = (
            ("GET", {"headers": {"Accept": "application/json"}}),
            (
                "POST",
                {
                    "headers": {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    "json": initialize,
                },
            ),
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for method, kwargs in attempts:
                try:
                    async with client.stream(method, mcp_url, **kwargs) as response:
                        # Drain a bounded prefix so the connection can close.
                        async for _chunk in response.aiter_bytes(2048):
                            break
                        if response.status_code != 401:
                            continue
                        header_url = _bearer_resource_metadata(
                            response.headers.get("www-authenticate")
                        )
                        if not header_url:
                            continue
                        try:
                            return _require_https_endpoint(header_url)
                        except _OAuthEndpointError:
                            logger.warning(
                                "Ignoring non-HTTPS resource_metadata URL from "
                                "WWW-Authenticate"
                            )
                            continue
                except httpx.HTTPError as exc:
                    logger.warning(
                        "MCP OAuth discovery probe failed (%s): %s",
                        method,
                        type(exc).__name__,
                    )
                    continue
        return None

    @classmethod
    async def _authorization_server_metadata(cls, issuer: str) -> dict[str, Any]:
        parsed = urlsplit(issuer)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.rstrip("/")
        candidates: list[str] = []
        if path:
            candidates.append(f"{origin}/.well-known/oauth-authorization-server{path}")
            candidates.append(f"{issuer}/.well-known/openid-configuration")
        else:
            candidates.append(f"{issuer}/.well-known/oauth-authorization-server")
            candidates.append(f"{issuer}/.well-known/openid-configuration")
        for url in candidates:
            data = await cls._try_json(url)
            if data is None:
                continue
            metadata_issuer = data.get("issuer")
            if not isinstance(metadata_issuer, str) or metadata_issuer.rstrip(
                "/"
            ) != issuer.rstrip("/"):
                logger.warning(
                    "Ignoring authorization-server metadata without an exact issuer match"
                )
                continue
            return data
        _fail(
            ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
            "tool_oauth_discovery_failed",
            status_code=400,
        )
        raise AssertionError("unreachable")

    @classmethod
    async def _try_json(cls, url: str) -> dict[str, Any] | None:
        try:
            return await cls._http_json(url, method="GET")
        except _OAuthEndpointError as exc:
            if exc.status in {400, 401, 403, 404, 410}:
                return None
            raise

    @classmethod
    async def _register_client(
        cls,
        *,
        registration_endpoint: str,
        redirect_uri: str,
        scopes: Sequence[str],
    ) -> tuple[str, str | None]:
        await ensure_external_http_url_allowed(registration_endpoint)
        payload: dict[str, Any] = {
            "client_name": CLIENT_NAME,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        if scopes:
            payload["scope"] = " ".join(scopes)
        try:
            data = await cls._http_json(
                registration_endpoint,
                method="POST",
                json_body=payload,
                headers={"Accept": "application/json"},
            )
        except _OAuthEndpointError:
            _fail(
                ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                "tool_oauth_client_registration_failed",
                status_code=400,
            )
        client_id = data.get("client_id")
        if not isinstance(client_id, str) or not client_id or len(client_id) > 500:
            _fail(
                ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                "tool_oauth_client_registration_failed",
                status_code=400,
            )
        client_secret = data.get("client_secret")
        if client_secret is not None:
            if (
                not isinstance(client_secret, str)
                or not client_secret
                or len(client_secret) > MAX_CLIENT_SECRET_LENGTH
            ):
                _fail(
                    ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
                    "tool_oauth_client_registration_failed",
                    status_code=400,
                )
        return client_id, client_secret

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    @classmethod
    async def _http_json(
        cls,
        url: str,
        *,
        method: str,
        data: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        max_bytes: int = MAX_HTTP_RESPONSE_BYTES,
    ) -> dict[str, Any]:
        await ensure_external_http_url_allowed(url)
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        timeout = httpx.Timeout(
            HTTP_TIMEOUT_SECONDS,
            connect=HTTP_CONNECT_TIMEOUT_SECONDS,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    method,
                    url,
                    data=dict(data) if data is not None else None,
                    json=dict(json_body) if json_body is not None else None,
                    headers=request_headers,
                ) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise _OAuthEndpointError("response_too_large")
                    text = body.decode("utf-8", "replace")
                    content_type = response.headers.get("content-type", "").lower()
                    payload: Any = None
                    if "json" in content_type or text:
                        try:
                            payload = json.loads(text) if text else None
                        except (ValueError, TypeError):
                            payload = None
                    if response.status_code >= 400:
                        error = "http_error"
                        description = None
                        if isinstance(payload, Mapping):
                            raw_error = payload.get("error")
                            raw_description = payload.get("error_description")
                            if isinstance(raw_error, str) and raw_error:
                                error = raw_error[:100]
                            if isinstance(raw_description, str):
                                description = raw_description[:300]
                        raise _OAuthEndpointError(
                            error,
                            description=description,
                            status=response.status_code,
                        )
                    if not isinstance(payload, Mapping):
                        raise _OAuthEndpointError(
                            "invalid_json",
                            status=response.status_code,
                        )
                    return dict(payload)
        except httpx.HTTPError as exc:
            logger.warning(
                "OAuth endpoint request failed (%s): %s",
                urlsplit(url).hostname,
                type(exc).__name__,
            )
            raise _OAuthEndpointError("network_error") from None

    # ------------------------------------------------------------------
    # Token exchange / rotation
    # ------------------------------------------------------------------

    @classmethod
    def _client_auth(
        cls, provider: ToolOAuthProvider
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return (headers, form fields) for client authentication."""
        headers: dict[str, str] = {}
        fields: dict[str, str] = {}
        method = provider.token_endpoint_auth_method
        secret = ""
        if provider.client_secret_encrypted:
            try:
                secret = decrypt_tool_secret(provider.client_secret_encrypted)
            except ToolSecretError:
                _fail(
                    ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE,
                    "tool_connection_secret_unreadable",
                    status_code=409,
                )
        if method == ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC:
            if not secret:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_client_secret_required",
                    status_code=409,
                )
            encoded = base64.b64encode(
                f"{quote(provider.client_id, safe='')}:{quote(secret, safe='')}".encode()
            ).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        elif method == ToolOAuthClientAuthMethod.CLIENT_SECRET_POST:
            if not secret:
                _fail(
                    ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    "tool_oauth_client_secret_required",
                    status_code=409,
                )
            fields["client_secret"] = secret
        return headers, fields

    @classmethod
    async def _request_token(
        cls,
        provider: ToolOAuthProvider,
        data: Mapping[str, str],
    ) -> _OAuthTokens:
        payload = {key: str(value) for key, value in data.items()}
        auth_headers, auth_fields = cls._client_auth(provider)
        payload.update(auth_fields)
        headers = {"Accept": "application/json", **auth_headers}
        response = await cls._http_json(
            provider.token_endpoint,
            method="POST",
            data=payload,
            headers=headers,
            max_bytes=MAX_TOKEN_RESPONSE_BYTES,
        )
        return cls._parse_token_response(response)

    @classmethod
    def _parse_token_response(cls, payload: Mapping[str, Any]) -> _OAuthTokens:
        if payload.get("error"):
            error = str(payload.get("error"))[:100]
            description = payload.get("error_description")
            raise _OAuthEndpointError(
                error,
                description=description[:300] if isinstance(description, str) else None,
            )
        access_token = payload.get("access_token")
        if (
            not isinstance(access_token, str)
            or not access_token
            or len(access_token) > MAX_ACCESS_TOKEN_LENGTH
        ):
            raise _OAuthEndpointError("invalid_access_token")
        refresh_token = payload.get("refresh_token")
        if refresh_token is not None:
            if (
                not isinstance(refresh_token, str)
                or not refresh_token
                or len(refresh_token) > MAX_REFRESH_TOKEN_LENGTH
            ):
                raise _OAuthEndpointError("invalid_refresh_token")
        id_token = payload.get("id_token")
        if id_token is not None and (
            not isinstance(id_token, str) or len(id_token) > 32768
        ):
            id_token = None
        try:
            expires_in = _parse_expires_in(payload.get("expires_in"))
        except _OAuthEndpointError:
            raise
        return _OAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=_sanitize_token_type(payload.get("token_type")),
            expires_in=expires_in,
            scope=_normalize_scope_values(payload.get("scope")),
            id_token=id_token,
        )

    @classmethod
    async def _access_token_for_resolved(
        cls,
        resolved: ResolvedConnection,
        *,
        force: bool,
        expiry_skew_seconds: int,
    ) -> str:
        token: str | None = None
        failure: BusinessError | None = None
        async with in_transaction() as db:
            connection = (
                await ToolConnection.filter(id=resolved.connection_id)
                .using_db(db)
                .select_for_update()
                .first()
            )
            if connection is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                    "tool_connection_not_found",
                    status_code=404,
                )
            if connection.secret_version != resolved.secret_version:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_oauth_version_conflict",
                    status_code=409,
                )
            if connection.status == ToolConnectionStatus.REVOKED:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INACTIVE,
                    "tool_connection_inactive",
                    status_code=409,
                )
            config = ToolConnectionService._decrypt_config(connection)
            access_token = config.get(CONNECTION_ACCESS_TOKEN)
            expires_at = _parse_expiry(config.get(CONNECTION_EXPIRES_AT))
            stored_type = (config.get(CONNECTION_TOKEN_TYPE) or "Bearer").lower()
            now = _utcnow()
            if stored_type != "bearer":
                failure = BusinessError(
                    code=ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                    msg_key="tool_oauth_config_invalid",
                    status_code=409,
                )
            elif (
                not force
                and access_token
                and expires_at is not None
                and expires_at - now > timedelta(seconds=expiry_skew_seconds)
            ):
                token = access_token
            else:
                refresh_token = config.get(CONNECTION_REFRESH_TOKEN)
                if not refresh_token:
                    if access_token and expires_at is not None and expires_at > now:
                        # No refresh credential exists; the current token is
                        # still usable, so do not pretend re-authorization is
                        # required yet.
                        token = access_token
                    else:
                        connection.status = ToolConnectionStatus.REAUTH_REQUIRED
                        await connection.save(
                            using_db=db,
                            update_fields=["status", "updated_at"],
                        )
                        failure = BusinessError(
                            code=ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED,
                            msg_key="tool_oauth_reauth_required",
                            status_code=409,
                        )
                else:
                    provider = await cls._provider_for_connection(connection, config)
                    if provider is None:
                        failure = BusinessError(
                            code=ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED,
                            msg_key="tool_oauth_reauth_required",
                            status_code=409,
                        )
                    else:
                        data: dict[str, str] = {
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": provider.client_id,
                        }
                        if (
                            provider.provider_kind == ToolOAuthProviderKind.MCP
                            and provider.resource
                        ):
                            data["resource"] = provider.resource
                        data.update(
                            {
                                key: value
                                for key, value in (provider.token_params or {}).items()
                                if key not in RESERVED_TOKEN_PARAMS
                            }
                        )
                        try:
                            tokens = await cls._request_token(provider, data)
                        except _OAuthEndpointError as exc:
                            if exc.error == "invalid_grant":
                                connection.status = ToolConnectionStatus.REAUTH_REQUIRED
                                await connection.save(
                                    using_db=db,
                                    update_fields=["status", "updated_at"],
                                )
                                failure = BusinessError(
                                    code=ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED,
                                    msg_key="tool_oauth_reauth_required",
                                    status_code=409,
                                )
                            else:
                                logger.warning(
                                    "OAuth refresh failed for connection %s: %s",
                                    connection.id,
                                    exc.error,
                                )
                                failure = BusinessError(
                                    code=(
                                        ResponseCode.TOOL_OAUTH_CONFIG_INVALID
                                        if exc.error == "unsupported_token_type"
                                        else ResponseCode.TOOL_OAUTH_EXCHANGE_FAILED
                                    ),
                                    msg_key=(
                                        "tool_oauth_config_invalid"
                                        if exc.error == "unsupported_token_type"
                                        else "tool_oauth_refresh_failed"
                                    ),
                                    status_code=(
                                        409
                                        if exc.error == "unsupported_token_type"
                                        else 502
                                    ),
                                )
                        else:
                            await cls._apply_tokens_locked(
                                connection=connection,
                                provider=provider,
                                tokens=tokens,
                                config=config,
                                allowed_scopes=cls._stored_scopes(config, provider),
                                bump_version_for_subject=False,
                                allow_userinfo=False,
                                db=db,
                            )
                            token = tokens.access_token
        if failure is not None:
            raise failure
        if token is None:
            raise BusinessError(
                code=ResponseCode.TOOL_OAUTH_EXCHANGE_FAILED,
                msg_key="tool_oauth_refresh_failed",
                status_code=502,
            )
        return token

    @classmethod
    async def _provider_for_connection(
        cls,
        connection: ToolConnection,
        config: Mapping[str, str],
    ) -> ToolOAuthProvider | None:
        provider_id = config.get(CONNECTION_PROVIDER_ID)
        if provider_id:
            try:
                provider = await ToolOAuthProvider.filter(id=UUID(provider_id)).first()
            except ValueError:
                provider = None
            if provider is not None:
                return provider
        if connection.tool_id is None:
            return None
        return (
            await ToolOAuthProvider.filter(tool_id=connection.tool_id)
            .order_by("-updated_at")
            .first()
        )

    @staticmethod
    def _stored_scopes(
        config: Mapping[str, str], provider: ToolOAuthProvider
    ) -> set[str]:
        raw = config.get(CONNECTION_SCOPE, "")
        if raw:
            return set(raw.split())
        return set(provider.scopes or [])

    @classmethod
    async def _store_tokens(
        cls,
        *,
        connection_id: UUID,
        provider: ToolOAuthProvider,
        tokens: _OAuthTokens,
        expected_secret_version: int,
        allowed_scopes: set[str],
        bump_version: bool,
        allow_userinfo: bool,
    ) -> None:
        identity_subject, identity_label = await cls._resolve_identity(
            provider, tokens, allow_userinfo=allow_userinfo
        )
        async with in_transaction() as db:
            connection = (
                await ToolConnection.filter(id=connection_id)
                .using_db(db)
                .select_for_update()
                .first()
            )
            if connection is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                    "tool_connection_not_found",
                    status_code=404,
                )
            if connection.status == ToolConnectionStatus.REVOKED:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INACTIVE,
                    "tool_connection_inactive",
                    status_code=409,
                )
            if connection.secret_version != expected_secret_version:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_oauth_version_conflict",
                    status_code=409,
                )
            config = ToolConnectionService._decrypt_config(connection)
            await cls._apply_tokens_locked(
                connection=connection,
                provider=provider,
                tokens=tokens,
                config=config,
                allowed_scopes=allowed_scopes,
                bump_version_for_subject=bump_version,
                allow_userinfo=False,
                db=db,
                identity=(identity_subject, identity_label),
            )

    @classmethod
    async def _apply_tokens_locked(
        cls,
        *,
        connection: ToolConnection,
        provider: ToolOAuthProvider,
        tokens: _OAuthTokens,
        config: dict[str, str],
        allowed_scopes: set[str],
        bump_version_for_subject: bool,
        allow_userinfo: bool,
        db: Any,
        identity: tuple[str | None, str | None] | None = None,
    ) -> None:
        if tokens.scope and allowed_scopes:
            escalated = set(tokens.scope) - set(allowed_scopes)
            if escalated:
                _fail(
                    ResponseCode.TOOL_OAUTH_SCOPE_ESCALATION,
                    "tool_oauth_scope_escalation",
                    status_code=403,
                )

        if identity is None:
            identity = await cls._resolve_identity(
                provider, tokens, allow_userinfo=allow_userinfo
            )
        subject, label = identity
        old_subject = config.get(CONNECTION_ACCOUNT_SUBJECT)
        changed_subject = bool(old_subject and subject and old_subject != subject)

        config[CONNECTION_ACCESS_TOKEN] = tokens.access_token
        config[CONNECTION_EXPIRES_AT] = (
            _utcnow() + timedelta(seconds=tokens.expires_in)
        ).isoformat()
        config[CONNECTION_TOKEN_TYPE] = tokens.token_type
        config[CONNECTION_PROVIDER_ID] = str(provider.id)
        granted_scopes = list(tokens.scope) or sorted(allowed_scopes)
        if granted_scopes:
            config[CONNECTION_SCOPE] = " ".join(granted_scopes)
        if tokens.refresh_token:
            config[CONNECTION_REFRESH_TOKEN] = tokens.refresh_token
        if subject:
            config[CONNECTION_ACCOUNT_SUBJECT] = subject
        elif old_subject:
            config[CONNECTION_ACCOUNT_SUBJECT] = old_subject

        encrypted, fields = ToolConnectionService._encrypt_config(config)
        connection.encrypted_config = encrypted
        connection.secret_fields = fields
        connection.status = ToolConnectionStatus.ACTIVE
        if label and (not connection.account_label or changed_subject):
            connection.account_label = label[:150]
        if bump_version_for_subject or changed_subject:
            connection.secret_version += 1
        await connection.save(
            using_db=db,
            update_fields=[
                "encrypted_config",
                "secret_fields",
                "status",
                "secret_version",
                "account_label",
                "updated_at",
            ],
        )

    @classmethod
    async def _resolve_identity(
        cls,
        provider: ToolOAuthProvider,
        tokens: _OAuthTokens,
        *,
        allow_userinfo: bool,
    ) -> tuple[str | None, str | None]:
        subject, label = _identity_from_claims(_decode_id_token_claims(tokens.id_token))
        if (subject or label) or not allow_userinfo:
            return subject, label
        if not provider.userinfo_endpoint:
            return subject, label
        try:
            claims = await cls._http_json(
                provider.userinfo_endpoint,
                method="GET",
                headers={
                    "Authorization": f"Bearer {tokens.access_token}",
                    "Accept": "application/json",
                },
            )
        except Exception:
            return subject, label
        return _identity_from_claims(claims)

    @classmethod
    async def _drop_tokens_for_failed_reauth(cls, connection_id: UUID) -> None:
        """Leave a failed callback recoverable without pretending it succeeded."""
        try:
            async with in_transaction() as db:
                connection = (
                    await ToolConnection.filter(id=connection_id)
                    .using_db(db)
                    .select_for_update()
                    .first()
                )
                if (
                    connection is None
                    or connection.status == ToolConnectionStatus.REVOKED
                ):
                    return
                config = ToolConnectionService._decrypt_config(connection)
                expires_at = _parse_expiry(config.get(CONNECTION_EXPIRES_AT))
                access_token = config.get(CONNECTION_ACCESS_TOKEN)
                if not access_token or expires_at is None or expires_at <= _utcnow():
                    connection.status = ToolConnectionStatus.REAUTH_REQUIRED
                    await connection.save(
                        using_db=db,
                        update_fields=["status", "updated_at"],
                    )
        except Exception:
            logger.exception(
                "Unable to mark OAuth connection %s as reauth required",
                connection_id,
            )

    # ------------------------------------------------------------------
    # Flow consumption
    # ------------------------------------------------------------------

    @staticmethod
    async def _validate_flow_actor(flow: ToolOAuthFlow) -> None:
        user = await User.filter(id=flow.user_id, is_active=True).first()
        if user is None:
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_state_invalid",
                status_code=400,
            )
        if flow.team_id is None or getattr(user, "is_superuser", False):
            return
        if not await TeamMember.filter(
            team_id=flow.team_id, user_id=flow.user_id
        ).exists():
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_state_invalid",
                status_code=400,
            )

    @classmethod
    async def _consume_flow(cls, state: str | None) -> ToolOAuthFlow:
        if not state or len(state) > 512:
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_state_invalid",
                status_code=400,
            )
        digest = _hash_state(state)
        flow = await ToolOAuthFlow.filter(state_hash=digest).first()
        if flow is None or flow.consumed_at is not None:
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_state_invalid",
                status_code=400,
            )
        now = _utcnow()
        consumed = await ToolOAuthFlow.filter(
            id=flow.id, consumed_at__isnull=True
        ).update(consumed_at=now)
        if not consumed:
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_state_invalid",
                status_code=400,
            )
        expires_at = _as_utc(flow.expires_at)
        if expires_at is None or expires_at <= now:
            _fail(
                ResponseCode.TOOL_OAUTH_STATE_INVALID,
                "tool_oauth_expired",
                status_code=400,
            )
        return flow


__all__ = [
    "CALLBACK_PATH",
    "CONNECTION_ACCESS_TOKEN",
    "CONNECTION_ACCOUNT_SUBJECT",
    "CONNECTION_EXPIRES_AT",
    "CONNECTION_PROVIDER_ID",
    "CONNECTION_REFRESH_TOKEN",
    "CONNECTION_SCOPE",
    "CONNECTION_TOKEN_TYPE",
    "RESERVED_CONNECTION_KEYS",
    "ToolOAuthService",
]

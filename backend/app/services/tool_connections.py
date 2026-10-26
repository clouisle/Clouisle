"""Tool connection storage, delegation grants and fail-closed resolution.

This module owns the *identity + secrets* layer. It deliberately knows nothing
about HTTP/MCP execution, approval policy or tool visibility: callers must
already have enforced tool access, and approvals must be evaluated separately.

Security properties enforced here:

* Personal connections always have an owner and are isolated per team.
* Team/site connections can never pretend to be a personal identity.
* Every write is authorized against the connection scope; administrators can
  never authorize (grant) another user's personal account.
* Secrets are Fernet-encrypted and only exposed through the internal
  :class:`ResolvedConnection` returned by :meth:`ToolConnectionService.resolve_connection`.
* Resolution re-validates membership, owner membership, grant state, expiry,
  operation allow-list and connection version on every call.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core.tool_secrets import (
    ToolSecretError,
    decrypt_tool_secret,
    encrypt_tool_secret,
)
from app.models.tool import Tool
from app.models.tool_connection import (
    ConnectionEntrypointType,
    ConnectionGrant,
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import (
    ConnectionEntrypoint,
    ConnectionGrantCreate,
    ConnectionGrantOut,
    ToolConnectionCreate,
    ToolConnectionOut,
    ToolConnectionUpdate,
)

logger = logging.getLogger(__name__)

TEAM_ADMIN_ROLES = frozenset({"owner", "admin"})

# Guards around secret material even when a service caller bypasses schemas.
MAX_SECRET_FIELDS = 50
MAX_SECRET_VALUE_LENGTH = 8192


@dataclass(frozen=True, slots=True)
class ResolvedConnection:
    """Internal execution identity.

    Contains decrypted secrets. NEVER serialize this into an API response,
    approval payload, run event, log line or task message.
    """

    connection_id: UUID
    team_id: UUID | None
    scope: ToolConnectionScope
    owner_user_id: UUID | None
    effective_user_id: UUID | None
    tool_id: UUID | None
    builtin_tool_key: str | None
    account_label: str | None
    status: ToolConnectionStatus
    secret_version: int
    grant_id: UUID | None
    grant_version: int | None
    allowed_operations: tuple[str, ...]
    secrets: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ConnectionBinding:
    """Secret-free snapshot for approval records and execution bookkeeping."""

    connection_id: UUID
    team_id: UUID | None
    scope: ToolConnectionScope
    owner_user_id: UUID | None
    effective_user_id: UUID | None
    secret_version: int
    status: ToolConnectionStatus
    is_active: bool
    grant_id: UUID | None
    grant_version: int | None
    allowed_operations: tuple[str, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fail(
    code: ResponseCode,
    msg_key: str,
    *,
    status_code: int = 403,
    **kwargs: Any,
) -> None:
    raise BusinessError(code=code, msg_key=msg_key, status_code=status_code, **kwargs)


class ToolConnectionService:
    """CRUD + resolution for :class:`ToolConnection` and grants."""

    # ------------------------------------------------------------------
    # Authorization primitives
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_actor(actor: User | UUID | str) -> User:
        if isinstance(actor, User):
            return actor
        if isinstance(actor, (UUID, str)):
            user = await User.filter(id=actor).first()
            if not user:
                _fail(
                    ResponseCode.UNAUTHORIZED,
                    "unauthorized",
                    status_code=401,
                )
            return user
        raise TypeError("actor must be a User instance or user id")

    @staticmethod
    async def _require_team(team_id: UUID) -> Team:
        team = await Team.filter(id=team_id).first()
        if not team:
            _fail(ResponseCode.TEAM_NOT_FOUND, "team_not_found", status_code=404)
        return team

    @classmethod
    async def _require_membership(
        cls, team_id: UUID, user: User, *, require_admin: bool = False
    ) -> TeamMember | None:
        await cls._require_team(team_id)
        if getattr(user, "is_superuser", False):
            return None
        membership = await TeamMember.filter(team_id=team_id, user_id=user.id).first()
        if not membership:
            _fail(ResponseCode.NOT_TEAM_MEMBER, "not_team_member", status_code=403)
        if require_admin and membership.role not in TEAM_ADMIN_ROLES:
            _fail(
                ResponseCode.TEAM_ADMIN_REQUIRED,
                "team_admin_required",
                status_code=403,
            )
        return membership

    @staticmethod
    def _require_superuser(user: User) -> None:
        if not getattr(user, "is_superuser", False):
            _fail(
                ResponseCode.PERMISSION_DENIED,
                "permission_denied",
                status_code=403,
            )

    @classmethod
    async def _authorize_manage(
        cls,
        connection: ToolConnection,
        user: User,
        *,
        allow_superuser_override: bool = False,
    ) -> None:
        """Authorize create/update/grant on a connection.

        Personal connections are owner-only even for superusers because an
        administrator must never stand in for a user's delegation decision.
        """
        if connection.scope == ToolConnectionScope.USER:
            if connection.owner_user_id != user.id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                    "tool_connection_access_denied",
                    status_code=403,
                )
            # Owner must still belong to the connection's team; leaving the
            # team disables management (and later resolution) fail-closed.
            if connection.team_id is not None:
                await cls._require_membership(connection.team_id, user)
            return
        if connection.scope == ToolConnectionScope.SITE:
            cls._require_superuser(user)
            return
        if allow_superuser_override and getattr(user, "is_superuser", False):
            return
        if connection.team_id is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )
        await cls._require_membership(connection.team_id, user, require_admin=True)

    @classmethod
    async def assert_manage_access(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        allow_superuser_override: bool = False,
    ) -> ToolConnectionOut:
        """Public wrapper for write/grant authorization on one connection.

        Used by OAuth start and other flows that must not duplicate the
        personal-owner / team-admin / site-admin rules.
        """
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_manage(
            connection,
            user,
            allow_superuser_override=allow_superuser_override,
        )
        return cls._to_out(connection)

    @classmethod
    async def _authorize_read(
        cls,
        connection: ToolConnection,
        user: User,
        *,
        team_id: UUID | None = None,
    ) -> None:
        if connection.scope == ToolConnectionScope.USER:
            if connection.owner_user_id != user.id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                    "tool_connection_access_denied",
                    status_code=403,
                )
            if connection.team_id:
                await cls._require_membership(connection.team_id, user)
            return
        if connection.scope == ToolConnectionScope.SITE:
            if team_id is not None:
                await cls._require_membership(team_id, user)
            elif not getattr(user, "is_superuser", False):
                _fail(
                    ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                    "tool_connection_access_denied",
                    status_code=403,
                )
            return
        if connection.team_id is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )
        await cls._require_membership(connection.team_id, user)

    # ------------------------------------------------------------------
    # Secret encoding
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_config_mapping(config: Mapping[str, Any]) -> dict[str, str]:
        if not isinstance(config, Mapping):
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )
        if len(config) > MAX_SECRET_FIELDS:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )
        cleaned: dict[str, str] = {}
        for name, value in config.items():
            if not isinstance(name, str) or not name.strip():
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            if not isinstance(value, str) or value == "":
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            if len(value) > MAX_SECRET_VALUE_LENGTH:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            cleaned[name] = value
        return cleaned

    @classmethod
    def _encrypt_config(cls, config: Mapping[str, Any]) -> tuple[str, list[str]]:
        cleaned = cls._validate_config_mapping(config)
        if not cleaned:
            return "", []
        payload = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
        return encrypt_tool_secret(payload), sorted(cleaned)

    @staticmethod
    def _validate_declared_fields(
        config: Mapping[str, str],
        declared_secret_fields: Collection[str] | None,
        required_secret_fields: Collection[str] | None,
    ) -> None:
        """Ensure only declared fields exist and every required field is set.

        ``None`` means the tool declares no restriction (e.g. legacy builtin
        tools); an empty collection means nothing is allowed/required.
        """
        if declared_secret_fields is not None:
            unknown = set(config) - set(declared_secret_fields)
            if unknown:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
        if required_secret_fields is not None:
            missing = set(required_secret_fields) - set(config)
            if missing:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )

    @staticmethod
    def _decrypt_config(connection: ToolConnection) -> dict[str, str]:
        if not connection.encrypted_config:
            return {}
        try:
            raw = decrypt_tool_secret(connection.encrypted_config)
            decoded = json.loads(raw)
        except (ToolSecretError, ValueError, TypeError):
            logger.warning(
                "Tool connection %s secrets cannot be decrypted", connection.id
            )
            _fail(
                ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE,
                "tool_connection_secret_unreadable",
                status_code=409,
            )
        if not isinstance(decoded, dict):
            _fail(
                ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE,
                "tool_connection_secret_unreadable",
                status_code=409,
            )
        return ToolConnectionService._validate_config_mapping(decoded)

    # ------------------------------------------------------------------
    # Service identity / default slot
    # ------------------------------------------------------------------

    @staticmethod
    def _service_key(tool_id: UUID | None, builtin_tool_key: str | None) -> str:
        if (tool_id is None) == (not builtin_tool_key):
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )
        return (
            f"tool:{tool_id}" if tool_id is not None else f"builtin:{builtin_tool_key}"
        )

    @staticmethod
    def _default_slot(
        *,
        scope: ToolConnectionScope,
        team_id: UUID | None,
        owner_user_id: UUID | None,
        service_key: str,
    ) -> str:
        if scope == ToolConnectionScope.SITE:
            return f"site:{service_key}"
        if scope == ToolConnectionScope.TEAM:
            return f"team:{team_id}:{service_key}"
        return f"user:{team_id}:{owner_user_id}:{service_key}"

    @staticmethod
    def _to_out(connection: ToolConnection) -> ToolConnectionOut:
        return ToolConnectionOut.model_validate(connection)

    @staticmethod
    def _grant_to_out(grant: ConnectionGrant) -> ConnectionGrantOut:
        return ConnectionGrantOut.model_validate(grant)

    # ------------------------------------------------------------------
    # Connection CRUD
    # ------------------------------------------------------------------

    @classmethod
    async def create_connection(
        cls,
        *,
        actor: User | UUID | str,
        payload: ToolConnectionCreate,
        declared_secret_fields: Collection[str] | None = None,
        required_secret_fields: Collection[str] | None = None,
    ) -> ToolConnectionOut:
        user = await cls._resolve_actor(actor)
        scope = payload.scope

        if scope == ToolConnectionScope.SITE:
            cls._require_superuser(user)
            team_id = None
            owner_user_id = None
        elif scope == ToolConnectionScope.TEAM:
            if payload.team_id is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            await cls._require_membership(payload.team_id, user, require_admin=True)
            team_id = payload.team_id
            owner_user_id = None
        else:
            if payload.team_id is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            await cls._require_membership(payload.team_id, user)
            team_id = payload.team_id
            owner_user_id = user.id

        if payload.tool_id is not None:
            if not await Tool.filter(id=payload.tool_id).exists():
                _fail(
                    ResponseCode.NOT_FOUND,
                    "tool_not_found",
                    status_code=404,
                )

        cls._validate_declared_fields(
            payload.config, declared_secret_fields, required_secret_fields
        )
        encrypted_config, secret_fields = cls._encrypt_config(payload.config)
        service_key = cls._service_key(payload.tool_id, payload.builtin_tool_key)
        default_slot: str | None = None
        if payload.is_default:
            default_slot = cls._default_slot(
                scope=scope,
                team_id=team_id,
                owner_user_id=owner_user_id,
                service_key=service_key,
            )

        connection = ToolConnection(
            id=uuid4(),
            team_id=team_id,
            tool_id=payload.tool_id,
            builtin_tool_key=payload.builtin_tool_key,
            scope=scope,
            owner_user_id=owner_user_id,
            name=payload.name,
            account_label=payload.account_label,
            encrypted_config=encrypted_config,
            secret_fields=secret_fields,
            secret_version=1,
            status=ToolConnectionStatus.ACTIVE,
            is_default=payload.is_default,
            default_slot=default_slot,
            created_by_id=user.id,
        )
        try:
            connection.validate_invariants()
        except ValueError as exc:
            logger.warning("Rejected tool connection for %s: %s", user.id, exc)
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )

        try:
            async with in_transaction():
                if default_slot:
                    await ToolConnection.filter(default_slot=default_slot).update(
                        is_default=False, default_slot=None
                    )
                await connection.save()
        except IntegrityError:
            # Concurrent default selection lost the unique slot race.
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_default_conflict",
                status_code=409,
            )
        return cls._to_out(connection)

    @classmethod
    async def update_connection(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        payload: ToolConnectionUpdate,
        declared_secret_fields: Collection[str] | None = None,
        required_secret_fields: Collection[str] | None = None,
    ) -> ToolConnectionOut:
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_manage(connection, user)

        if connection.status == ToolConnectionStatus.REVOKED:
            _fail(
                ResponseCode.TOOL_CONNECTION_INACTIVE,
                "tool_connection_inactive",
                status_code=409,
            )
        if (
            payload.expected_secret_version is not None
            and payload.expected_secret_version != connection.secret_version
        ):
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_version_conflict",
                status_code=409,
            )

        fields_set = payload.model_fields_set
        changed_secret_material = False

        if payload.name is not None:
            connection.name = payload.name
        if "account_label" in fields_set:
            normalized_label = payload.account_label
            if normalized_label != connection.account_label:
                connection.account_label = normalized_label
                changed_secret_material = True

        if payload.config_set is not None or payload.config_remove is not None:
            current = cls._decrypt_config(connection)
            updated = dict(current)
            if payload.config_remove:
                for name in payload.config_remove:
                    updated.pop(name, None)
            if payload.config_set:
                updated.update(cls._validate_config_mapping(payload.config_set))
            cls._validate_declared_fields(
                updated, declared_secret_fields, required_secret_fields
            )
            if updated != current:
                (
                    connection.encrypted_config,
                    connection.secret_fields,
                ) = cls._encrypt_config(updated)
                changed_secret_material = True

        if payload.status is not None:
            if payload.status == ToolConnectionStatus.REVOKED:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )
            connection.status = payload.status

        new_default_slot = connection.default_slot
        if payload.is_default is not None:
            if payload.is_default:
                connection.is_default = True
                new_default_slot = cls._default_slot(
                    scope=connection.scope,
                    team_id=connection.team_id,
                    owner_user_id=connection.owner_user_id,
                    service_key=cls._service_key(
                        connection.tool_id, connection.builtin_tool_key
                    ),
                )
            else:
                connection.is_default = False
                new_default_slot = None
        connection.default_slot = new_default_slot

        if changed_secret_material:
            connection.secret_version += 1

        try:
            connection.validate_invariants()
        except ValueError as exc:
            logger.warning("Rejected tool connection for %s: %s", user.id, exc)
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )

        try:
            async with in_transaction():
                if connection.is_default and connection.default_slot:
                    await (
                        ToolConnection.filter(default_slot=connection.default_slot)
                        .exclude(id=connection.id)
                        .update(is_default=False, default_slot=None)
                    )
                await connection.save()
        except IntegrityError:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_default_conflict",
                status_code=409,
            )
        return cls._to_out(connection)

    @classmethod
    async def revoke_connection(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        reason: str | None = None,
    ) -> ToolConnectionOut:
        """Permanently revoke a connection and every grant attached to it.

        Superusers may revoke any connection (abuse/security response), but this
        grants them no ability to decrypt, use or re-authorize it.
        """
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_manage(connection, user, allow_superuser_override=True)

        if connection.status != ToolConnectionStatus.REVOKED:
            now = _utcnow()
            async with in_transaction():
                connection.status = ToolConnectionStatus.REVOKED
                connection.is_default = False
                connection.default_slot = None
                await connection.save()
                await ConnectionGrant.filter(
                    connection_id=connection.id, revoked_at__isnull=True
                ).update(revoked_at=now, revoked_by_id=user.id)
            if reason:
                logger.info(
                    "Tool connection %s revoked by %s: %s",
                    connection.id,
                    user.id,
                    reason,
                )
        return cls._to_out(connection)

    @classmethod
    async def list_connections(
        cls,
        *,
        actor: User | UUID | str,
        team_id: UUID,
        tool_id: UUID | None = None,
        builtin_tool_key: str | None = None,
        include_site: bool = True,
        include_revoked: bool = False,
    ) -> list[ToolConnectionOut]:
        user = await cls._resolve_actor(actor)
        await cls._require_membership(team_id, user)

        query = Q(team_id=team_id, scope=ToolConnectionScope.TEAM) | Q(
            team_id=team_id,
            scope=ToolConnectionScope.USER,
            owner_user_id=user.id,
        )
        if include_site:
            query |= Q(team_id__isnull=True, scope=ToolConnectionScope.SITE)
        connections = ToolConnection.filter(query)
        if tool_id is not None:
            connections = connections.filter(tool_id=tool_id)
        if builtin_tool_key:
            connections = connections.filter(builtin_tool_key=builtin_tool_key)
        if not include_revoked:
            connections = connections.exclude(status=ToolConnectionStatus.REVOKED)
        return [cls._to_out(item) for item in await connections]

    @classmethod
    async def get_connection(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        team_id: UUID | None = None,
    ) -> ToolConnectionOut:
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_read(connection, user, team_id=team_id)
        return cls._to_out(connection)

    # ------------------------------------------------------------------
    # Grants
    # ------------------------------------------------------------------

    @classmethod
    async def create_grant(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        payload: ConnectionGrantCreate,
    ) -> ConnectionGrantOut:
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_manage(connection, user)

        if connection.status != ToolConnectionStatus.ACTIVE:
            _fail(
                ResponseCode.TOOL_CONNECTION_INACTIVE,
                "tool_connection_inactive",
                status_code=409,
            )

        team_id = payload.team_id
        if connection.scope == ToolConnectionScope.USER:
            # Personal accounts are team-isolated: a grant may only be created
            # for the team that owns the connection.
            if team_id is None:
                team_id = connection.team_id
            elif team_id != connection.team_id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                    "tool_connection_grant_denied",
                    status_code=403,
                )
            await cls._ensure_owner_in_team(connection)
        elif connection.scope == ToolConnectionScope.TEAM:
            if team_id is None:
                team_id = connection.team_id
            elif team_id != connection.team_id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                    "tool_connection_grant_denied",
                    status_code=403,
                )
        else:  # SITE
            if team_id is not None:
                await cls._require_membership(team_id, user)
            else:
                cls._require_superuser(user)

        if not await cls._entrypoint_exists(
            payload.entrypoint_type, payload.entrypoint_id, team_id
        ):
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_entrypoint_not_found",
                status_code=404,
            )

        operations = list(payload.allowed_operations)
        latest_grant = (
            await ConnectionGrant.filter(
                connection_id=connection.id,
                entrypoint_type=payload.entrypoint_type,
                entrypoint_id=payload.entrypoint_id,
                team_id=team_id,
            )
            .order_by("-version")
            .first()
        )
        version = latest_grant.version if latest_grant else 0

        grant = ConnectionGrant(
            id=uuid4(),
            connection_id=connection.id,
            granted_by_id=user.id,
            entrypoint_type=payload.entrypoint_type,
            entrypoint_id=payload.entrypoint_id,
            team_id=team_id,
            allowed_operations=operations,
            expires_at=payload.expires_at,
            version=version + 1,
        )
        try:
            grant.validate_invariants()
        except ValueError as exc:
            logger.warning("Rejected connection grant for %s: %s", user.id, exc)
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )

        now = _utcnow()
        async with in_transaction():
            # Re-granting replaces the active grant for the same entrypoint;
            # the version keeps approvals bound to the new authorization.
            await ConnectionGrant.filter(
                connection_id=connection.id,
                entrypoint_type=payload.entrypoint_type,
                entrypoint_id=payload.entrypoint_id,
                team_id=team_id,
                revoked_at__isnull=True,
            ).update(revoked_at=now, revoked_by_id=user.id)
            await grant.save()
        return cls._grant_to_out(grant)

    @classmethod
    async def list_grants(
        cls,
        *,
        actor: User | UUID | str,
        connection_id: UUID,
        include_revoked: bool = False,
    ) -> list[ConnectionGrantOut]:
        user = await cls._resolve_actor(actor)
        connection = await cls._load_connection(connection_id)
        await cls._authorize_manage(connection, user, allow_superuser_override=True)
        query = ConnectionGrant.filter(connection_id=connection.id)
        if not include_revoked:
            query = query.filter(revoked_at__isnull=True)
        return [cls._grant_to_out(item) for item in await query]

    @classmethod
    async def revoke_grant(
        cls,
        *,
        actor: User | UUID | str,
        grant_id: UUID,
        reason: str | None = None,
    ) -> ConnectionGrantOut:
        user = await cls._resolve_actor(actor)
        grant = await ConnectionGrant.filter(id=grant_id).first()
        if not grant:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_NOT_FOUND,
                "tool_connection_grant_not_found",
                status_code=404,
            )
        connection = await cls._load_connection(grant.connection_id)
        await cls._authorize_manage(connection, user, allow_superuser_override=True)
        if grant.revoked_at is None:
            grant.revoked_at = _utcnow()
            grant.revoked_by_id = user.id
            await grant.save()
            if reason:
                logger.info(
                    "Tool connection grant %s revoked by %s: %s",
                    grant.id,
                    user.id,
                    reason,
                )
        return cls._grant_to_out(grant)

    # ------------------------------------------------------------------
    # Default selection
    # ------------------------------------------------------------------

    @classmethod
    async def get_default_connection(
        cls,
        *,
        actor: User | UUID | str,
        team_id: UUID,
        scope: ToolConnectionScope,
        tool_id: UUID | None = None,
        builtin_tool_key: str | None = None,
    ) -> ToolConnection:
        """Return the caller's/team's explicit default for one scope.

        A materialized builtin may have connections created under either its
        stable ``tool_id`` or its ``builtin_tool_key``; both are tried within
        the same scope/team/owner only. Never falls back across scopes.
        """
        user = await cls._resolve_actor(actor)
        await cls._require_membership(team_id, user)

        service_keys: list[str] = []
        if tool_id is not None:
            service_keys.append(f"tool:{tool_id}")
        if builtin_tool_key:
            service_keys.append(f"builtin:{builtin_tool_key}")
        if not service_keys:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )

        for service_key in service_keys:
            if scope == ToolConnectionScope.USER:
                slot = cls._default_slot(
                    scope=scope,
                    team_id=team_id,
                    owner_user_id=user.id,
                    service_key=service_key,
                )
            elif scope == ToolConnectionScope.TEAM:
                slot = cls._default_slot(
                    scope=scope,
                    team_id=team_id,
                    owner_user_id=None,
                    service_key=service_key,
                )
            elif scope == ToolConnectionScope.SITE:
                slot = cls._default_slot(
                    scope=scope,
                    team_id=None,
                    owner_user_id=None,
                    service_key=service_key,
                )
            else:  # pragma: no cover
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_invalid",
                    status_code=400,
                )

            connection = await ToolConnection.filter(
                default_slot=slot, is_default=True
            ).first()
            if connection and connection.status == ToolConnectionStatus.ACTIVE:
                return connection

        _fail(
            ResponseCode.TOOL_CONNECTION_REQUIRED,
            "tool_connection_required",
            status_code=409,
        )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    @classmethod
    async def resolve_connection(
        cls,
        *,
        team_id: UUID,
        actor: User | UUID | str,
        connection_id: UUID | None = None,
        tool_id: UUID | None = None,
        builtin_tool_key: str | None = None,
        scope: ToolConnectionScope | None = None,
        operation: str | None = None,
        entrypoint: ConnectionEntrypoint | None = None,
        grant_id: UUID | None = None,
        use_default: bool = False,
        expected_secret_version: int | None = None,
        allowed_scopes: Collection[ToolConnectionScope] | None = None,
        allowed_secret_fields: Collection[str] | None = None,
        required_secret_fields: Collection[str] | None = None,
    ) -> ResolvedConnection:
        """Resolve the effective execution identity, fail closed.

        Raises :class:`BusinessError` (never returns an unauthenticated or
        ambiguous identity). Secrets are filtered to ``allowed_secret_fields``
        when the tool definition declares an explicit credential field list.
        """
        user = await cls._resolve_actor(actor)
        await cls._require_membership(team_id, user)

        if connection_id is not None and use_default:
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                status_code=400,
            )

        if connection_id is None:
            if not use_default:
                _fail(
                    ResponseCode.TOOL_CONNECTION_REQUIRED,
                    "tool_connection_required",
                    status_code=409,
                )
            if scope is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_REQUIRED,
                    "tool_connection_required",
                    status_code=409,
                )
            connection = await cls.get_default_connection(
                actor=user,
                team_id=team_id,
                scope=scope,
                tool_id=tool_id,
                builtin_tool_key=builtin_tool_key,
            )
        else:
            connection = await cls._load_connection(connection_id)

        cls._assert_team_binding(connection, team_id)
        cls._assert_service_binding(connection, tool_id, builtin_tool_key)

        if allowed_scopes is not None and connection.scope not in allowed_scopes:
            _fail(
                ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                "tool_connection_access_denied",
                status_code=403,
            )
        if scope is not None and connection.scope != scope:
            # An explicit connection that contradicts the requested identity
            # mode is never silently coerced.
            _fail(
                ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                "tool_connection_access_denied",
                status_code=403,
            )

        if connection.status != ToolConnectionStatus.ACTIVE:
            _fail(
                ResponseCode.TOOL_CONNECTION_INACTIVE,
                "tool_connection_inactive",
                status_code=409,
            )
        if (
            expected_secret_version is not None
            and expected_secret_version != connection.secret_version
        ):
            _fail(
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_version_conflict",
                status_code=409,
            )

        grant = await cls._authorize_connection_use(
            connection=connection,
            user=user,
            team_id=team_id,
            operation=operation,
            entrypoint=entrypoint,
            grant_id=grant_id,
        )

        secrets = cls._decrypt_config(connection)
        if allowed_secret_fields is not None:
            secrets = {
                name: value
                for name, value in secrets.items()
                if name in allowed_secret_fields
            }
        if required_secret_fields is not None:
            missing = set(required_secret_fields) - set(secrets)
            if missing:
                _fail(
                    ResponseCode.TOOL_CONNECTION_INACTIVE,
                    "tool_connection_secret_unreadable",
                    status_code=409,
                )

        return ResolvedConnection(
            connection_id=connection.id,
            team_id=connection.team_id,
            scope=connection.scope,
            owner_user_id=connection.owner_user_id,
            effective_user_id=(
                connection.owner_user_id
                if connection.scope == ToolConnectionScope.USER
                else None
            ),
            tool_id=connection.tool_id,
            builtin_tool_key=connection.builtin_tool_key,
            account_label=connection.account_label,
            status=connection.status,
            secret_version=connection.secret_version,
            grant_id=grant.id if grant else None,
            grant_version=grant.version if grant else None,
            allowed_operations=(
                tuple(grant.allowed_operations or []) if grant else ("*",)
            ),
            secrets=secrets,
        )

    @classmethod
    async def get_binding_snapshot(
        cls,
        *,
        team_id: UUID,
        actor: User | UUID | str,
        connection_id: UUID | None = None,
        tool_id: UUID | None = None,
        builtin_tool_key: str | None = None,
        scope: ToolConnectionScope | None = None,
        operation: str | None = None,
        entrypoint: ConnectionEntrypoint | None = None,
        grant_id: UUID | None = None,
        use_default: bool = False,
        expected_secret_version: int | None = None,
        allowed_scopes: Collection[ToolConnectionScope] | None = None,
        allowed_secret_fields: Collection[str] | None = None,
        required_secret_fields: Collection[str] | None = None,
    ) -> ConnectionBinding:
        """Secret-free authorization snapshot for approval/execution records."""
        resolved = await cls.resolve_connection(
            team_id=team_id,
            actor=actor,
            connection_id=connection_id,
            tool_id=tool_id,
            builtin_tool_key=builtin_tool_key,
            scope=scope,
            operation=operation,
            entrypoint=entrypoint,
            grant_id=grant_id,
            use_default=use_default,
            expected_secret_version=expected_secret_version,
            allowed_scopes=allowed_scopes,
            allowed_secret_fields=allowed_secret_fields,
            required_secret_fields=required_secret_fields,
        )
        return ConnectionBinding(
            connection_id=resolved.connection_id,
            team_id=resolved.team_id,
            scope=resolved.scope,
            owner_user_id=resolved.owner_user_id,
            effective_user_id=resolved.effective_user_id,
            secret_version=resolved.secret_version,
            status=resolved.status,
            is_active=resolved.status == ToolConnectionStatus.ACTIVE,
            grant_id=resolved.grant_id,
            grant_version=resolved.grant_version,
            allowed_operations=resolved.allowed_operations,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_connection(connection_id: UUID) -> ToolConnection:
        connection = await ToolConnection.filter(id=connection_id).first()
        if not connection:
            _fail(
                ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                "tool_connection_not_found",
                status_code=404,
            )
        return connection

    @staticmethod
    def _assert_team_binding(connection: ToolConnection, team_id: UUID | None) -> None:
        if connection.scope == ToolConnectionScope.SITE:
            if connection.team_id is not None or team_id is None:
                _fail(
                    ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                    "tool_connection_not_found",
                    status_code=404,
                )
            return
        if connection.team_id != team_id:
            # Do not disclose the existence of another team's connection.
            _fail(
                ResponseCode.TOOL_CONNECTION_NOT_FOUND,
                "tool_connection_not_found",
                status_code=404,
            )

    @staticmethod
    def _assert_service_binding(
        connection: ToolConnection,
        tool_id: UUID | None,
        builtin_tool_key: str | None,
    ) -> None:
        if tool_id is None and not builtin_tool_key:
            return
        if tool_id is not None and connection.tool_id == tool_id:
            return
        if builtin_tool_key and connection.builtin_tool_key == builtin_tool_key:
            return
        _fail(
            ResponseCode.TOOL_CONNECTION_NOT_FOUND,
            "tool_connection_not_found",
            status_code=404,
        )

    @classmethod
    async def _ensure_owner_in_team(cls, connection: ToolConnection) -> None:
        if connection.team_id is None or connection.owner_user_id is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )
        is_member = await TeamMember.filter(
            team_id=connection.team_id, user_id=connection.owner_user_id
        ).exists()
        if not is_member:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )

    @classmethod
    async def _authorize_connection_use(
        cls,
        *,
        connection: ToolConnection,
        user: User,
        team_id: UUID,
        operation: str | None,
        entrypoint: ConnectionEntrypoint | None,
        grant_id: UUID | None,
    ) -> ConnectionGrant | None:
        """Validate identity delegation; returns the grant when required."""
        if entrypoint is not None:
            if entrypoint.team_id is not None and entrypoint.team_id != team_id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                    "tool_connection_grant_denied",
                    status_code=403,
                )
            # Entrypoints can be deleted or disabled after the grant was
            # issued; revalidate on every resolution, not only on grant.
            if not await cls._entrypoint_exists(
                entrypoint.entrypoint_type,
                entrypoint.entrypoint_id,
                team_id,
            ):
                _fail(
                    ResponseCode.TOOL_CONNECTION_INVALID,
                    "tool_connection_entrypoint_not_found",
                    status_code=404,
                )

        if connection.scope != ToolConnectionScope.USER:
            # Team/site connections only require team membership and an
            # explicit binding; grants are personal-delegation only.
            if grant_id is not None:
                grant = await cls._load_valid_grant(
                    grant_id=grant_id,
                    connection=connection,
                    team_id=team_id,
                    operation=operation,
                    entrypoint=entrypoint,
                    require_owner_grant=False,
                )
                cls._assert_grant_team_binding(connection, grant, team_id)
            return None

        is_owner = connection.owner_user_id == user.id
        if is_owner:
            if grant_id is not None:
                grant = await cls._load_valid_grant(
                    grant_id=grant_id,
                    connection=connection,
                    team_id=team_id,
                    operation=operation,
                    entrypoint=entrypoint,
                    require_owner_grant=True,
                )
                cls._assert_grant_team_binding(connection, grant, team_id)
            return None

        # Background/interactive delegation of someone else's personal account.
        if grant_id is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_required",
                status_code=403,
            )
        if entrypoint is None:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_required",
                status_code=403,
            )
        await cls._ensure_owner_in_team(connection)
        grant = await cls._load_valid_grant(
            grant_id=grant_id,
            connection=connection,
            team_id=team_id,
            operation=operation,
            entrypoint=entrypoint,
            require_owner_grant=True,
        )
        cls._assert_grant_team_binding(connection, grant, team_id)
        return grant

    @staticmethod
    def _assert_grant_team_binding(
        connection: ToolConnection, grant: ConnectionGrant, team_id: UUID
    ) -> None:
        """Personal/team grants must match the connection's team exactly.

        Only site-wide grants may carry a NULL team; they are usable in any
        team the entrypoint actually runs in.
        """
        if connection.scope == ToolConnectionScope.SITE:
            if grant.team_id is not None and grant.team_id != team_id:
                _fail(
                    ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                    "tool_connection_grant_denied",
                    status_code=403,
                )
            return
        if grant.team_id != team_id:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )

    @classmethod
    async def _load_valid_grant(
        cls,
        *,
        grant_id: UUID,
        connection: ToolConnection,
        team_id: UUID,
        operation: str | None,
        entrypoint: ConnectionEntrypoint | None,
        require_owner_grant: bool,
    ) -> ConnectionGrant:
        grant = await ConnectionGrant.filter(
            id=grant_id, connection_id=connection.id
        ).first()
        if not grant:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_NOT_FOUND,
                "tool_connection_grant_not_found",
                status_code=404,
            )
        if not grant.is_active():
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_expired",
                status_code=403,
            )
        if grant.team_id is not None and grant.team_id != team_id:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )
        if require_owner_grant and grant.granted_by_id != connection.owner_user_id:
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )
        if entrypoint is not None:
            if (
                grant.entrypoint_type != entrypoint.entrypoint_type
                or grant.entrypoint_id != entrypoint.entrypoint_id
            ):
                _fail(
                    ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                    "tool_connection_grant_denied",
                    status_code=403,
                )
        if not grant.allows_operation(operation):
            _fail(
                ResponseCode.TOOL_CONNECTION_GRANT_DENIED,
                "tool_connection_grant_denied",
                status_code=403,
            )
        return grant

    @staticmethod
    async def _entrypoint_exists(
        entrypoint_type: ConnectionEntrypointType,
        entrypoint_id: str,
        team_id: UUID | None,
    ) -> bool:
        """Verify the entrypoint exists and belongs to the grant team.

        Lazy imports keep the storage layer independent of execution modules.
        Unknown/invalid ids fail closed.
        """
        try:
            parsed_id = UUID(str(entrypoint_id))
        except (ValueError, TypeError, AttributeError):
            return False

        if entrypoint_type == ConnectionEntrypointType.AGENT:
            from app.models.agent import Agent

            query = Agent.filter(id=parsed_id)
            if team_id is not None:
                query = query.filter(team_id=team_id)
            return await query.exists()

        if entrypoint_type == ConnectionEntrypointType.WORKFLOW:
            from app.models.workflow import Workflow

            query = Workflow.filter(id=parsed_id)
            if team_id is not None:
                query = query.filter(team_id=team_id)
            return await query.exists()

        if entrypoint_type == ConnectionEntrypointType.API_KEY:
            from app.models.api_key import APIKey

            api_key = await APIKey.filter(id=parsed_id, is_active=True).first()
            if not api_key:
                return False
            if api_key.expires_at is not None:
                expires_at = api_key.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= _utcnow():
                    return False
            if team_id is None:
                return True
            return await TeamMember.filter(
                team_id=team_id, user_id=api_key.user_id
            ).exists()

        if entrypoint_type == ConnectionEntrypointType.SCHEDULE:
            from app.models.workflow import TriggerType, Workflow

            query = Workflow.filter(id=parsed_id)
            if team_id is not None:
                query = query.filter(team_id=team_id)
            return await query.filter(trigger_type=TriggerType.CRON).exists()

        if entrypoint_type == ConnectionEntrypointType.CHANNEL:
            from app.models.integration import Integration

            from app.models.wechat_knowledge import WeChatKnowledgeBinding

            return (
                await Integration.filter(id=parsed_id).exists()
                or await WeChatKnowledgeBinding.filter(
                    id=parsed_id, status="connected"
                ).exists()
            )

        if entrypoint_type == ConnectionEntrypointType.EMBED:
            from app.models.agent import Agent

            query = Agent.filter(id=parsed_id)
            if team_id is not None:
                query = query.filter(team_id=team_id)
            return await query.exists()

        return False


__all__ = [
    "ConnectionBinding",
    "ResolvedConnection",
    "ToolConnectionService",
]

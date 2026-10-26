"""Migrate legacy plaintext tool credentials into encrypted team connections.

Design constraints enforced here:

* Migrated identities are TEAM (or SITE for global builtin config) only —
  personal ownership is never inferred.
* No plaintext secret is deleted before it is safely stored (per-record
  transaction); values that cannot be migrated fail startup instead of being
  dropped.
* Config templates become ``{{field}}`` placeholders so legacy renderers keep
  working once they resolve the connection. Non-secret config (URLs, args,
  non-sensitive headers, non-secret env values) is retained.
* Idempotent: connections are looked up by tool/team/scope/name and compared
  against the stored ciphertext before any update.
* A migrated non-web_search ``ToolConfig`` row is deleted in the same
  transaction that commits its connection, so no plaintext credential set
  survives the cutover. The single global ``web_search`` row is retained
  because it is the site search configuration store. A global
  (``team_id`` NULL) non-web_search row cannot be mapped without silently
  narrowing it to one team, so startup fails closed and an operator must run
  ``python -m app.core.tool_secret_migration --tool-name <name> --target-team
  <team-uuid>`` to choose the team explicitly.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID, uuid4

from tortoise.transactions import in_transaction

from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.tool import Tool
from app.models.tool_config import ToolConfig
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)

logger = logging.getLogger(__name__)

_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
    }
)


class LegacySecretMigrationError(RuntimeError):
    """Legacy configuration cannot be migrated without losing data."""


def _sanitize_field(component: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", component).strip("_")
    if not cleaned:
        raise LegacySecretMigrationError(
            f"cannot derive a credential field name from {component!r}"
        )
    if cleaned[0].isdigit():
        cleaned = f"value_{cleaned}"
    return cleaned


def _add_secret(
    secrets: dict[str, str],
    declared: set[str],
    name: str,
    value: Any,
    *,
    source: str,
) -> None:
    if not isinstance(value, str):
        raise LegacySecretMigrationError(
            f"{source}: value for {name!r} is not a string"
        )
    if not value:
        return
    if not _FIELD_NAME_PATTERN.fullmatch(name):
        raise LegacySecretMigrationError(
            f"{source}: {name!r} is not a valid credential field name"
        )
    existing = secrets.get(name)
    if existing is not None and existing != value:
        raise LegacySecretMigrationError(
            f"{source}: conflicting values for credential field {name!r}"
        )
    secrets[name] = value
    declared.add(name)


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and "{{" in value and "}}" in value


def _build_tool_secrets(
    tool: Tool,
) -> tuple[
    dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    """Return secrets plus rewritten credentials/http/mcp/database configs."""
    secrets: dict[str, str] = {}
    declared: set[str] = set()

    credentials = dict(tool.credentials or {})
    for name, value in list(credentials.items()):
        _add_secret(
            secrets, declared, name, value, source=f"tool {tool.id} credentials"
        )
        credentials.pop(name)

    http_config = dict(tool.http_config or {})
    headers = dict(http_config.get("headers") or {})
    for header, value in list(headers.items()):
        if str(header).lower() not in _SENSITIVE_HEADERS:
            continue
        if _is_template(value):
            continue
        field = f"http_header_{_sanitize_field(str(header).lower())}"
        _add_secret(
            secrets, declared, field, value, source=f"tool {tool.id} http header"
        )
        headers[header] = f"{{{{{field}}}}}"
    if headers:
        http_config["headers"] = headers

    mcp_config = dict(tool.mcp_config or {})
    env = dict(mcp_config.get("env") or {})
    for env_key, value in list(env.items()):
        if _is_template(value):
            continue
        field = _sanitize_field(str(env_key))
        _add_secret(secrets, declared, field, value, source=f"tool {tool.id} env")
        env[env_key] = f"{{{{{field}}}}}"
    if env:
        mcp_config["env"] = env

    mcp_headers = dict(mcp_config.get("headers") or {})
    for header, value in list(mcp_headers.items()):
        if str(header).lower() not in _SENSITIVE_HEADERS:
            continue
        if _is_template(value):
            continue
        field = f"mcp_header_{_sanitize_field(str(header).lower())}"
        _add_secret(
            secrets,
            declared,
            field,
            value,
            source=f"tool {tool.id} mcp header",
        )
        mcp_headers[header] = f"{{{{{field}}}}}"
    if mcp_headers:
        mcp_config["headers"] = mcp_headers

    database_config = dict(tool.database_config or {})
    for source_key, field in (("password", "password"), ("url", "url")):
        value = database_config.get(source_key)
        if value is None or value == "" or _is_template(value):
            continue
        _add_secret(
            secrets,
            declared,
            field,
            value,
            source=f"tool {tool.id} database {source_key}",
        )
        database_config[source_key] = f"{{{{{field}}}}}"

    return secrets, credentials, http_config, mcp_config, database_config


def _merge_connection_fields(tool: Tool, field_names: set[str]) -> None:
    fields = list(tool.connection_fields or [])
    existing = {
        item.get("name")
        for item in fields
        if isinstance(item, dict) and item.get("name")
    }
    for name in sorted(field_names):
        if name in existing:
            continue
        fields.append({"name": name, "label": name, "required": True, "secret": True})
    tool.connection_fields = fields


def _connection_name(tool: Tool) -> str:
    return f"Migrated {tool.name}"[:100]


async def _upsert_connection(
    *,
    tool_id,
    team_id,
    builtin_tool_key: str | None,
    name: str,
    scope: ToolConnectionScope,
    secrets: dict[str, str],
    created_by_id=None,
    legacy_builtin_key: str | None = None,
) -> ToolConnection:
    from tortoise.expressions import Q

    query = ToolConnection.filter(scope=scope, name=name)
    if tool_id is not None:
        if legacy_builtin_key:
            query = query.filter(
                Q(tool_id=tool_id)
                | Q(tool_id__isnull=True, builtin_tool_key=legacy_builtin_key)
            )
        else:
            query = query.filter(tool_id=tool_id)
    else:
        query = query.filter(builtin_tool_key=builtin_tool_key)
    if team_id is None:
        query = query.filter(team_id__isnull=True)
    else:
        query = query.filter(team_id=team_id)

    connection = await query.first()
    if connection is not None:
        try:
            stored = json.loads(decrypt_tool_secret(connection.encrypted_config))
        except Exception as exc:  # noqa: BLE001 - fail closed on unreadable data
            raise LegacySecretMigrationError(
                f"existing migrated connection {connection.id} is unreadable"
            ) from exc
        changed = False
        if stored != secrets:
            connection.encrypted_config = encrypt_tool_secret(
                json.dumps(secrets, sort_keys=True, separators=(",", ":"))
            )
            connection.secret_fields = sorted(secrets)
            connection.secret_version += 1
            changed = True
        if connection.tool_id != tool_id:
            connection.tool_id = tool_id
            changed = True
        if connection.builtin_tool_key != builtin_tool_key:
            connection.builtin_tool_key = builtin_tool_key
            changed = True
        if changed:
            connection.validate_invariants()
            await connection.save()
        return connection

    connection = ToolConnection(
        id=uuid4(),
        team_id=team_id,
        tool_id=tool_id,
        builtin_tool_key=builtin_tool_key,
        scope=scope,
        owner_user_id=None,
        name=name,
        account_label=None,
        encrypted_config=encrypt_tool_secret(
            json.dumps(secrets, sort_keys=True, separators=(",", ":"))
        ),
        secret_fields=sorted(secrets),
        secret_version=1,
        status=ToolConnectionStatus.ACTIVE,
        is_default=False,
        default_slot=None,
        created_by_id=created_by_id,
    )
    connection.validate_invariants()
    await connection.save()
    return connection


async def _migrate_tool(tool: Tool) -> str | None:
    (
        secrets,
        credentials,
        http_config,
        mcp_config,
        database_config,
    ) = _build_tool_secrets(tool)

    existing = (
        await ToolConnection.filter(
            tool_id=tool.id,
            team_id=tool.team_id,
            scope=ToolConnectionScope.TEAM,
            name=_connection_name(tool),
        ).first()
        if tool.team_id is not None
        else None
    )

    if not secrets:
        # Already migrated (or no secrets): only report the mapping.
        return str(existing.id) if existing else None

    if tool.team_id is None:
        raise LegacySecretMigrationError(
            f"tool {tool.id} has credentials but no team to own them"
        )

    async with in_transaction():
        connection = await _upsert_connection(
            tool_id=tool.id,
            team_id=tool.team_id,
            builtin_tool_key=None,
            name=_connection_name(tool),
            scope=ToolConnectionScope.TEAM,
            secrets=secrets,
            created_by_id=tool.created_by_id,
        )
        tool.credentials = credentials
        tool.http_config = http_config
        tool.mcp_config = mcp_config
        tool.database_config = database_config
        _merge_connection_fields(tool, set(secrets))
        if (tool.identity_policy or "none") == "none":
            tool.identity_policy = "team_only"
        await tool.save()
    return str(connection.id)


def _global_config_remediation(config: ToolConfig) -> str:
    return (
        f"Global ToolConfig {config.id} ({config.tool_name!r}) has no team. "
        "Global builtin credentials are unsupported because they would silently "
        "narrow to one team. Assign it explicitly and rerun:\n"
        "  python -m app.core.tool_secret_migration "
        f"--tool-name {config.tool_name} --target-team <team-uuid>"
    )


async def _migrate_tool_config(config: ToolConfig) -> tuple[str, str | None] | None:
    # Site web search remains governed by the dedicated site search settings;
    # legacy rows are never read by the builtin path, so the row is retained as
    # the site configuration store and no connection is fabricated for it.
    if config.tool_name == "web_search":
        return None

    # A row with no non-empty string secret is dead configuration. Removing it
    # before the global-team guard lets empty legacy rows clean up instead of
    # blocking startup.
    has_secret = False
    for name, value in dict(config.credentials or {}).items():
        if not isinstance(value, str):
            raise LegacySecretMigrationError(
                f"tool_config {config.id} ({config.tool_name}): "
                f"value for {name!r} is not a string"
            )
        if value:
            has_secret = True
    if not has_secret:
        async with in_transaction() as conn:
            await config.delete(using_db=conn)
        return None

    if config.team_id is None:
        raise LegacySecretMigrationError(_global_config_remediation(config))
    return await _migrate_tool_config_to_team(config, config.team_id)


async def _migrate_tool_config_to_team(
    config: ToolConfig, team_id: UUID
) -> tuple[str, str | None] | None:
    credentials = dict(config.credentials or {})
    secrets: dict[str, str] = {}
    declared: set[str] = set()
    for name, value in credentials.items():
        _add_secret(
            secrets,
            declared,
            name,
            value,
            source=f"tool_config {config.id} ({config.tool_name})",
        )
    if not secrets:
        # Nothing secret survives; the row is dead configuration and must not
        # remain readable after the CRUD removal.
        async with in_transaction() as conn:
            await config.delete(using_db=conn)
        return None

    name = f"Migrated {config.tool_name}"[:100]

    from app.schemas.response import BusinessError, ResponseCode
    from app.services.builtin_tools import get_builtin_definition

    try:
        definition = await get_builtin_definition(team_id, config.tool_name)
    except BusinessError as exc:
        if int(exc.code) == int(ResponseCode.NOT_FOUND):
            # Stale/unknown builtin key: keep the encrypted TEAM connection so
            # no secret is dropped, but execution stays blocked until an admin
            # configures a registered definition.
            async with in_transaction() as conn:
                connection = await _upsert_connection(
                    tool_id=None,
                    team_id=team_id,
                    builtin_tool_key=config.tool_name,
                    name=name,
                    scope=ToolConnectionScope.TEAM,
                    secrets=secrets,
                    created_by_id=None,
                )
                await config.delete(using_db=conn)
            logger.warning(
                "Legacy ToolConfig %s references unknown builtin %r; "
                "encrypted connection retained without a definition",
                config.id,
                config.tool_name,
            )
            return str(connection.id), None
        raise LegacySecretMigrationError(
            f"cannot materialize builtin definition for {config.tool_name!r}: "
            f"{exc.msg_key or exc.code}"
        ) from exc

    async with in_transaction() as conn:
        connection = await _upsert_connection(
            tool_id=definition.id,
            team_id=team_id,
            builtin_tool_key=None,
            name=name,
            scope=ToolConnectionScope.TEAM,
            secrets=secrets,
            created_by_id=None,
            legacy_builtin_key=config.tool_name,
        )
        _merge_connection_fields(definition, set(secrets))
        if (definition.identity_policy or "none") == "none":
            definition.identity_policy = "team_only"
        await definition.save(using_db=conn)
        await config.delete(using_db=conn)

    return str(connection.id), str(definition.id)


async def _bind_saved_entrypoints(
    binding_by_team: dict[UUID, dict[tuple[str, str], str]],
) -> tuple[int, int]:
    """Pin explicit migrated connections into saved Agent/Workflow configs.

    Only entries that do not already declare a connection are touched. No
    personal ownership or team default is inferred, and historical
    ``WorkflowVersion`` snapshots are never mutated.
    """
    from app.models.agent import Agent
    from app.models.workflow import Workflow

    agent_updates = 0
    workflow_updates = 0

    for agent in await Agent.all():
        table = binding_by_team.get(agent.team_id)
        if not table:
            continue
        configs = list(agent.tools_config or [])
        changed = False
        for entry in configs:
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            if entry_type == "builtin":
                key = ("builtin", str(entry.get("name") or ""))
            elif entry_type in {"mcp", "custom"}:
                tool_id = entry.get("server_id") or entry.get("tool_id")
                key = ("tool", str(tool_id or ""))
            else:
                continue
            connection_id = table.get(key)
            if not connection_id or entry.get("connection_id"):
                continue
            entry["connection_id"] = connection_id
            entry["connection_mode"] = "team"
            changed = True
        if changed:
            await Agent.filter(id=agent.id).update(tools_config=configs)
            agent_updates += 1

    for workflow in await Workflow.all():
        table = binding_by_team.get(workflow.team_id)
        if not table:
            continue
        definition = dict(workflow.definition or {})
        nodes = definition.get("nodes") or []
        changed = False
        for node in nodes:
            if not isinstance(node, dict):
                continue
            data = node.get("data") or {}
            config = data.get("toolConfig")
            if not isinstance(config, dict):
                config = data.get("config")
            if not isinstance(config, dict):
                continue
            tool_type = config.get("toolType") or config.get("tool_type")
            if tool_type == "builtin":
                key = (
                    "builtin",
                    str(config.get("toolName") or config.get("tool_name") or ""),
                )
            else:
                node_tool_id = config.get("toolId") or config.get("tool_id")
                key = ("tool", str(node_tool_id or ""))
            connection_id = table.get(key)
            if not connection_id:
                continue
            if config.get("connectionId") or config.get("connection_id"):
                continue
            config["connectionMode"] = "team"
            config["connectionId"] = connection_id
            changed = True
        if changed:
            # Current definition only; published version snapshots are history
            # and running workflows load the current definition.
            await Workflow.filter(id=workflow.id).update(definition=definition)
            workflow_updates += 1

    return agent_updates, workflow_updates


async def migrate_legacy_tool_secrets() -> dict[str, str]:
    """Migrate Tool/ToolConfig secrets; raises if data would be lost.

    Returns a mapping (``tool:<id>`` / ``builtin:<name>:<team|site>``) to the
    migrated connection id so the parent cutover can pin explicit bindings.
    """
    mapping: dict[str, str] = {}
    migration_bindings: dict[UUID, dict[tuple[str, str], str]] = {}
    migrated = 0

    def remember(team_id: UUID | None, key: tuple[str, str], connection_id: str):
        if team_id is None:
            return
        migration_bindings.setdefault(team_id, {})[key] = connection_id

    for tool in await Tool.all():
        connection_id = await _migrate_tool(tool)
        if connection_id:
            mapping[f"tool:{tool.id}"] = connection_id
            remember(tool.team_id, ("tool", str(tool.id)), connection_id)
            migrated += 1

    for config in await ToolConfig.all():
        result = await _migrate_tool_config(config)
        if result is None:
            continue
        connection_id, definition_id = result
        scope_key = str(config.team_id) if config.team_id else "site"
        mapping[f"builtin:{config.tool_name}:{scope_key}"] = connection_id
        if definition_id:
            mapping[f"tool:{definition_id}"] = connection_id
        remember(config.team_id, ("builtin", config.tool_name), connection_id)
        if definition_id:
            remember(config.team_id, ("tool", definition_id), connection_id)
        migrated += 1

    agent_updates, workflow_updates = await _bind_saved_entrypoints(migration_bindings)
    if migrated:
        logger.info(
            "Migrated %s legacy tool credential sets into encrypted connections",
            migrated,
        )
        logger.info("Legacy tool connection mapping: %s", mapping)
    if agent_updates or workflow_updates:
        logger.info(
            "Pinned migrated connections into %s Agent configs and %s workflow definitions",
            agent_updates,
            workflow_updates,
        )
    return mapping


async def migrate_global_tool_config(
    tool_name: str, target_team_id: UUID
) -> str | None:
    """Assign one global legacy config to an explicitly chosen team.

    The operator must name the team: a global row has no team of its own, and
    inferring one would silently change who can use the credential. The row is
    deleted only after the team connection commits.
    """
    if tool_name == "web_search":
        raise LegacySecretMigrationError(
            "web_search is site-owned; configure it under admin web search "
            "settings instead of migrating it to a team"
        )
    from app.models.user import Team

    config = await ToolConfig.filter(tool_name=tool_name, team_id__isnull=True).first()
    if config is None:
        raise LegacySecretMigrationError(
            f"no global ToolConfig rows found for {tool_name!r}"
        )
    if await Team.filter(id=target_team_id).first() is None:
        raise LegacySecretMigrationError(f"target team {target_team_id} does not exist")
    result = await _migrate_tool_config_to_team(config, target_team_id)
    if result is None:
        return None
    return result[0]


def main(argv: list[str] | None = None) -> int:
    import argparse
    import asyncio

    from app.core.config import settings

    parser = argparse.ArgumentParser(
        description=(
            "Assign one global legacy ToolConfig row to an explicit team and "
            "rewrite it as an encrypted team connection"
        )
    )
    parser.add_argument("--tool-name", required=True)
    parser.add_argument("--target-team", required=True, type=UUID)
    args = parser.parse_args(argv)

    async def _run() -> str | None:
        from tortoise import Tortoise

        await Tortoise.init(
            db_url=settings.DATABASE_URL
            or (
                f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            ),
            modules={"models": ["app.models"]},
        )
        try:
            return await migrate_global_tool_config(args.tool_name, args.target_team)
        finally:
            await Tortoise.close_connections()

    try:
        connection_id = asyncio.run(_run())
    except LegacySecretMigrationError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "tool_name": args.tool_name,
                "target_team": str(args.target_team),
                "connection_id": connection_id,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "LegacySecretMigrationError",
    "migrate_global_tool_config",
    "migrate_legacy_tool_secrets",
]


if __name__ == "__main__":
    raise SystemExit(main())

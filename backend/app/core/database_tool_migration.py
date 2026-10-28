"""One-way cutover: custom database tools become builtin database tools.

Database querying used to be a ``custom`` tool with ``custom_type=database``
and a plaintext ``database_config`` on the definition. It is now four builtin
tools (``postgresql_query``, ``mysql_query``, ``redis_query``,
``mongodb_query``) whose engine parameters and credentials live in encrypted
``ToolConnection`` rows.

Migration rules (all idempotent, credentials preserved):

* Every legacy database definition keeps its row: ``custom_type`` is cleared,
  ``type`` becomes ``builtin``, and the row is disabled with its original name.
  Nothing is deleted, so ``ToolExecution.tool_id`` (audit history) and any
  external reference to the old id stay valid; the retired row is not part of
  the builtin registry and can never execute.
* One canonical builtin definition per ``(team, engine)`` is created (or
  reused). Its approval policy is the strict merge of every merged legacy
  policy, so approval can only become more restrictive.
* Existing connections bound to the legacy definition keep their id, scope,
  owner and name; they are re-keyed to the canonical builtin key. Their
  decrypted secrets are merged with the legacy config (``{{password}}`` /
  ``{{url}}`` placeholders are resolved from the connection itself). Missing
  credentials abort startup instead of producing a silently empty connection.
* Live Agent and Workflow definitions and every ``WorkflowVersion`` snapshot
  are rewritten to the canonical builtin name and bound to the migrated
  connection when the choice is unambiguous. Ambiguous (several unbound
  connections) references stay explicitly unbound and are reported.
* Explicit defaults are preserved. Two connections claiming the default slot
  of the same team+scope+canonical key abort the migration with an actionable
  message instead of silently unsetting one.

The legacy ``tools.database_config`` column is kept for rollback safety; after
migration it is empty on every converted row.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from uuid import UUID

from tortoise.transactions import in_transaction

from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.tool import Tool, ToolType
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
)
from app.schemas.tool import BUILTIN_TOOLS_METADATA
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ToolApprovalPolicy,
)

logger = logging.getLogger(__name__)

ENGINE_BUILTIN_KEYS: dict[str, str] = {
    "postgresql": "postgresql_query",
    "postgres": "postgresql_query",
    "pgsql": "postgresql_query",
    "mysql": "mysql_query",
    "mariadb": "mysql_query",
    "redis": "redis_query",
    "mongodb": "mongodb_query",
    "mongo": "mongodb_query",
}

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_DECISION_RANK = {
    ApprovalDecision.ALLOW: 0,
    ApprovalDecision.REQUIRE_APPROVAL: 1,
    ApprovalDecision.DENY: 2,
}


class DatabaseToolMigrationError(RuntimeError):
    """Raised when a legacy database tool cannot be migrated without loss."""


def engine_builtin_key(db_type: Any) -> str | None:
    return ENGINE_BUILTIN_KEYS.get(str(db_type or "").strip().lower())


def declared_fields(builtin_key: str) -> list[str]:
    metadata = BUILTIN_TOOLS_METADATA.get(builtin_key, {})
    fields = metadata.get("connection_fields") or metadata.get("config_fields") or []
    names: list[str] = []
    for item in fields:
        name = item if isinstance(item, str) else item.get("name")
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return names


def merge_connection_config(
    database_config: Mapping[str, Any] | None,
    connection_secrets: Mapping[str, str] | None,
    builtin_key: str,
) -> dict[str, str]:
    """Return the complete connection mapping for one migrated connection.

    ``database_config`` may still contain the placeholders written by the
    legacy secret migration (``password: "{{password}}"``). Those placeholders
    resolve against the connection's own secrets; a missing value is fatal so
    a migrated tool can never silently lose its password or URL.
    """
    secrets = {
        str(key): str(value) for key, value in (connection_secrets or {}).items()
    }
    declared = set(declared_fields(builtin_key))

    # Pre-validate every referenced field before producing values, so an
    # unresolvable placeholder fails with one actionable error instead of a
    # partially substituted mapping.
    for key, value in (database_config or {}).items():
        if key == "db_type" or value is None or value == "" or key not in declared:
            continue
        for field in _PLACEHOLDER.findall(str(value)):
            if field not in secrets:
                raise DatabaseToolMigrationError(
                    f"database_config.{key} references connection field "
                    f"{field!r} that is not stored on the migrated connection "
                    "for the same tool"
                )

    merged: dict[str, str] = {}
    for key, value in (database_config or {}).items():
        if key == "db_type" or value is None or value == "":
            continue
        if key not in declared:
            # The legacy API already validated its own keys; anything else was
            # never consumed by an engine.
            continue
        if isinstance(value, bool):
            merged[key] = "true" if value else "false"
            continue
        merged[key] = _PLACEHOLDER.sub(
            lambda match: secrets[match.group(1)], str(value)
        )

    for key, value in secrets.items():
        if key in declared:
            merged.setdefault(key, value)

    return merged


def _policy(value: Any) -> ToolApprovalPolicy | None:
    if not isinstance(value, Mapping):
        return None
    if not value:
        # An empty policy was evaluated as the fail-closed default.
        return ToolApprovalPolicy()
    return ToolApprovalPolicy.model_validate(value)


def _flatten(policy: ToolApprovalPolicy) -> ToolApprovalPolicy:
    """Fold every operation override into the default decision and gates.

    An override replaces its layer's default for that operation, so two
    policies could otherwise combine as "allow override here" + "deny default
    there" and stay allow for the key. Folding into the default before the
    cross-policy merge can only add restrictions.
    """
    decision = policy.default_decision
    gates: tuple[ApprovalGate, ...] = tuple(policy.gates)
    for override in policy.operation_overrides.values():
        decision = max(
            (decision, override.default_decision), key=lambda item: _DECISION_RANK[item]
        )
        gates = _merge_gates(gates, override.gates)
    if decision != ApprovalDecision.REQUIRE_APPROVAL:
        # Gates on allow/deny are malformed and ignored by the evaluator;
        # carrying them would only add noise to the migrated policy.
        gates = ()
    return ToolApprovalPolicy(default_decision=decision, gates=gates)


def flatten_policy(value: Any) -> dict[str, Any]:
    """Return a policy whose operation overrides are folded into the default."""
    policy = _policy(value)
    if policy is None:
        return {}
    return _flatten(policy).model_dump(mode="json")


def merge_approval_policies(values: Iterable[Any]) -> dict[str, Any]:
    """Strictly merge policies: the result cannot be more permissive.

    Every input is flattened to a single default decision/gate set first (see
    ``_flatten``); the result therefore carries no operation overrides. This is
    the conservative choice for a migration and is documented as such.
    """
    merged: ToolApprovalPolicy | None = None
    for value in values:
        policy = _policy(value)
        if policy is None:
            continue
        flattened = _flatten(policy)
        if merged is None:
            merged = flattened
            continue
        decision = max(
            (merged.default_decision, flattened.default_decision),
            key=lambda item: _DECISION_RANK[item],
        )
        gates = (
            _merge_gates(merged.gates, flattened.gates)
            if decision == ApprovalDecision.REQUIRE_APPROVAL
            else ()
        )
        merged = ToolApprovalPolicy(default_decision=decision, gates=gates)
    return (merged or ToolApprovalPolicy()).model_dump(mode="json")


def _merge_gates(
    left: Sequence[ApprovalGate], right: Sequence[ApprovalGate]
) -> tuple[ApprovalGate, ...]:
    merged: list[ApprovalGate] = list(left)
    indexes = {
        (gate.kind, tuple(gate.user_ids), tuple(gate.roles)): index
        for index, gate in enumerate(merged)
    }
    for gate in right:
        signature = (gate.kind, tuple(gate.user_ids), tuple(gate.roles))
        index = indexes.get(signature)
        if index is None:
            indexes[signature] = len(merged)
            merged.append(gate)
            continue
        existing = merged[index]
        if existing.allow_self_approval and not gate.allow_self_approval:
            merged[index] = ApprovalGate(
                kind=existing.kind,
                user_ids=existing.user_ids,
                roles=existing.roles,
                allow_self_approval=False,
            )
    return tuple(merged)


def _binding_mode(connection: ToolConnection) -> str:
    return "personal" if connection.scope == ToolConnectionScope.USER else "team"


def rewrite_agent_tools_config(
    tools_config: Sequence[Any] | None,
    legacy_id: str,
    canonical_key: str,
    connection: ToolConnection | None,
) -> tuple[list[Any], bool]:
    """Point one Agent entry at the canonical builtin definition."""
    entries = list(tools_config or [])
    changed = False
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        entry_type = entry.get("type")
        if entry_type not in {"custom", "mcp"}:
            continue
        if str(entry.get("tool_id") or "") != legacy_id:
            continue
        if entry.get("connection_id"):
            # The legacy entry already chose an identity; keep that explicit
            # choice (the connection id survives the re-keying).
            connection_id = entry.get("connection_id")
            connection_mode = entry.get("connection_mode")
        elif connection is not None:
            connection_id = str(connection.id)
            connection_mode = _binding_mode(connection)
        else:
            connection_id = None
            connection_mode = None
        rewritten = {key: value for key, value in entry.items() if key != "tool_id"}
        rewritten.pop("server_id", None)
        rewritten["type"] = "builtin"
        rewritten["name"] = canonical_key
        if connection_id:
            rewritten["connection_id"] = str(connection_id)
            rewritten["connection_mode"] = connection_mode
        entries[index] = rewritten
        changed = True
    return entries, changed


def rewrite_workflow_definition(
    definition: Mapping[str, Any] | None,
    legacy_id: str,
    canonical_key: str,
    connection: ToolConnection | None,
) -> tuple[dict[str, Any], bool]:
    """Point every tool node of one definition snapshot at the builtin."""
    if not isinstance(definition, Mapping):
        return dict(definition or {}), False
    rewritten = json.loads(json.dumps(definition, default=str))
    changed = False
    for node in rewritten.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        data = node.get("data") or {}
        config = data.get("toolConfig")
        if not isinstance(config, dict):
            config = data.get("config")
        if not isinstance(config, dict):
            continue
        if config.get("toolType") not in {"custom", "mcp"}:
            continue
        if str(config.get("toolId") or config.get("tool_id") or "") != legacy_id:
            continue
        config["toolType"] = "builtin"
        config["toolName"] = canonical_key
        config.pop("toolId", None)
        config.pop("tool_id", None)
        selected_id = config.get("connectionId") or config.get("connection_id")
        selected_mode = config.get("connectionMode") or config.get("connection_mode")
        config.pop("connection_id", None)
        config.pop("connection_mode", None)
        if selected_id:
            config["connectionId"] = str(selected_id)
            if selected_mode:
                config["connectionMode"] = selected_mode
        elif connection is not None:
            config["connectionId"] = str(connection.id)
            config["connectionMode"] = _binding_mode(connection)
        changed = True
    return rewritten, changed


def default_slot_for(
    *, scope: ToolConnectionScope, team_id: UUID | None, owner_user_id, service_key: str
) -> str:
    from app.services.tool_connections import ToolConnectionService

    return ToolConnectionService._default_slot(
        scope=scope,
        team_id=team_id,
        owner_user_id=owner_user_id,
        service_key=service_key,
    )


async def _require_target_definition(
    team_id: UUID, canonical_key: str, *, using_db=None
) -> Tool:
    """Return the existing canonical builtin row, or create it.

    ``get_builtin_definition`` is the single materialization path, including its
    fail-closed name-collision behavior (a custom/MCP tool already occupying the
    registry name must be resolved by an operator, never shadowed).
    """
    from app.schemas.response import BusinessError
    from app.services.builtin_tools import get_builtin_definition

    existing = (
        await Tool.filter(team_id=team_id, name=canonical_key)
        .using_db(using_db)
        .first()
    )
    if existing is not None and existing.type == ToolType.BUILTIN:
        return existing
    if existing is not None:
        raise DatabaseToolMigrationError(
            f"team {team_id} already has a {existing.type.value} tool named "
            f"{canonical_key!r}; rename it, then restart to finish the database "
            "tool migration"
        )
    try:
        return await get_builtin_definition(team_id, canonical_key, using_db=using_db)
    except BusinessError as exc:
        raise DatabaseToolMigrationError(
            f"cannot materialize builtin {canonical_key!r} for team {team_id}: "
            f"{exc.msg_key or exc.code}"
        ) from exc


def _decrypt(connection: ToolConnection) -> dict[str, str]:
    if not connection.encrypted_config:
        return {}
    try:
        decoded = json.loads(decrypt_tool_secret(connection.encrypted_config))
    except Exception as exc:  # noqa: BLE001 - fail closed on unreadable data
        raise DatabaseToolMigrationError(
            f"connection {connection.id} has unreadable encrypted configuration"
        ) from exc
    if not isinstance(decoded, dict):
        raise DatabaseToolMigrationError(
            f"connection {connection.id} configuration is not a mapping"
        )
    return {str(key): str(value) for key, value in decoded.items()}


async def _migrate_existing_connection(
    connection: ToolConnection,
    *,
    canonical_key: str,
    config: dict[str, str],
    tx=None,
) -> ToolConnection:
    service_key = f"builtin:{canonical_key}"
    slot = None
    if connection.is_default:
        slot = default_slot_for(
            scope=connection.scope,
            team_id=connection.team_id,
            owner_user_id=connection.owner_user_id,
            service_key=service_key,
        )
        clash = (
            await ToolConnection.filter(default_slot=slot)
            .using_db(tx)
            .exclude(id=connection.id)
            .first()
        )
        if clash is not None:
            raise DatabaseToolMigrationError(
                f"connections {connection.id} and {clash.id} would both be the "
                f"default for {service_key} in team {connection.team_id}; unset "
                "one default connection and restart"
            )
    connection.tool_id = None
    connection.builtin_tool_key = canonical_key
    connection.encrypted_config = encrypt_tool_secret(
        json.dumps(config, sort_keys=True, separators=(",", ":"))
    )
    connection.secret_fields = sorted(config)
    connection.secret_version += 1
    connection.default_slot = slot
    connection.validate_invariants()
    await connection.save(using_db=tx)
    return connection


async def _create_connection(
    *,
    legacy: Tool,
    canonical_key: str,
    config: dict[str, str],
    tx=None,
) -> ToolConnection:
    # A PRIVATE legacy tool was creator-only. Preserve that audience instead of
    # widening its credentials to every team member through a TEAM connection.
    # A private row without a creator (deleted user) has no one to own a personal
    # connection; it stays team-scoped and is reported for operator review.
    private = getattr(legacy, "visibility", None) == "private"
    owner_user_id = legacy.created_by_id if private else None
    if private and owner_user_id is None:
        logger.warning(
            "Private database tool %s (%s) has no creator; its migrated "
            "connection is team-scoped",
            legacy.name,
            legacy.id,
        )
    personal = private and owner_user_id is not None
    connection = ToolConnection(
        team_id=legacy.team_id,
        tool_id=None,
        builtin_tool_key=canonical_key,
        scope=ToolConnectionScope.USER if personal else ToolConnectionScope.TEAM,
        owner_user_id=owner_user_id,
        name=f"Migrated {legacy.name}"[:100],
        account_label=None,
        encrypted_config=encrypt_tool_secret(
            json.dumps(config, sort_keys=True, separators=(",", ":"))
        ),
        secret_fields=sorted(config),
        secret_version=1,
        is_default=False,
        default_slot=None,
        created_by_id=legacy.created_by_id,
    )
    connection.validate_invariants()
    await connection.save(using_db=tx)
    return connection


def _primary_connection(
    connections: list[ToolConnection],
) -> ToolConnection | None:
    """Bind only when the legacy definition owned exactly one identity."""
    return connections[0] if len(connections) == 1 else None


def _row_id(row: Any) -> UUID:
    if isinstance(row, Mapping):
        raw = row.get("id")
    elif hasattr(row, "keys"):
        raw = row["id"]
    elif isinstance(row, (tuple, list)):
        raw = row[0]
    else:
        raw = getattr(row, "id", row)
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise DatabaseToolMigrationError(
            f"cannot read the id of a legacy database tool row ({raw!r})"
        ) from exc


async def _load_legacy_tools(tx) -> list[Tool]:
    """Load every unconverted database definition inside the migration tx.

    ``CustomToolType`` no longer contains ``database``, so the retired value is
    cleared in bulk before any row is read. The ids are captured first: an
    empty legacy config must still fail loudly instead of silently becoming an
    orphaned custom tool. Rows cleared by an interrupted attempt are found by
    their non-empty ``database_config`` (only database tools ever wrote it).
    """
    _, rows = await tx.execute_query(
        "SELECT id FROM tools WHERE custom_type = 'database'"
    )
    legacy_ids = {str(_row_id(row)) for row in rows}
    await tx.execute_query(
        "UPDATE tools SET custom_type = NULL WHERE custom_type = 'database'"
    )
    candidates = await Tool.filter(
        type=ToolType.CUSTOM, custom_type__isnull=True
    ).using_db(tx)
    by_id = {str(tool.id): tool for tool in candidates}
    loaded: list[Tool] = []
    for legacy_id in sorted(legacy_ids):
        tool = by_id.get(legacy_id)
        if tool is not None:
            loaded.append(tool)
    for tool in candidates:
        if str(tool.id) in legacy_ids:
            continue
        if tool.database_config:
            loaded.append(tool)
    return loaded


async def _migrate_one(
    tx,
    legacy: Tool,
    *,
    bindings: dict[str, tuple[str, ToolConnection | None]],
    counters: dict[str, int],
) -> None:
    legacy_id = legacy.id
    database_config = dict(legacy.database_config or {})
    canonical_key = engine_builtin_key(database_config.get("db_type"))
    if canonical_key is None:
        raise DatabaseToolMigrationError(
            f"database tool {legacy.name!r} ({legacy.id}) has unsupported db_type "
            f"{database_config.get('db_type')!r}; supported engines are "
            f"{sorted(set(ENGINE_BUILTIN_KEYS))}"
        )
    if legacy.team_id is None:
        raise DatabaseToolMigrationError(
            f"database tool {legacy.name!r} ({legacy.id}) has no owning team"
        )

    is_target = legacy.name == canonical_key
    target = (
        legacy
        if is_target
        else await _require_target_definition(
            legacy.team_id, canonical_key, using_db=tx
        )
    )

    bound = (
        await ToolConnection.filter(tool_id=legacy_id)
        .using_db(tx)
        .order_by("created_at")
    )
    raw_credentials = {
        str(key): str(value)
        for key, value in (legacy.credentials or {}).items()
        if value is not None and value != ""
    }
    migrated: list[ToolConnection] = []
    for connection in bound:
        # The connection is authoritative; raw definition credentials only
        # fill fields it does not carry yet (partial legacy secret migration).
        secrets = {**raw_credentials, **_decrypt(connection)}
        config = merge_connection_config(database_config, secrets, canonical_key)
        _require_complete_config(connection, config)
        migrated.append(
            await _migrate_existing_connection(
                connection,
                canonical_key=canonical_key,
                config=config,
                tx=tx,
            )
        )
    if not migrated:
        connection = await _create_connection(
            legacy=legacy,
            canonical_key=canonical_key,
            config=_merge_for_new_connection(
                database_config, canonical_key, legacy, raw_credentials
            ),
            tx=tx,
        )
        migrated.append(connection)
        counters["connections_created"] += 1
    counters["connections_migrated"] += len(migrated)

    # Strict merge: approval can only become more restrictive. The canonical
    # row may already carry a policy (existing builtin, or the legacy row itself
    # when its name is the canonical key).
    current_target = await Tool.filter(id=target.id).using_db(tx).first()
    merged_policy = merge_approval_policies(
        [
            current_target.approval_policy if current_target else None,
            None if is_target else flatten_policy(legacy.approval_policy),
        ]
    )
    # Two definitions merge into one: a previously disabled legacy tool must
    # not become reachable because the target happened to be enabled. The
    # definition version bump invalidates approvals pinned to the old policy.
    target_enabled = bool(current_target.is_enabled) if current_target else True
    merged_enabled = target_enabled and bool(legacy.is_enabled)
    merged_version = int(getattr(current_target, "definition_version", 1) or 1) + 1

    if is_target:
        from app.llm.tools import tool_registry

        info = tool_registry.get_tool(canonical_key)
        metadata = BUILTIN_TOOLS_METADATA.get(canonical_key, {})
        legacy.type = ToolType.BUILTIN
        legacy.custom_type = None
        legacy.display_name = canonical_key
        if info is not None:
            legacy.description = info.description
            legacy.parameters = [
                parameter.model_dump() for parameter in info.parameters
            ]
        legacy.category = str(
            getattr(metadata.get("category"), "value", metadata.get("category"))
        )
        legacy.icon = metadata.get("icon")
        legacy.definition_version = merged_version
        legacy.identity_policy = "selectable"
        legacy.connection_fields = [
            dict(field) for field in metadata.get("connection_fields", [])
        ]
        legacy.approval_policy = merged_policy
        legacy.database_config = {}
        legacy.credentials = {}
        await legacy.save(using_db=tx)
    else:
        # Retired historical record: keeps its id, name and audit history,
        # never dispatches (not a registry name) and stays disabled.
        await (
            Tool.filter(id=legacy_id)
            .using_db(tx)
            .update(
                type=ToolType.BUILTIN,
                custom_type=None,
                is_enabled=False,
                database_config={},
                credentials={},
            )
        )
        await (
            Tool.filter(id=target.id)
            .using_db(tx)
            .update(
                approval_policy=merged_policy,
                is_enabled=merged_enabled,
                definition_version=merged_version,
            )
        )
        counters["retired"] += 1

    bindings[str(legacy_id)] = (canonical_key, _primary_connection(migrated))
    counters["tools"] += 1
    logger.info(
        "Migrated %s database tool %s (%s) to builtin %s with %d connection(s)",
        legacy.team_id,
        legacy.name,
        legacy.id,
        canonical_key,
        len(migrated),
    )


def _require_complete_config(
    connection: ToolConnection, config: dict[str, str]
) -> None:
    if not config.get("host") and not (config.get("url") or config.get("uri")):
        raise DatabaseToolMigrationError(
            f"connection {connection.id} for database tool migration has no host "
            "or URL; refusing to create an empty identity"
        )


def _merge_for_new_connection(
    database_config: Mapping[str, Any],
    canonical_key: str,
    legacy: Tool,
    legacy_credentials: Mapping[str, str],
) -> dict[str, str]:
    config = merge_connection_config(database_config, legacy_credentials, canonical_key)
    if not config.get("host") and not (config.get("url") or config.get("uri")):
        raise DatabaseToolMigrationError(
            f"database tool {legacy.name!r} ({legacy.id}) has no host or URL to "
            "preserve"
        )
    return config


async def _rewrite_references(
    tx,
    bindings: dict[str, tuple[str, ToolConnection | None]],
    counters: dict[str, int],
) -> None:
    if not bindings:
        return
    from app.models.agent import Agent
    from app.models.workflow import Workflow, WorkflowVersion

    ambiguous: list[str] = []
    converted_keys = {key for key, _ in bindings.values()}

    for agent in await Agent.all().using_db(tx):
        configs = list(agent.tools_config or [])
        changed = False
        for legacy_id, (canonical_key, connection) in bindings.items():
            if connection is None:
                # Report only when the agent actually referenced this tool.
                for entry in configs:
                    if (
                        isinstance(entry, dict)
                        and str(entry.get("tool_id") or "") == legacy_id
                        and not entry.get("connection_id")
                    ):
                        ambiguous.append(f"agent {agent.id} ({agent.name})")
            configs, entry_changed = rewrite_agent_tools_config(
                configs, legacy_id, canonical_key, connection
            )
            changed = changed or entry_changed

        # One builtin definition can be attached only once per Agent (entries
        # are keyed by the model-facing tool name). This catches both two
        # migrated databases and a migrated database plus a pre-existing
        # canonical entry: fail instead of picking or dropping a connection.
        per_key: dict[str, int] = {}
        for entry in configs:
            if (
                isinstance(entry, dict)
                and entry.get("type") == "builtin"
                and entry.get("name") in converted_keys
            ):
                name = str(entry["name"])
                per_key[name] = per_key.get(name, 0) + 1
        duplicates = {key: count for key, count in per_key.items() if count > 1}
        if duplicates:
            raise DatabaseToolMigrationError(
                f"agent {agent.name!r} ({agent.id}) would attach more than one "
                f"database tool for the same builtin ({duplicates}); remove the "
                "duplicate attachment, then restart the migration"
            )

        if changed:
            await Agent.filter(id=agent.id).using_db(tx).update(tools_config=configs)
            counters["agents"] += 1

    for workflow in await Workflow.all().using_db(tx):
        definition, changed = _rewrite_definition(workflow.definition, bindings)
        if changed:
            await (
                Workflow.filter(id=workflow.id)
                .using_db(tx)
                .update(definition=definition)
            )
            counters["workflows"] += 1

    # Version snapshots must stay runnable/restorable after the cutover.
    for version in await WorkflowVersion.all().using_db(tx):
        definition, changed = _rewrite_definition(version.definition, bindings)
        if changed:
            await (
                WorkflowVersion.filter(id=version.id)
                .using_db(tx)
                .update(definition=definition)
            )
            counters["versions"] += 1

    if ambiguous:
        logger.warning(
            "Database tool migration left %d Agent tool reference(s) unbound "
            "because the definition owned several connections; select a "
            "connection explicitly: %s",
            len(ambiguous),
            ", ".join(sorted(set(ambiguous))),
        )


def _rewrite_definition(
    definition: Mapping[str, Any] | None,
    bindings: dict[str, tuple[str, ToolConnection | None]],
) -> tuple[dict[str, Any], bool]:
    current = dict(definition or {})
    changed = False
    for legacy_id, (canonical_key, connection) in bindings.items():
        current, item_changed = rewrite_workflow_definition(
            current, legacy_id, canonical_key, connection
        )
        changed = changed or item_changed
    return current, changed


_MIGRATION_LOCK_KEY = 764_219_033  # arbitrary but stable PostgreSQL advisory key


async def _acquire_migration_lock(tx) -> None:
    """Serialize concurrent API/worker startups on PostgreSQL.

    The whole cutover runs in one transaction; an xact-scoped advisory lock is
    released by commit/rollback. Other backends (SQLite tests) serialize writes
    on their own.
    """
    from tortoise import Tortoise

    capabilities = getattr(Tortoise.get_connection("default"), "capabilities", None)
    if getattr(capabilities, "dialect", None) == "postgres":
        await tx.execute_query(
            "SELECT pg_advisory_xact_lock($1)", [_MIGRATION_LOCK_KEY]
        )


async def migrate_custom_database_tools() -> dict[str, int]:
    """Run the cutover atomically. Raises ``DatabaseToolMigrationError`` on loss."""
    from app.services.builtin_tools import ensure_builtin_registry

    ensure_builtin_registry()
    counters = {
        "tools": 0,
        "connections_created": 0,
        "connections_migrated": 0,
        "retired": 0,
        "agents": 0,
        "workflows": 0,
        "versions": 0,
    }

    # One transaction for definitions, connections and reference rewrites: a
    # failure on any later row rolls the whole cutover back and the next
    # startup retries from the untouched legacy rows.
    async with in_transaction() as tx:
        await _acquire_migration_lock(tx)
        legacy_tools = await _load_legacy_tools(tx)
        if not legacy_tools:
            return counters
        bindings: dict[str, tuple[str, ToolConnection | None]] = {}
        for legacy in legacy_tools:
            await _migrate_one(tx, legacy, bindings=bindings, counters=counters)
        await _rewrite_references(tx, bindings, counters)

    logger.info("Database tool cutover finished: %s", counters)
    return counters


__all__ = [
    "DatabaseToolMigrationError",
    "ENGINE_BUILTIN_KEYS",
    "declared_fields",
    "engine_builtin_key",
    "merge_approval_policies",
    "merge_connection_config",
    "migrate_custom_database_tools",
    "rewrite_agent_tools_config",
    "rewrite_workflow_definition",
]

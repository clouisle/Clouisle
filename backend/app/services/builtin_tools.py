"""Stable per-team Tool records for registry-defined builtin tools.

Builtin execution must flow through the same connection/approval boundary as
stored tools, which requires a real ``Tool`` row (``ToolExecution.tool_id`` is
mandatory). Definitions are materialized lazily and never reuse a custom/MCP
tool name: a collision fails closed instead of shadowing user content.

Approval defaults to allow for materialized builtin definitions. Confirmation
is opt-in and explicit: the Agent's ``require_approval`` switch or the tool's
own stored policy is applied by the execution boundary for every call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from tortoise.exceptions import IntegrityError, OperationalError

from app.llm.tools import tool_registry
from app.llm.tools.registry import ToolInfo
from app.models.tool import Tool, ToolCategory, ToolType, ToolVisibility
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import BUILTIN_TOOLS_METADATA
from app.schemas.tool_approval import ApprovalDecision, ToolApprovalPolicy

# Model-facing internal tools implemented directly by chat_tools/agent paths,
# not present in the registry. They still need a real Tool row for the unified
# approval boundary. Approval is fail-closed except for the explicit read-only
# set below, whose implementations were audited for persistence/network effects.
_INTERNAL_TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_assets": "List assets available to the current conversation or run",
    "inspect_asset": "Inspect asset metadata",
    "read_asset": "Read extracted asset text",
    "search_asset": "Search asset text",
    "materialize_asset": "Materialize an asset for model consumption",
    "view_asset": "View an asset",
    "knowledge_search": "Search the agent's knowledge bases",
    "create_memory_entity": "Create a memory entity",
    "create_memory_relation": "Create a memory relation",
    "update_memory_entity": "Update a memory entity",
    "search_memory": "Search memory",
    "get_memory_subgraph": "Read a memory subgraph",
    "file_download": "Download a file",
    "read_tool_result": "Recover a persisted tool result from this conversation",
}

#: Internal chat/agent tools default to allow; an Agent's ``require_approval``
#: switch or the tool's own stored policy opts into confirmation explicitly,
#: and that requirement is applied by the execution boundary, not inferred here.


def supported_internal_tool_keys() -> tuple[str, ...]:
    """Names that can be materialized without a registry entry."""
    return tuple(sorted(_INTERNAL_TOOL_DESCRIPTIONS))


def ensure_builtin_registry() -> None:
    """Builtin registration is idempotent and required in worker processes."""
    from app.llm.tools.builtin import register_all_builtin_tools

    if tool_registry.get_tool("get_current_time") is None:
        register_all_builtin_tools()


def _approval_policy() -> dict:
    return ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW).model_dump(
        mode="json"
    )


def _internal_approval_policy() -> dict:
    return ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW).model_dump(
        mode="json"
    )


async def _refresh_internal_approval(
    definition: Tool, name: str, *, using_db=None
) -> Tool:
    """Upgrade a legacy empty synthetic policy without touching admin choices."""
    policy = _internal_approval_policy()
    if policy and not definition.approval_policy:
        await (
            Tool.filter(id=definition.id)
            .using_db(using_db)
            .update(approval_policy=policy)
        )
        definition.approval_policy = policy
    return definition


def _parameters(info) -> list[dict]:
    return [parameter.model_dump() for parameter in info.parameters]


def derive_builtin_identity(info: ToolInfo) -> tuple[str, list[dict]]:
    """Return (identity_policy, connection_fields) for a registry builtin.

    Credential-requiring builtins must never persist ``identity_policy=none``
    or the manager cannot configure a connection. Metadata may live on the
    ToolInfo (``requires_config``/``config_fields``) or in
    ``BUILTIN_TOOLS_METADATA``; either source is honored. ``team_only`` stays
    the default; a builtin that supports both personal and team identities
    opts in explicitly with ``identity_policy: selectable``.
    """
    metadata = BUILTIN_TOOLS_METADATA.get(info.name, {})
    requires_config = bool(
        getattr(info, "requires_config", False)
        or metadata.get("requires_config", False)
    )
    if not requires_config:
        return "none", []

    raw_policy = metadata.get("identity_policy") or "team_only"
    identity_policy = (
        raw_policy
        if raw_policy in {"team_only", "personal_only", "selectable"}
        else "team_only"
    )

    raw_fields = getattr(info, "connection_fields", None)
    if raw_fields is None:
        raw_fields = metadata.get("connection_fields")
    if raw_fields is None:
        raw_fields = getattr(info, "config_fields", None)
    if raw_fields is None:
        raw_fields = metadata.get("config_fields") or []

    fields: list[dict] = []
    seen: set[str] = set()
    for item in raw_fields:
        if isinstance(item, str):
            field = {
                "name": item,
                "label": item,
                "required": True,
                "secret": True,
            }
        elif isinstance(item, Mapping):
            name = item.get("name")
            if not isinstance(name, str) or not name or name in seen:
                continue
            field = {
                "name": name,
                "label": str(item.get("label") or name),
                "required": bool(item.get("required", True)),
                "secret": bool(item.get("secret", True)),
            }
            for key in ("label_key", "input_type", "default", "options", "input_mode"):
                if key in item:
                    field[key] = item[key]
        else:
            continue
        if field["name"] in seen:
            continue
        seen.add(field["name"])
        fields.append(field)
    return identity_policy, fields


def _merge_identity_fields(
    existing_fields: list, new_fields: list[dict]
) -> tuple[list[dict], bool]:
    merged = [dict(item) for item in (existing_fields or []) if isinstance(item, dict)]
    names = {item.get("name") for item in merged}
    changed = False
    for field in new_fields:
        if field["name"] in names:
            for index, existing in enumerate(merged):
                if existing.get("name") == field["name"] and field.get("label_key"):
                    updated = {**existing, **field}
                    if updated != existing:
                        merged[index] = updated
                        changed = True
            continue
        merged.append(field)
        names.add(field["name"])
        changed = True
    return merged, changed


async def _refresh_registry_identity(
    definition: Tool, info: ToolInfo, *, using_db=None
) -> Tool:
    """Upgrade legacy ``none`` identities when registry metadata requires config."""
    policy, fields = derive_builtin_identity(info)
    if policy == "none":
        return definition
    changed = False
    if (definition.identity_policy or "none") == "none":
        definition.identity_policy = policy
        changed = True
    merged, fields_changed = _merge_identity_fields(
        list(definition.connection_fields or []), fields
    )
    if fields_changed:
        definition.connection_fields = merged
        changed = True
    if changed:
        await (
            Tool.filter(id=definition.id)
            .using_db(using_db)
            .update(
                identity_policy=definition.identity_policy,
                connection_fields=definition.connection_fields,
            )
        )
    return definition


def extract_builtin_binding(entry: dict) -> dict[str, str | None]:
    """Read an explicitly configured connection binding from a tool entry.

    Accepts both entry-level keys (used by agents) and the nested ``config``
    object for compatibility with older saved definitions.
    """
    config = entry.get("config") if isinstance(entry, dict) else None
    if not isinstance(config, dict):
        config = {}

    def pick(*names: str):
        for name in names:
            value = entry.get(name)
            if value not in (None, ""):
                return value
            value = config.get(name)
            if value not in (None, ""):
                return value
        return None

    return {
        "connection_mode": pick("connection_mode", "connectionMode"),
        "connection_id": pick("connection_id", "connectionId"),
    }


def parse_optional_uuid(value) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        ) from exc


class _Descriptor:
    __slots__ = ("description", "parameters", "definition_version")

    def __init__(
        self, description: str, parameters: list[dict], definition_version: int
    ) -> None:
        self.description = description
        self.parameters = parameters
        self.definition_version = definition_version


def _coerce_descriptor(name: str, descriptor: Any) -> _Descriptor:
    if isinstance(descriptor, ToolInfo):
        return _Descriptor(
            descriptor.description,
            [parameter.model_dump() for parameter in descriptor.parameters],
            1,
        )
    if not isinstance(descriptor, Mapping):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        )
    if descriptor.get("name") != name:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        )
    description = descriptor.get("description")
    parameters = descriptor.get("parameters") or []
    definition_version = descriptor.get("definition_version", 1)
    if not isinstance(description, str) or not description:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        )
    if not isinstance(parameters, list) or any(
        not isinstance(item, dict) for item in parameters
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        )
    if not isinstance(definition_version, int) or definition_version < 1:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_connection_invalid",
            status_code=400,
        )
    return _Descriptor(description, list(parameters), definition_version)


async def _refresh_definition(
    definition: Tool, descriptor: _Descriptor, *, using_db=None
) -> Tool:
    changed = (
        definition.description != descriptor.description
        or list(definition.parameters or []) != descriptor.parameters
        or definition.definition_version != descriptor.definition_version
    )
    if changed:
        await (
            Tool.filter(id=definition.id)
            .using_db(using_db)
            .update(
                description=descriptor.description,
                parameters=descriptor.parameters,
                definition_version=descriptor.definition_version,
            )
        )
        definition.description = descriptor.description
        definition.parameters = descriptor.parameters
        definition.definition_version = descriptor.definition_version
    return definition


async def get_builtin_definition(
    team_id: UUID | None,
    name: str,
    *,
    descriptor: ToolInfo | Mapping | None = None,
    using_db=None,
) -> Tool:
    """Return (and lazily materialize) a stable tool definition for a team.

    Registry/sandbox entries are authoritative and returned as-is. Internal
    chat/agent tools and dynamic ``skill_*`` tools may be materialized from an
    explicit descriptor. Descriptor-supplied policy is ignored; only the
    audited internal read-only set gets an explicit allow, everything else
    stays require-approval. Never executes the tool or falls back to another
    team. ``using_db`` lets a startup migration materialize inside its
    transaction.
    """
    if team_id is None:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="user_context_required",
            status_code=403,
        )

    ensure_builtin_registry()
    info = tool_registry.get_tool(name)
    if info is None:
        sandbox_infos = tool_registry.get_sandbox_tool_infos([name])
        info = sandbox_infos[0] if sandbox_infos else None

    synthetic = info is None
    if synthetic:
        if descriptor is not None:
            resolved = _coerce_descriptor(name, descriptor)
        elif name in _INTERNAL_TOOL_DESCRIPTIONS:
            resolved = _Descriptor(_INTERNAL_TOOL_DESCRIPTIONS[name], [], 1)
        else:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="tool_not_found",
                status_code=404,
            )
    else:
        resolved = None

    existing = await Tool.filter(team_id=team_id, name=name).using_db(using_db).first()
    if existing is not None:
        tool_type = getattr(existing.type, "value", existing.type)
        if tool_type != ToolType.BUILTIN.value:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="tool_name_exists",
                status_code=409,
            )
        if synthetic and resolved is not None:
            existing = await _refresh_definition(existing, resolved, using_db=using_db)
            return await _refresh_internal_approval(existing, name, using_db=using_db)
        if not synthetic and info is not None:
            return await _refresh_registry_identity(existing, info, using_db=using_db)
        return existing

    if synthetic:
        identity_policy = "none"
        connection_fields: list[dict] = []
    else:
        identity_policy, connection_fields = derive_builtin_identity(info)

    definition = Tool(
        id=uuid4(),
        team_id=team_id,
        name=name,
        display_name=name,
        description=resolved.description if resolved else info.description,
        category=ToolCategory.OTHER.value,
        visibility=ToolVisibility.TEAM,
        type=ToolType.BUILTIN,
        parameters=resolved.parameters if resolved else _parameters(info),
        approval_policy=(
            _internal_approval_policy() if synthetic else _approval_policy()
        ),
        identity_policy=identity_policy,
        connection_fields=connection_fields,
        is_enabled=True,
        definition_version=resolved.definition_version if resolved else 1,
        created_by_id=None,
    )
    try:
        try:
            await definition.save(using_db=using_db)
        except OperationalError as exc:
            if "value too long for type character varying" in str(exc):
                from app.core.init_data import init_tool_type_field

                await init_tool_type_field()
                await definition.save(using_db=using_db)
            else:
                raise
    except IntegrityError:
        # Concurrent lazy creation: adopt the winner only if it is builtin.
        existing = (
            await Tool.filter(team_id=team_id, name=name).using_db(using_db).first()
        )
        if existing is None:
            raise
        tool_type = getattr(existing.type, "value", existing.type)
        if tool_type != ToolType.BUILTIN.value:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="tool_name_exists",
                status_code=409,
            )
        if synthetic and resolved is not None:
            existing = await _refresh_definition(existing, resolved, using_db=using_db)
            return await _refresh_internal_approval(existing, name, using_db=using_db)
        if not synthetic and info is not None:
            return await _refresh_registry_identity(existing, info, using_db=using_db)
        return existing
    return definition


__all__ = [
    "derive_builtin_identity",
    "ensure_builtin_registry",
    "extract_builtin_binding",
    "get_builtin_definition",
    "parse_optional_uuid",
    "supported_internal_tool_keys",
]

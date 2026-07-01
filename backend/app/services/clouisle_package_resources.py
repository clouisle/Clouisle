"""Resource-specific import/export adapters for `.clouisle` packages."""

from __future__ import annotations

import copy
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from tortoise.transactions import in_transaction

from app.models.agent import (
    Agent,
    AgentKnowledgeBase,
    AgentStatus,
    AgentVisibility,
)
from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBase,
)
from app.models.model import Model, TeamModel
from app.models.tool import (
    CustomToolType as DBCustomToolType,
    Tool,
    ToolType as DBToolType,
)
from app.models.user import Team, User
from app.models.workflow import (
    TriggerType,
    Workflow,
    WorkflowStatus,
    WorkflowVisibility,
)
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleDependencyStatus,
    ClouisleImportInstallOut,
    ClouisleImportInstallRequest,
    ClouisleManifest,
    ClouislePackageConflict,
    ClouislePackageDependency,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, ResponseCode
from app.api.v1.endpoints.upload import save_generated_upload
from app.services.document_processor import document_processor


def _has_permission(user: User, permission: str) -> bool:
    if user.is_superuser:
        return True
    return any(
        perm.code in (permission, "*")
        for role in getattr(user, "roles", [])
        for perm in getattr(role, "permissions", [])
    )


def _require_permission(user: User, permission: str) -> None:
    if not _has_permission(user, permission):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="operation_not_permitted",
            status_code=403,
            permission=permission,
        )


def _uuid(value: Any) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _copy_json(value: Any) -> Any:
    return copy.deepcopy(value) if value is not None else None


def _sanitize_dict(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lower_key = str(key).lower()
            if any(
                token in lower_key
                for token in (
                    "password",
                    "secret",
                    "token",
                    "api_key",
                    "apikey",
                    "access_key",
                    "private_key",
                    "credential",
                    "authorization",
                )
            ):
                continue
            result[key] = _sanitize_dict(item)
        return result
    if isinstance(value, list):
        return [_sanitize_dict(item) for item in value]
    return value


def _asset_package_path(field: str, value: str) -> str | None:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 8 or parts[:4] != ["api", "v1", "upload", "files"]:
        return None
    category, year, month, filename = parts[4:]
    if not all((category, year, month, filename)):
        return None
    safe_field = field.replace("_", "-")
    return f"assets/{safe_field}/{category}/{year}/{month}/{filename}"


def _upload_path_from_asset_path(asset_path: str) -> tuple[str, str, str] | None:
    parts = asset_path.split("/")
    if len(parts) != 6 or parts[0] != "assets":
        return None
    category, year, month, filename = parts[2:]
    return category, f"{year}/{month}", filename


def _asset_source_path(asset_path: str) -> Path | None:
    from app.api.v1.endpoints.upload import UPLOAD_ROOT

    parsed = _upload_path_from_asset_path(asset_path)
    if not parsed:
        return None
    category, date_path, filename = parsed
    return UPLOAD_ROOT.joinpath(category, *date_path.split("/"), filename).resolve()


def _collect_payload_assets(
    payload: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    assets: dict[str, str] = {}
    for field in fields:
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        asset_path = _asset_package_path(field, value)
        if not asset_path:
            continue
        source_path = _asset_source_path(asset_path)
        if not source_path or not source_path.is_file():
            continue
        files[asset_path] = source_path.read_bytes()
        assets[field] = asset_path
    if assets:
        payload["assets"] = {**(payload.get("assets") or {}), **assets}
    return files


async def _restore_payload_assets(
    payload: dict[str, Any], package_dir: Path | None
) -> dict[str, Any]:
    if not package_dir:
        return payload
    assets = payload.get("assets") or {}
    if not isinstance(assets, dict):
        return payload
    restored = copy.deepcopy(payload)
    for field, asset_path in assets.items():
        if not isinstance(field, str) or not isinstance(asset_path, str):
            continue
        source = package_dir.joinpath(*asset_path.split("/")).resolve()
        if source != package_dir and package_dir not in source.parents:
            continue
        if not source.is_file():
            continue
        content = source.read_bytes()
        content_type = mimetypes.guess_type(source.name)[0]
        upload_info = await save_generated_upload(
            content=content,
            category="clouisle-assets",
            content_type=content_type,
            filename=source.name,
        )
        restored[field] = upload_info["url"]
    return restored


async def _resolve_model_dependency(
    dep: ClouislePackageDependency, team_id: UUID
) -> ClouislePackageDependency:
    model_type = dep.hints.get("model_type")
    provider = dep.hints.get("provider")
    model_id = dep.hints.get("model_id")
    if not (model_type or provider or model_id):
        dep.status = ClouisleDependencyStatus.MISSING
        dep.message = "clouisle_dependency_missing"
        return dep
    query = TeamModel.filter(team_id=team_id, is_enabled=True).prefetch_related("model")
    team_models = await query
    for team_model in team_models:
        model = team_model.model
        if model_type and model.model_type != model_type:
            continue
        if provider and model.provider != provider:
            continue
        if model_id and model.model_id != model_id:
            continue
        dep.status = ClouisleDependencyStatus.RESOLVED
        dep.matched_id = team_model.id
        return dep
    dep.status = ClouisleDependencyStatus.MISSING
    dep.message = "clouisle_dependency_missing"
    return dep


async def _resolve_resource_dependency(
    dep: ClouislePackageDependency, team_id: UUID
) -> ClouislePackageDependency:
    model_cls: type[Tool] | type[Agent] | type[Workflow] | type[KnowledgeBase] | None
    if dep.type == "tool":
        model_cls = Tool
    elif dep.type == "agent":
        model_cls = Agent
    elif dep.type == "workflow":
        model_cls = Workflow
    elif dep.type == "knowledge_base":
        model_cls = KnowledgeBase
    else:
        dep.status = ClouisleDependencyStatus.UNSUPPORTED
        dep.message = "clouisle_dependency_missing"
        return dep

    source_uuid = _uuid(dep.source_id)
    item = None
    if source_uuid:
        item = await model_cls.filter(id=source_uuid, team_id=team_id).first()
    lookup_name = dep.hints.get("name") or dep.name
    if not item and lookup_name:
        item = await model_cls.filter(name=lookup_name, team_id=team_id).first()
    if item:
        dep.status = ClouisleDependencyStatus.RESOLVED
        dep.matched_id = item.id
    else:
        dep.status = ClouisleDependencyStatus.MISSING
        dep.message = "clouisle_dependency_missing"
    return dep


class ResourcePackageAdapter(ABC):
    resource_type: ClouisleResourceType
    read_permission: str
    import_permission: str
    update_permission: str

    def ensure_export_permission(self, user: User) -> None:
        _require_permission(user, self.read_permission)

    def ensure_import_permission(self, user: User) -> None:
        _require_permission(user, self.import_permission)

    def ensure_update_permission(self, user: User) -> None:
        _require_permission(user, self.update_permission)

    @abstractmethod
    async def export(
        self,
        resource_id: UUID,
        user: User,
        *,
        check_permission: bool = True,
        check_scope: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        raise NotImplementedError

    async def export_files(self, resource_payload: dict[str, Any]) -> dict[str, bytes]:
        return {}

    async def materialize_files(
        self, resource_payload: dict[str, Any], package_dir: Path | None
    ) -> dict[str, Any]:
        return resource_payload

    @abstractmethod
    async def detect_conflict(
        self, resource_payload: dict[str, Any], team_id: UUID
    ) -> ClouislePackageConflict:
        raise NotImplementedError

    async def resolve_dependencies(
        self, manifest: ClouisleManifest, team_id: UUID, user: User
    ) -> list[ClouislePackageDependency]:
        resolved: list[ClouislePackageDependency] = []
        for dep in manifest.dependencies:
            dep_copy = dep.model_copy(deep=True)
            if dep_copy.type == "model":
                resolved.append(await _resolve_model_dependency(dep_copy, team_id))
            else:
                resolved.append(await _resolve_resource_dependency(dep_copy, team_id))
        return resolved

    @abstractmethod
    async def install(
        self,
        *,
        manifest: ClouisleManifest,
        resource_payload: dict[str, Any],
        team: Team,
        user: User,
        install_in: ClouisleImportInstallRequest,
        package_dir: Path | None = None,
        check_update_permission: bool = True,
    ) -> ClouisleImportInstallOut:
        raise NotImplementedError

    async def _target_name(
        self,
        resource_payload: dict[str, Any],
        team_id: UUID,
        install_in: ClouisleImportInstallRequest,
        model_cls: type[Tool] | type[Agent] | type[Workflow] | type[KnowledgeBase],
    ) -> str:
        base_name = install_in.target_name or str(resource_payload["name"])
        if install_in.action != ClouisleConflictAction.RENAME:
            return base_name
        candidate = base_name
        suffix = 1
        while await model_cls.filter(team_id=team_id, name=candidate).exists():
            candidate = f"{base_name}_import_{suffix}"
            suffix += 1
        return candidate


class ToolPackageAdapter(ResourcePackageAdapter):
    resource_type = ClouisleResourceType.TOOL
    read_permission = "tool:read"
    import_permission = "tool:create"
    update_permission = "tool:update"

    async def export(
        self,
        resource_id: UUID,
        user: User,
        *,
        check_permission: bool = True,
        check_scope: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        from app.api.v1.endpoints.tools import check_team_access

        if check_permission:
            self.ensure_export_permission(user)
        tool = await Tool.filter(id=resource_id).first()
        if not tool:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND, msg_key="tool_not_found", status_code=404
            )
        if check_scope:
            await check_team_access(tool.team_id, user)
        payload = {
            "name": tool.name,
            "display_name": tool.display_name,
            "description": tool.description,
            "icon": tool.icon,
            "category": tool.category,
            "type": _enum_value(tool.type),
            "custom_type": _enum_value(tool.custom_type),
            "parameters": _copy_json(tool.parameters) or [],
            "http_config": _sanitize_dict(tool.http_config or {}),
            "code_config": _sanitize_dict(tool.code_config or {}),
            "mcp_config": _sanitize_dict(tool.mcp_config or {}),
            "is_enabled": tool.is_enabled,
        }
        return payload, [], tool.name

    async def export_files(self, resource_payload: dict[str, Any]) -> dict[str, bytes]:
        return _collect_payload_assets(resource_payload, ("icon",))

    async def materialize_files(
        self, resource_payload: dict[str, Any], package_dir: Path | None
    ) -> dict[str, Any]:
        return await _restore_payload_assets(resource_payload, package_dir)

    async def detect_conflict(
        self, resource_payload: dict[str, Any], team_id: UUID
    ) -> ClouislePackageConflict:
        existing = await Tool.filter(
            team_id=team_id, name=resource_payload.get("name")
        ).first()
        if not existing:
            return ClouislePackageConflict()
        return ClouislePackageConflict(
            type="name_exists",
            existing_id=existing.id,
            existing_name=existing.name,
            message="clouisle_name_conflict",
        )

    async def install(
        self,
        *,
        manifest: ClouisleManifest,
        resource_payload: dict[str, Any],
        team: Team,
        user: User,
        install_in: ClouisleImportInstallRequest,
        package_dir: Path | None = None,
        check_update_permission: bool = True,
    ) -> ClouisleImportInstallOut:
        fields = _tool_fields(resource_payload)
        async with in_transaction():
            if install_in.action == ClouisleConflictAction.UPDATE:
                if check_update_permission:
                    self.ensure_update_permission(user)
                existing = await Tool.filter(
                    team_id=team.id, name=resource_payload.get("name")
                ).first()
                if not existing:
                    raise BusinessError(
                        code=ResponseCode.NOT_FOUND,
                        msg_key="tool_not_found",
                        status_code=404,
                    )
                for key, value in fields.items():
                    setattr(existing, key, value)
                await existing.save()
                return ClouisleImportInstallOut(updated=existing.id)

            target_name = await self._target_name(
                resource_payload, team.id, install_in, Tool
            )
            if await Tool.filter(team_id=team.id, name=target_name).exists():
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="clouisle_name_conflict"
                )
            tool = await Tool.create(
                team=team,
                name=target_name,
                created_by=user,
                credentials={},
                is_enabled=False,
                **fields,
            )
            return ClouisleImportInstallOut(installed=tool.id)


class AgentPackageAdapter(ResourcePackageAdapter):
    resource_type = ClouisleResourceType.AGENT
    read_permission = "agent:read"
    import_permission = "agent:create"
    update_permission = "agent:update"

    async def export(
        self,
        resource_id: UUID,
        user: User,
        *,
        check_permission: bool = True,
        check_scope: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        from app.api.v1.endpoints.agents import check_agent_access

        if check_permission:
            self.ensure_export_permission(user)
        agent = await check_agent_access(resource_id, user)
        kb_links = await AgentKnowledgeBase.filter(agent_id=agent.id).prefetch_related(
            "knowledge_base"
        )
        dependencies: list[dict[str, Any]] = []
        model_summary = None
        if agent.model_id:
            team_model = (
                await TeamModel.filter(id=agent.model_id)
                .prefetch_related("model")
                .first()
            )
            if team_model:
                model_summary = _model_summary(team_model)
                dependencies.append(
                    {
                        "type": "model",
                        "source_id": str(team_model.id),
                        "name": team_model.model.name,
                        "required": True,
                        "hints": model_summary,
                    }
                )
        for tool_config in agent.tools_config or []:
            tool_id = tool_config.get("tool_id")
            if tool_id:
                tool = await Tool.filter(id=tool_id).first()
                dependencies.append(
                    {
                        "type": "tool",
                        "source_id": str(tool_id),
                        "name": tool.display_name if tool else tool_config.get("name"),
                        "required": True,
                        "hints": {"name": tool.name} if tool else {},
                    }
                )
        for link in kb_links:
            dependencies.append(
                {
                    "type": "knowledge_base",
                    "source_id": str(link.knowledge_base_id),
                    "name": link.knowledge_base.name,
                    "required": True,
                    "hints": {},
                }
            )

        payload = {
            "name": agent.name,
            "description": agent.description,
            "icon": agent.icon,
            "avatar_url": agent.avatar_url,
            "model": model_summary,
            "system_prompt": agent.system_prompt,
            "max_iterations": agent.max_iterations,
            "hide_tool_calls": agent.hide_tool_calls,
            "tools_config": _copy_json(agent.tools_config) or [],
            "enable_vision": agent.enable_vision,
            "enable_file_upload": agent.enable_file_upload,
            "file_upload_config": _copy_json(agent.file_upload_config) or {},
            "enable_user_input_request": agent.enable_user_input_request,
            "enable_memory": agent.enable_memory,
            "memory_config": _copy_json(agent.memory_config) or {},
            "context_compression_config": _copy_json(agent.context_compression_config)
            or {},
            "enable_image_generation": agent.enable_image_generation,
            "image_generation_config": _copy_json(agent.image_generation_config) or {},
            "enable_video_generation": agent.enable_video_generation,
            "video_generation_config": _copy_json(agent.video_generation_config) or {},
            "rag_mode": _enum_value(agent.rag_mode),
            "variables": _copy_json(agent.variables) or [],
            "opening_message": agent.opening_message,
            "suggested_questions": _copy_json(agent.suggested_questions) or [],
            "embed_config": _copy_json(agent.embed_config) or {},
            "knowledge_base_configs": [
                {
                    "knowledge_base_id": str(link.knowledge_base_id),
                    "name": link.knowledge_base.name,
                    "retrieval_top_k": link.retrieval_top_k,
                    "score_threshold": link.score_threshold,
                    "search_mode": link.search_mode,
                }
                for link in kb_links
            ],
        }
        return payload, dependencies, agent.name

    async def export_files(self, resource_payload: dict[str, Any]) -> dict[str, bytes]:
        return _collect_payload_assets(resource_payload, ("icon", "avatar_url"))

    async def materialize_files(
        self, resource_payload: dict[str, Any], package_dir: Path | None
    ) -> dict[str, Any]:
        return await _restore_payload_assets(resource_payload, package_dir)

    async def detect_conflict(
        self, resource_payload: dict[str, Any], team_id: UUID
    ) -> ClouislePackageConflict:
        existing = await Agent.filter(
            team_id=team_id, name=resource_payload.get("name")
        ).first()
        if not existing:
            return ClouislePackageConflict()
        return ClouislePackageConflict(
            type="name_exists",
            existing_id=existing.id,
            existing_name=existing.name,
            message="clouisle_name_conflict",
        )

    async def install(
        self,
        *,
        manifest: ClouisleManifest,
        resource_payload: dict[str, Any],
        team: Team,
        user: User,
        install_in: ClouisleImportInstallRequest,
        package_dir: Path | None = None,
        check_update_permission: bool = True,
    ) -> ClouisleImportInstallOut:
        agent_fields = _agent_fields(resource_payload, install_in.dependency_mapping)
        async with in_transaction():
            if install_in.action == ClouisleConflictAction.UPDATE:
                if check_update_permission:
                    self.ensure_update_permission(user)
                existing = await Agent.filter(
                    team_id=team.id, name=resource_payload.get("name")
                ).first()
                if not existing:
                    raise BusinessError(
                        code=ResponseCode.NOT_FOUND,
                        msg_key="agent_not_found",
                        status_code=404,
                    )
                for key, value in agent_fields.items():
                    setattr(existing, key, value)
                await existing.save()
                await _replace_agent_kbs(
                    existing, resource_payload, install_in.dependency_mapping
                )
                return ClouisleImportInstallOut(updated=existing.id)

            target_name = await self._target_name(
                resource_payload, team.id, install_in, Agent
            )
            if await Agent.filter(team_id=team.id, name=target_name).exists():
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="clouisle_name_conflict"
                )
            agent = await Agent.create(
                team=team,
                name=target_name,
                status=AgentStatus.DRAFT,
                visibility=AgentVisibility.PRIVATE,
                created_by=user,
                **agent_fields,
            )
            await _replace_agent_kbs(
                agent, resource_payload, install_in.dependency_mapping
            )
            return ClouisleImportInstallOut(installed=agent.id)


class WorkflowPackageAdapter(ResourcePackageAdapter):
    resource_type = ClouisleResourceType.WORKFLOW
    read_permission = "workflow:read"
    import_permission = "workflow:create"
    update_permission = "workflow:update"

    async def export(
        self,
        resource_id: UUID,
        user: User,
        *,
        check_permission: bool = True,
        check_scope: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        from app.api.v1.endpoints.workflows import check_workflow_access

        if check_permission:
            self.ensure_export_permission(user)
        workflow = await check_workflow_access(resource_id, user)
        definition = _copy_json(workflow.definition) or {}
        dependencies = await _workflow_dependencies(definition, workflow.team_id)
        payload = {
            "name": workflow.name,
            "description": workflow.description,
            "icon": workflow.icon,
            "definition": definition,
            "variables": _copy_json(workflow.variables) or [],
            "trigger_type": _enum_value(workflow.trigger_type),
            "trigger_config": _sanitize_dict(workflow.trigger_config or {}),
            "visibility": _enum_value(workflow.visibility),
            "embed_config": _copy_json(workflow.embed_config) or {},
        }
        return payload, dependencies, workflow.name

    async def export_files(self, resource_payload: dict[str, Any]) -> dict[str, bytes]:
        return _collect_payload_assets(resource_payload, ("icon",))

    async def materialize_files(
        self, resource_payload: dict[str, Any], package_dir: Path | None
    ) -> dict[str, Any]:
        return await _restore_payload_assets(resource_payload, package_dir)

    async def detect_conflict(
        self, resource_payload: dict[str, Any], team_id: UUID
    ) -> ClouislePackageConflict:
        existing = await Workflow.filter(
            team_id=team_id, name=resource_payload.get("name")
        ).first()
        if not existing:
            return ClouislePackageConflict()
        return ClouislePackageConflict(
            type="name_exists",
            existing_id=existing.id,
            existing_name=existing.name,
            message="clouisle_name_conflict",
        )

    async def install(
        self,
        *,
        manifest: ClouisleManifest,
        resource_payload: dict[str, Any],
        team: Team,
        user: User,
        install_in: ClouisleImportInstallRequest,
        package_dir: Path | None = None,
        check_update_permission: bool = True,
    ) -> ClouisleImportInstallOut:
        fields = _workflow_fields(resource_payload, install_in.dependency_mapping)
        async with in_transaction():
            if install_in.action == ClouisleConflictAction.UPDATE:
                if check_update_permission:
                    self.ensure_update_permission(user)
                existing = await Workflow.filter(
                    team_id=team.id, name=resource_payload.get("name")
                ).first()
                if not existing:
                    raise BusinessError(
                        code=ResponseCode.NOT_FOUND,
                        msg_key="workflow_not_found",
                        status_code=404,
                    )
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.version += 1
                await existing.save()
                return ClouisleImportInstallOut(updated=existing.id)

            target_name = await self._target_name(
                resource_payload, team.id, install_in, Workflow
            )
            if await Workflow.filter(team_id=team.id, name=target_name).exists():
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="clouisle_name_conflict"
                )
            workflow = await Workflow.create(
                team=team,
                name=target_name,
                status=WorkflowStatus.DRAFT,
                visibility=WorkflowVisibility.PRIVATE,
                webhook_token=None,
                created_by=user,
                **fields,
            )
            return ClouisleImportInstallOut(installed=workflow.id)


class KnowledgeBasePackageAdapter(ResourcePackageAdapter):
    resource_type = ClouisleResourceType.KNOWLEDGE_BASE
    read_permission = "kb:read"
    import_permission = "kb:create"
    update_permission = "kb:update"

    async def export(
        self,
        resource_id: UUID,
        user: User,
        *,
        check_permission: bool = True,
        check_scope: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        from app.api.v1.endpoints.knowledge_bases import check_kb_access

        if check_permission:
            self.ensure_export_permission(user)
        if check_scope:
            kb = await check_kb_access(resource_id, user)
        else:
            kb = await KnowledgeBase.filter(id=resource_id).first()
            if not kb:
                raise BusinessError(
                    code=ResponseCode.KB_NOT_FOUND,
                    msg_key="kb_not_found",
                    status_code=404,
                )
        if kb.created_by_id != user.id:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="operation_not_permitted",
                status_code=403,
                permission=self.read_permission,
            )
        dependencies: list[dict[str, Any]] = []
        if kb.embedding_model_id:
            model = await Model.filter(id=kb.embedding_model_id).first()
            if model:
                dependencies.append(
                    {
                        "type": "model",
                        "source_id": str(model.id),
                        "name": model.name,
                        "required": True,
                        "hints": _model_hints(model),
                    }
                )
        if kb.rerank_model_id:
            model = await Model.filter(id=kb.rerank_model_id).first()
            if model:
                dependencies.append(
                    {
                        "type": "model",
                        "source_id": str(model.id),
                        "name": model.name,
                        "required": False,
                        "hints": _model_hints(model),
                    }
                )
        documents = await Document.filter(knowledge_base_id=kb.id).all()
        payload = {
            "name": kb.name,
            "description": kb.description,
            "icon": kb.icon,
            "settings": _copy_json(kb.settings) or {},
            "embedding_model": await _model_ref(kb.embedding_model_id),
            "rerank_model": await _model_ref(kb.rerank_model_id),
            "documents": [
                {
                    "name": doc.name,
                    "doc_type": doc.doc_type,
                    "package_file": _kb_document_package_path(doc),
                    "source_file": doc.file_path,
                    "source_url": doc.source_url,
                    "file_size": doc.file_size,
                    "metadata": _copy_json(doc.metadata) or {},
                    "chunks": [
                        {
                            "content": chunk.content,
                            "chunk_index": chunk.chunk_index,
                            "token_count": chunk.token_count,
                            "metadata": _copy_json(chunk.metadata) or {},
                        }
                        for chunk in await DocumentChunk.filter(
                            document_id=doc.id
                        ).all()
                    ],
                }
                for doc in documents
            ],
        }
        return payload, dependencies, kb.name

    async def export_files(self, resource_payload: dict[str, Any]) -> dict[str, bytes]:
        files = _collect_payload_assets(resource_payload, ("icon",))
        for doc in resource_payload.get("documents") or []:
            package_file = doc.get("package_file")
            source_file = doc.get("source_file")
            if not package_file or not source_file:
                continue
            source = Path(source_file)
            if source.is_file():
                files[package_file] = source.read_bytes()
            doc.pop("source_file", None)
        return files

    async def materialize_files(
        self, resource_payload: dict[str, Any], package_dir: Path | None
    ) -> dict[str, Any]:
        return await _restore_payload_assets(resource_payload, package_dir)

    async def detect_conflict(
        self, resource_payload: dict[str, Any], team_id: UUID
    ) -> ClouislePackageConflict:
        existing = await KnowledgeBase.filter(
            team_id=team_id, name=resource_payload.get("name")
        ).first()
        if not existing:
            return ClouislePackageConflict()
        return ClouislePackageConflict(
            type="name_exists",
            existing_id=existing.id,
            existing_name=existing.name,
            message="clouisle_name_conflict",
        )

    async def install(
        self,
        *,
        manifest: ClouisleManifest,
        resource_payload: dict[str, Any],
        team: Team,
        user: User,
        install_in: ClouisleImportInstallRequest,
        package_dir: Path | None = None,
        check_update_permission: bool = True,
    ) -> ClouisleImportInstallOut:
        fields = await _kb_fields(resource_payload, install_in.dependency_mapping)
        async with in_transaction():
            if install_in.action == ClouisleConflictAction.UPDATE:
                if check_update_permission:
                    self.ensure_update_permission(user)
                existing = await KnowledgeBase.filter(
                    team_id=team.id, name=resource_payload.get("name")
                ).first()
                if not existing:
                    raise BusinessError(
                        code=ResponseCode.KB_NOT_FOUND,
                        msg_key="kb_not_found",
                        status_code=404,
                    )
                for key, value in fields.items():
                    setattr(existing, key, value)
                await existing.save()
                return ClouisleImportInstallOut(
                    updated=existing.id, warnings=["clouisle_kb_documents_not_updated"]
                )

            target_name = await self._target_name(
                resource_payload, team.id, install_in, KnowledgeBase
            )
            if await KnowledgeBase.filter(team_id=team.id, name=target_name).exists():
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="clouisle_name_conflict"
                )
            kb = await KnowledgeBase.create(
                team=team, name=target_name, created_by=user, **fields
            )
            for doc_payload in resource_payload.get("documents") or []:
                doc_file_path = _restore_kb_document_file(
                    package_dir,
                    kb.id,
                    doc_payload.get("package_file"),
                    doc_payload.get("name") or "Imported document",
                )
                doc = await Document.create(
                    knowledge_base=kb,
                    name=doc_payload.get("name") or "Imported document",
                    doc_type=doc_payload.get("doc_type") or "txt",
                    file_path=doc_file_path,
                    file_size=doc_payload.get("file_size"),
                    source_url=None if doc_file_path else doc_payload.get("source_url"),
                    status=DocumentStatus.PENDING.value,
                    metadata=doc_payload.get("metadata") or {},
                    uploaded_by=user,
                )
                for chunk_payload in doc_payload.get("chunks") or []:
                    await DocumentChunk.create(
                        document=doc,
                        content=chunk_payload.get("content") or "",
                        chunk_index=int(chunk_payload.get("chunk_index") or 0),
                        token_count=int(chunk_payload.get("token_count") or 0),
                        metadata=chunk_payload.get("metadata") or {},
                        status="pending",
                    )
            return ClouisleImportInstallOut(installed=kb.id)


def _tool_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": payload.get("display_name")
        or payload.get("name")
        or "Imported Tool",
        "description": payload.get("description") or "",
        "icon": payload.get("icon"),
        "category": payload.get("category") or "other",
        "type": DBToolType(payload.get("type") or DBToolType.CUSTOM.value),
        "custom_type": DBCustomToolType(payload["custom_type"])
        if payload.get("custom_type")
        else None,
        "parameters": payload.get("parameters") or [],
        "http_config": payload.get("http_config") or {},
        "code_config": payload.get("code_config") or {},
        "mcp_config": payload.get("mcp_config") or {},
    }


def _agent_fields(payload: dict[str, Any], mapping: dict[str, UUID]) -> dict[str, Any]:
    tools_config = copy.deepcopy(payload.get("tools_config") or [])
    for config in tools_config:
        tool_id = config.get("tool_id")
        if tool_id and tool_id in mapping:
            config["tool_id"] = str(mapping[tool_id])
    model_id = None
    model = payload.get("model") or {}
    source_model_id = model.get("team_model_id") or model.get("id")
    if source_model_id and source_model_id in mapping:
        model_id = mapping[source_model_id]
    return {
        "description": payload.get("description"),
        "icon": payload.get("icon"),
        "avatar_url": payload.get("avatar_url"),
        "model_id": model_id,
        "system_prompt": payload.get("system_prompt"),
        "max_iterations": int(payload.get("max_iterations") or 5),
        "hide_tool_calls": bool(payload.get("hide_tool_calls") or False),
        "tools_config": tools_config,
        "tools_credentials": {},
        "enable_vision": bool(payload.get("enable_vision") or False),
        "enable_file_upload": bool(payload.get("enable_file_upload") or False),
        "file_upload_config": payload.get("file_upload_config") or {},
        "enable_user_input_request": bool(
            payload.get("enable_user_input_request") or False
        ),
        "enable_memory": bool(payload.get("enable_memory") or False),
        "memory_config": payload.get("memory_config") or {},
        "context_compression_config": payload.get("context_compression_config") or {},
        "enable_image_generation": bool(
            payload.get("enable_image_generation") or False
        ),
        "image_generation_config": payload.get("image_generation_config") or {},
        "enable_video_generation": bool(
            payload.get("enable_video_generation") or False
        ),
        "video_generation_config": payload.get("video_generation_config") or {},
        "rag_mode": payload.get("rag_mode") or "agentic",
        "variables": payload.get("variables") or [],
        "opening_message": payload.get("opening_message"),
        "suggested_questions": payload.get("suggested_questions") or [],
        "embed_config": payload.get("embed_config") or {},
    }


async def _replace_agent_kbs(
    agent: Agent, payload: dict[str, Any], mapping: dict[str, UUID]
) -> None:
    await AgentKnowledgeBase.filter(agent_id=agent.id).delete()
    for kb_config in payload.get("knowledge_base_configs") or []:
        source_id = str(kb_config.get("knowledge_base_id") or "")
        target_id = mapping.get(source_id)
        if not target_id:
            continue
        score_threshold = kb_config.get("score_threshold")
        await AgentKnowledgeBase.create(
            agent=agent,
            knowledge_base_id=target_id,
            retrieval_top_k=kb_config.get("retrieval_top_k") or 5,
            score_threshold=score_threshold if score_threshold is not None else 0.3,
            search_mode=kb_config.get("search_mode") or "hybrid",
        )


def _workflow_fields(
    payload: dict[str, Any], mapping: dict[str, UUID]
) -> dict[str, Any]:
    definition = _rewrite_references(
        copy.deepcopy(payload.get("definition") or {}), mapping
    )
    trigger_type = payload.get("trigger_type") or TriggerType.MANUAL.value
    if trigger_type == TriggerType.WEBHOOK.value:
        trigger_type = TriggerType.MANUAL.value
    return {
        "description": payload.get("description"),
        "icon": payload.get("icon"),
        "definition": definition,
        "variables": payload.get("variables") or [],
        "trigger_type": TriggerType(trigger_type),
        "trigger_config": payload.get("trigger_config") or {},
        "embed_config": payload.get("embed_config") or {},
    }


async def _kb_fields(
    payload: dict[str, Any], mapping: dict[str, UUID]
) -> dict[str, Any]:
    embedding = payload.get("embedding_model") or {}
    rerank = payload.get("rerank_model") or {}
    embedding_source = str(embedding.get("team_model_id") or embedding.get("id") or "")
    rerank_source = str(rerank.get("team_model_id") or rerank.get("id") or "")
    embedding_model_id = await _mapped_model_id(mapping.get(embedding_source))
    rerank_model_id = await _mapped_model_id(mapping.get(rerank_source))
    return {
        "description": payload.get("description"),
        "icon": payload.get("icon"),
        "settings": payload.get("settings") or None,
        "embedding_model_id": embedding_model_id,
        "rerank_model_id": rerank_model_id,
    }


async def _mapped_model_id(mapped_team_model_id: UUID | None) -> UUID | None:
    if not mapped_team_model_id:
        return None
    team_model = await TeamModel.filter(id=mapped_team_model_id).first()
    return team_model.model_id if team_model else mapped_team_model_id


async def _workflow_dependencies(
    definition: dict[str, Any], team_id: UUID
) -> list[dict[str, Any]]:
    deps: dict[tuple[str, str], dict[str, Any]] = {}
    for node in definition.get("nodes") or []:
        data = node.get("data") or {}
        for dep_type, keys in {
            "agent": ("agentId", "agent_id"),
            "tool": ("toolId", "tool_id"),
            "workflow": ("workflowId", "workflow_id"),
            "knowledge_base": ("knowledgeBaseId", "knowledge_base_id", "kbId", "kb_id"),
            "model": ("modelId", "model_id"),
        }.items():
            for value in _find_values(data, keys):
                summary = await _lookup_dependency_summary(dep_type, value, team_id)
                deps[(dep_type, str(value))] = {
                    "type": dep_type,
                    "source_id": str(value),
                    "name": summary["name"],
                    "required": True,
                    "hints": summary["hints"],
                }
    return list(deps.values())


def _find_values(value: Any, keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and item:
                values.append(item)
            values.extend(_find_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            values.extend(_find_values(item, keys))
    return values


def _rewrite_references(value: Any, mapping: dict[str, UUID]) -> Any:
    if isinstance(value, dict):
        return {key: _rewrite_references(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_references(item, mapping) for item in value]
    if isinstance(value, str) and value in mapping:
        return str(mapping[value])
    return value


async def _lookup_dependency_summary(
    dep_type: str, value: Any, team_id: UUID
) -> dict[str, Any]:
    dep_id = _uuid(value)
    if not dep_id:
        return {"name": None, "hints": {}}
    if dep_type == "model":
        team_model = (
            await TeamModel.filter(id=dep_id, team_id=team_id)
            .prefetch_related("model")
            .first()
        )
        return (
            {"name": team_model.model.name, "hints": _model_hints(team_model.model)}
            if team_model
            else {"name": None, "hints": {}}
        )
    if dep_type == "agent":
        agent = await Agent.filter(id=dep_id, team_id=team_id).first()
        return (
            {"name": agent.name, "hints": {}} if agent else {"name": None, "hints": {}}
        )
    if dep_type == "tool":
        tool = await Tool.filter(id=dep_id, team_id=team_id).first()
        return (
            {"name": tool.display_name, "hints": {"name": tool.name}}
            if tool
            else {"name": None, "hints": {}}
        )
    if dep_type == "workflow":
        workflow = await Workflow.filter(id=dep_id, team_id=team_id).first()
        return (
            {"name": workflow.name, "hints": {}}
            if workflow
            else {"name": None, "hints": {}}
        )
    if dep_type == "knowledge_base":
        knowledge_base = await KnowledgeBase.filter(id=dep_id, team_id=team_id).first()
        return (
            {"name": knowledge_base.name, "hints": {}}
            if knowledge_base
            else {"name": None, "hints": {}}
        )
    return {"name": None, "hints": {}}


def _model_hints(model: Model) -> dict[str, Any]:
    return {
        "provider": model.provider,
        "model_id": model.model_id,
        "model_type": model.model_type,
    }


def _model_summary(team_model: TeamModel) -> dict[str, Any]:
    return {
        "team_model_id": str(team_model.id),
        **_model_hints(team_model.model),
        "name": team_model.model.name,
    }


async def _model_ref(model_id: UUID | None) -> dict[str, Any] | None:
    if not model_id:
        return None
    model = await Model.filter(id=model_id).first()
    if not model:
        return None
    return {"id": str(model.id), **_model_hints(model), "name": model.name}


def _safe_package_filename(value: str) -> str:
    name = Path(value).name.strip().replace("\\", "_").replace("/", "_")
    return name if name and name not in {".", ".."} else "document.bin"


def _kb_document_package_path(doc: Document) -> str | None:
    if not doc.file_path:
        return None
    source = Path(doc.file_path)
    if not source.is_file():
        return None
    return f"documents/{doc.id}/{_safe_package_filename(doc.name or source.name)}"


def _restore_kb_document_file(
    package_dir: Path | None,
    kb_id: UUID,
    package_file: str | None,
    document_name: str,
) -> str | None:
    if not package_dir or not package_file:
        return None
    source = package_dir.joinpath(*package_file.split("/")).resolve()
    if source != package_dir and package_dir not in source.parents:
        return None
    if not source.is_file():
        return None
    safe_name = _safe_package_filename(document_name)
    target_path = document_processor.get_storage_path(kb_id, safe_name)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target_path


_ADAPTERS: dict[ClouisleResourceType, ResourcePackageAdapter] = {
    ClouisleResourceType.TOOL: ToolPackageAdapter(),
    ClouisleResourceType.AGENT: AgentPackageAdapter(),
    ClouisleResourceType.WORKFLOW: WorkflowPackageAdapter(),
    ClouisleResourceType.KNOWLEDGE_BASE: KnowledgeBasePackageAdapter(),
}


def get_adapter(resource_type: ClouisleResourceType) -> ResourcePackageAdapter:
    return _ADAPTERS[resource_type]

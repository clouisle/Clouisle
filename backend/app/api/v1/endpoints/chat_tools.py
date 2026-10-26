"""Chat tool execution functions."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.services.citations import stable_citation_id, with_rag_citation_ids

if TYPE_CHECKING:
    from app.models.agent import Agent

logger = logging.getLogger(__name__)


class AssetViewResult(dict):
    """Metadata-only view result for durable ref replay."""

    def __init__(self, *, display_result: dict[str, Any], llm_result: str):
        super().__init__(display_result=display_result, llm_result=llm_result)

    @property
    def display_result(self) -> dict[str, Any]:
        return self["display_result"]

    @property
    def llm_result(self) -> str:
        return self["llm_result"]


def _document_error_json(exc: ValueError, locale: str | None = None) -> str:
    from app.core.i18n import has_translation, t

    key = str(exc)
    return json.dumps(
        {"error": t(key, lang=locale) if has_translation(key, lang=locale) else key},
        ensure_ascii=False,
    )


def _document_result_json(ref: str, asset: Any, document: dict[str, Any]) -> str:
    payload = dict(document)
    # The model-facing identity is the ref; keep the internal UUID out of the
    # response and leave room under the service's per-call byte budget.
    payload.pop("asset_id", None)
    payload["ref"] = ref
    payload["citation_id"] = stable_citation_id("asset", asset.id)
    return json.dumps(payload, ensure_ascii=False)


async def _execute_asset_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    agent: "Agent | None",
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any = None,
    session_id: str | None = None,
) -> str:
    from uuid import UUID

    from app.models.asset import AssetScopeType
    from app.schemas.response import BusinessError
    from app.services.asset import asset_service
    from app.services.upload_storage import get_upload_storage_backend
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.core.i18n import t

    if not agent or (not user and workflow_run_id is None):
        return json.dumps({"error": t("agent_context_required")}, ensure_ascii=False)
    ref = arguments.get("ref")
    if tool_name != "list_assets" and not isinstance(ref, str):
        return json.dumps({"error": t("validation_error")}, ensure_ascii=False)

    if workflow_run_id is not None:
        try:
            scope_id = UUID(str(workflow_run_id))
        except (ValueError, AttributeError):
            return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
        scope_type = AssetScopeType.WORKFLOW_RUN
    else:
        if not conversation_id:
            return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
        try:
            scope_id = UUID(str(conversation_id))
        except (ValueError, AttributeError):
            return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
        scope_type = AssetScopeType.CONVERSATION

    if tool_name == "list_assets":
        from app.services.asset_access import list_authorized_assets

        try:
            result = await list_authorized_assets(
                scope_type=scope_type,
                scope_id=scope_id,
                user=user,
                expected_team_id=getattr(agent, "team_id", None),
                query=arguments.get("query", ""),
                kind=arguments.get("kind"),
                cursor=arguments.get("cursor"),
                limit=arguments.get("limit", 10),
            )
            return json.dumps(result, ensure_ascii=False)
        except ValueError as exc:
            return json.dumps(
                {"error": t("validation_error"), "detail": str(exc)}, ensure_ascii=False
            )
        except BusinessError:
            return json.dumps({"error": t("access_denied")}, ensure_ascii=False)

    try:
        from app.services.asset_access import resolve_authorized_asset_ref

        asset = await resolve_authorized_asset_ref(
            ref,
            scope_type=scope_type,
            scope_id=scope_id,
            user=user,
            expected_team_id=getattr(agent, "team_id", None),
        )
    except BusinessError as exc:
        if exc.status_code == 403:
            return json.dumps({"error": t("access_denied")}, ensure_ascii=False)
        return json.dumps({"error": t("file_not_found")}, ensure_ascii=False)

    try:
        if tool_name == "materialize_asset":
            path = arguments.get("path")
            if not isinstance(path, str) or not path.strip():
                return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
            if not session_id:
                return json.dumps(
                    {"error": t("sandbox_session_required")}, ensure_ascii=False
                )
            from app.llm.tools.sandbox_paths import normalize_workspace_path
            from app.services.sandbox.gateway import sandbox_gateway
            from app.services.sandbox.models import (
                SandboxInputFileSpec,
                SandboxJob,
                SandboxJobSource,
                SandboxLimits,
            )

            try:
                safe_path = normalize_workspace_path(path)
            except ValueError:
                return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code="return {'materialized': True}",
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=30, disk_mb=512),
                metadata={
                    "team_id": str(agent.team_id) if agent.team_id else None,
                    "user_id": str(user.id) if user is not None else None,
                    "workflow_run_id": (
                        str(scope_id)
                        if scope_type == AssetScopeType.WORKFLOW_RUN
                        else None
                    ),
                },
                input_files=[
                    SandboxInputFileSpec(
                        target_path=safe_path,
                        asset_id=asset.id,
                        asset_ref=ref,
                        scope_type=scope_type.value,
                        scope_id=scope_id,
                        expected_checksum=asset.checksum,
                        expected_size=asset.size,
                    )
                ],
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=session_id,
                agent_id=str(agent.id),
                team_id=str(agent.team_id) if agent.team_id else None,
                timeout_seconds=60,
            )
            if not result.success:
                return json.dumps(
                    {"error": result.error or t("tool_execution_failed")},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "ref": ref,
                    "path": safe_path,
                    "filename": asset.display_filename,
                    "size": asset.size,
                },
                ensure_ascii=False,
            )
        if tool_name == "inspect_asset":
            return json.dumps(
                {
                    "ref": ref,
                    "filename": asset.display_filename,
                    "content_type": asset.content_type,
                    "size": asset.size,
                    "source": asset.source.value,
                    "capabilities": asset_service.capabilities(asset),
                },
                ensure_ascii=False,
            )
        user_locale = getattr(user, "locale", None) if user is not None else None
        if tool_name in {"read_asset", "search_asset"}:
            from app.services.asset_document import (
                read_document,
                search_document,
            )

            storage = await get_upload_storage_backend(UPLOAD_ROOT)
            try:
                if tool_name == "read_asset":
                    document = await read_document(
                        asset,
                        storage=storage,
                        start_line=arguments.get("start_line", 1),
                        line_count=arguments.get("line_count", 100),
                        cursor=arguments.get("cursor"),
                    )
                else:
                    query = arguments.get("query")
                    if not isinstance(query, str) or not query:
                        return json.dumps(
                            {"error": t("validation_error")}, ensure_ascii=False
                        )
                    document = await search_document(
                        asset,
                        storage=storage,
                        query=query,
                        context_lines=arguments.get("context_lines", 2),
                        limit=arguments.get("limit", 20),
                        cursor=arguments.get("cursor"),
                    )
            except ValueError as exc:
                return _document_error_json(exc, user_locale)
            return _document_result_json(ref, asset, document)
        if tool_name == "view_asset":
            from app.api.v1.endpoints.chat_helpers.model_utils import (
                resolve_agent_chat_model,
            )
            from app.services.asset_view import resolve_view_content

            extracted_text = bool(arguments.get("extracted_text", False))
            selection = arguments.get("selection")
            raw_mime_type = asset.content_type.split(";", 1)[0].strip().lower()
            if extracted_text:
                if selection is not None:
                    return json.dumps(
                        {"error": t("validation_error")}, ensure_ascii=False
                    )
                from app.services.asset_document import read_document

                storage = await get_upload_storage_backend(UPLOAD_ROOT)
                try:
                    document = await read_document(asset, storage=storage)
                except ValueError as exc:
                    return _document_error_json(exc, user_locale)
                return _document_result_json(ref, asset, document)
            if not raw_mime_type.startswith(("image/", "audio/", "video/")) and (
                raw_mime_type != "application/pdf"
            ):
                # Documents have no native multimodal input; use the bounded reader.
                from app.services.asset_document import read_document

                storage = await get_upload_storage_backend(UPLOAD_ROOT)
                try:
                    document = await read_document(asset, storage=storage)
                except ValueError as exc:
                    return _document_error_json(exc, user_locale)
                return _document_result_json(ref, asset, document)
            chat_model = await resolve_agent_chat_model(agent)
            if raw_mime_type == "application/pdf":
                page_start = (
                    selection.get("page_start") if isinstance(selection, dict) else None
                )
                page_end = (
                    selection.get("page_end") if isinstance(selection, dict) else None
                )
                if (
                    type(page_start) is not int
                    or type(page_end) is not int
                    or page_start < 1
                    or page_end < page_start
                ):
                    from app.llm.capabilities import (
                        get_effective_input_capabilities,
                    )
                    from app.llm.types import ContentType

                    if (
                        ContentType.FILE
                        in get_effective_input_capabilities(chat_model.model).modalities
                    ):
                        return json.dumps(
                            {"error": t("asset_page_range_required")},
                            ensure_ascii=False,
                        )
                    from app.services.asset_document import read_document

                    storage = await get_upload_storage_backend(UPLOAD_ROOT)
                    try:
                        document = await read_document(asset, storage=storage)
                    except ValueError as exc:
                        return _document_error_json(exc, user_locale)
                    return _document_result_json(ref, asset, document)
            asset, content_part, marker = await resolve_view_content(
                ref,
                scope_type=scope_type,
                scope_id=scope_id,
                user=user,
                agent=agent,
                model_config=chat_model.model,
                materialize=False,
                extracted_text=extracted_text,
                selection=selection,
            )
            return AssetViewResult(
                display_result={
                    "kind": "asset.view",
                    "version": 1,
                    "ref": ref,
                    "modality": json.loads(marker)["modality"],
                    "mime_type": asset.content_type,
                    "filename": asset.display_filename,
                    "checksum": asset.checksum,
                    "extracted_text": extracted_text,
                    "size": asset.size,
                },
                llm_result=marker,
            )
    except RuntimeError as exc:
        logger.warning("Asset tool storage error: %s", exc)
        return json.dumps({"error": t("file_not_found")}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("Asset tool failed: %s", exc)
        return json.dumps({"error": t("tool_execution_failed")}, ensure_ascii=False)


_CHAT_MEMORY_TOOL_NAMES = frozenset(
    {
        "create_memory_entity",
        "create_memory_relation",
        "update_memory_entity",
        "search_memory",
        "get_memory_subgraph",
    }
)


def _skill_definition_version(skill: Any, config: dict[str, Any]) -> int:
    """Bind the stable tool definition to the real Skill content and config.

    A pending approval stores this version. Editing the Skill (version, package
    content, schema or the Agent's config) changes the version, so resuming the
    old approval is rejected instead of executing changed code.
    """
    import hashlib

    payload = {
        "id": str(getattr(skill, "id", "")),
        "version": getattr(skill, "version", None),
        "package_hash": getattr(skill, "package_hash", None),
        "package_path": getattr(skill, "package_path", None),
        "source_type": getattr(skill, "source_type", None),
        "source_uri": getattr(skill, "source_uri", None),
        "source_ref": getattr(skill, "source_ref", None),
        "source_subdir": getattr(skill, "source_subdir", None),
        "input_schema": getattr(skill, "input_schema", None),
        "default_config": getattr(skill, "default_config", None),
        "config": config,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return max(1, int(hashlib.sha256(encoded).hexdigest()[:12], 16))


def _is_policy_managed_tool(tool_name: str) -> bool:
    from app.api.v1.endpoints.chat_helpers.asset_tools import ASSET_TOOL_NAMES

    return (
        tool_name.startswith("skill_")
        or tool_name == "knowledge_search"
        or tool_name in _CHAT_MEMORY_TOOL_NAMES
        or tool_name in ASSET_TOOL_NAMES
    )


async def _policy_tool_context(
    *,
    agent: Any,
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any,
) -> Any:
    """Trusted call context for operations resolved before builtin dispatch.

    Entrypoint and interactivity come only from the runtime identity. When no
    identity was established the call is treated as non-interactive, so an
    approval that needs the caller fails closed instead of silently executing.
    """
    from app.models.tool_approval import ExecutionEntrypoint
    from app.models.user import User
    from app.schemas.response import BusinessError
    from app.services.tool_context import (
        coerce_execution_entrypoint,
        coerce_execution_run_kind,
        current_tool_identity,
    )
    from app.services.tool_execution import ToolCallContext

    team_id = getattr(agent, "team_id", None) if agent else None
    if agent is None or team_id is None:
        raise BusinessError(code=403, msg_key="agent_context_required", status_code=403)
    actor = (
        await User.get_or_none(id=getattr(user, "id", None))
        if getattr(user, "id", None)
        else None
    )
    if actor is None:
        raise BusinessError(code=403, msg_key="user_context_required", status_code=403)

    runtime = current_tool_identity()
    if runtime is not None:
        entrypoint = coerce_execution_entrypoint(
            runtime.entrypoint, default=ExecutionEntrypoint.CHAT.value
        )
        entrypoint_id = runtime.entrypoint_id or (
            str(workflow_run_id)
            if workflow_run_id is not None
            else str(conversation_id)
            if conversation_id is not None
            else str(agent.id)
        )
        interactive = runtime.interactive
    else:
        entrypoint = (
            ExecutionEntrypoint.WORKFLOW
            if workflow_run_id is not None
            else ExecutionEntrypoint.CHAT
        )
        entrypoint_id = str(
            workflow_run_id
            if workflow_run_id is not None
            else conversation_id
            if conversation_id is not None
            else agent.id
        )
        # No trusted origin: fail closed for caller-gated approvals.
        interactive = False
    return ToolCallContext(
        actor=actor,
        team_id=team_id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
        run_kind=(
            coerce_execution_run_kind(getattr(runtime, "run_kind", "agent"))
            if runtime and runtime.run_id
            else None
        ),
        run_id=runtime.run_id if runtime else None,
        tool_call_id=runtime.tool_call_id if runtime else None,
        interactive=interactive,
    )


async def _resolve_policy_invoke(
    tool_name: str,
    *,
    agent: Any,
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any,
    session_id: str | None,
) -> tuple[Any, Any]:
    """Resolve the stable definition and the real operation for a managed tool."""
    from app.services.builtin_tools import get_builtin_definition

    if tool_name.startswith("skill_"):
        from app.services.skill import SkillService
        from app.llm.tools import tool_registry

        # Authorization stays ahead of approval: the Skill must belong to the
        # Agent and its effective config is resolved before the execution row.
        skill, skill_config = await SkillService.resolve_agent_skill_tool(
            agent, tool_name
        )
        # The stable definition is keyed by the real skill tool name (which
        # embeds the Skill id) and versioned by a fingerprint over the actual
        # Skill content and config. There is no synthetic registry entry.
        descriptor = {
            "name": tool_name,
            "description": (
                skill.description or skill.display_name or skill.name or tool_name
            ),
            "parameters": [],
            "definition_version": _skill_definition_version(skill, skill_config),
        }
        definition = await get_builtin_definition(
            agent.team_id, tool_name, descriptor=descriptor
        )
        skill_tool = SkillService.to_tool_info(skill, config=skill_config)

        async def invoke(parameters: dict, _resolved: Any) -> Any:
            return await tool_registry.execute_tool_info(
                skill_tool,
                parameters,
                agent=agent,
                session_id=session_id,
            )

        return definition, invoke

    definition = await get_builtin_definition(agent.team_id, tool_name)

    async def invoke(parameters: dict, _resolved: Any) -> Any:
        if tool_name == "knowledge_search":
            return await _execute_knowledge_search(parameters, agent)
        if tool_name in _CHAT_MEMORY_TOOL_NAMES:
            return await _execute_memory_tool(tool_name, parameters, user)
        return await _execute_asset_tool(
            tool_name,
            parameters,
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
            session_id=session_id,
        )

    return definition, invoke


async def _execute_policy_managed_tool(
    tool_name: str,
    arguments: dict,
    *,
    agent: Any,
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any,
    session_id: str | None,
) -> Any:
    """One authorization/approval boundary for early chat tool operations.

    Assets, knowledge search, user memory and Agent skills used to execute
    inline before any approval gate. They now share the stored-tool boundary:
    a stable per-team ``Tool`` row (the registry definition is reused when one
    exists), identical team authorization, and one approval execution. The
    operation itself runs only inside ``execute_stored_tool`` after the gate
    opens; a pending execution returns ``ToolInteractionRequest`` unchanged.
    """
    from app.core.i18n import t
    from app.llm.tools.interaction import ToolInteractionRequest
    from app.schemas.response import BusinessError
    from app.services.error_messages import exception_to_user_message
    from app.services.tool_execution import PendingToolApproval, execute_stored_tool

    if tool_name == "knowledge_search" and agent is None:
        return json.dumps({"error": t("agent_context_required")})
    if tool_name in _CHAT_MEMORY_TOOL_NAMES and user is None:
        return json.dumps({"error": t("user_context_required")})
    if tool_name.startswith("skill_") and agent is None:
        return json.dumps(
            {"error": t("agent_context_required_for_skill")}, ensure_ascii=False
        )

    fallback_key = (
        "skill_execution_failed"
        if tool_name.startswith("skill_")
        else "tool_execution_failed"
    )
    try:
        from dataclasses import replace
        from app.services.tool_context import get_agent_tool_require_approval

        require_approval = get_agent_tool_require_approval(agent, tool_name)
        context = await _policy_tool_context(
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
        context = replace(context, require_approval=require_approval)
        definition, invoke = await _resolve_policy_invoke(
            tool_name,
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
            session_id=session_id,
        )
        result = await execute_stored_tool(
            definition,
            tool_name,
            arguments,
            context,
            invoke,
        )
    except BusinessError as exc:
        return json.dumps(
            {"error": t(exc.msg_key or fallback_key, **exc.kwargs)},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("Policy-managed tool failed: %s", exc)
        return json.dumps(
            {"error": exception_to_user_message(exc, fallback_key=fallback_key)},
            ensure_ascii=False,
        )
    if isinstance(result, PendingToolApproval):
        from app.services.tool_context import current_tool_identity

        runtime = current_tool_identity()
        if runtime is not None and runtime.tool_call_prefix:
            # A workflow Agent node owns a blocking call with no durable pause:
            # an interaction object would be stringified into a fake result.
            # Cancel the unexecuted approval and fail closed explicitly.
            from app.schemas.tool_approval import ToolExecutionCancelReason
            from app.services import tool_approvals

            try:
                await tool_approvals.cancel_execution(
                    result.execution_id,
                    reason=ToolExecutionCancelReason.CANCELLED,
                )
            except Exception:
                logger.warning(
                    "Failed to cancel un-resumable tool approval %s",
                    result.execution_id,
                    exc_info=True,
                )
            return json.dumps(
                {
                    "error": t("tool_approval_unavailable"),
                    "tool_name": tool_name,
                    "success": False,
                },
                ensure_ascii=False,
            )
        return ToolInteractionRequest(
            tool_name=tool_name,
            arguments={
                "interaction_kind": "tool_approval",
                "execution_id": str(result.execution_id),
            },
        )
    return result


async def _execute_knowledge_search(arguments: dict, agent: Any) -> str:
    from app.core.i18n import t

    try:
        from app.models.agent import AgentKnowledgeBase
        from app.services.retrieval import (
            RetrievalRequest,
            RetrievalTarget,
            retrieve,
            validated_search_mode,
        )

        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 5)
        agent_kbs = await AgentKnowledgeBase.filter(agent_id=agent.id).prefetch_related(
            "knowledge_base"
        )
        targets = tuple(
            RetrievalTarget(
                kb_id=link.knowledge_base.id,
                kb_name=link.knowledge_base.name,
                team_id=link.knowledge_base.team_id,
                status=link.knowledge_base.status,
                embedding_model_id=link.knowledge_base.embedding_model_id,
                rerank_model_id=link.knowledge_base.rerank_model_id,
                settings=link.knowledge_base.settings,
                search_mode=validated_search_mode(link.search_mode),
                score_threshold=link.score_threshold,
            )
            for link in agent_kbs
        )
        response = await retrieve(
            RetrievalRequest(query=query, targets=targets, top_k=top_k)
        )
        return json.dumps(
            {"contexts": with_rag_citation_ids(response.results)},
            ensure_ascii=False,
            default=str,
        )
    except Exception as e:
        logger.exception("RAG search failed: %s", e)
        return json.dumps({"error": t("rag_search_failed")})


async def _execute_memory_tool(tool_name: str, arguments: dict, user: Any) -> str:
    from app.services.error_messages import exception_to_user_message
    from app.services.memory import MemoryService

    try:
        user_id = user.id
        if tool_name == "create_memory_entity":
            result = await MemoryService.handle_create_entity(
                user_id=user_id,
                name=arguments.get("name", ""),
                entity_type=arguments.get("entity_type", "fact"),
                description=arguments.get("description"),
                properties=arguments.get("properties"),
            )
        elif tool_name == "create_memory_relation":
            result = await MemoryService.handle_create_relation(
                user_id=user_id,
                source_entity_name=arguments.get("source_entity_name", ""),
                target_entity_name=arguments.get("target_entity_name", ""),
                relation_type=arguments.get("relation_type", "related_to"),
                description=arguments.get("description"),
            )
        elif tool_name == "update_memory_entity":
            result = await MemoryService.handle_update_entity(
                user_id=user_id,
                entity_name=arguments.get("entity_name", ""),
                description=arguments.get("description"),
                properties=arguments.get("properties"),
            )
        elif tool_name == "search_memory":
            top_k_raw = arguments.get("top_k", 5)
            try:
                top_k_val = max(1, min(int(top_k_raw), 10))
            except (ValueError, TypeError):
                top_k_val = 5

            time_window_raw = arguments.get("time_window_days")
            try:
                time_window_val = (
                    int(time_window_raw) if time_window_raw is not None else None
                )
            except (ValueError, TypeError):
                time_window_val = None

            result = await MemoryService.handle_search_memory(
                user_id=user_id,
                query=arguments.get("query", ""),
                top_k=top_k_val,
                time_window_days=time_window_val,
                entity_type=arguments.get("entity_type"),
            )
        else:
            entity_ids = arguments.get("entity_ids", [])
            if not isinstance(entity_ids, list):
                entity_ids = []
            relation_types = arguments.get("relation_types")
            if not isinstance(relation_types, list):
                relation_types = None
            try:
                max_depth = max(1, min(int(arguments.get("max_depth", 1)), 3))
            except (ValueError, TypeError):
                max_depth = 1
            result = await MemoryService.handle_get_memory_subgraph(
                user_id=user_id,
                entity_ids=entity_ids,
                max_depth=max_depth,
                direction=arguments.get("direction", "both"),
                relation_types=relation_types,
            )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.exception("Memory tool failed: %s", e)
        return json.dumps(
            {
                "error": exception_to_user_message(
                    e, fallback_key="memory_tool_execution_failed"
                )
            },
            ensure_ascii=False,
        )


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    agent: "Agent | None" = None,
    tool_timeouts: dict | None = None,
    user: Any = None,
    session_id: str | None = None,
    current_images: list[Any] | None = None,
    conversation_id: Any = None,
    workflow_run_id: Any = None,
) -> Any:
    """Execute a tool and return the result payload."""
    from app.core.i18n import t
    from app.llm.tools import tool_registry

    if tool_name == "ask_user":
        # In-band interaction, not an external execution: no approval gate.
        return await tool_registry.execute(tool_name, arguments)

    from app.services.error_messages import exception_to_user_message

    if _is_policy_managed_tool(tool_name):
        return await _execute_policy_managed_tool(
            tool_name,
            arguments,
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
            session_id=session_id,
        )

    if tool_timeouts is None:
        tool_timeouts = {
            "http": 30,
            "code": 60,
            "mcp": 60,
            "download": 60,
        }

    if tool_name.startswith(("mcp_", "custom_")):
        from app.services.agent_tool_execution import execute_agent_stored_tool
        from app.llm.tools.interaction import ToolInteractionRequest
        from app.schemas.response import BusinessError

        try:
            result = await execute_agent_stored_tool(agent, tool_name, arguments, user)
        except BusinessError as exc:
            return json.dumps(
                {"error": t(exc.msg_key or "tool_execution_failed")},
                ensure_ascii=False,
            )
        if isinstance(result, ToolInteractionRequest):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)

    # Try to execute as a registered builtin or skill-attached sandbox tool
    tool_info = tool_registry.get_tool(tool_name)
    sandbox_tool_class = tool_registry.get_sandbox_tool_class(tool_name)
    if (tool_info and tool_info.handler) or sandbox_tool_class:
        from app.llm.tools.interaction import ToolInteractionRequest
        from app.models.tool_approval import ExecutionEntrypoint
        from app.models.user import User
        from app.schemas.response import BusinessError
        from app.services.tool import ToolExecutor
        from app.services.tool_context import (
            coerce_execution_entrypoint,
            coerce_execution_run_kind,
            current_tool_identity,
        )
        from app.services.tool_execution import PendingToolApproval, ToolCallContext

        agent_tool_config: dict[str, Any] = {}
        binding: dict[str, Any] = {
            "connection_mode": None,
            "connection_id": None,
        }
        if agent and getattr(agent, "tools_config", None):
            for tc in agent.tools_config:
                if (
                    isinstance(tc, dict)
                    and tc.get("type") == "builtin"
                    and tc.get("name") == tool_name
                ):
                    agent_tool_config = tc.get("config") or {}
                    from app.services.builtin_tools import (
                        extract_builtin_binding,
                    )

                    binding = extract_builtin_binding(tc)
                    break

        # 搜索引擎由 agent 编排配置严格决定，不交由模型决定
        if tool_name == "web_search":
            arguments["search_engine"] = agent_tool_config.get("engine") or "auto"

        team_id = getattr(agent, "team_id", None) if agent else None
        actor = (
            await User.get_or_none(id=getattr(user, "id", None))
            if getattr(user, "id", None)
            else None
        )
        if agent is None or team_id is None or actor is None:
            return json.dumps({"error": t("user_context_required")}, ensure_ascii=False)

        runtime = current_tool_identity()
        from app.services.builtin_tools import parse_optional_uuid

        try:
            bound_connection_id = parse_optional_uuid(binding["connection_id"])
        except BusinessError as e:
            return json.dumps(
                {"error": t(e.msg_key or "tool_connection_invalid")},
                ensure_ascii=False,
            )
        from app.services.tool_context import get_agent_tool_require_approval

        require_approval = get_agent_tool_require_approval(agent, tool_name)
        context = ToolCallContext(
            actor=actor,
            team_id=team_id,
            entrypoint=(
                coerce_execution_entrypoint(runtime.entrypoint, default="chat")
                if runtime
                else ExecutionEntrypoint.CHAT
            ),
            entrypoint_id=(
                runtime.entrypoint_id
                if runtime and runtime.entrypoint_id
                else (str(conversation_id) if conversation_id else str(agent.id))
            ),
            run_kind=(
                coerce_execution_run_kind(getattr(runtime, "run_kind", "agent"))
                if runtime and runtime.run_id
                else None
            ),
            run_id=runtime.run_id if runtime else None,
            tool_call_id=runtime.tool_call_id if runtime else None,
            connection_mode=binding["connection_mode"],
            connection_id=bound_connection_id,
            interactive=runtime.interactive if runtime else True,
            require_approval=require_approval,
        )

        try:
            result = await ToolExecutor().execute_builtin_tool(
                tool_name=tool_name,
                arguments=arguments,
                team_id=team_id,
                context=context,
                conversation_id=conversation_id,
                workflow_run_id=workflow_run_id,
                agent_tool_config=agent_tool_config,
                agent=agent,
                user=user,
                session_id=session_id,
                current_images=current_images,
            )
            if isinstance(result, PendingToolApproval):
                return ToolInteractionRequest(
                    tool_name=tool_name,
                    arguments={
                        "interaction_kind": "tool_approval",
                        "execution_id": str(result.execution_id),
                    },
                )
            return result
        except BusinessError as e:
            return json.dumps(
                {"error": t(e.msg_key or "tool_execution_failed", **e.kwargs)},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.exception("Builtin tool execution failed: %s", e)
            return json.dumps(
                {
                    "error": exception_to_user_message(
                        e, fallback_key="tool_execution_failed"
                    )
                },
                ensure_ascii=False,
            )

    # Tool not found
    return json.dumps(
        {"error": t("tool_not_found", tool_name=tool_name)}, ensure_ascii=False
    )


async def build_file_content_for_context(
    agent: "Agent",
    file_urls: list[Any] | None,
    legacy_files: list[Any] | None,
    user_locale: str | None,
    tool_timeouts: dict[str, Any] | None,
    user: Any,
) -> tuple[str, list[dict[str, Any]] | None]:
    """Describe attachments as references; never inline extracted text."""
    if not agent.enable_attachments:
        return "", None

    from app.api.v1.endpoints.chat_helpers.asset_tools import (
        describe_attachment_references,
    )

    documents = describe_attachment_references(
        [*(file_urls or []), *(legacy_files or [])]
    )
    if not documents:
        return "", None

    return json.dumps({"documents": documents}, ensure_ascii=False), None


def _get_item_value(item: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object by key."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)

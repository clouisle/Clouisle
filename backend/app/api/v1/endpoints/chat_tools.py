"""Chat tool execution functions."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.tool import Tool

logger = logging.getLogger(__name__)


async def _execute_asset_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    agent: "Agent | None",
    user: Any,
    conversation_id: Any,
    session_id: str | None = None,
) -> str:
    from uuid import UUID

    from app.models.asset import AssetScopeType
    from app.schemas.response import BusinessError
    from app.services.asset import asset_service
    from app.services.file_parser import FileParseConfig, file_parser_service
    from app.services.upload_storage import get_upload_storage_backend
    from app.api.v1.endpoints.upload import UPLOAD_ROOT

    from app.core.i18n import t

    if not agent or not user:
        return json.dumps({"error": t("agent_context_required")}, ensure_ascii=False)
    ref = arguments.get("ref")
    if not isinstance(ref, str):
        return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
    if not conversation_id:
        return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
    try:
        scope_id = UUID(str(conversation_id))
    except (ValueError, AttributeError):
        return json.dumps({"error": t("validation_error")}, ensure_ascii=False)
    try:
        asset = await asset_service.resolve_ref(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=scope_id,
            ref=ref,
            team_id=getattr(agent, "team_id", None),
            user_id=user.id,
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
                input_files=[
                    SandboxInputFileSpec(
                        target_path=safe_path,
                        asset_id=asset.id,
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
        storage = await get_upload_storage_backend(UPLOAD_ROOT)
        if tool_name == "read_asset":
            if "read" not in asset_service.capabilities(asset):
                return json.dumps(
                    {"error": t("unsupported_file_type")}, ensure_ascii=False
                )
            content = await asset_service.read(asset, storage=storage)
            max_chars = min(max(int(arguments.get("max_chars", 12000)), 1), 50000)
            text = content.decode("utf-8", errors="replace")[:max_chars]
            return json.dumps(
                {
                    "ref": ref,
                    "filename": asset.display_filename,
                    "content": text,
                },
                ensure_ascii=False,
            )
        if "parse" not in asset_service.capabilities(asset):
            return json.dumps({"error": t("unsupported_file_type")}, ensure_ascii=False)
        content = await asset_service.read(asset, storage=storage)
        parse_config = FileParseConfig.model_validate(
            getattr(agent, "attachment_config", None) or {}
        )
        parsed = await file_parser_service.parse_file(
            content,
            asset.original_filename,
            parse_config,
        )
        return json.dumps(
            {
                "ref": ref,
                "filename": parsed.filename,
                "content": parsed.content,
                "truncated": parsed.truncated,
            },
            ensure_ascii=False,
        )
    except RuntimeError as exc:
        logger.warning("Asset tool storage error: %s", exc)
        return json.dumps({"error": t("file_not_found")}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("Asset tool failed: %s", exc)
        return json.dumps({"error": t("tool_execution_failed")}, ensure_ascii=False)


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    agent: "Agent | None" = None,
    tool_timeouts: dict | None = None,
    user: Any = None,
    session_id: str | None = None,
    current_images: list[Any] | None = None,
    conversation_id: Any = None,
) -> Any:
    """Execute a tool and return the result payload."""
    from app.core.i18n import t
    from app.models.tool import Tool, CustomToolType
    from app.llm.tools import tool_registry
    from app.services.error_messages import exception_to_user_message

    if tool_name in {"inspect_asset", "read_asset", "parse_asset", "materialize_asset"}:
        return await _execute_asset_tool(
            tool_name,
            arguments,
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            session_id=session_id,
        )

    if tool_timeouts is None:
        tool_timeouts = {
            "http": 30,
            "code": 60,
            "mcp": 60,
            "download": 60,
        }

    # Knowledge base search
    if tool_name == "knowledge_search":
        if not agent:
            return json.dumps({"error": t("agent_context_required")})

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
            agent_kbs = await AgentKnowledgeBase.filter(
                agent_id=agent.id
            ).prefetch_related("knowledge_base")
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
                {"contexts": response.results}, ensure_ascii=False, default=str
            )
        except Exception as e:
            logger.exception("RAG search failed: %s", e)
            return json.dumps({"error": t("rag_search_failed")})

    # Memory tools
    memory_tools = {
        "create_memory_entity",
        "create_memory_relation",
        "update_memory_entity",
        "search_memory",
    }
    if tool_name in memory_tools:
        if not user:
            return json.dumps({"error": t("user_context_required")})
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
            else:
                result = await MemoryService.handle_search_memory(
                    user_id=user_id,
                    query=arguments.get("query", ""),
                    top_k=arguments.get("top_k", 5),
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

    # Skill tool (format: skill_<name>_<short_id>)
    if tool_name.startswith("skill_"):
        from app.services.skill import SkillService
        from app.schemas.response import BusinessError

        if not agent:
            return json.dumps(
                {"error": t("agent_context_required_for_skill")}, ensure_ascii=False
            )

        try:
            skill, skill_config = await SkillService.resolve_agent_skill_tool(
                agent,
                tool_name,
            )
            skill_tool = SkillService.to_tool_info(skill, config=skill_config)
            return await tool_registry.execute_tool_info(
                skill_tool,
                arguments,
                agent=agent,
                session_id=session_id,
            )
        except BusinessError as e:
            return json.dumps(
                {"error": t(e.msg_key or "skill_execution_failed", **e.kwargs)},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.exception("Skill execution failed: %s", e)
            return json.dumps(
                {
                    "error": exception_to_user_message(
                        e, fallback_key="skill_execution_failed"
                    )
                },
                ensure_ascii=False,
            )

    # MCP tool (format: mcp_<server_name>_<tool_name>)
    if tool_name.startswith("mcp_"):
        from app.llm.tools.mcp_client import execute_mcp_tool

        parts = tool_name.split("_", 2)
        if len(parts) >= 3:
            server_name = parts[1]
            actual_tool_name = parts[2]
            try:
                server_tool = await Tool.filter(
                    name=server_name, type="mcp", is_enabled=True
                ).first()
                if not server_tool or not server_tool.mcp_config:
                    return json.dumps(
                        {
                            "error": t(
                                "mcp_tool_missing_configuration", tool_name=server_name
                            )
                        },
                        ensure_ascii=False,
                    )
                mcp_result = await execute_mcp_tool(
                    mcp_config=server_tool.mcp_config,
                    tool_name=actual_tool_name,
                    arguments=arguments,
                    timeout=tool_timeouts.get("mcp", 60),
                )
                return json.dumps(
                    {
                        "success": mcp_result.success,
                        "result": mcp_result.result,
                        "error": mcp_result.error,
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                logger.exception("MCP tool execution failed: %s", e)
                return json.dumps(
                    {
                        "error": exception_to_user_message(
                            e, fallback_key="mcp_tool_execution_failed"
                        )
                    },
                    ensure_ascii=False,
                )
        return json.dumps({"error": t("invalid_mcp_tool_name")}, ensure_ascii=False)

    # Custom tool (format: custom_<name>)
    if tool_name.startswith("custom_"):
        tool_name_without_prefix = tool_name[len("custom_") :]
        tool = await Tool.filter(name=tool_name_without_prefix, is_enabled=True).first()
        if not tool:
            return json.dumps({"error": t("custom_tool_not_found")}, ensure_ascii=False)

        tool_type = tool.custom_type

        # HTTP tool
        if tool_type == CustomToolType.HTTP:
            try:
                from app.llm.tools.executors import (
                    execute_http_tool as _execute_http_tool,
                    format_http_result_for_llm,
                )

                result = await _execute_http_tool(
                    http_config=tool.http_config,
                    arguments=arguments,
                    credentials=tool.credentials,
                    timeout=tool_timeouts.get("http", 30),
                )
                llm_result = format_http_result_for_llm(result)
                return json.dumps(
                    {"result": result, "llm_result": llm_result}, ensure_ascii=False
                )
            except Exception as e:
                logger.exception("HTTP tool execution failed: %s", e)
                return json.dumps(
                    {
                        "error": exception_to_user_message(
                            e, fallback_key="tool_execution_failed"
                        )
                    },
                    ensure_ascii=False,
                )

        # Code tool
        if tool_type == CustomToolType.CODE:
            try:
                result = await _execute_code_tool(
                    tool=tool,
                    arguments=arguments,
                    tool_timeouts=tool_timeouts,
                    session_id=session_id,
                    agent=agent,
                )
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.exception("Code tool execution failed: %s", e)
                return json.dumps(
                    {
                        "error": exception_to_user_message(
                            e, fallback_key="code_tool_execution_failed"
                        )
                    },
                    ensure_ascii=False,
                )

        return json.dumps({"error": t("unsupported_tool_type")}, ensure_ascii=False)

    # File download tool
    if tool_name == "file_download":
        try:
            from app.llm.tools.executors import (
                execute_http_tool as _execute_http_tool,
                format_http_result_for_llm,
            )

            result = await _execute_http_tool(
                http_config={"url": arguments.get("url", ""), "method": "GET"},
                arguments={},
                timeout=tool_timeouts.get("download", 60),
            )
            llm_result = format_http_result_for_llm(result)
            return json.dumps(
                {"result": result, "llm_result": llm_result}, ensure_ascii=False
            )
        except Exception as e:
            logger.exception("File download failed: %s", e)
            return json.dumps(
                {
                    "error": exception_to_user_message(
                        e, fallback_key="tool_execution_failed"
                    )
                },
                ensure_ascii=False,
            )

    # Try to execute as a registered builtin or skill-attached sandbox tool
    tool_info = tool_registry.get_tool(tool_name)
    sandbox_tool_class = tool_registry.get_sandbox_tool_class(tool_name)
    if (tool_info and tool_info.handler) or sandbox_tool_class:
        try:
            credentials = None
            if (
                tool_info
                and tool_info.handler
                and _tool_accepts_credentials(tool_info.handler)
            ):
                credentials = await _get_builtin_tool_credentials(tool_name, agent)
            return await tool_registry.execute(
                tool_name,
                arguments,
                credentials=credentials,
                session_id=session_id,
                agent=agent,
                user=user,
                current_images=current_images,
                conversation_id=conversation_id,
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


def _tool_accepts_credentials(handler: Any) -> bool:
    import inspect

    return "credentials" in inspect.signature(handler).parameters


async def _get_builtin_tool_credentials(
    tool_name: str, agent: "Agent | None"
) -> dict[str, str]:
    from app.models.tool_config import ToolConfig

    credentials: dict[str, str] = {}
    team_id = getattr(agent, "team_id", None) if agent else None

    if team_id:
        tool_config = await ToolConfig.filter(
            tool_name=tool_name, team_id=team_id
        ).first()
        if tool_config:
            credentials = tool_config.credentials or {}

    if not credentials:
        global_config = await ToolConfig.filter(
            tool_name=tool_name, team_id=None
        ).first()
        if global_config:
            credentials = global_config.credentials or {}

    if not credentials and tool_name == "web_search":
        from app.core.config import settings

        if settings.TAVILY_API_KEY:
            credentials["TAVILY_API_KEY"] = settings.TAVILY_API_KEY

    return credentials


async def _execute_code_tool(
    tool: "Tool",
    arguments: dict,
    tool_timeouts: dict | None = None,
    session_id: str | None = None,
    agent: "Agent | None" = None,
) -> dict[str, Any]:
    """Execute a code tool."""
    from app.llm.tools.sandbox import execute_code
    from app.services.error_messages import exception_to_user_message

    code_config = tool.code_config or {}
    language = code_config.get("language", "python")
    code = code_config.get("code", "")
    timeout = tool_timeouts.get("code", 60) if tool_timeouts else 60

    try:
        result = await execute_code(
            language=language,
            code=code,
            params=arguments,
            timeout=timeout,
            session_id=session_id,
            agent_id=str(agent.id) if agent and getattr(agent, "id", None) else None,
            team_id=str(agent.team_id)
            if agent and getattr(agent, "team_id", None)
            else None,
        )
        return {
            "success": result.success,
            "result": result.result,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
        }
    except Exception as e:
        logger.exception("Code tool execution failed: %s", e)
        return {
            "error": exception_to_user_message(
                e, fallback_key="code_tool_execution_failed"
            ),
            "success": False,
        }


# ============ Additional Tool Functions ============


async def execute_http_tool(
    tool: "Tool",
    arguments: dict,
    timeout: float = 30.0,
) -> str:
    """
    Execute an HTTP-based custom tool.

    Args:
        tool: The Tool model instance
        arguments: Tool arguments passed from LLM
        timeout: Execution timeout in seconds

    Returns:
        JSON string with execution result
    """
    from app.llm.tools.executors import (
        execute_http_tool as shared_execute_http_tool,
        format_http_result_for_llm,
    )

    result = await shared_execute_http_tool(
        http_config=tool.http_config,
        arguments=arguments,
        credentials=tool.credentials,
        timeout=timeout,
    )
    return format_http_result_for_llm(result)


async def execute_code_tool(
    tool: "Tool",
    arguments: dict,
    timeout: float = 60.0,
) -> str:
    """
    Execute a code-based custom tool.

    Args:
        tool: The Tool model instance
        arguments: Tool arguments passed from LLM
        timeout: Execution timeout in seconds

    Returns:
        JSON string with execution result
    """
    from app.core.i18n import t
    from app.llm.tools.sandbox import execute_code
    from app.services.error_messages import exception_to_user_message

    code_config = tool.code_config or {}
    language = code_config.get("language", "python")
    code = code_config.get("code", "")

    if not code:
        return json.dumps({"error": t("tool_code_not_defined")}, ensure_ascii=False)

    try:
        exec_result = await execute_code(
            language=language,
            code=code,
            params=arguments,
            timeout=timeout,
        )

        if exec_result.success:
            result = exec_result.result
            # Include stdout logs if present
            if exec_result.stdout:
                if isinstance(result, dict):
                    result["__logs__"] = exec_result.stdout
                else:
                    result = {"value": result, "__logs__": exec_result.stdout}
            return (
                json.dumps(result, ensure_ascii=False)
                if isinstance(result, (dict, list))
                else str(result)
            )
        else:
            return json.dumps(
                {
                    "error": exec_result.error or t("code_execution_failed"),
                    "logs": exec_result.stdout or "",
                },
                ensure_ascii=False,
            )

    except Exception as e:
        logger.exception("Code tool execution error: %s", e)
        return json.dumps(
            {
                "error": exception_to_user_message(
                    e,
                    fallback_key="code_tool_execution_failed",
                )
            },
            ensure_ascii=False,
        )


async def build_file_content_for_prompt(
    agent: "Agent",
    file_urls: list[Any] | None,
    legacy_files: list[Any] | None,
    user_locale: str | None,
    tool_timeouts: dict[str, Any] | None,
    user: Any,
) -> str:
    content, _ = await build_file_content_for_context(
        agent=agent,
        file_urls=file_urls,
        legacy_files=legacy_files,
        user_locale=user_locale,
        tool_timeouts=tool_timeouts,
        user=user,
    )
    return content


async def build_file_content_for_context(
    agent: "Agent",
    file_urls: list[Any] | None,
    legacy_files: list[Any] | None,
    user_locale: str | None,
    tool_timeouts: dict[str, Any] | None,
    user: Any,
) -> tuple[str, list[dict[str, Any]] | None]:
    """Format only deprecated pre-parsed file payloads for the prompt."""
    from app.services.file_parser import file_parser_service, ParsedFile

    if not agent.enable_attachments:
        return "", None

    parsed_files: list[ParsedFile] = []
    for file_item in legacy_files or []:
        parsed_files.append(
            ParsedFile(
                filename=_get_item_value(file_item, "filename", ""),
                content=_get_item_value(file_item, "content", ""),
                mime_type=_get_item_value(file_item, "mime_type", "text/plain"),
                size=_get_item_value(file_item, "size", 0),
                truncated=bool(_get_item_value(file_item, "truncated", False)),
                original_length=_get_item_value(file_item, "original_length"),
            )
        )

    if not parsed_files:
        return "", None

    return (
        file_parser_service.format_files_for_prompt(parsed_files, locale=user_locale),
        None,
    )


def _get_item_value(item: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object by key."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)

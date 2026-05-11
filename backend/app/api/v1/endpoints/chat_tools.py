"""Chat tool execution functions."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.tool import Tool

logger = logging.getLogger(__name__)


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    agent: "Agent | None" = None,
    tool_timeouts: dict | None = None,
    user: Any = None,
    session_id: str | None = None,
) -> Any:
    """Execute a tool and return the result payload."""
    from app.core.i18n import t
    from app.models.tool import Tool, CustomToolType
    from app.llm.tools import tool_registry
    from app.services.error_messages import resolve_user_visible_error

    # Initialize default timeouts if not provided
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
            from app.services.vector_store import VectorStore

            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            contexts = []
            agent_kbs = await AgentKnowledgeBase.filter(
                agent_id=agent.id
            ).prefetch_related("knowledge_base")

            for agent_kb in agent_kbs:
                kb = agent_kb.knowledge_base
                vector_store = VectorStore(
                    embedding_model_id=str(kb.embedding_model_id)
                    if kb.embedding_model_id
                    else None,
                    rerank_model_id=str(kb.rerank_model_id)
                    if getattr(kb, "rerank_model_id", None)
                    else None,
                    team_id=str(kb.team_id) if kb.team_id else None,
                )
                results = await vector_store.search(
                    kb_id=kb.id,
                    query=query,
                    search_mode=agent_kb.search_mode,
                    top_k=top_k,
                    score_threshold=agent_kb.score_threshold,
                )
                for result in results:
                    contexts.append(
                        {
                            "kb_id": str(kb.id),
                            "kb_name": kb.name,
                            "document_id": str(result.get("document_id")),
                            "document_name": result.get("document_name"),
                            "content": result.get("content"),
                            "score": result.get("score"),
                        }
                    )
            return json.dumps({"contexts": contexts}, ensure_ascii=False)
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
            return json.dumps({"error": str(e)}, ensure_ascii=False)

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
                    "error": resolve_user_visible_error(
                        str(e),
                        fallback_key="skill_execution_failed",
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
                result = await execute_mcp_tool(
                    mcp_config=server_tool.mcp_config,
                    tool_name=actual_tool_name,
                    arguments=arguments,
                    timeout=tool_timeouts.get("mcp", 60),
                )
                return json.dumps(
                    {
                        "success": result.success,
                        "result": result.result,
                        "error": result.error,
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                logger.exception("MCP tool execution failed: %s", e)
                return json.dumps(
                    {
                        "error": resolve_user_visible_error(
                            str(e), fallback_key="mcp_tool_failed"
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
                        "error": resolve_user_visible_error(
                            str(e), fallback_key="http_tool_failed"
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
                        "error": resolve_user_visible_error(
                            str(e), fallback_key="code_tool_failed"
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
                    "error": resolve_user_visible_error(
                        str(e), fallback_key="download_failed"
                    )
                },
                ensure_ascii=False,
            )

    # Try to execute as a registered builtin or skill-attached sandbox tool
    tool_info = tool_registry.get_tool(tool_name)
    sandbox_tool_class = tool_registry.get_sandbox_tool_class(tool_name)
    if (tool_info and tool_info.handler) or sandbox_tool_class:
        try:
            return await tool_registry.execute(
                tool_name,
                arguments,
                session_id=session_id,
                agent=agent,
                user=user,
            )
        except Exception as e:
            logger.exception("Builtin tool execution failed: %s", e)
            return json.dumps(
                {
                    "error": resolve_user_visible_error(
                        str(e), fallback_key="tool_execution_failed"
                    )
                },
                ensure_ascii=False,
            )

    # Tool not found
    return json.dumps(
        {"error": t("tool_not_found", tool_name=tool_name)}, ensure_ascii=False
    )


async def _execute_code_tool(
    tool: "Tool",
    arguments: dict,
    tool_timeouts: dict | None = None,
    session_id: str | None = None,
    agent: "Agent | None" = None,
) -> dict[str, Any]:
    """Execute a code tool."""
    from app.llm.tools.sandbox import execute_code

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
        return {"error": str(e), "success": False}


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
    from app.services.error_messages import resolve_user_visible_error

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
                "error": resolve_user_visible_error(
                    str(e),
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
    """
    Build file content string for LLM prompt.

    Parses uploaded files and returns formatted content for the model.

    Args:
        agent: The agent
        file_urls: List of file URL dictionaries with url, filename, mime_type, size
        legacy_files: List of legacy file dictionaries with content already
        user_locale: User's locale for i18n
        tool_timeouts: Timeout configuration for downloads
        user: User instance

    Returns:
        Formatted file content string for the prompt
    """
    from app.core.i18n import t
    from app.services.file_parser import (
        file_parser_service,
        ParsedFile,
        FileParseConfig,
    )

    if not agent.enable_file_upload:
        return ""

    parsed_files: list[ParsedFile] = []
    file_config = agent.file_upload_config or {}
    parser_config = file_config.get("parser")
    parse_config = FileParseConfig(
        max_content_length=file_config.get("max_content_length", 100000),
        truncate_strategy=file_config.get("truncate_strategy", "end"),
    )

    if file_urls and parser_config:
        parser_type = parser_config.get("type", "builtin")
        parser_name = parser_config.get("name", "markitdown")
        parser_tool_id = parser_config.get("tool_id")

        if parser_type == "builtin" and parser_name == "markitdown":
            from app.api.v1.endpoints.upload import UPLOAD_ROOT, _resolve_upload_path

            for f in file_urls:
                filename = _get_item_value(f, "filename", "")
                mime_type = _get_item_value(f, "mime_type", "application/octet-stream")
                size = _get_item_value(f, "size", 0)
                url = _get_item_value(f, "url", "")
                if not url:
                    continue
                try:
                    prefix = "/api/v1/upload/files/"
                    if not url.startswith(prefix):
                        raise ValueError("only_upload_file_urls_are_allowed")
                    relative_parts = [
                        unquote(part) for part in url[len(prefix) :].split("/")
                    ]
                    if len(relative_parts) != 4:
                        raise ValueError("invalid_upload_file_url")
                    file_path = _resolve_upload_path(*relative_parts)
                    if not file_path.is_file():
                        raise ValueError("upload_file_not_found")
                    file_path.relative_to(UPLOAD_ROOT)
                    parsed_files.append(
                        await file_parser_service.parse_file(
                            file_path.read_bytes(),
                            filename,
                            parse_config,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to parse file %s: %s", filename, e)
                    parsed_files.append(
                        ParsedFile(
                            filename=filename,
                            content=t("file_parse_failed_placeholder"),
                            mime_type=mime_type,
                            size=size,
                        )
                    )
        elif parser_type == "custom" and parser_tool_id:
            from app.models.tool import Tool

            custom_tool = await Tool.filter(id=parser_tool_id, is_enabled=True).first()
            if custom_tool:
                try:
                    urls = [_get_item_value(f, "url", "") for f in file_urls]
                    result = await execute_tool_call(
                        f"custom_{custom_tool.name}",
                        {"files_url": [url for url in urls if url]},
                        agent=agent,
                        tool_timeouts=tool_timeouts,
                        user=user,
                    )
                    display_result = _get_tool_result_display(result)
                    if display_result:
                        parsed_files.append(
                            ParsedFile(
                                filename=t("custom_parser_filename"),
                                content=display_result,
                                mime_type="text/plain",
                                size=len(display_result),
                            )
                        )
                except Exception as e:
                    logger.warning("Custom parser failed: %s", e)
                    parsed_files.append(
                        ParsedFile(
                            filename=t("custom_parser_filename"),
                            content=t("custom_parser_failed_placeholder"),
                            mime_type="text/plain",
                            size=0,
                        )
                    )

    if not parsed_files and legacy_files:
        for f in legacy_files:
            filename = _get_item_value(f, "filename", "")
            content = _get_item_value(f, "content", "")
            mime_type = _get_item_value(f, "mime_type", "text/plain")
            size = _get_item_value(f, "size", 0)
            truncated = _get_item_value(f, "truncated", False)
            original_length = _get_item_value(f, "original_length")
            parsed_files.append(
                ParsedFile(
                    filename=filename,
                    content=content,
                    mime_type=mime_type,
                    size=size,
                    truncated=bool(truncated),
                    original_length=original_length,
                )
            )

    if not parsed_files:
        return ""

    return file_parser_service.format_files_for_prompt(parsed_files, locale=user_locale)


def _get_item_value(item: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object by key."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _get_tool_result_display(result: Any) -> str | None:
    """Extract display string from tool execution result."""
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, str):
        return result
    return str(result) if result is not None else None

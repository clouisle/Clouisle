"""
Agent service for AI assistant functionality.

Provides chat functionality for agents with tools and knowledge bases.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, TYPE_CHECKING, cast

from app.core.i18n import t
from app.llm import model_manager
from app.services.error_messages import resolve_user_visible_error
from app.llm.types import (
    ContentPart,
    ContentType,
    ImageContent,
    Message,
    MessageRole,
    ToolDefinition,
    FunctionDefinition,
)
from app.models.agent import Agent, AgentKnowledgeBase, RAGMode
from app.services.system_prompt import WORKFLOW_MODE, build_system_prompt

if TYPE_CHECKING:
    from app.llm.types.chat import ToolCall

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service for executing agent chat interactions.

    Supports:
    - Streaming and non-streaming responses
    - Tool calling with configurable iterations
    - RAG with knowledge bases
    """

    async def chat(
        self,
        agent: Agent,
        message: str,
        context: dict[str, Any] | None = None,
        user_id: str | None = None,
        max_turns: int = 10,
        conversation_history: list[dict] | None = None,
        user_locale: str | None = None,
        images: list[Any] | None = None,
        files: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a non-streaming chat and return normalized trace data."""
        messages = await self._build_messages(
            agent=agent,
            message=message,
            context=context,
            conversation_history=conversation_history,
            user_locale=user_locale,
            images=images,
            files=files,
        )
        team_id = str(agent.team_id) if agent.team_id else None
        model_id = await self._resolve_model_id(agent)
        tools = await self._get_agent_tools(agent)
        response_text = ""
        tool_calls: list[dict[str, Any]] = []
        dialogue: list[dict[str, Any]] = []
        artifacts: list[Any] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for current_turn in range(1, max_turns + 1):
            if team_id:
                response = await model_manager.team_chat(
                    team_id=team_id,
                    messages=cast(list[Any], messages),
                    tools=tools or None,
                    model_id=model_id,
                    user_id=user_id,
                )
            else:
                response = await model_manager.chat(
                    messages=cast(list[Any], messages),
                    tools=tools or None,
                    model_id=model_id,
                    user_id=user_id,
                )
            usage = getattr(response, "usage", None)
            if usage:
                total_usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                total_usage["completion_tokens"] += (
                    getattr(usage, "completion_tokens", 0) or 0
                )
                total_usage["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
            response_tool_calls = getattr(response, "tool_calls", None) or []
            content = getattr(response, "content", None) or ""
            reasoning_content = getattr(response, "reasoning_content", None)
            if not response_tool_calls:
                response_text = content
                dialogue.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "reasoning_content": reasoning_content,
                        "iteration": current_turn,
                    }
                )
                break
            normalized_calls = [tc.model_dump() for tc in response_tool_calls]
            tool_calls.extend(normalized_calls)
            dialogue.append(
                {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "tool_calls": normalized_calls,
                    "iteration": current_turn,
                }
            )
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    reasoning_content=reasoning_content,
                    tool_calls=response_tool_calls,
                )
            )
            for tool_call in response_tool_calls:
                tool_result = await self._execute_tool(agent=agent, tool_call=tool_call)
                artifacts.extend(self._extract_artifacts(tool_result))
                dialogue.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_call.function.name,
                        "content": str(tool_result),
                        "iteration": current_turn,
                    }
                )
                messages.append(
                    Message(
                        role=MessageRole.TOOL,
                        content=str(tool_result),
                        tool_call_id=tool_call.id,
                    )
                )
        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "usage": total_usage,
            "dialogue": dialogue,
            "artifacts": artifacts,
        }

    async def chat_stream(
        self,
        agent: Agent,
        message: str,
        context: dict[str, Any] | None = None,
        user_id: str | None = None,
        max_turns: int = 10,
        conversation_history: list[dict] | None = None,
        user_locale: str | None = None,
        images: list[Any] | None = None,
        files: list[Any] | None = None,
    ) -> AsyncIterator[str | dict]:
        """Execute a streaming chat and yield normalized trace events."""
        messages = await self._build_messages(
            agent=agent,
            message=message,
            context=context,
            conversation_history=conversation_history,
            user_locale=user_locale,
            images=images,
            files=files,
        )
        team_id = str(agent.team_id) if agent.team_id else None
        model_id = await self._resolve_model_id(agent)
        tools = await self._get_agent_tools(agent)
        dialogue: list[dict[str, Any]] = []
        artifacts: list[Any] = []
        for current_turn in range(1, max_turns + 1):
            accumulated_content = ""
            accumulated_reasoning = ""
            accumulated_tool_calls = []
            final_usage = None
            stream = (
                model_manager.team_chat_stream(
                    team_id=team_id,
                    messages=cast(list[Any], messages),
                    tools=tools or None,
                    model_id=model_id,
                    user_id=user_id,
                )
                if team_id
                else model_manager.chat_stream(
                    messages=cast(list[Any], messages),
                    tools=tools or None,
                    model_id=model_id,
                    user_id=user_id,
                )
            )
            async for chunk in stream:
                delta = getattr(chunk, "delta", None)
                content_delta = getattr(delta, "content", None) or ""
                reasoning_delta = getattr(delta, "reasoning_content", None) or ""
                tool_call_deltas = getattr(delta, "tool_calls", None) or []
                if content_delta:
                    accumulated_content += content_delta
                    yield content_delta
                if reasoning_delta:
                    accumulated_reasoning += reasoning_delta
                    yield {"reasoning": reasoning_delta}
                for tool_call in tool_call_deltas:
                    accumulated_tool_calls.append(tool_call)
                    yield {"tool_call": tool_call.model_dump()}
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage:
                    final_usage = chunk_usage
            if final_usage:
                yield {"usage": final_usage.model_dump()}
            if accumulated_tool_calls:
                normalized_calls = [tc.model_dump() for tc in accumulated_tool_calls]
                dialogue.append(
                    {
                        "role": "assistant",
                        "content": accumulated_content,
                        "reasoning_content": accumulated_reasoning or None,
                        "tool_calls": normalized_calls,
                        "iteration": current_turn,
                    }
                )
                messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content,
                        reasoning_content=accumulated_reasoning or None,
                        tool_calls=accumulated_tool_calls,
                    )
                )
                for tool_call in accumulated_tool_calls:
                    tool_result = await self._execute_tool(
                        agent=agent, tool_call=tool_call
                    )
                    artifacts.extend(self._extract_artifacts(tool_result))
                    dialogue.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_call.function.name,
                            "content": str(tool_result),
                            "iteration": current_turn,
                        }
                    )
                    messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=str(tool_result),
                            tool_call_id=tool_call.id,
                        )
                    )
                    yield {
                        "tool_result": {
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_call.function.name,
                            "result": tool_result,
                        }
                    }
                continue
            dialogue.append(
                {
                    "role": "assistant",
                    "content": accumulated_content,
                    "reasoning_content": accumulated_reasoning or None,
                    "iteration": current_turn,
                }
            )
            yield {"dialogue": dialogue, "artifacts": artifacts}
            break

        else:
            yield {"dialogue": dialogue, "artifacts": artifacts}

    async def _build_messages(
        self,
        agent: Agent,
        message: str,
        context: dict[str, Any] | None = None,
        conversation_history: list[dict] | None = None,
        user_locale: str | None = None,
        images: list[Any] | None = None,
        files: list[Any] | None = None,
    ) -> list[Message]:
        """Build system, history, and current multimodal user messages."""
        messages: list[Message] = []
        base_prompt = agent.system_prompt or ""
        if context:
            base_prompt += "\n\nContext:\n" + "\n".join(
                f"- {k}: {v}" for k, v in context.items()
            )
        system_prompt = build_system_prompt(
            agent,
            base_prompt=base_prompt,
            user_message=message,
            user_locale=user_locale,
            invocation_mode=WORKFLOW_MODE,
        )
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
        for msg in conversation_history or []:
            role = msg.get("role", "user")
            if role in {"user", "assistant", "system"}:
                messages.append(
                    Message(role=MessageRole(role), content=msg.get("content", ""))
                )
        image_parts = []
        for item in images or []:
            url = item.get("url") if isinstance(item, dict) else item
            if url:
                image_parts.append(
                    ContentPart(
                        type=ContentType.IMAGE,
                        image=ImageContent(
                            url=str(url),
                            asset_ref=item.get("asset_ref")
                            if isinstance(item, dict)
                            else None,
                        ),
                    )
                )
        file_content = await self._parse_workflow_files(agent, files)
        if image_parts or file_content:
            parts = [ContentPart(type=ContentType.TEXT, text=message), *image_parts]
            if file_content:
                parts.append(
                    ContentPart(
                        type=ContentType.TEXT,
                        text=f"<uploaded_files>\n{file_content}\n</uploaded_files>",
                    )
                )
            user_content: str | list[ContentPart] = parts
        else:
            user_content = message
        messages.append(Message(role=MessageRole.USER, content=user_content))
        if agent.rag_mode != RAGMode.OFF:
            rag_context = await self._retrieve_rag_context(agent, message)
            if rag_context:
                messages.insert(
                    -1,
                    Message(
                        role=MessageRole.SYSTEM,
                        content=f"Relevant context:\n{rag_context}",
                    ),
                )
        return messages

    @staticmethod
    async def _parse_workflow_files(agent: Agent, files: list[Any] | None) -> str:
        if not files or not agent.enable_attachments:
            return ""
        from app.llm.tools.builtin.file_parser import parse_files

        urls = []
        for item in files:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]))
            elif item:
                urls.append(str(item))
        if not urls:
            return ""
        config = agent.attachment_config or {}
        return await parse_files(
            urls,
            max_content_length=int(config.get("max_content_length", 100000)),
            truncate_strategy=str(config.get("truncate_strategy", "end")),
        )

    @staticmethod
    async def _resolve_model_id(agent: Agent) -> str | None:
        """Resolve the Agent's TeamModel selection to its global model UUID."""
        configured_team_model_id = getattr(agent, "model_id", None)
        if not configured_team_model_id:
            return None
        from app.models.model import TeamModel

        team_model = await TeamModel.filter(
            id=configured_team_model_id,
            team_id=agent.team_id,
        ).first()
        if not team_model:
            raise ValueError("Configured agent model is unavailable")
        return str(team_model.model_id)

    @staticmethod
    def _extract_artifacts(value: Any) -> list[Any]:
        if not isinstance(value, dict):
            return []
        artifacts: list[Any] = []
        for key in ("artifacts", "files"):
            items = value.get(key)
            if isinstance(items, list):
                artifacts.extend(item for item in items if isinstance(item, dict))
        nested = value.get("display_result")
        if isinstance(nested, dict):
            artifacts.extend(AgentService._extract_artifacts(nested))
        return artifacts

    async def _get_agent_tools(self, agent: Agent) -> list[ToolDefinition]:
        """Get tools configured for the agent."""
        tools = []

        tools_config = agent.tools_config or []

        for tool_cfg in tools_config:
            tool_type = tool_cfg.get("type", "")

            if tool_type == "builtin":
                # Built-in tools like web_search, code_interpreter, etc.
                tool_name = tool_cfg.get("name", "")
                tool_def = self._get_builtin_tool(tool_name)
                if tool_def:
                    tools.append(tool_def)
            elif tool_type == "skill":
                from app.services.skill import SkillService

                skill_id = tool_cfg.get("skill_id")
                if skill_id:
                    try:
                        skill = await SkillService.get_skill_for_team(
                            skill_id,
                            agent.team_id,
                            enabled_only=True,
                        )
                        tools.append(SkillService.to_tool_definition(skill))
                    except Exception as e:
                        logger.warning("Failed to get skill tool %s: %s", skill_id, e)
            elif tool_type == "mcp":
                # MCP server tools - would need MCP integration
                pass

        if agent.enable_image_generation:
            media_tool = self._get_builtin_tool("generate_image")
            if media_tool:
                tools.append(media_tool)

        if agent.enable_video_generation:
            media_tool = self._get_builtin_tool("generate_video")
            if media_tool:
                tools.append(media_tool)

        # If agentic RAG, add search tool
        if agent.rag_mode == RAGMode.AGENTIC:
            tools.append(
                ToolDefinition(
                    type="function",
                    function=FunctionDefinition(
                        name="search_knowledge_base",
                        description="Search the agent's knowledge base for relevant information",
                        parameters={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query",
                                },
                            },
                            "required": ["query"],
                        },
                    ),
                )
            )

        return tools

    def _get_builtin_tool(self, name: str) -> ToolDefinition | None:
        """Get a built-in tool definition."""
        from app.llm.tools import tool_registry

        tool_defs = tool_registry.to_openai_tools([name])
        if not tool_defs:
            return None
        return ToolDefinition.model_validate(tool_defs[0])

    async def _execute_tool(
        self,
        agent: Agent,
        tool_call: ToolCall,
    ) -> Any:
        """Execute a tool call and return the result."""
        from app.llm.tools import tool_registry
        from app.models.tool_config import ToolConfig
        import json

        tool_name = tool_call.function.name

        # Parse arguments
        try:
            if isinstance(tool_call.function.arguments, str):
                arguments = json.loads(tool_call.function.arguments)
            else:
                arguments = tool_call.function.arguments or {}
        except json.JSONDecodeError:
            logger.error(
                f"Failed to parse tool arguments: {tool_call.function.arguments}"
            )
            return {"error": t("invalid_tool_arguments")}

        if tool_name.startswith("skill_"):
            from app.services.skill import SkillService
            from app.services.skill_executor import SkillExecutor

            try:
                skill, skill_config = await SkillService.resolve_agent_skill_tool(
                    agent,
                    tool_name,
                )
                result = await SkillExecutor.execute(
                    skill=skill,
                    arguments=arguments,
                    config=skill_config,
                    tenant_id=str(agent.team_id) if agent.team_id else None,
                )
                return result.to_dict()
            except Exception as e:
                logger.exception("Skill execution error: %s", e)
                return {"error": resolve_user_visible_error(str(e))}

        # Get credentials for builtin tools
        if not tool_registry.get_tool(tool_name):
            return {
                "error": t("tool_not_found"),
                "tool_name": tool_name,
                "success": False,
            }

        credentials = {}
        team_id = agent.team_id

        logger.info(
            f"[TOOL EXEC] Executing tool '{tool_name}' for agent {agent.id}, team_id: {team_id}"
        )
        logger.info(f"[TOOL EXEC] Arguments: {arguments}")

        # Try to get team-specific config first
        if team_id:
            logger.info(
                f"[TOOL EXEC] Looking for team config: tool_name={tool_name}, team_id={team_id}"
            )
            tool_config = await ToolConfig.filter(
                tool_name=tool_name, team_id=team_id
            ).first()
            if tool_config:
                credentials = tool_config.credentials or {}
                logger.info(f"[TOOL EXEC] Found team config for {tool_name}")
                logger.info(f"[TOOL EXEC] Credentials keys: {list(credentials.keys())}")
                logger.info(
                    f"[TOOL EXEC] Has TAVILY_API_KEY: {'TAVILY_API_KEY' in credentials}"
                )
            else:
                logger.warning(f"[TOOL EXEC] No team config found for {tool_name}")

        # If no team config, try global config
        if not credentials:
            logger.info(f"[TOOL EXEC] Looking for global config: tool_name={tool_name}")
            global_config = await ToolConfig.filter(
                tool_name=tool_name, team_id=None
            ).first()
            if global_config:
                credentials = global_config.credentials or {}
                logger.info(
                    f"[TOOL EXEC] Found global config for {tool_name}, has credentials: {bool(credentials)}"
                )
            else:
                logger.warning(f"[TOOL EXEC] No global config found for {tool_name}")

        logger.info(
            f"[TOOL EXEC] Final credentials for {tool_name}: {list(credentials.keys())}"
        )
        logger.info(
            f"[TOOL EXEC] Calling tool_registry.execute with credentials: {bool(credentials)}"
        )

        # Execute the tool
        try:
            result = await tool_registry.execute(
                name=tool_name,
                arguments=arguments,
                credentials=credentials,
                agent=agent,
                team_id=str(agent.team_id) if agent.team_id else None,
            )
            return result
        except Exception as e:
            logger.exception(f"Tool execution error: {e}")
            return {
                "error": resolve_user_visible_error(str(e)),
                "success": False,
            }

    async def _retrieve_rag_context(
        self,
        agent: Agent,
        query: str,
    ) -> str | None:
        """Retrieve relevant context from knowledge bases."""
        try:
            # Load agent's knowledge bases
            agent_kbs = await AgentKnowledgeBase.filter(
                agent_id=agent.id
            ).prefetch_related("knowledge_base")

            if not agent_kbs:
                return None

            from app.services.retrieval import (
                RetrievalRequest,
                RetrievalTarget,
                retrieve,
                validated_search_mode,
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
                    top_k=link.retrieval_top_k,
                    score_threshold=link.score_threshold,
                )
                for link in agent_kbs
                if link.knowledge_base
            )
            response = await retrieve(
                RetrievalRequest(query=query, targets=targets, top_k=10)
            )
            if not response.results:
                return None

            context_parts = []
            for chunk in response.results:
                context_parts.append(f"[{chunk['kb_name']}] {chunk.get('content', '')}")

            return "\n\n".join(context_parts)

        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
            return None

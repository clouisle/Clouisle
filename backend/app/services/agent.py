"""
Agent service for AI assistant functionality.

Provides chat functionality for agents with tools and knowledge bases.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, TYPE_CHECKING, cast

from app.core.i18n import t
from app.llm import model_manager
from app.services.error_messages import resolve_user_visible_error
from app.llm.types import Message, MessageRole, ToolDefinition, FunctionDefinition
from app.models.agent import Agent, AgentKnowledgeBase, RAGMode

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
    ) -> dict[str, Any]:
        """
        Execute a non-streaming chat with the agent.

        Args:
            agent: Agent instance
            message: User message
            context: Additional context variables
            user_id: User ID for tracking
            max_turns: Maximum tool call iterations
            conversation_history: Previous messages in the conversation

        Returns:
            dict with response, tool_calls, and usage
        """
        messages = await self._build_messages(
            agent=agent,
            message=message,
            context=context,
            conversation_history=conversation_history,
        )

        tools = await self._get_agent_tools(agent)

        # Get team model or default
        team_id = str(agent.team_id) if agent.team_id else None
        model_id = str(agent.model_id) if agent.model_id else None

        response_text = ""
        tool_calls = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        current_turn = 0
        while current_turn < max_turns:
            current_turn += 1

            response = await model_manager.chat(
                messages=cast(list[Any], messages),
                tools=tools if tools else None,
                team_id=team_id,
                model=model_id,
                user_id=user_id,
            )

            # Accumulate usage
            if response.usage:
                total_usage["prompt_tokens"] += response.usage.prompt_tokens or 0
                total_usage["completion_tokens"] += (
                    response.usage.completion_tokens or 0
                )
                total_usage["total_tokens"] += response.usage.total_tokens or 0

            # Check for tool calls
            if response.tool_calls:
                tool_calls.extend([tc.model_dump() for tc in response.tool_calls])

                # Add assistant message with tool calls
                messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                    )
                )

                # Execute tools and add tool results
                for tool_call in response.tool_calls:
                    tool_result = await self._execute_tool(
                        agent=agent,
                        tool_call=tool_call,
                    )

                    # Add tool result message
                    messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=str(tool_result),
                            tool_call_id=tool_call.id,
                        )
                    )

                # Continue to next turn to get final response
                continue
            else:
                # No tool calls, we have the final response
                response_text = response.content or ""
                break

        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "usage": total_usage,
        }

    async def chat_stream(
        self,
        agent: Agent,
        message: str,
        context: dict[str, Any] | None = None,
        user_id: str | None = None,
        max_turns: int = 10,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str | dict]:
        """
        Execute a streaming chat with the agent.

        Yields:
            str for content tokens
            dict for tool calls and metadata ({"tool_call": ...} or {"usage": ...})
        """
        messages = await self._build_messages(
            agent=agent,
            message=message,
            context=context,
            conversation_history=conversation_history,
        )

        tools = await self._get_agent_tools(agent)

        # Get team model or default
        team_id = str(agent.team_id) if agent.team_id else None
        model_id = str(agent.model_id) if agent.model_id else None

        current_turn = 0
        while current_turn < max_turns:
            current_turn += 1

            accumulated_content = ""
            accumulated_tool_calls = []
            final_usage = None

            async for chunk in model_manager.chat_stream(
                messages=cast(list[Any], messages),
                tools=tools if tools else None,
                team_id=team_id,
                model=model_id,
                user_id=user_id,
            ):
                if chunk.delta.content:
                    accumulated_content += chunk.delta.content
                    yield chunk.delta.content

                if chunk.delta.tool_calls:
                    for tc in chunk.delta.tool_calls:
                        accumulated_tool_calls.append(tc)
                        yield {"tool_call": tc.model_dump()}

                if chunk.usage:
                    final_usage = chunk.usage

            # Yield usage at the end
            if final_usage:
                yield {"usage": final_usage.model_dump()}

            # If there were tool calls, execute them
            if accumulated_tool_calls:
                # Add assistant message with tool calls
                messages.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=accumulated_content,
                        tool_calls=accumulated_tool_calls,
                    )
                )

                # Execute tools and add results
                for tool_call in accumulated_tool_calls:
                    tool_result = await self._execute_tool(
                        agent=agent,
                        tool_call=tool_call,
                    )

                    # Add tool result message
                    messages.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=str(tool_result),
                            tool_call_id=tool_call.id,
                        )
                    )

                # Continue to next turn to get final response
                continue
            else:
                # No tool calls, we're done
                break

    async def _build_messages(
        self,
        agent: Agent,
        message: str,
        context: dict[str, Any] | None = None,
        conversation_history: list[dict] | None = None,
    ) -> list[Message]:
        """Build message list for the chat."""
        messages = []

        # System prompt
        system_prompt = agent.system_prompt or ""

        # Add context variables to system prompt if provided
        if context:
            context_str = "\n\nContext:\n" + "\n".join(
                f"- {k}: {v}" for k, v in context.items()
            )
            system_prompt += context_str

        if system_prompt:
            messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content=system_prompt,
                )
            )

        # Add conversation history
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "user":
                    messages.append(Message(role=MessageRole.USER, content=content))
                elif role == "assistant":
                    messages.append(
                        Message(role=MessageRole.ASSISTANT, content=content)
                    )
                elif role == "system":
                    messages.append(Message(role=MessageRole.SYSTEM, content=content))

        # Add current user message
        messages.append(
            Message(
                role=MessageRole.USER,
                content=message,
            )
        )

        # RAG context (if enabled)
        if agent.rag_mode != RAGMode.OFF:
            rag_context = await self._retrieve_rag_context(agent, message)
            if rag_context:
                # Insert RAG context before the user message
                context_message = Message(
                    role=MessageRole.SYSTEM,
                    content=f"Relevant context:\n{rag_context}",
                )
                messages.insert(-1, context_message)

        return messages

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
            return {"error": t("tool_not_found"), "tool_name": tool_name, "success": False}

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

            from app.services.vector_store import VectorStore

            all_chunks = []
            for agent_kb in agent_kbs:
                kb = agent_kb.knowledge_base
                if not kb:
                    continue

                # Search in each knowledge base
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
                    top_k=agent_kb.retrieval_top_k,
                    score_threshold=agent_kb.score_threshold,
                )

                for result in results:
                    all_chunks.append(
                        {
                            "content": result.get("content", ""),
                            "score": result.get("score", 0),
                            "source": kb.name,
                        }
                    )

            if not all_chunks:
                return None

            # Sort by score and take top results
            all_chunks.sort(key=lambda x: x["score"], reverse=True)
            top_chunks = all_chunks[:10]  # Top 10 across all KBs

            context_parts = []
            for chunk in top_chunks:
                context_parts.append(f"[{chunk['source']}] {chunk['content']}")

            return "\n\n".join(context_parts)

        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
            return None

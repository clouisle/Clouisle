"""
API endpoints for AI-powered prompt generation.
Provides streaming SSE response for generating agent system prompts.
"""

import json
import logging

from fastapi import APIRouter, Depends

from app.core.i18n import t
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api import deps
from app.models.user import User
from app.models.model import Model
from app.schemas.response import (
    ResponseCode,
)

router = APIRouter()
logger = logging.getLogger(__name__)
GENERIC_STREAM_ERROR_KEY = "unknown_error"


# ============ Request/Response Models ============


class PromptGenerateContext(BaseModel):
    """Context information for prompt generation."""

    agent_name: str | None = Field(None, description="Agent name")
    agent_description: str | None = Field(None, description="Agent description")
    tools: list[dict] | None = Field(None, description="Configured tools")
    knowledge_bases: list[dict] | None = Field(
        None, description="Linked knowledge bases"
    )
    variables: list[dict] | None = Field(None, description="Defined variables")


class PromptStyle(BaseModel):
    """Prompt generation style options."""

    tone: str = Field(
        "professional", description="Tone: professional, friendly, concise, detailed"
    )
    focus: str = Field(
        "balanced", description="Focus: task-oriented, conversational, balanced"
    )
    include_cot: bool = Field(
        False, description="Include chain-of-thought instructions"
    )
    include_constraints: bool = Field(True, description="Include behavior constraints")


class PromptGenerateRequest(BaseModel):
    """Request body for prompt generation."""

    description: str = Field(
        ..., description="User's description of what the agent should do"
    )
    context: PromptGenerateContext | None = Field(
        None, description="Current agent context"
    )
    style: PromptStyle | None = Field(None, description="Generation style options")
    language: str = Field("zh", description="Output language: zh or en")


class SSEEventType:
    """SSE event types for prompt generation."""

    START = "start"
    CONTENT_DELTA = "content_delta"
    COMPLETE = "complete"
    ERROR = "error"


# ============ Meta-Prompt Template ============


META_PROMPT_ZH = """你是一个专业的 AI Agent 系统提示词设计专家。你的任务是根据用户的需求描述，生成高质量的系统提示词（System Prompt）。

## 用户需求描述
{description}

## 当前 Agent 上下文
{context}

## 生成风格要求
- 语气：{tone_desc}
- 侧重：{focus_desc}
{style_requirements}

## 输出要求
请直接输出系统提示词内容，不要包含任何解释或前缀。提示词应该：
1. 清晰定义 Agent 的角色和职责
2. 说明 Agent 应该如何与用户交互
3. 如果有工具或知识库，说明如何使用它们
4. 如果有变量，说明变量的用途
5. 包含必要的行为约束和边界条件

请开始生成提示词："""


META_PROMPT_EN = """You are an expert AI Agent system prompt designer. Your task is to generate high-quality system prompts based on user requirements.

## User Requirements
{description}

## Current Agent Context
{context}

## Generation Style
- Tone: {tone_desc}
- Focus: {focus_desc}
{style_requirements}

## Output Requirements
Please output the system prompt directly without any explanation or prefix. The prompt should:
1. Clearly define the Agent's role and responsibilities
2. Explain how the Agent should interact with users
3. If tools or knowledge bases exist, explain how to use them
4. If variables exist, explain their purpose
5. Include necessary behavioral constraints and boundaries

Please generate the prompt:"""


def build_context_string(context: PromptGenerateContext | None, language: str) -> str:
    """Build context string from agent configuration."""
    if not context:
        return "无额外上下文" if language == "zh" else "No additional context"

    parts = []

    if context.agent_name:
        label = "Agent 名称" if language == "zh" else "Agent Name"
        parts.append(f"- {label}: {context.agent_name}")

    if context.agent_description:
        label = "Agent 描述" if language == "zh" else "Agent Description"
        parts.append(f"- {label}: {context.agent_description}")

    if context.tools:
        label = "可用工具" if language == "zh" else "Available Tools"
        tool_names = [
            t.get("name", t.get("display_name", "unknown")) for t in context.tools
        ]
        parts.append(f"- {label}: {', '.join(tool_names)}")

    if context.knowledge_bases:
        label = "关联知识库" if language == "zh" else "Linked Knowledge Bases"
        kb_names = [kb.get("name", "unknown") for kb in context.knowledge_bases]
        parts.append(f"- {label}: {', '.join(kb_names)}")

    if context.variables:
        label = "自定义变量" if language == "zh" else "Custom Variables"
        var_list = []
        for v in context.variables:
            var_name = v.get("name", "unknown")
            var_label = v.get("label", "")
            if var_label:
                var_list.append(f"{var_name}({var_label})")
            else:
                var_list.append(var_name)
        parts.append(f"- {label}: {', '.join(var_list)}")

    if not parts:
        return "无额外上下文" if language == "zh" else "No additional context"

    return "\n".join(parts)


def get_tone_description(tone: str, language: str) -> str:
    """Get tone description based on language."""
    tone_map_zh = {
        "professional": "专业正式",
        "friendly": "友好亲切",
        "concise": "简洁高效",
        "detailed": "详细周到",
    }
    tone_map_en = {
        "professional": "Professional and formal",
        "friendly": "Friendly and approachable",
        "concise": "Concise and efficient",
        "detailed": "Detailed and thorough",
    }
    tone_map = tone_map_zh if language == "zh" else tone_map_en
    return tone_map.get(tone) or tone_map["professional"]


def get_focus_description(focus: str, language: str) -> str:
    """Get focus description based on language."""
    focus_map_zh = {
        "task-oriented": "以任务为导向，注重效率和结果",
        "conversational": "以对话为主，注重用户体验",
        "balanced": "任务与对话平衡",
    }
    focus_map_en = {
        "task-oriented": "Task-oriented, focusing on efficiency and results",
        "conversational": "Conversational, focusing on user experience",
        "balanced": "Balanced between task and conversation",
    }
    focus_map = focus_map_zh if language == "zh" else focus_map_en
    return focus_map.get(focus) or focus_map["balanced"]


def build_style_requirements(style: PromptStyle | None, language: str) -> str:
    """Build additional style requirements."""
    if not style:
        return ""

    requirements = []

    if style.include_cot:
        if language == "zh":
            requirements.append(
                "- 包含思维链（Chain-of-Thought）引导，让 Agent 展示推理过程"
            )
        else:
            requirements.append(
                "- Include Chain-of-Thought guidance for showing reasoning process"
            )

    if style.include_constraints:
        if language == "zh":
            requirements.append("- 包含行为约束和安全边界")
        else:
            requirements.append(
                "- Include behavioral constraints and safety boundaries"
            )

    return "\n".join(requirements) if requirements else ""


# ============ Endpoints ============


@router.post("/generate")
async def generate_prompt(
    request: PromptGenerateRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Generate system prompt using AI (streaming SSE).

    Uses the default chat model to generate prompts.

    Returns Server-Sent Events:
    - start: Generation started
    - content_delta: {"delta": "..."}
    - complete: Generation complete
    - error: {"code": ..., "msg": "..."}
    """

    async def event_generator():
        try:
            # Get default chat model
            default_model = await Model.filter(
                model_type="chat",
                is_default=True,
                is_enabled=True,
            ).first()

            if not default_model:
                yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': t('no_chat_model_available')})}\n\n"
                return

            # Build meta-prompt
            language = request.language or "zh"
            style = request.style or PromptStyle()

            context_str = build_context_string(request.context, language)
            tone_desc = get_tone_description(style.tone, language)
            focus_desc = get_focus_description(style.focus, language)
            style_requirements = build_style_requirements(style, language)

            meta_prompt_template = (
                META_PROMPT_ZH if language == "zh" else META_PROMPT_EN
            )
            meta_prompt = meta_prompt_template.format(
                description=request.description,
                context=context_str,
                tone_desc=tone_desc,
                focus_desc=focus_desc,
                style_requirements=style_requirements,
            )

            # Send start event
            yield f"event: {SSEEventType.START}\ndata: {json.dumps({'model': default_model.name})}\n\n"

            # Import LLM manager
            from app.llm.adapters.chat.factory import create_chat_model
            from langchain_core.messages import HumanMessage

            # Create chat model
            chat_model = create_chat_model(default_model)

            # Stream the response
            full_content = ""
            async for chunk in chat_model.astream([HumanMessage(content=meta_prompt)]):
                if hasattr(chunk, "content") and chunk.content:
                    full_content += chunk.content
                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.content})}\n\n"

            # Send complete event
            yield f"event: {SSEEventType.COMPLETE}\ndata: {json.dumps({'total_length': len(full_content)})}\n\n"

        except Exception as e:
            logger.exception(f"Error generating prompt: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/optimize")
async def optimize_prompt(
    current_prompt: str,
    feedback: str,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Optimize an existing prompt based on feedback (streaming SSE).

    This endpoint is for iterative improvement of prompts.
    """

    async def event_generator():
        try:
            # Get default chat model
            default_model = await Model.filter(
                model_type="chat",
                is_default=True,
                is_enabled=True,
            ).first()

            if not default_model:
                yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': t('no_chat_model_available')})}\n\n"
                return

            # Build optimization prompt
            optimize_prompt_text = f"""你是一个专业的 AI Agent 系统提示词优化专家。请根据用户的反馈优化以下系统提示词。

## 当前提示词
{current_prompt}

## 用户反馈
{feedback}

## 输出要求
请直接输出优化后的完整系统提示词，不要包含任何解释或前缀。

请开始输出优化后的提示词："""

            # Send start event
            yield f"event: {SSEEventType.START}\ndata: {json.dumps({'model': default_model.name})}\n\n"

            # Import and create chat model
            from app.llm.adapters.chat.factory import create_chat_model
            from langchain_core.messages import HumanMessage

            chat_model = create_chat_model(default_model)

            # Stream the response
            full_content = ""
            async for chunk in chat_model.astream(
                [HumanMessage(content=optimize_prompt_text)]
            ):
                if hasattr(chunk, "content") and chunk.content:
                    full_content += chunk.content
                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.content})}\n\n"

            # Send complete event
            yield f"event: {SSEEventType.COMPLETE}\ndata: {json.dumps({'total_length': len(full_content)})}\n\n"

        except Exception as e:
            logger.exception(f"Error optimizing prompt: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

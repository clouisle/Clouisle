"""
工具管理 API 端点

提供工具列表、创建、更新、删除、测试执行等功能。
"""

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api import deps
from app.models.user import User, Team, TeamMember
from app.models.tool import (
    Tool,
    ToolType as DBToolType,
    CustomToolType as DBCustomToolType,
    ToolCategory as DBToolCategory,
)
from app.llm.tools import tool_registry
from app.llm.tools.sandbox import execute_code
from app.llm.tools.mcp_client import execute_mcp_tool, list_mcp_tools
from app.llm.tools.executors import execute_http_tool
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.schemas.tool import (
    ToolType,
    CustomToolType,
    ToolCategory,
    ToolParameterSchema,
    ToolOut,
    ToolDetailOut,
    ToolListOut,
    ToolCreateInput,
    ToolUpdateInput,
    ToolExecuteRequest,
    ToolExecuteResponse,
    CodeExecuteRequest,
    CodeExecuteResponse,
    HttpConfigSchema,
    CodeConfigSchema,
    McpConfigSchema,
    McpToolInfoOut,
    McpToolsListRequest,
    McpToolsListResponse,
    BUILTIN_TOOLS_METADATA,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


async def check_team_access(
    team_id: UUID, user: User, require_admin: bool = False
) -> Team:
    """检查用户是否有团队访问权限"""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return team

    membership = await TeamMember.filter(team=team, user=user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=403,
        )

    if require_admin and membership.role not in ["owner", "admin"]:
        raise BusinessError(
            code=ResponseCode.TEAM_ADMIN_REQUIRED,
            msg_key="team_admin_required",
            status_code=403,
        )

    return team


def get_builtin_tools() -> list[ToolOut]:
    """获取所有内置工具"""
    tools = []
    for tool_info in tool_registry.get_all_tools():
        metadata = BUILTIN_TOOLS_METADATA.get(tool_info.name, {})

        parameters = [
            ToolParameterSchema(
                name=p.name,
                type=p.type,
                description=p.description,
                required=p.required,
                enum=p.enum,
                default=p.default,
            )
            for p in tool_info.parameters
        ]

        tools.append(
            ToolOut(
                name=tool_info.name,
                display_name=metadata.get("display_name", tool_info.name),
                description=tool_info.description,
                type=ToolType.BUILTIN,
                category=ToolCategory(metadata.get("category", ToolCategory.OTHER)),
                icon=metadata.get("icon"),
                parameters=parameters,
                is_enabled=True,
                requires_config=metadata.get("requires_config", False),
                config_fields=metadata.get("config_fields", []),
            )
        )

    return tools


def db_tool_to_out(tool: Tool, creator_name: str | None = None) -> ToolOut:
    """将数据库工具转换为输出格式"""
    return ToolOut(
        id=tool.id,
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        type=ToolType(tool.type.value),
        category=ToolCategory(tool.category.value),
        icon=tool.icon,
        parameters=[ToolParameterSchema(**p) for p in tool.parameters],
        is_enabled=tool.is_enabled,
        requires_config=bool(tool.credentials),
        config_fields=list(tool.credentials.keys()) if tool.credentials else [],
        custom_type=CustomToolType(tool.custom_type.value)
        if tool.custom_type
        else None,
        http_config=HttpConfigSchema(**tool.http_config) if tool.http_config else None,
        code_config=CodeConfigSchema(**tool.code_config) if tool.code_config else None,
        mcp_config=McpConfigSchema(**tool.mcp_config) if tool.mcp_config else None,
        team_id=tool.team_id,
        created_by_name=creator_name,
    )


def db_tool_to_detail(tool: Tool, creator_name: str | None = None) -> ToolDetailOut:
    """将数据库工具转换为详情输出格式"""
    return ToolDetailOut(
        id=tool.id,
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        type=ToolType(tool.type.value),
        category=ToolCategory(tool.category.value),
        icon=tool.icon,
        parameters=[ToolParameterSchema(**p) for p in tool.parameters],
        is_enabled=tool.is_enabled,
        requires_config=bool(tool.credentials),
        config_fields=list(tool.credentials.keys()) if tool.credentials else [],
        custom_type=CustomToolType(tool.custom_type.value)
        if tool.custom_type
        else None,
        http_config=HttpConfigSchema(**tool.http_config) if tool.http_config else None,
        code_config=CodeConfigSchema(**tool.code_config) if tool.code_config else None,
        mcp_config=McpConfigSchema(**tool.mcp_config) if tool.mcp_config else None,
        team_id=tool.team_id,
        created_at=tool.created_at.isoformat() if tool.created_at else None,
        updated_at=tool.updated_at.isoformat() if tool.updated_at else None,
        created_by_name=creator_name,
    )


# ============ API Endpoints ============


@router.get("", response_model=Response[ToolListOut])
async def list_tools(
    team_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取所有可用工具

    返回内置工具、自定义工具和 MCP Server 工具列表。
    """
    await check_team_access(team_id, current_user)

    # 获取内置工具
    builtin_tools = get_builtin_tools()

    # 获取团队的自定义工具（预加载创建者信息）
    custom_db_tools = await Tool.filter(
        team_id=team_id,
        type=DBToolType.CUSTOM,
    ).prefetch_related("created_by").order_by("-updated_at")

    custom_tools = []
    for t in custom_db_tools:
        creator_name = t.created_by.username if t.created_by else None
        custom_tools.append(db_tool_to_out(t, creator_name))

    # 获取团队的 MCP 工具（预加载创建者信息）
    mcp_db_tools = await Tool.filter(
        team_id=team_id,
        type=DBToolType.MCP,
    ).prefetch_related("created_by").order_by("-updated_at")

    mcp_tools = []
    for t in mcp_db_tools:
        creator_name = t.created_by.username if t.created_by else None
        mcp_tools.append(db_tool_to_out(t, creator_name))

    return success(
        data=ToolListOut(
            builtin=builtin_tools,
            custom=custom_tools,
            mcp=mcp_tools,
        ),
        msg_key="success",
    )


@router.get("/builtin", response_model=Response[list[ToolOut]])
async def list_builtin_tools(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """获取所有内置工具"""
    return success(
        data=get_builtin_tools(),
        msg_key="success",
    )


@router.post("/mcp/list-tools", response_model=Response[McpToolsListResponse])
async def get_mcp_tools(
    request: McpToolsListRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 MCP 服务器的工具列表

    连接到指定的 MCP 服务器并列出所有可用工具。
    """
    try:
        mcp_config = request.mcp_config.model_dump()
        tools = await list_mcp_tools(mcp_config)
        return success(
            data=McpToolsListResponse(
                tools=[
                    McpToolInfoOut(
                        name=t.name,
                        description=t.description,
                        parameters=t.parameters,
                    )
                    for t in tools
                ],
            ),
            msg_key="success",
        )
    except Exception as e:
        logger.exception(f"Failed to list MCP tools: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="mcp_connection_failed",
            status_code=500,
            detail=str(e),
        )


@router.post("", response_model=Response[ToolDetailOut])
async def create_tool(
    team_id: UUID,
    tool_in: ToolCreateInput,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """创建自定义工具"""
    await check_team_access(team_id, current_user, require_admin=True)

    # 检查名称是否已存在
    existing = await Tool.filter(team_id=team_id, name=tool_in.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS,
            msg_key="tool_name_exists",
            status_code=400,
        )

    # 创建工具
    tool = await Tool.create(
        team_id=team_id,
        name=tool_in.name,
        display_name=tool_in.display_name,
        description=tool_in.description,
        icon=tool_in.icon,
        category=DBToolCategory(tool_in.category.value),
        type=DBToolType(tool_in.type.value),
        custom_type=(
            DBCustomToolType(tool_in.custom_type.value) if tool_in.custom_type else None
        ),
        parameters=[p.model_dump() for p in tool_in.parameters],
        http_config=tool_in.http_config.model_dump() if tool_in.http_config else {},
        code_config=tool_in.code_config.model_dump() if tool_in.code_config else {},
        mcp_config=tool_in.mcp_config.model_dump() if tool_in.mcp_config else {},
        credentials=tool_in.credentials,
        is_enabled=tool_in.is_enabled,
        created_by=current_user,
    )

    return success(
        data=db_tool_to_detail(tool, current_user.username),
        msg_key="tool_created",
    )


@router.get("/id/{tool_id}", response_model=Response[ToolDetailOut])
async def get_tool_by_id(
    tool_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """根据 ID 获取工具详情"""
    tool = await Tool.filter(id=tool_id).prefetch_related("created_by").first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    await check_team_access(tool.team_id, current_user)

    creator_name = tool.created_by.username if tool.created_by else None
    return success(
        data=db_tool_to_detail(tool, creator_name),
        msg_key="success",
    )


@router.get("/name/{tool_name}", response_model=Response[ToolOut])
async def get_tool_by_name(
    tool_name: str,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """根据名称获取工具（内置或自定义）"""
    # 先检查内置工具
    tool_info = tool_registry.get_tool(tool_name)
    if tool_info:
        metadata = BUILTIN_TOOLS_METADATA.get(tool_name, {})
        parameters = [
            ToolParameterSchema(
                name=p.name,
                type=p.type,
                description=p.description,
                required=p.required,
                enum=p.enum,
                default=p.default,
            )
            for p in tool_info.parameters
        ]

        return success(
            data=ToolOut(
                name=tool_info.name,
                display_name=metadata.get("display_name", tool_info.name),
                description=tool_info.description,
                type=ToolType.BUILTIN,
                category=ToolCategory(metadata.get("category", ToolCategory.OTHER)),
                icon=metadata.get("icon"),
                parameters=parameters,
                is_enabled=True,
                requires_config=metadata.get("requires_config", False),
                config_fields=metadata.get("config_fields", []),
            ),
            msg_key="success",
        )

    # 检查自定义工具
    if team_id:
        await check_team_access(team_id, current_user)
        tool = await Tool.filter(team_id=team_id, name=tool_name).first()
        if tool:
            return success(
                data=db_tool_to_out(tool),
                msg_key="success",
            )

    raise BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="tool_not_found",
        status_code=404,
    )


@router.put("/{tool_id}", response_model=Response[ToolDetailOut])
async def update_tool(
    tool_id: UUID,
    tool_in: ToolUpdateInput,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """更新工具"""
    tool = await Tool.filter(id=tool_id).prefetch_related("created_by").first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    await check_team_access(tool.team_id, current_user, require_admin=True)

    # 如果修改名称，检查是否冲突
    if tool_in.name and tool_in.name != tool.name:
        existing = await Tool.filter(team_id=tool.team_id, name=tool_in.name).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.ALREADY_EXISTS,
                msg_key="tool_name_exists",
                status_code=400,
            )
        tool.name = tool_in.name

    # 更新字段
    if tool_in.display_name is not None:
        tool.display_name = tool_in.display_name
    if tool_in.description is not None:
        tool.description = tool_in.description
    if tool_in.icon is not None:
        tool.icon = tool_in.icon
    if tool_in.category is not None:
        tool.category = DBToolCategory(tool_in.category.value)
    if tool_in.custom_type is not None:
        tool.custom_type = DBCustomToolType(tool_in.custom_type.value)
    if tool_in.parameters is not None:
        tool.parameters = [p.model_dump() for p in tool_in.parameters]
    if tool_in.http_config is not None:
        tool.http_config = tool_in.http_config.model_dump()
    if tool_in.code_config is not None:
        tool.code_config = tool_in.code_config.model_dump()
    if tool_in.mcp_config is not None:
        tool.mcp_config = tool_in.mcp_config.model_dump()
    if tool_in.credentials is not None:
        tool.credentials = tool_in.credentials
    if tool_in.is_enabled is not None:
        tool.is_enabled = tool_in.is_enabled

    await tool.save()

    creator_name = tool.created_by.username if tool.created_by else None
    return success(
        data=db_tool_to_detail(tool, creator_name),
        msg_key="tool_updated",
    )


@router.delete("/{tool_id}", response_model=Response[None])
async def delete_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """删除工具"""
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    await check_team_access(tool.team_id, current_user, require_admin=True)

    await tool.delete()

    return success(
        data=None,
        msg_key="tool_deleted",
    )


@router.post("/test", response_model=Response[ToolExecuteResponse])
async def test_tool(
    request: ToolExecuteRequest,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    测试执行工具

    支持内置工具和自定义工具。
    """
    start_time = time.time()

    # 先尝试内置工具
    builtin_tool = tool_registry.get_tool(request.name)
    if builtin_tool:
        try:
            result = await tool_registry.execute(request.name, request.arguments)
            duration_ms = int((time.time() - start_time) * 1000)

            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=True,
                    result=result,
                    duration_ms=duration_ms,
                ),
                msg_key="success",
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Builtin tool execution error: {e}")

            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                ),
                msg_key="success",
            )

    # 尝试自定义工具
    if team_id:
        await check_team_access(team_id, current_user)
        custom_tool = await Tool.filter(team_id=team_id, name=request.name).first()

        if custom_tool:
            # MCP 工具
            if custom_tool.type == DBToolType.MCP:
                mcp_config = custom_tool.mcp_config or {}
                if not mcp_config:
                    return success(
                        data=ToolExecuteResponse(
                            name=request.name,
                            success=False,
                            error="MCP configuration is missing",
                            duration_ms=int((time.time() - start_time) * 1000),
                        ),
                        msg_key="success",
                    )

                # MCP 工具名称可能与数据库中的 name 不同
                # 使用请求中的 tool_name 参数，如果没有则使用工具名称
                mcp_tool_name = (
                    request.arguments.pop("__tool_name__", None) or request.name
                )

                try:
                    result = await execute_mcp_tool(
                        mcp_config=mcp_config,
                        tool_name=mcp_tool_name,
                        arguments=request.arguments,
                        timeout=60.0,
                    )
                    duration_ms = int((time.time() - start_time) * 1000)

                    return success(
                        data=ToolExecuteResponse(
                            name=request.name,
                            success=result.success,
                            result=result.result,
                            error=result.error,
                            duration_ms=duration_ms,
                        ),
                        msg_key="success",
                    )
                except Exception as e:
                    logger.exception(f"MCP tool execution error: {e}")
                    duration_ms = int((time.time() - start_time) * 1000)
                    return success(
                        data=ToolExecuteResponse(
                            name=request.name,
                            success=False,
                            error=str(e),
                            duration_ms=duration_ms,
                        ),
                        msg_key="success",
                    )
            # 自定义 HTTP 工具
            elif custom_tool.custom_type == DBCustomToolType.HTTP:
                result = await execute_http_tool(
                    custom_tool.http_config,
                    request.arguments,
                    custom_tool.credentials,
                )
                duration_ms = int((time.time() - start_time) * 1000)

                return success(
                    data=ToolExecuteResponse(
                        name=request.name,
                        success=result.get("success", False),
                        result=result.get("result"),
                        error=result.get("error"),
                        duration_ms=duration_ms,
                    ),
                    msg_key="success",
                )
            elif custom_tool.custom_type == DBCustomToolType.CODE:
                # 执行代码工具
                code_config = custom_tool.code_config or {}
                language = code_config.get("language", "javascript")
                code = code_config.get("code", "")

                if not code:
                    return success(
                        data=ToolExecuteResponse(
                            name=request.name,
                            success=False,
                            error="No code defined for this tool",
                            duration_ms=int((time.time() - start_time) * 1000),
                        ),
                        msg_key="success",
                    )

                exec_result = await execute_code(
                    language=language,
                    code=code,
                    params=request.arguments,
                    timeout=30.0,
                )
                duration_ms = int((time.time() - start_time) * 1000)

                # 构建结果，包含 stdout 日志
                result_data = exec_result.result
                if exec_result.stdout:
                    if isinstance(result_data, dict):
                        result_data["__logs__"] = exec_result.stdout
                    else:
                        result_data = {
                            "value": result_data,
                            "__logs__": exec_result.stdout,
                        }

                return success(
                    data=ToolExecuteResponse(
                        name=request.name,
                        success=exec_result.success,
                        result=result_data,
                        error=exec_result.error,
                        duration_ms=duration_ms,
                    ),
                    msg_key="success",
                )
            else:
                return success(
                    data=ToolExecuteResponse(
                        name=request.name,
                        success=False,
                        error=f"Unsupported tool type: {custom_tool.custom_type}",
                        duration_ms=int((time.time() - start_time) * 1000),
                    ),
                    msg_key="success",
                )

    raise BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="tool_not_found",
        status_code=404,
    )


@router.post("/execute-code", response_model=Response[CodeExecuteResponse])
async def execute_code_directly(
    request: CodeExecuteRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    直接执行代码（不需要保存工具）

    用于代码工具的即时测试。支持 JavaScript 和 Python。
    """
    start_time = time.time()

    # 验证语言
    if request.language.lower() not in ("javascript", "python"):
        return success(
            data=CodeExecuteResponse(
                success=False,
                error=f"Unsupported language: {request.language}. Only 'javascript' and 'python' are supported.",
                duration_ms=int((time.time() - start_time) * 1000),
            ),
            msg_key="success",
        )

    # 执行代码
    exec_result = await execute_code(
        language=request.language,
        code=request.code,
        params=request.params,
        timeout=request.timeout,
    )
    duration_ms = int((time.time() - start_time) * 1000)

    return success(
        data=CodeExecuteResponse(
            success=exec_result.success,
            result=exec_result.result,
            error=exec_result.error,
            logs=exec_result.stdout or None,
            duration_ms=duration_ms,
        ),
        msg_key="success",
    )


@router.post("/{tool_id}/toggle", response_model=Response[ToolDetailOut])
async def toggle_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """切换工具启用状态"""
    tool = await Tool.filter(id=tool_id).prefetch_related("created_by").first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    await check_team_access(tool.team_id, current_user, require_admin=True)

    tool.is_enabled = not tool.is_enabled
    await tool.save()

    creator_name = tool.created_by.username if tool.created_by else None
    return success(
        data=db_tool_to_detail(tool, creator_name),
        msg_key="tool_updated",
    )


@router.post("/{tool_id}/duplicate", response_model=Response[ToolDetailOut])
async def duplicate_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """复制工具"""
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    await check_team_access(tool.team_id, current_user, require_admin=True)

    # 生成新名称
    base_name = f"{tool.name}_copy"
    new_name = base_name
    counter = 1
    while await Tool.filter(team_id=tool.team_id, name=new_name).exists():
        new_name = f"{base_name}_{counter}"
        counter += 1

    # 创建副本
    new_tool = await Tool.create(
        team_id=tool.team_id,
        name=new_name,
        display_name=f"{tool.display_name} (Copy)",
        description=tool.description,
        icon=tool.icon,
        category=tool.category,
        type=tool.type,
        custom_type=tool.custom_type,
        parameters=tool.parameters,
        http_config=tool.http_config,
        code_config=tool.code_config,
        mcp_config=tool.mcp_config,
        credentials=tool.credentials,
        is_enabled=False,  # 副本默认禁用
        created_by=current_user,
    )

    return success(
        data=db_tool_to_detail(new_tool, current_user.username),
        msg_key="tool_duplicated",
    )

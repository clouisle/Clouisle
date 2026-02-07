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
from app.core.i18n import t
from app.models.user import User, Team, TeamMember
from app.models.tool import (
    Tool,
    ToolShare,
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
    ToolSharePermission,
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
    ToolShareInput,
    ToolShareOut,
    ToolShareListOut,
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


def get_builtin_tools(user_locale: str | None = None) -> list[ToolOut]:
    """获取所有内置工具

    Args:
        user_locale: User's locale from database for i18n display names
    """
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

        # Get display name from i18n using user's locale
        display_name_key = metadata.get("display_name_key")
        display_name = (
            t(display_name_key, lang=user_locale)
            if display_name_key
            else tool_info.name
        )

        tools.append(
            ToolOut(
                name=tool_info.name,
                display_name=display_name,
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
    include_shared: bool = True,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取所有可用工具

    返回内置工具、自定义工具和 MCP Server 工具列表。
    如果 include_shared=True，还会包含共享给该团队的工具。
    """
    await check_team_access(team_id, current_user)

    # 获取内置工具
    builtin_tools = get_builtin_tools(current_user.locale)

    # 获取团队的自定义工具（预加载创建者信息）
    custom_db_tools = (
        await Tool.filter(
            team_id=team_id,
            type=DBToolType.CUSTOM,
        )
        .prefetch_related("created_by")
        .order_by("-updated_at")
    )

    custom_tools = []
    for tool in custom_db_tools:
        creator_name = tool.created_by.username if tool.created_by else None
        tool_out = db_tool_to_out(tool, creator_name)
        # 添加共享信息
        tool_out.is_owned = True
        tool_out.owner_team_id = tool.team_id
        # 计算共享数量
        share_count = await ToolShare.filter(tool_id=tool.id).count()
        tool_out.shared_with_count = share_count
        custom_tools.append(tool_out)

    # 获取团队的 MCP 工具（预加载创建者信息）
    mcp_db_tools = (
        await Tool.filter(
            team_id=team_id,
            type=DBToolType.MCP,
        )
        .prefetch_related("created_by")
        .order_by("-updated_at")
    )

    mcp_tools = []
    for tool in mcp_db_tools:
        creator_name = tool.created_by.username if tool.created_by else None
        tool_out = db_tool_to_out(tool, creator_name)
        # 添加共享信息
        tool_out.is_owned = True
        tool_out.owner_team_id = tool.team_id
        # 计算共享数量
        share_count = await ToolShare.filter(tool_id=tool.id).count()
        tool_out.shared_with_count = share_count
        mcp_tools.append(tool_out)

    # 如果需要包含共享工具
    if include_shared:
        # 获取共享给该团队的工具
        shares = await ToolShare.filter(shared_with_team_id=team_id).prefetch_related(
            "tool", "tool__team", "tool__created_by"
        )

        for share in shares:
            tool = share.tool
            creator_name = tool.created_by.username if tool.created_by else None
            tool_out = db_tool_to_out(tool, creator_name)

            # 添加共享信息
            tool_out.is_owned = False
            tool_out.owner_team_id = tool.team_id
            tool_out.owner_team_name = tool.team.name
            tool_out.share_permission = ToolSharePermission(share.permission)

            if tool.type == DBToolType.CUSTOM:
                custom_tools.append(tool_out)
            else:
                mcp_tools.append(tool_out)

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
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """获取所有内置工具"""
    return success(
        data=get_builtin_tools(current_user.locale),
        msg_key="success",
    )


@router.get("/file-parsers", response_model=Response[list[ToolOut]])
async def list_file_parsers(
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取可用于文件上传功能的解析器列表

    包括：
    - 内置的文件解析器（如 markitdown）
    - 自定义的文件解析工具（category=file）
    """
    await check_team_access(team_id, current_user)

    parsers: list[ToolOut] = []

    # 1. 获取内置的文件解析器
    for tool_info in tool_registry.get_all_tools():
        metadata = BUILTIN_TOOLS_METADATA.get(tool_info.name, {})
        if metadata.get("is_file_parser"):
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
            # Get display name from i18n using user's locale
            display_name_key = metadata.get("display_name_key")
            display_name = (
                t(display_name_key, lang=current_user.locale)
                if display_name_key
                else tool_info.name
            )

            parsers.append(
                ToolOut(
                    name=tool_info.name,
                    display_name=display_name,
                    description=tool_info.description,
                    type=ToolType.BUILTIN,
                    category=ToolCategory(metadata.get("category", ToolCategory.FILE)),
                    icon=metadata.get("icon"),
                    parameters=parameters,
                    is_enabled=True,
                )
            )

    # 2. 获取自定义的文件解析工具（category=file 的自定义工具）
    custom_tools = await Tool.filter(
        team_id=team_id,
        is_enabled=True,
        category=ToolCategory.FILE,
    ).all()

    for tool in custom_tools:
        parameters = (
            [
                ToolParameterSchema(**p)
                for p in (tool.http_config.get("parameters") or [])
            ]
            if tool.http_config
            else []
        )

        parsers.append(
            ToolOut(
                id=str(tool.id),
                name=tool.name,
                display_name=tool.display_name,
                description=tool.description or "",
                type=ToolType.CUSTOM,
                category=tool.category,
                icon=tool.icon,
                parameters=parameters,
                is_enabled=tool.is_enabled,
            )
        )

    return success(data=parsers, msg_key="success")


@router.post("/mcp/list-tools", response_model=Response[McpToolsListResponse])
async def get_mcp_tools(
    request: McpToolsListRequest,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:create")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
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

        # Get display name from i18n using user's locale
        display_name_key = metadata.get("display_name_key")
        display_name = (
            t(display_name_key, lang=current_user.locale)
            if display_name_key
            else tool_info.name
        )

        return success(
            data=ToolOut(
                name=tool_info.name,
                display_name=display_name,
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
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:delete")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
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
            # 对于内置工具，从 ToolConfig 表中获取 credentials
            from app.models.tool_config import ToolConfig

            credentials = {}

            # 优先从团队配置获取，其次从全局配置获取
            if team_id:
                tool_config = await ToolConfig.filter(
                    tool_name=request.name, team_id=team_id
                ).first()
                if tool_config:
                    credentials = tool_config.credentials or {}

            # 如果团队配置不存在，尝试获取全局配置
            if not credentials:
                global_config = await ToolConfig.filter(
                    tool_name=request.name, team_id=None
                ).first()
                if global_config:
                    credentials = global_config.credentials or {}

            # 如果还是没有配置，尝试从环境变量获取（兜底）
            if not credentials:
                from app.core.config import settings

                if hasattr(settings, "TAVILY_API_KEY") and settings.TAVILY_API_KEY:
                    credentials["TAVILY_API_KEY"] = settings.TAVILY_API_KEY

            result = await tool_registry.execute(
                request.name, request.arguments, credentials=credentials
            )
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
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
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
    current_user: User = Depends(deps.PermissionChecker("tool:create")),
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


# ============ Tool Configuration Management ============


@router.get("/config", response_model=Response[list[dict]])
async def list_tool_configs(
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取工具配置列表

    如果提供 team_id，返回该团队的配置；否则返回全局配置（仅超级管理员）
    """
    from app.models.tool_config import ToolConfig

    if team_id:
        await check_team_access(team_id, current_user)
        configs = await ToolConfig.filter(team_id=team_id).all()
    else:
        # 全局配置仅超级管理员可访问
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )
        configs = await ToolConfig.filter(team_id=None).all()

    from app.schemas.tool_config import ToolConfigOut

    return success(
        data=[ToolConfigOut.model_validate(c).model_dump() for c in configs],
        msg_key="success",
    )


@router.get("/config/{tool_name}", response_model=Response[dict])
async def get_tool_config(
    tool_name: str,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取指定工具的配置
    """
    from app.models.tool_config import ToolConfig

    if team_id:
        await check_team_access(team_id, current_user)
        config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    else:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )
        config = await ToolConfig.filter(tool_name=tool_name, team_id=None).first()

    if not config:
        # For team-scoped builtin tools, create a default empty config
        if team_id:
            from app.llm.tools import tool_registry

            if tool_registry.get_tool(tool_name):
                config = await ToolConfig.create(
                    tool_name=tool_name,
                    team_id=team_id,
                    credentials={},
                )
            else:
                raise BusinessError(
                    code=ResponseCode.NOT_FOUND,
                    msg_key="tool_config_not_found",
                    status_code=404,
                )
        else:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="tool_config_not_found",
                status_code=404,
            )

    from app.schemas.tool_config import ToolConfigOut

    return success(
        data=ToolConfigOut.model_validate(config).model_dump(),
        msg_key="success",
    )


@router.post("/config", response_model=Response[dict])
async def create_tool_config(
    data: dict,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
) -> Any:
    """
    创建工具配置
    """
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigCreate, ToolConfigOut

    config_data = ToolConfigCreate(**data)

    if team_id:
        await check_team_access(team_id, current_user)
    else:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )

    # 检查是否已存在
    existing = await ToolConfig.filter(
        tool_name=config_data.tool_name, team_id=team_id
    ).first()

    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="tool_config_already_exists",
            status_code=400,
        )

    # 创建配置
    config = await ToolConfig.create(
        tool_name=config_data.tool_name,
        team_id=team_id,
        credentials=config_data.credentials,
    )

    return success(
        data=ToolConfigOut.model_validate(config).model_dump(),
        msg_key="tool_config_created",
    )


@router.put("/config/{tool_name}", response_model=Response[dict])
async def update_tool_config(
    tool_name: str,
    data: dict,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
) -> Any:
    """
    更新工具配置
    """
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigUpdate, ToolConfigOut

    config_data = ToolConfigUpdate(**data)

    if team_id:
        await check_team_access(team_id, current_user)
        config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    else:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )
        config = await ToolConfig.filter(tool_name=tool_name, team_id=None).first()

    if not config:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_config_not_found",
            status_code=404,
        )

    # 更新配置
    config.credentials = config_data.credentials
    await config.save()

    return success(
        data=ToolConfigOut.model_validate(config).model_dump(),
        msg_key="tool_config_updated",
    )


@router.delete("/config/{tool_name}", response_model=Response[None])
async def delete_tool_config(
    tool_name: str,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("tool:delete")),
) -> Any:
    """
    删除工具配置
    """
    from app.models.tool_config import ToolConfig

    if team_id:
        await check_team_access(team_id, current_user)
        config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    else:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )
        config = await ToolConfig.filter(tool_name=tool_name, team_id=None).first()

    if not config:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_config_not_found",
            status_code=404,
        )

    await config.delete()

    return success(
        data=None,
        msg_key="tool_config_deleted",
    )


# ============ Tool Sharing APIs ============


@router.post("/{tool_id}/share", response_model=Response[ToolShareOut])
async def share_tool(
    tool_id: UUID,
    share_data: ToolShareInput,
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
) -> Any:
    """
    共享工具给其他团队

    只有工具所有者团队的管理员可以共享工具
    """
    # 获取工具
    tool = await Tool.filter(id=tool_id).prefetch_related("team", "created_by").first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    # 检查用户是否是工具所有者团队的管理员
    await check_team_access(tool.team_id, current_user, require_admin=True)

    # 检查目标团队是否存在
    target_team = await Team.filter(id=share_data.team_id).first()
    if not target_team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # 不能共享给自己的团队
    if tool.team_id == share_data.team_id:
        raise BusinessError(
            code=ResponseCode.INVALID_INPUT,
            msg_key="cannot_share_to_own_team",
            status_code=400,
        )

    # 检查是否已经共享
    existing_share = await ToolShare.filter(
        tool_id=tool_id, shared_with_team_id=share_data.team_id
    ).first()

    if existing_share:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="tool_already_shared",
            status_code=400,
        )

    # 创建共享记录
    share = await ToolShare.create(
        tool_id=tool_id,
        shared_with_team_id=share_data.team_id,
        permission=share_data.permission,
        shared_by_id=current_user.id,
    )

    # 预加载关联数据
    await share.fetch_related("tool", "shared_with_team", "shared_by")

    return success(
        data=ToolShareOut(
            id=share.id,
            tool_id=share.tool_id,
            tool_name=share.tool.name,
            tool_display_name=share.tool.display_name,
            shared_with_team_id=share.shared_with_team_id,
            shared_with_team_name=share.shared_with_team.name,
            permission=ToolSharePermission(share.permission),
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.username,
            shared_at=share.shared_at,
        ).model_dump(),
        msg_key="tool_shared_successfully",
    )


@router.get("/{tool_id}/shares", response_model=Response[ToolShareListOut])
async def list_tool_shares(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取工具的共享列表

    只有工具所有者团队的成员可以查看
    """
    # 获取工具
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    # 检查用户是否是工具所有者团队的成员
    await check_team_access(tool.team_id, current_user)

    # 获取共享列表
    shares = (
        await ToolShare.filter(tool_id=tool_id)
        .prefetch_related("tool", "shared_with_team", "shared_by")
        .order_by("-shared_at")
    )

    share_list = [
        ToolShareOut(
            id=share.id,
            tool_id=share.tool_id,
            tool_name=share.tool.name,
            tool_display_name=share.tool.display_name,
            shared_with_team_id=share.shared_with_team_id,
            shared_with_team_name=share.shared_with_team.name,
            permission=ToolSharePermission(share.permission),
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.username,
            shared_at=share.shared_at,
        )
        for share in shares
    ]

    return success(
        data=ToolShareListOut(
            shares=share_list,
            total=len(share_list),
        ).model_dump()
    )


@router.delete("/{tool_id}/share/{team_id}", response_model=Response[None])
async def unshare_tool(
    tool_id: UUID,
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("tool:update")),
) -> Any:
    """
    取消工具共享

    只有工具所有者团队的管理员可以取消共享
    """
    # 获取工具
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    # 检查用户是否是工具所有者团队的管理员
    await check_team_access(tool.team_id, current_user, require_admin=True)

    # 查找共享记录
    share = await ToolShare.filter(tool_id=tool_id, shared_with_team_id=team_id).first()

    if not share:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_share_not_found",
            status_code=404,
        )

    # 删除共享记录
    await share.delete()

    return success(
        data=None,
        msg_key="tool_unshared_successfully",
    )


@router.get("/shared-with-me", response_model=Response[ToolListOut])
async def list_shared_tools(
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    """
    获取共享给当前团队的工具列表
    """
    # 检查团队访问权限
    await check_team_access(team_id, current_user)

    # 获取共享给该团队的工具
    shares = await ToolShare.filter(shared_with_team_id=team_id).prefetch_related(
        "tool", "tool__team", "tool__created_by"
    )

    custom_tools = []
    mcp_tools = []

    for share in shares:
        tool = share.tool

        # 构建工具输出
        tool_out = ToolOut(
            id=tool.id,
            name=tool.name,
            display_name=tool.display_name,
            description=tool.description,
            type=ToolType.CUSTOM if tool.type == DBToolType.CUSTOM else ToolType.MCP,
            category=ToolCategory(tool.category),
            icon=tool.icon,
            parameters=[ToolParameterSchema(**param) for param in tool.parameters],
            is_enabled=tool.is_enabled,
            custom_type=CustomToolType(tool.custom_type) if tool.custom_type else None,
            http_config=HttpConfigSchema(**tool.http_config)
            if tool.http_config
            else None,
            code_config=CodeConfigSchema(**tool.code_config)
            if tool.code_config
            else None,
            mcp_config=McpConfigSchema(**tool.mcp_config) if tool.mcp_config else None,
            # 共享相关字段
            is_owned=False,
            owner_team_id=tool.team_id,
            owner_team_name=tool.team.name,
            share_permission=ToolSharePermission(share.permission),
            team_id=tool.team_id,
            created_by_name=tool.created_by.username if tool.created_by else None,
        )

        if tool.type == DBToolType.CUSTOM:
            custom_tools.append(tool_out)
        else:
            mcp_tools.append(tool_out)

    return success(
        data=ToolListOut(
            builtin=[],  # 共享工具列表不包含内置工具
            custom=custom_tools,
            mcp=mcp_tools,
        ).model_dump()
    )

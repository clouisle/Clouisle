"""
工具相关的 Pydantic Schema
"""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolType(str, Enum):
    """工具类型"""

    BUILTIN = "builtin"  # 内置工具
    CUSTOM = "custom"  # 自定义工具
    MCP = "mcp"  # MCP Server 工具


class CustomToolType(str, Enum):
    """自定义工具执行类型"""

    HTTP = "http"  # HTTP API 调用
    CODE = "code"  # 代码执行


class ToolCategory(str, Enum):
    """工具分类"""

    TIME = "time"  # 时间相关
    MATH = "math"  # 数学计算
    SEARCH = "search"  # 搜索
    WEB = "web"  # 网页操作
    FILE = "file"  # 文件操作
    CODE = "code"  # 代码执行
    API = "api"  # API 调用
    DATA = "data"  # 数据处理
    OTHER = "other"  # 其他


class ToolParameterSchema(BaseModel):
    """工具参数定义"""

    name: str = Field(..., description="参数名")
    type: str = Field(
        ..., description="参数类型 (string, integer, number, boolean, array, object)"
    )
    description: str | None = Field(default=None, description="参数描述")
    required: bool = Field(default=False, description="是否必填")
    enum: list[str] | None = Field(default=None, description="枚举值")
    default: Any = Field(default=None, description="默认值")


# ============ HTTP Tool Config ============


class HttpMethod(str, Enum):
    """HTTP 方法"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HttpConfigSchema(BaseModel):
    """HTTP 工具配置"""

    method: HttpMethod = Field(default=HttpMethod.GET, description="HTTP 方法")
    url: str = Field(..., description="请求 URL，支持 {{variable}} 占位符")
    headers: dict[str, str] = Field(default_factory=dict, description="请求头")
    query_params: dict[str, str] = Field(default_factory=dict, description="查询参数")
    body_template: str | None = Field(default=None, description="请求体模板 (JSON)")
    timeout: int = Field(default=30, ge=1, le=300, description="超时时间（秒）")
    response_path: str | None = Field(
        default=None, description="响应 JSON 路径，如 data.result"
    )


class CodeConfigSchema(BaseModel):
    """代码工具配置"""

    language: str = Field(..., description="代码语言 (javascript/python)")
    code: str = Field(..., description="代码内容")
    dependencies: list[str] = Field(default_factory=list, description="依赖包列表")


class McpConfigSchema(BaseModel):
    """MCP Server 配置"""

    transport: str = Field(default="stdio", description="传输类型 (stdio/sse/http)")
    # stdio 模式
    command: str | None = Field(default=None, description="命令 (stdio 模式)")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: dict[str, str] = Field(default_factory=dict, description="环境变量")
    # SSE/HTTP 模式
    url: str | None = Field(default=None, description="URL (sse/http 模式)")
    headers: dict[str, str] = Field(default_factory=dict, description="请求头")


# ============ Tool Output Schemas ============


class ToolOut(BaseModel):
    """工具输出"""

    id: UUID | None = Field(default=None, description="工具 ID (自定义工具)")
    name: str = Field(..., description="工具名称（唯一标识）")
    display_name: str = Field(..., description="显示名称")
    description: str = Field(..., description="工具描述")
    type: ToolType = Field(..., description="工具类型")
    category: ToolCategory = Field(..., description="工具分类")
    icon: str | None = Field(default=None, description="图标（emoji 或 URL）")
    parameters: list[ToolParameterSchema] = Field(
        default_factory=list, description="参数列表"
    )
    is_enabled: bool = Field(default=True, description="是否启用")
    requires_config: bool = Field(
        default=False, description="是否需要配置（如 API Key）"
    )
    config_fields: list[str] = Field(default_factory=list, description="需要配置的字段")

    # 自定义工具额外字段
    custom_type: CustomToolType | None = Field(
        default=None, description="自定义工具类型"
    )
    http_config: HttpConfigSchema | None = Field(default=None, description="HTTP 配置")
    code_config: CodeConfigSchema | None = Field(default=None, description="代码配置")
    mcp_config: McpConfigSchema | None = Field(
        default=None, description="MCP Server 配置"
    )


class ToolListOut(BaseModel):
    """工具列表输出"""

    builtin: list[ToolOut] = Field(default_factory=list, description="内置工具")
    custom: list[ToolOut] = Field(default_factory=list, description="自定义工具")
    mcp: list[ToolOut] = Field(default_factory=list, description="MCP Server 工具")


class ToolDetailOut(ToolOut):
    """工具详情输出（包含更多信息）"""

    team_id: UUID | None = Field(default=None, description="所属团队")
    created_at: str | None = Field(default=None, description="创建时间")
    updated_at: str | None = Field(default=None, description="更新时间")
    created_by_name: str | None = Field(default=None, description="创建者名称")


# ============ Tool Input Schemas ============


class ToolCreateInput(BaseModel):
    """创建工具输入"""

    name: str = Field(..., min_length=1, max_length=100, description="工具名称")
    display_name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    description: str = Field(default="", description="工具描述")
    icon: str | None = Field(default=None, max_length=100, description="图标")
    category: ToolCategory = Field(default=ToolCategory.OTHER, description="分类")
    type: ToolType = Field(default=ToolType.CUSTOM, description="工具类型")
    custom_type: CustomToolType | None = Field(
        default=None, description="自定义工具类型（仅 type=custom 时有效）"
    )
    parameters: list[ToolParameterSchema] = Field(
        default_factory=list, description="参数定义"
    )
    http_config: HttpConfigSchema | None = Field(default=None, description="HTTP 配置")
    code_config: CodeConfigSchema | None = Field(default=None, description="代码配置")
    mcp_config: McpConfigSchema | None = Field(
        default=None, description="MCP Server 配置"
    )
    credentials: dict[str, str] = Field(default_factory=dict, description="凭证")
    is_enabled: bool = Field(default=True, description="是否启用")


class ToolUpdateInput(BaseModel):
    """更新工具输入"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1)
    icon: str | None = None
    category: ToolCategory | None = None
    custom_type: CustomToolType | None = None
    parameters: list[ToolParameterSchema] | None = None
    http_config: HttpConfigSchema | None = None
    code_config: CodeConfigSchema | None = None
    mcp_config: McpConfigSchema | None = None
    credentials: dict[str, str] | None = None
    is_enabled: bool | None = None


# ============ MCP Schemas ============


class McpToolInfoOut(BaseModel):
    """MCP 工具信息输出"""

    name: str = Field(..., description="工具名称")
    description: str | None = Field(default=None, description="工具描述")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="参数 JSON Schema"
    )


class McpToolsListRequest(BaseModel):
    """获取 MCP 工具列表请求"""

    mcp_config: McpConfigSchema = Field(..., description="MCP Server 配置")


class McpToolsListResponse(BaseModel):
    """获取 MCP 工具列表响应"""

    tools: list[McpToolInfoOut] = Field(
        default_factory=list, description="可用工具列表"
    )
    server_name: str | None = Field(default=None, description="服务器名称")
    server_version: str | None = Field(default=None, description="服务器版本")


# ============ Tool Execution Schemas ============


class ToolExecuteRequest(BaseModel):
    """工具执行请求"""

    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="参数")


class ToolExecuteResponse(BaseModel):
    """工具执行响应"""

    name: str = Field(..., description="工具名称")
    success: bool = Field(..., description="是否成功")
    result: Any = Field(default=None, description="执行结果")
    error: str | None = Field(default=None, description="错误信息")
    duration_ms: int | None = Field(default=None, description="执行耗时（毫秒）")


class CodeExecuteRequest(BaseModel):
    """代码执行请求（直接执行，不需要保存工具）"""

    language: str = Field(..., description="代码语言 (javascript/python)")
    code: str = Field(..., description="代码内容")
    params: dict[str, Any] = Field(default_factory=dict, description="传入参数")
    timeout: float = Field(default=30.0, ge=1.0, le=60.0, description="超时时间（秒）")


class CodeExecuteResponse(BaseModel):
    """代码执行响应"""

    success: bool = Field(..., description="是否成功")
    result: Any = Field(default=None, description="执行结果")
    error: str | None = Field(default=None, description="错误信息")
    logs: str | None = Field(default=None, description="日志输出")
    duration_ms: int | None = Field(default=None, description="执行耗时（毫秒）")


# ============ 内置工具元数据 ============

BUILTIN_TOOLS_METADATA: dict[str, dict[str, Any]] = {
    "get_current_time": {
        "display_name": "获取当前时间",
        "category": ToolCategory.TIME,
        "icon": "🕐",
        "requires_config": False,
    },
    "format_datetime": {
        "display_name": "格式化日期时间",
        "category": ToolCategory.TIME,
        "icon": "📅",
        "requires_config": False,
    },
    "calculate": {
        "display_name": "数学计算",
        "category": ToolCategory.MATH,
        "icon": "🔢",
        "requires_config": False,
    },
    "unit_convert": {
        "display_name": "单位转换",
        "category": ToolCategory.MATH,
        "icon": "📐",
        "requires_config": False,
    },
    "web_search": {
        "display_name": "网页搜索",
        "category": ToolCategory.SEARCH,
        "icon": "🔍",
        "requires_config": True,
        "config_fields": ["TAVILY_API_KEY"],
    },
    "fetch_webpage": {
        "display_name": "获取网页内容",
        "category": ToolCategory.WEB,
        "icon": "🌐",
        "requires_config": False,
    },
}

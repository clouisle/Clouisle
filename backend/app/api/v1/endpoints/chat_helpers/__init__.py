"""
Chat helper modules for modular organization.
"""

from .config import (
    get_language_instruction,
    build_system_prompt_with_language,
    get_streaming_config,
)
from .stream_utils import send_heartbeat_if_needed
from .message_builder import build_messages
from .model_utils import get_model_identifier, get_model_capabilities
from .tool_utils import get_agent_tools, get_tool_display_names
from .tool_executor import execute_tool_call, execute_http_tool, execute_code_tool
from .rag_utils import perform_rag_retrieval, aggregate_rag_contexts, build_rag_prompt
from .version_utils import (
    get_message_versions,
    get_version_count,
    build_message_out_with_versions,
)

__all__ = [
    "get_language_instruction",
    "build_system_prompt_with_language",
    "get_streaming_config",
    "send_heartbeat_if_needed",
    "build_messages",
    "get_model_identifier",
    "get_model_capabilities",
    "get_agent_tools",
    "get_tool_display_names",
    "execute_tool_call",
    "execute_http_tool",
    "execute_code_tool",
    "perform_rag_retrieval",
    "aggregate_rag_contexts",
    "build_rag_prompt",
    "get_message_versions",
    "get_version_count",
    "build_message_out_with_versions",
]

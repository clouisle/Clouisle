"""
Chat helper modules for modular organization.
"""

from .config import (
    get_streaming_config,
)
from .general import (
    get_item_value,
    parse_user_input_request,
    get_tool_execution_payloads,
    append_generated_images,
    collect_conversation_images,
    append_conversation_image_inventory,
    get_compression_trigger,
)
from .stream_utils import (
    StreamIdleTimeoutError,
    iter_with_idle_timeout,
    send_heartbeat_if_needed,
)
from .model_utils import (
    ChatModelResolution,
    get_model_capabilities,
    get_model_identifier,
    resolve_agent_chat_model,
)
from .tool_utils import get_agent_tools, get_tool_display_names
from app.api.v1.endpoints.chat_tools import (
    execute_tool_call,
    execute_http_tool,
    execute_code_tool,
)
from app.api.v1.endpoints.chat_rag import (
    perform_rag_retrieval,
    aggregate_rag_contexts,
    build_rag_prompt,
)
from .version_utils import (
    get_message_versions,
    get_version_count,
    build_message_out_with_versions,
)

__all__ = [
    "get_streaming_config",
    "get_item_value",
    "parse_user_input_request",
    "get_tool_execution_payloads",
    "append_generated_images",
    "collect_conversation_images",
    "append_conversation_image_inventory",
    "get_compression_trigger",
    "StreamIdleTimeoutError",
    "iter_with_idle_timeout",
    "send_heartbeat_if_needed",
    "ChatModelResolution",
    "resolve_agent_chat_model",
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

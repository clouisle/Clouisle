"""
Lazy stream result for deferred LLM execution.

When an LLM node is configured for streaming, instead of executing immediately,
it returns a LazyStreamResult. When an Answer node references this result,
the LLM execution is triggered and tokens are streamed directly to the Answer node.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.workflow.context import ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class LazyStreamResult:
    """
    A lazy result that defers LLM execution until referenced.

    When an Answer node resolves a variable pointing to this result,
    the LLM will execute and stream tokens using the Answer node's ID.
    """

    # LLM execution parameters
    model_id: str
    messages: list[dict[str, Any]]
    temperature: float
    max_tokens: int | None
    top_p: float
    response_format: dict[str, Any] | None = None

    # Context for execution
    context: "ExecutionContext" = None  # type: ignore
    source_node_id: str = ""

    # State
    _executed: bool = False
    _result: str | None = None
    _reasoning: str | None = None
    _usage: dict[str, int] | None = None

    async def execute(self, stream_to_node_id: str | None = None) -> str:
        """
        Execute the LLM call and return the result.

        Args:
            stream_to_node_id: If provided, stream tokens to this node ID

        Returns:
            The complete LLM response text
        """
        if self._executed:
            return self._result or ""

        from app.llm import model_manager
        from app.services.workflow.stream import StreamManager

        logger.info(
            f"LazyStreamResult executing LLM for node {self.source_node_id}, streaming to {stream_to_node_id}"
        )

        stream_manager = (
            StreamManager(self.context.run_id) if stream_to_node_id else None
        )

        full_response = ""
        full_reasoning = ""
        last_usage = None

        async for chunk in model_manager.chat_stream(
            messages=self.messages,
            model_id=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            response_format=self.response_format,
        ):
            # ChatStreamChunk has delta with content
            if chunk.delta and chunk.delta.content:
                full_response += chunk.delta.content
                # Stream token to the specified node (usually the Answer node)
                if stream_manager and stream_to_node_id:
                    await stream_manager.publish_token(
                        stream_to_node_id, chunk.delta.content
                    )

            # Capture reasoning content (thinking/chain-of-thought)
            if chunk.delta and chunk.delta.reasoning_content:
                full_reasoning += chunk.delta.reasoning_content

            # Capture usage from the last chunk
            if chunk.usage:
                last_usage = chunk.usage

        self._executed = True
        self._result = full_response
        self._reasoning = full_reasoning if full_reasoning else None
        self._usage = {
            "prompt_tokens": last_usage.prompt_tokens if last_usage else 0,
            "completion_tokens": last_usage.completion_tokens if last_usage else 0,
            "total_tokens": last_usage.total_tokens if last_usage else 0,
        }

        logger.info(
            f"LazyStreamResult completed, response length: {len(full_response)}, "
            f"reasoning length: {len(full_reasoning)}, usage: {self._usage}"
        )
        return full_response

    @property
    def reasoning(self) -> str | None:
        """Get the reasoning content after execution."""
        return self._reasoning

    @property
    def usage(self) -> dict[str, int] | None:
        """Get the usage stats after execution."""
        return self._usage

    def __repr__(self) -> str:
        status = "executed" if self._executed else "pending"
        return f"<LazyStreamResult({self.source_node_id}, {status})>"

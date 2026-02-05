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

    # Context for execution
    context: "ExecutionContext"
    source_node_id: str

    # State
    _executed: bool = False
    _result: str | None = None

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

        async for chunk in model_manager.chat_stream(
            messages=self.messages,
            model_id=self.model_id,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
        ):
            # ChatStreamChunk has delta with content
            if chunk.delta and chunk.delta.content:
                full_response += chunk.delta.content
                # Stream token to the specified node (usually the Answer node)
                if stream_manager and stream_to_node_id:
                    await stream_manager.publish_token(
                        stream_to_node_id, chunk.delta.content
                    )

        self._executed = True
        self._result = full_response

        logger.info(
            f"LazyStreamResult completed, response length: {len(full_response)}"
        )
        return full_response

    def __repr__(self) -> str:
        status = "executed" if self._executed else "pending"
        return f"<LazyStreamResult({self.source_node_id}, {status})>"

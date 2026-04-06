"""
基于聊天模型的重排序适配器
"""

import json
import logging
import re
from typing import Any

from app.llm.adapters.chat import BaseChatAdapter
from app.llm.types import Message, MessageRole, RerankResponse, RerankResult, Usage

from .base import BaseRerankAdapter

logger = logging.getLogger(__name__)


class LLMRerankAdapter(BaseRerankAdapter):
    """通过结构化 JSON 输出实现 LLM 重排序。"""

    MAX_DOCUMENT_CHARS = 3000

    def __init__(self, model_config: Any, chat_adapter: BaseChatAdapter):
        super().__init__(model_config)
        self.chat_adapter = chat_adapter

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        if not documents:
            return RerankResponse(model=self.model_config.model_id, results=[])

        response = await self._request_rerank(query, documents, **kwargs)
        results = self._parse_results(response.content or "", len(documents))

        if not results:
            raise ValueError("No valid rerank results returned by model")

        existing_indices = {item.index for item in results}
        for index in range(len(documents)):
            if index not in existing_indices:
                results.append(RerankResult(index=index, score=0.0))

        results.sort(key=lambda item: item.score, reverse=True)
        if top_n is not None:
            results = results[:top_n]

        return RerankResponse(
            model=self.model_config.model_id,
            results=results,
            usage=response.usage if response.usage else Usage(),
        )

    async def _request_rerank(
        self,
        query: str,
        documents: list[str],
        **kwargs: Any,
    ):
        messages = self._build_messages(query, documents)

        try:
            return await self.chat_adapter.chat(
                messages,
                response_format={"type": "json_object"},
                **kwargs,
            )
        except Exception as exc:
            logger.warning(
                "Rerank JSON mode failed for %s/%s, retrying without response_format: %s",
                getattr(self.model_config, "provider", "unknown"),
                getattr(self.model_config, "model_id", "unknown"),
                exc,
            )
            return await self.chat_adapter.chat(messages, **kwargs)

    def _build_messages(self, query: str, documents: list[str]) -> list[Message]:
        system_prompt = (
            "You are a reranking model. Rank the candidate documents by how well they "
            "answer the query. Return JSON only with this format: "
            '{"results":[{"index":0,"score":0.95,"reason":"short explanation"}]}. '
            "Include each document at most once. Scores must be between 0 and 1. "
            "Higher score means more relevant."
        )
        serialized_docs = "\n\n".join(
            f"[Document {index}]\n{self._truncate_document(doc)}"
            for index, doc in enumerate(documents)
        )
        user_prompt = f"Query:\n{query}\n\nCandidate documents:\n{serialized_docs}"
        return [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_prompt),
        ]

    def _truncate_document(self, content: str) -> str:
        if len(content) <= self.MAX_DOCUMENT_CHARS:
            return content
        return content[: self.MAX_DOCUMENT_CHARS].rstrip() + "\n...[truncated]"

    def _parse_results(self, content: str, document_count: int) -> list[RerankResult]:
        payload = self._extract_json_payload(content)
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("results", [])
        else:
            items = []

        parsed: list[RerankResult] = []
        seen_indices: set[int] = set()

        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                raw_index = item.get("index")
                if raw_index is None:
                    continue
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= document_count or index in seen_indices:
                continue

            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(1.0, score))

            reason = item.get("reason")
            if reason is not None:
                reason = str(reason)[:500]

            parsed.append(
                RerankResult(
                    index=index,
                    score=score,
                    reason=reason,
                )
            )
            seen_indices.add(index)

        return parsed

    def _extract_json_payload(self, content: str) -> Any:
        text = content.strip()
        if not text:
            return {}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

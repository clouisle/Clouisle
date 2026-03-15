"""
OpenAI-compatible native rerank adapter.

Used for providers exposing a dedicated `/rerank` endpoint, such as SiliconFlow.
"""

from typing import Any

import httpx

from app.llm.types import RerankResponse, RerankResult, Usage

from .base import BaseRerankAdapter


class OpenAICompatibleRerankAdapter(BaseRerankAdapter):
    """Call native rerank endpoints on OpenAI-compatible providers."""

    def _get_endpoint(self) -> str:
        if not getattr(self.model_config, "base_url", None):
            raise ValueError("Native rerank requires base_url to be configured")
        return str(self.model_config.base_url).rstrip("/") + "/rerank"

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = getattr(self.model_config, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_payload(
        self,
        query: str,
        documents: list[str],
        top_n: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_config.model_id,
            "query": query,
            "documents": documents,
            "return_documents": False,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        config = getattr(self.model_config, "config", None) or {}
        for field in (
            "instruction",
            "max_chunks_per_doc",
            "overlap_tokens",
            "return_documents",
        ):
            if kwargs.get(field) is not None:
                payload[field] = kwargs[field]
            elif config.get(field) is not None:
                payload[field] = config[field]

        return payload

    def _parse_usage(self, data: dict[str, Any]) -> Usage:
        tokens = data.get("tokens")
        if not tokens:
            meta = data.get("meta")
            if isinstance(meta, list) and meta:
                first_meta = meta[0]
                if isinstance(first_meta, dict):
                    tokens = first_meta.get("tokens")

        if not isinstance(tokens, dict):
            return Usage()

        prompt_tokens = int(tokens.get("input_tokens", 0) or 0)
        completion_tokens = int(tokens.get("output_tokens", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens

        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _parse_results(self, data: dict[str, Any]) -> list[RerankResult]:
        parsed: list[RerankResult] = []

        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue

            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue

            try:
                score = float(item.get("relevance_score", item.get("score", 0.0)) or 0.0)
            except (TypeError, ValueError):
                score = 0.0

            parsed.append(
                RerankResult(
                    index=index,
                    score=max(0.0, min(1.0, score)),
                )
            )

        parsed.sort(key=lambda item: item.score, reverse=True)
        return parsed

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
        **kwargs: Any,
    ) -> RerankResponse:
        if not documents:
            return RerankResponse(model=self.model_config.model_id, results=[])

        timeout = kwargs.get("timeout") or 60
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._get_endpoint(),
                headers=self._build_headers(),
                json=self._build_payload(query, documents, top_n, **kwargs),
            )
            response.raise_for_status()
            data = response.json()

        return RerankResponse(
            model=self.model_config.model_id,
            results=self._parse_results(data),
            usage=self._parse_usage(data),
        )

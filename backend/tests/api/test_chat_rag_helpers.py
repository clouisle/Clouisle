from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints.chat_helpers.rag_utils import (
    aggregate_rag_contexts,
    build_rag_prompt,
    perform_rag_retrieval,
)


@pytest.mark.anyio
async def test_perform_rag_retrieval_maps_canonical_results_to_legacy_keys():
    agent = SimpleNamespace()
    canonical = [
        {
            "kb_id": "kb-1",
            "kb_name": "Policies",
            "content": "Leave policy",
            "score": 0.8,
        }
    ]

    with patch(
        "app.api.v1.endpoints.chat_helpers.rag_utils._perform_retrieval",
        AsyncMock(return_value=canonical),
    ) as retrieval:
        results = await perform_rag_retrieval(agent, "leave")

    retrieval.assert_awaited_once_with(agent, "leave")
    assert results == [
        {
            "knowledge_base_id": "kb-1",
            "knowledge_base_name": "Policies",
            "content": "Leave policy",
            "metadata": {},
            "score": 0.8,
        }
    ]


def test_aggregate_rag_contexts_keeps_highest_scoring_duplicate():
    lower = {"content": "same", "score": 0.2}
    higher = {"content": "same", "score": 0.9}
    other = {"content": "other", "score": 0.5}

    assert aggregate_rag_contexts([lower, other, higher]) == [higher, other]


def test_build_rag_prompt_handles_empty_and_non_empty_contexts():
    assert build_rag_prompt([], "Question") == "Question"

    prompt = build_rag_prompt(
        [
            {
                "knowledge_base_name": "Policies",
                "content": "Leave policy",
                "score": 0.8,
            }
        ],
        "Question",
    )
    assert "[Knowledge Base: Policies]\nLeave policy" in prompt
    assert "User Question: Question" in prompt

"""Tests for LLM-based label suggestion service."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.retrieval_label_suggest import (
    suggest_label,
    suggest_labels_batch,
)


@pytest.mark.anyio
async def test_suggest_label_disabled_when_flag_is_false():
    """When RETRIEVAL_EVAL_LLM_LABELING_ENABLED=False, always return None."""
    kb = SimpleNamespace(id="kb-1", default_llm_model_id=None, team_id="team-1")
    user = SimpleNamespace(id="user-1")

    with patch("app.services.retrieval_label_suggest.settings") as mock_settings:
        mock_settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED = False

        result = await suggest_label("query", "chunk text", kb, user)

    assert result is None


@pytest.mark.anyio
async def test_suggest_label_returns_none_for_placeholder_implementation():
    """Current placeholder implementation always returns None even when enabled."""
    kb = SimpleNamespace(id="kb-1", default_llm_model_id="model-1", team_id="team-1")
    user = SimpleNamespace(id="user-1")

    with patch("app.services.retrieval_label_suggest.settings") as mock_settings:
        mock_settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED = True
        mock_settings.RETRIEVAL_EVAL_LLM_LABELING_TIMEOUT = 10

        result = await suggest_label("query", "chunk text", kb, user)

    # Placeholder implementation returns None
    assert result is None


@pytest.mark.anyio
async def test_suggest_labels_batch_returns_empty_when_disabled():
    """Batch suggestions return empty dict when feature is disabled."""
    kb = SimpleNamespace(id="kb-1", team_id="team-1")
    user = SimpleNamespace(id="user-1")
    chunks = [("chunk-1", "text 1"), ("chunk-2", "text 2")]

    with patch("app.services.retrieval_label_suggest.settings") as mock_settings:
        mock_settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED = False

        result = await suggest_labels_batch("query", chunks, kb, user)

    assert result == {}


@pytest.mark.anyio
async def test_suggest_labels_batch_maps_successful_suggestions():
    """Batch processing maps chunk IDs to successful grades, omits failures."""
    kb = SimpleNamespace(id="kb-1", default_llm_model_id="model-1", team_id="team-1")
    user = SimpleNamespace(id="user-1")
    chunks = [("chunk-1", "text 1"), ("chunk-2", "text 2"), ("chunk-3", "text 3")]

    with (
        patch("app.services.retrieval_label_suggest.settings") as mock_settings,
        patch("app.services.retrieval_label_suggest.suggest_label") as mock_suggest,
    ):
        mock_settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED = True
        # First succeeds with grade 3, second times out (None), third succeeds with grade 1
        mock_suggest.side_effect = [3, None, 1]

        result = await suggest_labels_batch("query", chunks, kb, user)

    assert result == {"chunk-1": 3, "chunk-3": 1}
    assert "chunk-2" not in result  # Timeout/failure omitted

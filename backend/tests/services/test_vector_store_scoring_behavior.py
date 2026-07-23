import importlib
from unittest.mock import Mock

from app.services.vector_store import vector_store

vector_store_module = importlib.import_module("app.services.vector_store")


def test_quick_similarity_scores_exact_partial_and_missing_terms():
    assert vector_store._quick_similarity_score("setup guide", [], "setup guide") == 0.0
    assert (
        vector_store._quick_similarity_score(
            "setup guide", ["setup", "guide"], "Complete setup guide"
        )
        == 1.0
    )
    assert (
        vector_store._quick_similarity_score(
            "setup help", ["setup", "missing"], "Setup instructions"
        )
        == 0.45
    )
    assert (
        vector_store._quick_similarity_score(
            "unknown", ["unknown"], "Setup instructions"
        )
        == 0.0
    )


def test_semantic_and_fulltext_scores_handle_boundaries():
    assert vector_store._estimate_semantic_similarity("", "content") == 0.0
    assert vector_store._estimate_semantic_similarity("setup", "setup guide") == 1.0
    assert vector_store._estimate_semantic_similarity("setup", "unrelated") == 0.0

    assert vector_store._calculate_fulltext_score("setup", [], "setup guide") == 0.0
    assert (
        vector_store._calculate_fulltext_score(
            "setup guide", ["setup", "guide"], "A setup guide"
        )
        == 1.0
    )
    assert (
        vector_store._calculate_fulltext_score(
            "setup missing", ["setup", "missing"], "Setup instructions"
        )
        == 0.5
    )
    assert (
        vector_store._calculate_fulltext_score(
            "unknown", ["unknown"], "Setup instructions"
        )
        == 0.0
    )


def test_rrf_merge_prioritizes_shared_results_without_mutating_inputs():
    vector_results = [
        {"chunk_id": "shared", "content": "vector shared", "score": 0.9},
        {"chunk_id": "vector", "content": "vector only", "score": 0.8},
    ]
    fulltext_results = [
        {"chunk_id": "shared", "content": "text shared", "score": 1.0},
        {"chunk_id": "text", "content": "text only", "score": 0.7},
    ]

    merged = vector_store._merge_results_rrf(vector_results, fulltext_results)

    assert [result["chunk_id"] for result in merged] == ["shared", "vector", "text"]
    assert merged[0] == {
        "chunk_id": "shared",
        "content": "vector shared",
        "score": 1.0,
        "search_type": "hybrid",
    }
    assert merged[1]["score"] == merged[2]["score"] == 0.4919
    assert vector_results[0]["score"] == 0.9
    assert fulltext_results[0]["score"] == 1.0


def test_search_term_and_token_parsing_filters_noise_and_duplicates(monkeypatch):
    monkeypatch.setattr(
        vector_store_module.jieba,
        "lcut",
        Mock(return_value=[" ", "a", "中", "!!!", "Setup", "setup", "Guide"]),
    )

    assert vector_store._extract_search_terms("ignored") == ["中", "setup", "guide"]
    assert vector_store._tokenize("ignored") == {"a", "中", "setup", "guide"}


def test_similarity_scoring_covers_high_ratio_and_partial_ngram_paths(monkeypatch):
    assert (
        vector_store._quick_similarity_score(
            "setup guide", ["setup", "guide"], "guide before setup"
        )
        == 1.0
    )
    assert vector_store._estimate_semantic_similarity("abcd", "xxabcxx") > 0.0

    monkeypatch.setattr(vector_store, "_tokenize", Mock(return_value=set()))
    assert vector_store._estimate_semantic_similarity("query", "content") == 0.0

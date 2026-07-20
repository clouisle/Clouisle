from app.services.vector_store import vector_store


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

import json
from unittest.mock import AsyncMock

import pytest

from app.services import retrieval, retrieval_rollout


@pytest.mark.asyncio
async def test_rollout_precedence_and_deterministic_assignment(monkeypatch):
    values = {
        "retrieval_hybrid_mode": "rollout",
        "retrieval_hybrid_team_ids": ["included"],
        "retrieval_hybrid_percentage": 0,
    }
    get_value = AsyncMock(side_effect=lambda key, default: values.get(key, default))
    monkeypatch.setattr(retrieval_rollout.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        retrieval_rollout.settings, "RETRIEVAL_HYBRID_KILL_SWITCH", False
    )

    assert await retrieval_rollout.hybrid_enabled(["included"]) is True
    assert await retrieval_rollout.hybrid_enabled(["excluded"]) is False
    assert retrieval_rollout.rollout_bucket(["b", "a", "a"]) == (
        retrieval_rollout.rollout_bucket(["a", "b"])
    )

    values["retrieval_hybrid_mode"] = "enabled"
    assert await retrieval_rollout.hybrid_enabled(["excluded"]) is True
    values["retrieval_hybrid_mode"] = "disabled"
    values["retrieval_hybrid_percentage"] = 100
    assert await retrieval_rollout.hybrid_enabled(["included"]) is False
    monkeypatch.setattr(
        retrieval_rollout.settings, "RETRIEVAL_HYBRID_KILL_SWITCH", True
    )
    assert await retrieval_rollout.hybrid_enabled(["included"]) is False


@pytest.mark.asyncio
async def test_rollout_setting_failure_preserves_current_behavior(monkeypatch):
    monkeypatch.setattr(
        retrieval_rollout.settings, "RETRIEVAL_HYBRID_KILL_SWITCH", False
    )
    monkeypatch.setattr(
        retrieval_rollout.SiteSetting,
        "get_value",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    assert await retrieval_rollout.hybrid_enabled(["team"]) is True


@pytest.mark.asyncio
async def test_metrics_and_shadow_are_bounded_and_privacy_safe(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(retrieval_rollout, "get_redis", AsyncMock(return_value=redis))

    await retrieval_rollout.record_metrics(
        candidate_count=2,
        timings=(("recall", 12.5), ("total", 12000.0)),
        fallback_count=1,
        error_count=0,
        index_version=3,
    )
    await retrieval_rollout.record_shadow(
        [
            {
                "chunk_id": "chunk-1",
                "content": "secret chunk",
                "query": "secret query",
            }
        ],
        latency_ms=4.5,
        index_version=3,
    )

    fields = [call.args[1:] for call in redis.hincrby.await_args_list]
    assert ("candidates", 2) in fields
    assert ("latency:recall:le:50", 1) in fields
    assert ("latency:total:le:inf", 1) in fields
    payload = json.loads(redis.lpush.await_args.args[1])
    assert payload == {
        "ids": [{"chunk_id": "chunk-1", "rank": 1}],
        "versions": {"retrieval": 1, "lexical_index": 3},
        "latency_ms": 4.5,
    }
    redis.ltrim.assert_awaited_once_with("retrieval:shadow:v1", 0, 999)


@pytest.mark.asyncio
async def test_observability_failures_never_escape(monkeypatch):
    monkeypatch.setattr(
        retrieval_rollout,
        "get_redis",
        AsyncMock(side_effect=RuntimeError("redis unavailable")),
    )

    await retrieval_rollout.record_metrics(
        candidate_count=0,
        timings=(),
        fallback_count=0,
        error_count=1,
        index_version=1,
    )


@pytest.mark.asyncio
async def test_retrieve_uses_vector_primary_and_isolated_hybrid_shadow(monkeypatch):
    primary = retrieval.RetrievalResponse(
        ({"chunk_id": "primary", "content": "answer"},), (), ()
    )
    shadow = retrieval.RetrievalResponse(
        ({"chunk_id": "shadow", "content": "must not escape"},), (), ()
    )
    retrieve_once = AsyncMock(side_effect=[primary, shadow])
    record_metrics = AsyncMock()
    record_shadow = AsyncMock()
    monkeypatch.setattr(retrieval, "hybrid_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(retrieval, "_retrieve_once", retrieve_once)
    monkeypatch.setattr(retrieval, "record_metrics", record_metrics)
    monkeypatch.setattr(retrieval, "record_shadow", record_shadow)
    monkeypatch.setattr(retrieval.settings, "RETRIEVAL_SHADOW_ENABLED", True)
    target = retrieval.RetrievalTarget(
        kb_id=retrieval.UUID("00000000-0000-0000-0000-000000000001"),
        kb_name="kb",
        team_id=retrieval.UUID("00000000-0000-0000-0000-000000000002"),
        status="active",
        embedding_model_id=retrieval.UUID("00000000-0000-0000-0000-000000000003"),
    )
    request = retrieval.RetrievalRequest(query="private query", targets=(target,))

    response = await retrieval.retrieve(request)

    assert response is primary
    assert retrieve_once.await_args_list[0].args[0].search_mode == "vector"
    assert retrieve_once.await_args_list[1].args[0] == retrieval._effective_request(
        request
    )
    assert record_shadow.await_args.args[0] == shadow.results
    record_metrics.assert_awaited_once()


@pytest.mark.asyncio
async def test_shadow_failure_does_not_change_primary_answer(monkeypatch):
    primary = retrieval.RetrievalResponse(({"chunk_id": "primary"},), (), ())
    monkeypatch.setattr(retrieval, "hybrid_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        retrieval,
        "_retrieve_once",
        AsyncMock(side_effect=[primary, RuntimeError("shadow failed")]),
    )
    monkeypatch.setattr(retrieval, "record_metrics", AsyncMock())
    monkeypatch.setattr(retrieval, "record_shadow", AsyncMock())
    monkeypatch.setattr(retrieval.settings, "RETRIEVAL_SHADOW_ENABLED", True)
    target = retrieval.RetrievalTarget(
        kb_id=retrieval.UUID("00000000-0000-0000-0000-000000000001"),
        kb_name="kb",
        team_id=retrieval.UUID("00000000-0000-0000-0000-000000000002"),
        status="active",
        embedding_model_id=retrieval.UUID("00000000-0000-0000-0000-000000000003"),
    )

    response = await retrieval.retrieve(
        retrieval.RetrievalRequest(query="private query", targets=(target,))
    )

    assert response is primary

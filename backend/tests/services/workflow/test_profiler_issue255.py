from unittest.mock import patch

import pytest

from app.services.workflow.profiler import ExecutionProfiler, NodeProfile, StageProfile


def test_finish_aggregates_metrics_bottlenecks_and_suggestions():
    profiler = ExecutionProfiler("run-1", "workflow-1")
    profiler._profile.node_profiles = {
        "llm": NodeProfile(
            "llm", "llm", duration_ms=6000, retries=3, tokens_used=11_001
        ),
        "http": NodeProfile("http", "http_request", duration_ms=2000),
        "code": NodeProfile("code", "code", duration_ms=1500, success=False),
        "template": NodeProfile("template", "template", cache_hit=True),
        "condition": NodeProfile("condition", "condition"),
        "variable": NodeProfile("variable", "variable_assignment"),
        "code-2": NodeProfile("code-2", "code"),
        "template-2": NodeProfile("template-2", "template"),
    }
    profiler._profile.stage_profiles = [
        StageProfile(0, ["llm"], duration_ms=4000, parallel_nodes=1),
        StageProfile(1, ["http", "code"], parallel_nodes=2),
        StageProfile(2, ["template", "condition"], parallel_nodes=2),
        StageProfile(3, ["variable", "code-2"], parallel_nodes=2),
    ]

    with patch("app.services.workflow.profiler.time.time", side_effect=[10.0, 20.0]):
        profiler.start()
        profile = profiler.finish()

    assert profile.total_nodes == 8
    assert profile.successful_nodes == 7
    assert profile.failed_nodes == 1
    assert profile.cached_nodes == 1
    assert profile.total_tokens == 11_001
    assert profile.total_retries == 3
    assert profile.cache_hit_rate == pytest.approx(0.125)
    assert profile.parallel_efficiency == pytest.approx(0.475)
    assert (profile.slowest_node_id, profile.slowest_node_ms) == ("llm", 6000)

    bottleneck_types = [item["type"] for item in profile.bottlenecks]
    assert bottleneck_types.count("slow_node") == 3
    assert {
        "high_retries",
        "sequential_bottleneck",
        "low_cache_rate",
    }.issubset(bottleneck_types)
    assert (
        next(item for item in profile.bottlenecks if item["node_id"] == "llm")[
            "severity"
        ]
        == "high"
    )
    assert (
        next(item for item in profile.bottlenecks if item["node_id"] == "http")[
            "severity"
        ]
        == "medium"
    )

    suggestions = "\n".join(profile.suggestions)
    assert "faster LLM model" in suggestions
    assert "HTTP request node http is slow" in suggestions
    assert "Code node code is slow" in suggestions
    assert "high retry count" in suggestions
    assert "sequential bottleneck" in suggestions
    assert "Cache hit rate is low" in suggestions
    assert "High token usage" in suggestions
    assert "Low parallel efficiency" in suggestions
    assert "High overall retry rate" in suggestions


def test_finish_detects_dominant_node_and_ignores_empty_sequential_stage():
    profiler = ExecutionProfiler("run-2", "workflow-2")
    profiler._profile.node_profiles["dominant"] = NodeProfile(
        "dominant", "answer", duration_ms=600
    )
    profiler._profile.stage_profiles = [
        StageProfile(0, [], duration_ms=400, parallel_nodes=1)
    ]

    with patch("app.services.workflow.profiler.time.time", side_effect=[5.0, 6.0]):
        profiler.start()
        profile = profiler.finish()

    assert profile.bottlenecks == [
        {
            "type": "dominant_node",
            "node_id": "dominant",
            "node_type": "answer",
            "percentage": 60.0,
            "severity": "medium",
        }
    ]
    assert profile.suggestions == []

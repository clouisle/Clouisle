"""Retrieval-specific rollout and fail-open observability helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from app.core.config import settings
from app.core.redis import get_redis
from app.models.site_setting import SiteSetting

METRIC_TTL_SECONDS = 604800
LATENCY_BUCKETS = (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


def rollout_bucket(team_ids: Sequence[str]) -> int:
    subject = ",".join(sorted(set(team_ids)))
    return int.from_bytes(hashlib.sha256(subject.encode()).digest()[:8], "big") % 100


async def hybrid_enabled(team_ids: Sequence[str]) -> bool:
    if settings.RETRIEVAL_HYBRID_KILL_SWITCH:
        return False
    try:
        mode = str(
            await SiteSetting.get_value("retrieval_hybrid_mode", "rollout")
        ).lower()
    except Exception:
        return True
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    try:
        included = {
            str(value)
            for value in await SiteSetting.get_value("retrieval_hybrid_team_ids", [])
        }
        percentage = int(
            await SiteSetting.get_value("retrieval_hybrid_percentage", 100)
        )
    except Exception:
        return True
    if included.intersection(team_ids):
        return True
    return rollout_bucket(team_ids) < max(0, min(100, percentage))


def _latency_bucket(latency_ms: float) -> str:
    return str(next((value for value in LATENCY_BUCKETS if latency_ms <= value), "inf"))


async def record_metrics(
    *,
    candidate_count: int,
    timings: Sequence[tuple[str, float]],
    fallback_count: int,
    error_count: int,
    index_version: int,
) -> None:
    try:
        redis = await get_redis()
        key = "retrieval:metrics:v1"
        values: dict[str, int] = {
            "requests": 1,
            "candidates": candidate_count,
            "fallbacks": fallback_count,
            "errors": error_count,
            "empty": int(candidate_count == 0),
            f"index_version:{index_version}": 1,
        }
        for stage, latency_ms in timings:
            values[f"latency:{stage}:count"] = 1
            values[f"latency:{stage}:sum_ms"] = round(latency_ms)
            values[f"latency:{stage}:le:{_latency_bucket(latency_ms)}"] = 1
        for field, value in values.items():
            await redis.hincrby(key, field, value)  # type: ignore[misc]
        await redis.expire(key, METRIC_TTL_SECONDS)  # type: ignore[misc]
    except Exception:
        return


async def record_shadow(
    results: Sequence[dict[str, Any]], *, latency_ms: float, index_version: int
) -> None:
    try:
        redis = await get_redis()
        payload = {
            "ids": [
                {"chunk_id": str(result.get("chunk_id") or ""), "rank": rank}
                for rank, result in enumerate(results, 1)
            ],
            "versions": {"retrieval": 1, "lexical_index": index_version},
            "latency_ms": latency_ms,
        }
        key = "retrieval:shadow:v1"
        await redis.lpush(  # type: ignore[misc]
            key, json.dumps(payload, separators=(",", ":"))
        )
        await redis.ltrim(key, 0, 999)  # type: ignore[misc]
        await redis.expire(key, METRIC_TTL_SECONDS)  # type: ignore[misc]
    except Exception:
        return

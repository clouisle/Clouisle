"""File-backed cache for parsed uploaded file content."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.upload import UPLOAD_ROOT
from app.services.file_parser import ParsedFile

CACHE_VERSION = "v1"
CACHE_DIR = UPLOAD_ROOT / ".cache" / "file-parses"


def build_parser_hash(parser_config: dict[str, Any], parse_config: Any) -> str:
    payload = {
        "version": CACHE_VERSION,
        "parser": parser_config,
        "parse": {
            "max_content_length": getattr(parse_config, "max_content_length", None),
            "truncate_strategy": getattr(parse_config, "truncate_strategy", None),
        },
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_source_signature(file_path: Path) -> dict[str, int]:
    stat = file_path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def build_cache_key(
    *,
    url: str,
    file_path: Path,
    parser_hash: str,
    source_signature: dict[str, int],
) -> str:
    payload = {
        "version": CACHE_VERSION,
        "url": url,
        "path": str(file_path.relative_to(UPLOAD_ROOT)),
        "parser_hash": parser_hash,
        "source": source_signature,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(cache_key: str) -> Path:
    return CACHE_DIR / cache_key[:2] / f"{cache_key}.json"


async def read_cached_file(
    file_item: dict[str, Any],
    *,
    file_path: Path,
    url: str,
    parser_hash: str,
) -> ParsedFile | None:
    metadata = file_item.get("parse_cache")
    if not isinstance(metadata, dict) or metadata.get("status") != "success":
        return None

    source_signature = build_source_signature(file_path)
    expected_key = build_cache_key(
        url=url,
        file_path=file_path,
        parser_hash=parser_hash,
        source_signature=source_signature,
    )
    if (
        metadata.get("key") != expected_key
        or metadata.get("parser_hash") != parser_hash
    ):
        return None
    if metadata.get("source") != source_signature:
        return None

    path = _cache_path(expected_key)
    if not path.is_file():
        return None

    try:
        raw = await run_in_threadpool(path.read_text, encoding="utf-8")
        data = json.loads(raw)
        return ParsedFile(**data["parsed_file"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError):
        return None


async def write_cached_file(
    file_item: dict[str, Any],
    parsed_file: ParsedFile,
    *,
    file_path: Path,
    url: str,
    parser_hash: str,
) -> dict[str, Any]:
    source_signature = build_source_signature(file_path)
    cache_key = build_cache_key(
        url=url,
        file_path=file_path,
        parser_hash=parser_hash,
        source_signature=source_signature,
    )
    path = _cache_path(cache_key)
    await run_in_threadpool(path.parent.mkdir, parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "parser_hash": parser_hash,
        "source": source_signature,
        "parsed_file": parsed_file.model_dump(mode="json"),
    }
    await run_in_threadpool(
        path.write_text,
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    updated = dict(file_item)
    updated["parse_cache"] = {
        "status": "success",
        "key": cache_key,
        "parser_hash": parser_hash,
        "source": source_signature,
        "cached_at": datetime.now(UTC).isoformat(),
    }
    return updated

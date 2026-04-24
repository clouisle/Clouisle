#!/usr/bin/env python3
"""Clear workflow runtime state from Redis ahead of the typed-variable cutover.

Background:
    The typed-variable refactor changes the on-the-wire format used by
    `ExecutionContext` and `WorkflowCache` from `json.dumps` to a
    msgpack-in-base64 frame (prefix `mp1:`). Old payloads can't be loaded by
    the new code (`loads_value` raises `ValueError` on a missing prefix), and
    new payloads are unreadable by old code. The contract is a hard cutover:
    drain the affected Redis namespaces during deployment.

What this script deletes:
    workflow:run:*   – per-run variables / outputs / branches / status / meta
    wf:cache:*       – workflow-definition / plan / node / llm / tool caches

What this script preserves:
    Anything not under the two prefixes above (auth tokens, sessions, etc.).

Usage:
    REDIS_URL=redis://localhost:6379 python scripts/clear_workflow_runtime.py
    REDIS_URL=redis://localhost:6379 python scripts/clear_workflow_runtime.py --dry-run

Exit code is non-zero if Redis is unreachable.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import redis  # type: ignore[import-not-found]
except ImportError:
    print(
        "Missing dependency: install `redis` (or run inside the backend uv env).",
        file=sys.stderr,
    )
    sys.exit(2)

PATTERNS = ["workflow:run:*", "wf:cache:*"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (env REDIS_URL also accepted).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count keys but do not delete.",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=500,
        help="Delete in batches of this size (default 500).",
    )
    args = parser.parse_args()

    try:
        client: "redis.Redis[bytes]" = redis.Redis.from_url(args.redis_url)
        client.ping()
    except Exception as exc:
        print(f"Cannot connect to {args.redis_url}: {exc}", file=sys.stderr)
        return 1

    grand_total = 0
    for pattern in PATTERNS:
        cursor = 0
        batch: list[bytes] = []
        deleted_for_pattern = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=args.batch)
            batch.extend(keys)
            while len(batch) >= args.batch:
                chunk, batch = batch[: args.batch], batch[args.batch :]
                if not args.dry_run:
                    client.delete(*chunk)
                deleted_for_pattern += len(chunk)
            if cursor == 0:
                break
        if batch:
            if not args.dry_run:
                client.delete(*batch)
            deleted_for_pattern += len(batch)
        action = "would delete" if args.dry_run else "deleted"
        print(f"{pattern}: {action} {deleted_for_pattern} key(s)")
        grand_total += deleted_for_pattern

    summary = "would delete" if args.dry_run else "deleted"
    print(f"Total: {summary} {grand_total} key(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

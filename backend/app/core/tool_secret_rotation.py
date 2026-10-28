"""Rotate tool-domain envelope secrets onto the configured primary key.

Usage::

    python -m app.core.tool_secret_rotation --dry-run
    python -m app.core.tool_secret_rotation --batch-size 200

Every value is rewrapped to the current primary key id. Legacy unprefixed
Fernet tokens are migrated too. Updates are compare-and-swap against the exact
old ciphertext (``filter(id=..., field=old).update(field=new)``) so a concurrent
token refresh/approval write is never overwritten; such rows are counted as
conflicts and left untouched. Undecryptable values are reported by row id and
make the command exit non-zero. No secret material is printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from uuid import UUID

from app.core.config import settings
from app.core.tool_secrets import (
    ENVELOPE_PREFIX,
    ToolSecretError,
    current_key_id,
    is_envelope,
    reencrypt_tool_secret,
)


def _source_key_id(value: str) -> str:
    if not is_envelope(value):
        return "legacy"
    key_id = value[len(ENVELOPE_PREFIX) :].partition(":")[0]
    return key_id or "malformed"


@dataclass
class RotationStats:
    model: str
    scanned: int = 0
    rotated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
    source_key_ids: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "scanned": self.scanned,
            "rotated": self.rotated,
            "unchanged": self.unchanged,
            "conflicts": self.conflicts,
            "failed": self.failed,
            "failures": self.failures,
            "source_key_ids": self.source_key_ids,
        }


@dataclass(frozen=True, slots=True)
class _Target:
    label: str
    model: type
    field: str


def _targets() -> tuple[_Target, ...]:
    from app.models.tool_approval import ToolExecution
    from app.models.tool_connection import ToolConnection
    from app.models.tool_interaction import InteractionRequest
    from app.models.tool_oauth import ToolOAuthFlow, ToolOAuthProvider

    return (
        _Target("ToolConnection", ToolConnection, "encrypted_config"),
        _Target("ToolExecution", ToolExecution, "parameters_cipher"),
        _Target("ToolOAuthProvider", ToolOAuthProvider, "client_secret_encrypted"),
        _Target("ToolOAuthFlow", ToolOAuthFlow, "code_verifier_encrypted"),
        _Target("InteractionRequest", InteractionRequest, "response_cipher"),
    )


async def _rotate_target(
    target: _Target,
    *,
    dry_run: bool,
    batch_size: int,
) -> RotationStats:
    stats = RotationStats(model=target.label)
    last_id: UUID | None = None
    while True:
        query = target.model.all()
        if last_id is not None:
            query = query.filter(id__gt=last_id)
        rows = await query.order_by("id").limit(batch_size)
        if not rows:
            break
        for row in rows:
            last_id = row.id
            old = getattr(row, target.field)
            if not old:
                continue
            stats.scanned += 1
            source = _source_key_id(old)
            stats.source_key_ids[source] = stats.source_key_ids.get(source, 0) + 1
            try:
                new, changed = reencrypt_tool_secret(old)
            except ToolSecretError:
                stats.failed += 1
                stats.failures.append(str(row.id))
                continue
            if not changed:
                stats.unchanged += 1
                continue
            if dry_run:
                stats.rotated += 1
                continue
            updated = await target.model.filter(
                id=row.id, **{target.field: old}
            ).update(**{target.field: new})
            if updated:
                stats.rotated += 1
            else:
                stats.conflicts += 1
    return stats


async def rotate_tool_secrets(*, dry_run: bool = False, batch_size: int = 200) -> dict:
    """Rewrap every tool-domain ciphertext; returns a secret-free summary."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    # Fail before touching rows if the keyring/primary key is unusable.
    key_id = current_key_id()
    stats = [
        await _rotate_target(target, dry_run=dry_run, batch_size=batch_size)
        for target in _targets()
    ]
    return {
        "key_id": key_id,
        "dry_run": dry_run,
        "rotated": sum(item.rotated for item in stats),
        "unchanged": sum(item.unchanged for item in stats),
        "conflicts": sum(item.conflicts for item in stats),
        "failed": sum(item.failed for item in stats),
        "targets": [item.as_dict() for item in stats],
    }


def _database_url() -> str:
    return settings.DATABASE_URL or (
        f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rewrap tool-domain secrets onto TOOL_SECRET_PRIMARY_KEY_ID"
    )
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument(
        "--batch-size", type=int, default=200, help="rows per keyset batch"
    )
    args = parser.parse_args(argv)

    async def _run() -> dict:
        from tortoise import Tortoise

        await Tortoise.init(db_url=_database_url(), modules={"models": ["app.models"]})
        try:
            return await rotate_tool_secrets(
                dry_run=args.dry_run, batch_size=args.batch_size
            )
        finally:
            await Tortoise.close_connections()

    summary = asyncio.run(_run())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

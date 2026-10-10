"""Small in-process Redis substitute for sandbox service tests.

The production stores use Lua to make a few multi-key mutations atomic. This
fake models those specific scripts in Python; it is not a general Redis emulator.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any


class FakeRedis:
    """Synchronous, thread-safe Redis subset shared with ``AsyncFakeRedis``."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, float] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    def _purge(self, key: str) -> None:
        expiry = self.expirations.get(key)
        if expiry is not None and expiry <= time.monotonic():
            self._delete_key(key)

    def _delete_key(self, key: str) -> bool:
        found = key in self.values or key in self.sorted_sets or key in self.hashes
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        self.sorted_sets.pop(key, None)
        self.hashes.pop(key, None)
        return found

    def _ttl_ms(self, key: str) -> int:
        self._purge(key)
        if (
            key not in self.values
            and key not in self.sorted_sets
            and key not in self.hashes
        ):
            return -2
        expiry = self.expirations.get(key)
        return -1 if expiry is None else max(0, int((expiry - time.monotonic()) * 1000))

    def get(self, name: str) -> str | None:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            return self.values.get(key)

    def set(
        self,
        name: str,
        value: Any,
        ex: float | None = None,
        px: float | None = None,
        nx: bool = False,
        xx: bool = False,
        **_options: Any,
    ) -> bool | None:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            exists = key in self.values or key in self.sorted_sets or key in self.hashes
            if (nx and exists) or (xx and not exists):
                return None
            self.values[key] = self._text(value)
            self.expirations.pop(key, None)
            if px is not None:
                self.expirations[key] = time.monotonic() + float(px) / 1000
            elif ex is not None:
                self.expirations[key] = time.monotonic() + float(ex)
            return True

    def setex(self, name: str, time_seconds: float, value: Any) -> bool:
        return bool(self.set(name, value, ex=time_seconds))

    def delete(self, *names: str) -> int:
        with self._lock:
            return sum(self._delete_key(self._text(name)) for name in names)

    def exists(self, name: str) -> int:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            return int(
                key in self.values or key in self.sorted_sets or key in self.hashes
            )

    def expire(self, name: str, time_seconds: float) -> bool:
        return self.pexpire(name, float(time_seconds) * 1000)

    def pexpire(self, name: str, time_ms: float) -> bool:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            if not self.exists(key):
                return False
            self.expirations[key] = time.monotonic() + float(time_ms) / 1000
            return True

    def ttl(self, name: str) -> int:
        milliseconds = self.pttl(name)
        return (
            -2
            if milliseconds == -2
            else -1
            if milliseconds == -1
            else milliseconds // 1000
        )

    def pttl(self, name: str) -> int:
        with self._lock:
            return self._ttl_ms(self._text(name))

    def zadd(self, name: str, mapping: Mapping[str, float]) -> int:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            items = self.sorted_sets.setdefault(key, {})
            added = 0
            for member, score in mapping.items():
                member = self._text(member)
                added += int(member not in items)
                items[member] = float(score)
            return added

    def zscore(self, name: str, value: str) -> float | None:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            return self.sorted_sets.get(key, {}).get(self._text(value))

    def zrem(self, name: str, *values: str) -> int:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            items = self.sorted_sets.get(key, {})
            removed = sum(self._text(value) in items for value in values)
            for value in values:
                items.pop(self._text(value), None)
            return removed

    @staticmethod
    def _score(value: Any, *, lower: bool) -> float:
        text = str(value).lower()
        if text in {"-inf", "-infinity"}:
            return float("-inf")
        if text in {"+inf", "inf", "+infinity", "infinity"}:
            return float("inf")
        if text.startswith("("):
            number = float(text[1:])
            return number + 1e-12 if lower else number - 1e-12
        return float(text)

    def zrangebyscore(
        self,
        name: str,
        min: Any,
        max: Any,
        start: int = 0,
        num: int | None = None,
        withscores: bool = False,
    ) -> list[Any]:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            low, high = self._score(min, lower=True), self._score(max, lower=False)
            selected = sorted(
                (
                    (member, score)
                    for member, score in self.sorted_sets.get(key, {}).items()
                    if low <= score <= high
                ),
                key=lambda item: (item[1], item[0]),
            )
            selected = (
                selected[start:] if num is None else selected[start : start + num]
            )
            return selected if withscores else [member for member, _ in selected]

    def zrange(
        self, name: str, start: int, end: int, withscores: bool = False
    ) -> list[Any]:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            items = sorted(
                self.sorted_sets.get(key, {}).items(),
                key=lambda item: (item[1], item[0]),
            )
            stop = len(items) if end == -1 else end + 1
            selected = items[start:stop]
            return selected if withscores else [member for member, _ in selected]

    def zremrangebyscore(self, name: str, min: Any, max: Any) -> int:
        with self._lock:
            key = self._text(name)
            self._purge(key)
            low, high = self._score(min, lower=True), self._score(max, lower=False)
            items = self.sorted_sets.get(key, {})
            removed = [
                member for member, score in items.items() if low <= score <= high
            ]
            for member in removed:
                items.pop(member, None)
            return len(removed)

    def hset(
        self,
        name: str,
        key: str | None = None,
        value: Any = None,
        mapping: Mapping[str, Any] | None = None,
    ) -> int:
        with self._lock:
            bucket = self.hashes.setdefault(self._text(name), {})
            pairs = dict(mapping or {})
            if key is not None:
                pairs[key] = value
            added = sum(self._text(field) not in bucket for field in pairs)
            bucket.update(
                {self._text(field): self._text(item) for field, item in pairs.items()}
            )
            return added

    def hget(self, name: str, key: str) -> str | None:
        with self._lock:
            self._purge(self._text(name))
            return self.hashes.get(self._text(name), {}).get(self._text(key))

    def hkeys(self, name: str) -> list[str]:
        with self._lock:
            self._purge(self._text(name))
            return list(self.hashes.get(self._text(name), {}))

    def hlen(self, name: str) -> int:
        return len(self.hkeys(name))

    def hdel(self, name: str, *keys: str) -> int:
        with self._lock:
            bucket = self.hashes.get(self._text(name), {})
            removed = sum(self._text(key) in bucket for key in keys)
            for key in keys:
                bucket.pop(self._text(key), None)
            return removed

    def mget(self, keys: Iterable[str] | str, *more_keys: str) -> list[str | None]:
        names = (
            [keys, *more_keys]
            if isinstance(keys, str)
            else list(keys) + list(more_keys)
        )
        return [self.get(name) for name in names]

    def eval(self, script: str, numkeys: int, *values: Any) -> Any:
        with self._lock:
            keys = [self._text(value) for value in values[:numkeys]]
            args = [self._text(value) for value in values[numkeys:]]
            if "owner.instance_id ~= ARGV[1]" in script:
                return self._refresh_worker(keys, args)
            if "cjson.decode(current).instance_id ~= ARGV[1]" in script:
                current = self.get(keys[0])
                if current is None or json.loads(current).get("instance_id") != args[0]:
                    return 0
                return self.delete(keys[0])
            if "local previous = redis.call('GET', KEYS[1])" in script:
                return self._save_result(keys, args)
            if "local status = redis.call('GET', KEYS[1])" in script:
                status = self.get(keys[0])
                if status in {"completed", "failed", "cancelled"}:
                    return 0
                return int(bool(self.set(keys[1], "1", ex=float(args[0]), nx=True)))
            if "local actual = redis.call('GET', KEYS[2])" in script:
                if not self._binding_matches(keys[1], args[0]):
                    return 0
                return self._session_script(script, keys, args)
            raise AssertionError(
                f"Unsupported Redis Lua script in sandbox tests: {script[:120]!r}"
            )

    def _binding_matches(self, key: str, expected_json: str) -> bool:
        actual_json = self.get(key)
        if not expected_json:
            return actual_json is None
        if actual_json is None:
            return False
        actual, expected = json.loads(actual_json), json.loads(expected_json)
        return all(
            actual.get(field) == expected.get(field)
            for field in (
                "epoch",
                "generation",
                "workspace_id",
                "instance_id",
                "worker_id",
                "node_id",
                "storage_id",
                "status",
            )
        )

    def _refresh_worker(self, keys: list[str], args: list[str]) -> int:
        current = self.get(keys[0])
        if current:
            owner = json.loads(current)
            if owner.get("instance_id") != args[0]:
                return 0
            if owner.get("storage_id") != args[3] or owner.get("node_id") != args[4]:
                return 0
        self.set(keys[0], args[1], ex=float(args[2]))
        self.hset(keys[1], args[5], args[1])
        return 1

    def _save_result(self, keys: list[str], args: list[str]) -> str | None:
        previous = self.get(keys[0])
        incoming = json.loads(args[1])
        status = args[2]
        if previous:
            old = json.loads(previous)
            if old.get("status") in {"completed", "failed", "cancelled"}:
                return previous
            ranks = {
                "queued": 0,
                "preparing": 1,
                "running": 2,
                "collecting": 3,
                "completed": 4,
                "failed": 4,
                "cancelled": 4,
            }
            if ranks.get(status, 0) < ranks.get(old.get("status"), 0):
                return previous
        deadline = incoming.get("deadline_at")
        if (
            deadline is not None
            and status not in {"failed", "cancelled"}
            and time.time() >= float(deadline)
        ):
            return "__DEADLINE__"
        if args[3]:
            actual_payload = self.get(keys[2])
            if not actual_payload:
                return None
            actual, expected = json.loads(actual_payload), json.loads(args[3])
            if (
                any(
                    actual.get(field) != expected.get(field)
                    for field in (
                        "epoch",
                        "generation",
                        "workspace_id",
                        "worker_id",
                        "instance_id",
                        "node_id",
                        "storage_id",
                    )
                )
                or actual.get("status") != "READY"
            ):
                return None
        ttl = float(args[0])
        self.setex(keys[0], ttl, args[1])
        self.setex(keys[1], ttl, status)
        return args[1]

    def _session_script(self, script: str, keys: list[str], args: list[str]) -> Any:
        if "b.status = 'RECOVERING'" in script:
            if not self.exists(keys[0]) or not self.set(
                keys[2], args[1], px=float(args[2]), nx=True
            ):
                return 0
            binding = json.loads(args[3])
            binding["status"] = "RECOVERING"
            binding["recovery_id"] = args[1]
            if binding.get("recovery_started_at") is None:
                binding["recovery_started_at"] = float(args[4])
            ttl = max(1, self.pttl(keys[0]) + float(args[5]))
            self.set(keys[1], json.dumps(binding), px=ttl)
            return json.dumps(binding)

        if "s.revision = (s.revision or 0) + 1" in script:
            if self.get(keys[2]) != args[1] or not self.exists(keys[0]):
                return 0
            session_ttl = self.pttl(keys[0])
            self.set(keys[1], args[2], px=max(1, session_ttl + float(args[4])))
            self.delete(keys[2], keys[3])
            session = json.loads(self.get(keys[0]))
            if args[3] == "1":
                session["disk_usage_bytes"] = 0
            session["revision"] = session.get("revision", 0) + 1
            self.set(keys[0], json.dumps(session), px=max(1, self.pttl(keys[0])))
            return 1

        if "if redis.call('GET', KEYS[3]) ~= ARGV[2] then return 0 end" in script:
            if self.get(keys[2]) != args[1] or not self.exists(keys[0]):
                return 0
            self.set(keys[1], args[2], px=max(1, self.pttl(keys[0]) + float(args[3])))
            return 1

        if "local binding_ttl_ms" in script:
            payload = self.get(keys[0])
            create = args[1] == "1"
            if create:
                if payload or self.exists(keys[1]):
                    return 0
            else:
                if not payload or json.loads(payload).get("revision", 0) != int(
                    args[2]
                ):
                    return 0
            ttl = float(args[3])
            self.setex(keys[0], ttl, args[4])
            if self.exists(keys[1]):
                self.pexpire(keys[1], ttl * 1000 + float(args[9]))
            self.zrem(keys[5], args[7])
            self.zrem(keys[6], args[7])
            self.zadd(keys[2], {args[7]: float(args[5])})
            self.zadd(keys[3], {args[7]: float(args[6])})
            if args[8]:
                self.setex(keys[4], ttl, args[7])
            return 1

        if "ARGV[2] == 'compare'" in script:
            mode, round_id, ttl = args[1], args[2], args[3]
            if mode == "compare":
                if self.get(keys[0]) != round_id:
                    return 0
                self.delete(keys[0])
            elif mode == "delete":
                self.delete(keys[0])
            elif ttl:
                self.setex(keys[0], float(ttl), round_id)
            else:
                self.set(keys[0], round_id)
            return 1

        if "redis.call('ZREM', KEYS[1], ARGV[2])" in script:
            self.zrem(keys[0], args[1])
            self.zrem(keys[2], args[1])
            return 1

        if "local score = redis.call('ZSCORE', KEYS[3], ARGV[2])" in script:
            score = self.zscore(keys[2], args[1])
            if score is None:
                return 0
            if float(score) > float(args[2]):
                return 0
            if "redis.call('ZREM', KEYS[3], ARGV[2])" in script:
                self.zrem(keys[2], args[1])
            self.zadd(keys[3] if len(keys) == 4 else keys[2], {args[1]: float(args[3])})
            return 1

        if "ARGV[2] == '1' and payload" in script:
            payload = self.get(keys[0])
            if args[1] == "1" and payload:
                return 0
            if payload:
                session = json.loads(payload)
                conversation_id = session.get("conversation_id")
                if conversation_id:
                    conversation_key = args[3] + conversation_id
                    if self.get(conversation_key) == args[4]:
                        self.delete(conversation_key)
            if args[2]:
                self.set(keys[1], args[2], px=float(args[5]))
            self.delete(keys[0], keys[2], keys[3], keys[6])
            for key in (keys[4], keys[5], keys[7], keys[8]):
                self.zrem(key, args[4])
            return 1

        raise AssertionError(f"Unsupported sandbox session script: {script[:160]!r}")

    def ping(self) -> bool:
        return True

    def flushdb(self) -> bool:
        with self._lock:
            self.values.clear()
            self.expirations.clear()
            self.sorted_sets.clear()
            self.hashes.clear()
        return True

    def close(self) -> None:
        return None


class AsyncFakeRedis:
    """Async Redis-shaped view over a shared ``FakeRedis`` instance."""

    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.get(*args, **kwargs)

    async def set(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.set(*args, **kwargs)

    async def setex(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.setex(*args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.delete(*args, **kwargs)

    async def exists(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.exists(*args, **kwargs)

    async def expire(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.expire(*args, **kwargs)

    async def pexpire(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.pexpire(*args, **kwargs)

    async def ttl(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.ttl(*args, **kwargs)

    async def pttl(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.pttl(*args, **kwargs)

    async def zadd(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zadd(*args, **kwargs)

    async def zscore(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zscore(*args, **kwargs)

    async def zrem(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zrem(*args, **kwargs)

    async def zrange(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zrange(*args, **kwargs)

    async def zrangebyscore(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zrangebyscore(*args, **kwargs)

    async def zremrangebyscore(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.zremrangebyscore(*args, **kwargs)

    async def hset(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.hset(*args, **kwargs)

    async def hget(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.hget(*args, **kwargs)

    async def hkeys(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.hkeys(*args, **kwargs)

    async def hlen(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.hlen(*args, **kwargs)

    async def mget(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.mget(*args, **kwargs)

    async def eval(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis.eval(*args, **kwargs)

    async def aclose(self) -> None:
        return None

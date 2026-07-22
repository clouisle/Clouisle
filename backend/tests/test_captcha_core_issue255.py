import hashlib
import json
from collections.abc import Iterator

import pytest

from app.core import captcha


class ExpiringCache:
    def __init__(self, clock: list[float]) -> None:
        self.clock = clock
        self.values: dict[str, tuple[float, str]] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = (self.clock[0] + ttl, value)

    async def getdel(self, key: str) -> str | None:
        value = await self.get(key)
        self.values.pop(key, None)
        return value

    async def get(self, key: str) -> str | None:
        expires_at, value = self.values.get(key, (0, ""))
        if expires_at <= self.clock[0]:
            self.values.pop(key, None)
            return None
        return value


@pytest.fixture
def cache(monkeypatch: pytest.MonkeyPatch) -> tuple[ExpiringCache, list[float]]:
    clock = [1_000.0]
    store = ExpiringCache(clock)

    async def get_cache() -> ExpiringCache:
        return store

    monkeypatch.setattr(captcha, "get_redis", get_cache)
    monkeypatch.setattr(captcha.time, "time", lambda: clock[0])
    return store, clock


def pointer() -> list[dict[str, object]]:
    return [
        {"x": 100, "y": 100, "t": 0, "event": "enter"},
        {"x": 80, "y": 105, "t": 100},
        {"x": 60, "y": 95, "t": 220},
        {"x": 40, "y": 105, "t": 330, "event": "down"},
        {"x": 41, "y": 106, "t": 450, "event": "up"},
    ]


def set_tokens(monkeypatch: pytest.MonkeyPatch, *tokens: str) -> None:
    values: Iterator[str] = iter(tokens)
    monkeypatch.setattr(captcha.secrets, "token_urlsafe", lambda _size: next(values))


@pytest.mark.parametrize(
    "elapsed_ms", [captcha.MIN_ELAPSED_MS, captcha.CAPTCHA_TTL * 1000]
)
def test_pointer_elapsed_boundaries_are_inclusive(elapsed_ms: int) -> None:
    assert captcha._is_human_pointer_trajectory(pointer(), elapsed_ms) is True


@pytest.mark.parametrize(
    ("candidate", "elapsed_ms"),
    [
        (pointer(), captcha.MIN_ELAPSED_MS - 1),
        (pointer(), captcha.CAPTCHA_TTL * 1000 + 1),
        (pointer()[:4], 700),
        ([{"y": 1, "t": 0}] * 5, 700),
        ([{"x": float("inf"), "y": 1, "t": 0}] * 5, 700),
        ([{**point, "t": -1} for point in pointer()], 700),
        ([{**point, "x": 1, "y": 1} for point in pointer()], 700),
        ([{**point, "event": "move"} for point in pointer()], 700),
        (pointer()[:-1] + [{"x": 80, "y": 80, "t": 450, "event": "up"}], 700),
        (
            pointer()[:-2]
            + [
                {"x": -1, "y": 105, "t": 330, "event": "down"},
                {"x": -1, "y": 106, "t": 450, "event": "up"},
            ],
            700,
        ),
        (pointer()[:2] + [{**pointer()[2], "t": 50}] + pointer()[3:], 700),
        (pointer()[:1] + [{"x": 600, "y": 100, "t": 1}] + pointer()[2:], 700),
        (
            [
                {"x": 0, "y": 0, "t": 0},
                {"x": 8, "y": 8, "t": 100},
                {"x": 16, "y": 16, "t": 200},
                {"x": 20, "y": 20, "t": 300, "event": "down"},
                {"x": 20, "y": 20, "t": 400, "event": "up"},
            ],
            700,
        ),
        (
            [
                {"x": 100, "y": 100, "t": 0},
                {"x": 80, "y": 100, "t": 100},
                {"x": 60, "y": 100, "t": 200},
                {"x": 40, "y": 100, "t": 300, "event": "down"},
                {"x": 40, "y": 100, "t": 400, "event": "up"},
            ],
            700,
        ),
        (
            [
                {"x": 100, "y": 100, "t": 0},
                {"x": 90, "y": 100, "t": 100},
                {"x": 90, "y": 90, "t": 200},
                {"x": 80, "y": 90, "t": 300, "event": "down"},
                {"x": 80, "y": 90, "t": 400, "event": "up"},
            ],
            700,
        ),
        (
            [
                {"x": 100, "y": 100, "t": 0},
                {"x": 80, "y": 100, "t": 100},
                {"x": 60, "y": 100, "t": 200},
                {"x": 40, "y": 100, "t": 300, "event": "down"},
                {"x": 40, "y": 100, "t": 300, "event": "up"},
            ],
            700,
        ),
    ],
)
def test_pointer_rejects_boundary_violations(
    candidate: list[dict[str, object]], elapsed_ms: int
) -> None:
    assert captcha._is_human_pointer_trajectory(candidate, elapsed_ms) is False


@pytest.mark.asyncio
async def test_generate_mint_verify_and_replay(
    cache: tuple[ExpiringCache, list[float]], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, clock = cache
    set_tokens(monkeypatch, "captcha-id", "private-marker", "proof-token")

    captcha_id, challenge = await captcha.generate_captcha()
    public = json.loads(challenge)

    assert captcha_id == "captcha-id"
    assert public["created_at"] == 1_000_000
    assert public["marker"] == hashlib.sha256(b"private-marker").hexdigest()
    assert await captcha.get_captcha_answer(captcha_id) is None

    proof = await captcha.create_captcha_proof(
        captcha_id, challenge, "human_check", 450, pointer()
    )

    assert proof == "proof-token"
    assert await captcha.get_captcha_answer(captcha_id) == "proof-token"
    assert await captcha.verify_captcha(captcha_id, " proof-token ") is True
    assert await captcha.verify_captcha(captcha_id, proof) is False
    assert clock[0] == 1_000.0
    assert store.values == {}


@pytest.mark.asyncio
async def test_expired_proof_and_bad_signature_are_consumed(
    cache: tuple[ExpiringCache, list[float]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, clock = cache
    set_tokens(
        monkeypatch,
        "first-id",
        "first-marker",
        "first-proof",
        "second-id",
        "second-marker",
        "second-proof",
    )

    first_id, first_challenge = await captcha.generate_captcha()
    first_proof = await captcha.create_captcha_proof(
        first_id, first_challenge, "human_check", 450, pointer()
    )
    clock[0] += captcha.CAPTCHA_TTL
    assert await captcha.verify_captcha(first_id, first_proof or "") is False

    second_id, second_challenge = await captcha.generate_captcha()
    second_proof = await captcha.create_captcha_proof(
        second_id, second_challenge, "human_check", 450, pointer()
    )
    assert await captcha.verify_captcha(second_id, "wrong-signature") is False
    assert await captcha.verify_captcha(second_id, second_proof or "") is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("captcha_id", "challenge", "clicked_option"),
    [
        ("", "{}", "human_check"),
        ("id", "not-json", "human_check"),
        ("id", '{"type":"other"}', "human_check"),
        ("id", '{"type":"click-choice","options":["other"]}', "human_check"),
        (
            "id",
            '{"type":"click-choice","options":["human_check"],"marker":1}',
            "human_check",
        ),
    ],
)
async def test_mint_rejects_invalid_configuration_without_issuing_proof(
    cache: tuple[ExpiringCache, list[float]],
    captcha_id: str,
    challenge: str,
    clicked_option: str,
) -> None:
    store, _clock = cache

    assert (
        await captcha.create_captcha_proof(
            captcha_id, challenge, clicked_option, 450, pointer()
        )
        is None
    )
    assert not any(key.startswith(captcha.CAPTCHA_PROOF_PREFIX) for key in store.values)


@pytest.mark.asyncio
async def test_mint_rejects_expired_and_mismatched_markers(
    cache: tuple[ExpiringCache, list[float]], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _clock = cache
    valid_marker = hashlib.sha256(b"stored").hexdigest()
    challenge = json.dumps(
        {"type": "click-choice", "options": ["human_check"], "marker": valid_marker}
    )

    assert (
        await captcha.create_captcha_proof(
            "expired", challenge, "human_check", 450, pointer()
        )
        is None
    )

    await store.setex("captcha:mismatch", captcha.CAPTCHA_TTL, "different")
    monkeypatch.setattr(captcha.secrets, "compare_digest", lambda _left, _right: False)
    assert (
        await captcha.create_captcha_proof(
            "mismatch", challenge, "human_check", 450, pointer()
        )
        is None
    )


@pytest.mark.asyncio
async def test_verify_rejects_missing_inputs_without_cache_access(
    cache: tuple[ExpiringCache, list[float]],
) -> None:
    assert await captcha.verify_captcha("", "token") is False
    assert await captcha.verify_captcha("id", "") is False

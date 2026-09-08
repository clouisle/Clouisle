import pytest

from app.core import i18n
from app.core.i18n_legacy import TRANSLATIONS


@pytest.fixture(autouse=True)
def reset_language():
    token = i18n.current_language.set("en")
    try:
        yield
    finally:
        i18n.current_language.reset(token)


def test_retrieval_failure_copy_is_generic_and_fully_rendered():
    for language, expected in (
        ("en", "Knowledge retrieval failed. Please try again."),
        ("zh", "知识检索失败，请稍后重试。"),
    ):
        message = i18n.t("vector_search_failed", lang=language)
        assert message == expected
        assert "{error}" not in message


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (None, "en"),
        ("ZH-cn", "zh"),
        ("en-US", "en"),
        ("unsupported", "en"),
        ("", "en"),
    ],
)
def test_normalize_language_resolves_supported_locale(language, expected):
    assert i18n.normalize_language(language) == expected


def test_language_context_uses_normalized_value_and_default():
    assert i18n.get_language() == "en"

    i18n.set_language("zh-CN")

    assert i18n.get_language() == "zh"


def test_translation_falls_back_to_english_babel_catalog(monkeypatch):
    messages = {
        "zh": {},
        "en": {"greeting": "Hello {name}"},
    }
    monkeypatch.setattr(
        i18n, "_get_babel_message", lambda key, lang: messages[lang].get(key)
    )

    assert i18n.t("greeting", lang="zh", name="Ada") == "Hello Ada"


def test_translation_falls_back_to_legacy_key_and_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(i18n, "_get_babel_message", lambda key, lang: None)
    i18n._MISSING_BABEL_KEYS_LOGGED.clear()

    assert i18n.t("access_denied", lang="zh") == TRANSLATIONS["access_denied"]["zh"]
    assert i18n.t("access_denied", lang="zh") == TRANSLATIONS["access_denied"]["zh"]

    assert (
        caplog.messages.count(
            "Missing Babel translation in locale 'zh'; using legacy fallback"
        )
        == 1
    )


def test_translation_returns_key_when_no_catalog_contains_it(monkeypatch):
    monkeypatch.setattr(i18n, "_get_babel_message", lambda key, lang: None)

    assert i18n.t("not_a_translation_key", lang="zh") == "not_a_translation_key"


def test_translation_keeps_unformatted_message_when_arguments_are_incomplete(
    monkeypatch,
):
    monkeypatch.setattr(
        i18n,
        "_get_babel_message",
        lambda key, lang: "Welcome, {name}!" if key == "welcome" else None,
    )

    assert i18n.t("welcome", name="Ada") == "Welcome, Ada!"
    assert i18n.t("welcome", locale="zh") == "Welcome, {name}!"


def test_has_translation_checks_babel_english_and_legacy_fallbacks(monkeypatch):
    messages = {
        "zh": {"localized": "本地化"},
        "en": {"english_only": "English only"},
    }
    monkeypatch.setattr(
        i18n, "_get_babel_message", lambda key, lang: messages[lang].get(key)
    )

    assert i18n.has_translation("localized", lang="zh")
    assert i18n.has_translation("english_only", lang="zh")
    assert i18n.has_translation("access_denied", lang="zh")
    assert not i18n.has_translation("")
    assert not i18n.has_translation("missing", lang="zh")


def test_code_message_uses_unknown_error_for_unmapped_or_invalid_codes(monkeypatch):
    translated_keys = []
    monkeypatch.setattr(
        i18n,
        "t",
        lambda key, lang=None: translated_keys.append((key, lang)) or key,
    )

    assert i18n.get_code_message(999999, lang="zh") == "unknown_error"

    assert translated_keys == [("unknown_error", "zh")]


def test_all_response_codes_mapped_to_valid_translation_keys():
    from app.schemas.response import ResponseCode

    for code in ResponseCode:
        msg_key = None

        def mock_t(key, lang=None, **kwargs):
            nonlocal msg_key
            msg_key = key
            return key

        old_t = i18n.t
        i18n.t = mock_t
        try:
            i18n.get_code_message(code)
        finally:
            i18n.t = old_t

        if code != ResponseCode.UNKNOWN_ERROR:
            assert msg_key != "unknown_error", f"{code} mapped to unknown_error"
            assert i18n.has_translation(msg_key), (
                f"{code} key {msg_key} missing from catalog"
            )


@pytest.mark.asyncio
async def test_resolve_language_follows_user_system_default_precedence(monkeypatch):
    # 1. User specified -> user wins over system and default
    monkeypatch.setattr(
        i18n,
        "get_default_language",
        lambda: __import__("asyncio").sleep(0, result="zh"),
    )
    assert await i18n.resolve_language("en") == "en"

    monkeypatch.setattr(
        i18n,
        "get_default_language",
        lambda: __import__("asyncio").sleep(0, result="en"),
    )
    assert await i18n.resolve_language("zh-CN") == "zh"

    # 2. No user specified -> system wins over default
    monkeypatch.setattr(
        i18n,
        "get_default_language",
        lambda: __import__("asyncio").sleep(0, result="zh"),
    )
    assert await i18n.resolve_language(None) == "zh"
    assert await i18n.resolve_language("") == "zh"

    # 3. Neither specified -> default ('en') wins
    monkeypatch.setattr(
        i18n, "get_default_language", lambda: __import__("asyncio").sleep(0, result="")
    )
    assert await i18n.resolve_language(None) == "en"


@pytest.mark.asyncio
async def test_get_default_language_discards_stale_fetch_if_cache_updated(monkeypatch):
    import asyncio
    from app.models import SiteSetting

    i18n.set_default_language_cache("en")

    async def slow_get_value(key, default):
        await asyncio.sleep(0.01)
        return "es"

    monkeypatch.setattr(SiteSetting, "get_value", slow_get_value)

    fetch_task = asyncio.create_task(i18n.get_default_language())
    await asyncio.sleep(
        0
    )  # Yield to allow fetch_task to begin and capture read_version

    # Simulate concurrent settings write advancing cache version while fetch is in-flight
    i18n.set_default_language_cache("zh")
    assert i18n.get_default_language_sync() == "zh"

    result = await fetch_task
    # Stale read should not overwrite "zh"
    assert i18n.get_default_language_sync() == "zh"
    assert result == "zh"
    i18n.set_default_language_cache("en")


def test_resolve_language_sync_follows_user_system_default_precedence(monkeypatch):
    # 1. User specified -> user wins over system and default
    i18n.set_default_language_cache("zh")
    assert i18n.resolve_language_sync("en") == "en"

    i18n.set_default_language_cache("en")
    assert i18n.resolve_language_sync("zh-CN") == "zh"

    # 2. No user specified -> system wins over default
    i18n.set_default_language_cache("zh")
    assert i18n.resolve_language_sync(None) == "zh"
    assert i18n.resolve_language_sync("") == "zh"

    # 3. Neither specified -> default ('en') wins
    i18n.set_default_language_cache(None)
    monkeypatch.setattr(i18n, "_cached_default_language", "")
    assert i18n.resolve_language_sync(None) == "en"


def test_system_prompt_and_terminal_content_follow_user_system_default_precedence():
    from app.services.system_prompt import build_system_prompt
    from app.api.v1.endpoints.chat import build_max_iterations_terminal_content
    from types import SimpleNamespace

    agent = SimpleNamespace(id="agent-test", system_prompt="", tools_config=[])

    try:
        # System is configured as Chinese
        i18n.set_default_language_cache("zh")

        # Case A: user has no preference -> system default (zh) applies
        prompt = build_system_prompt(agent, user_locale=None)
        assert "## 回复语言\n你必须使用中文回复。不要使用其他语言。" in prompt
        terminal = build_max_iterations_terminal_content(user_locale=None)
        assert "本轮已达到最大工具调用轮次" in terminal

        # Case B: user explicitly requests English -> user (en) wins over system (zh)
        prompt_en = build_system_prompt(agent, user_locale="en")
        assert "## Response Language\nYou MUST respond in English only." in prompt_en
        terminal_en = build_max_iterations_terminal_content(user_locale="en")
        assert "maximum tool-call iterations" in terminal_en
    finally:
        i18n.set_default_language_cache("en")

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

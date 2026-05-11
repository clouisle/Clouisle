from __future__ import annotations

from pathlib import Path
from typing import Final

from babel.messages import pofile

ROOT: Final = Path(__file__).resolve().parents[1]
LOCALES_DIR: Final = ROOT / "app" / "locales"
LEGACY_PATH: Final = ROOT / "app" / "core" / "i18n_legacy.py"
DOMAIN: Final = "messages"
SUPPORTED_LANGS: Final[tuple[str, ...]] = ("en", "zh")
HEADER: Final = (
    '"""Generated legacy compatibility translations from Babel catalogs."""\n\n'
)


def load_catalog(lang: str) -> dict[str, str]:
    po_path = LOCALES_DIR / lang / "LC_MESSAGES" / f"{DOMAIN}.po"
    if not po_path.exists():
        raise FileNotFoundError(f"Missing catalog: {po_path}")

    with po_path.open("r", encoding="utf-8") as file_obj:
        catalog = pofile.read_po(file_obj)

    messages: dict[str, str] = {}
    for key, message in catalog._messages.items():
        if isinstance(key, str) and key:
            value = message.string if isinstance(message.string, str) else ""
            messages[key] = value
    return messages


def build_translations() -> dict[str, dict[str, str]]:
    catalogs = {lang: load_catalog(lang) for lang in SUPPORTED_LANGS}
    keys = sorted(catalogs[SUPPORTED_LANGS[0]])
    translations: dict[str, dict[str, str]] = {}
    for key in keys:
        translations[key] = {
            lang: catalogs[lang].get(key) or catalogs[SUPPORTED_LANGS[0]].get(key, key)
            for lang in SUPPORTED_LANGS
        }
    return translations


def render_legacy_module(translations: dict[str, dict[str, str]]) -> str:
    return (
        HEADER
        + "TRANSLATIONS: dict[str, dict[str, str]] = "
        + repr(translations)
        + "\n"
    )

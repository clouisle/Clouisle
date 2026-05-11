from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LOCALES_DIR = ROOT / "app" / "locales"
DOMAIN = "messages"
SUPPORTED_LANGS = ("en", "zh")

HEADER_TEMPLATE = """msgid ""
msgstr ""
"Project-Id-Version: clouisle-backend\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"""


def escape_po(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_catalog(lang: str, catalogs: dict[str, dict[str, str]]) -> str:
    lines = [HEADER_TEMPLATE.format(lang=lang).strip(), ""]
    base_catalog = catalogs[SUPPORTED_LANGS[0]]
    for key in sorted(base_catalog):
        translation = catalogs[lang].get(key) or base_catalog.get(key, key)
        lines.extend(
            [
                f'msgid "{escape_po(key)}"',
                f'msgstr "{escape_po(translation)}"',
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    from scripts.i18n_catalog_utils import load_catalog

    catalogs = {lang: load_catalog(lang) for lang in SUPPORTED_LANGS}
    for lang in SUPPORTED_LANGS:
        locale_dir = LOCALES_DIR / lang / "LC_MESSAGES"
        locale_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = locale_dir / f"{DOMAIN}.po"
        catalog_path.write_text(render_catalog(lang, catalogs), encoding="utf-8")
        print(f"Wrote {catalog_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

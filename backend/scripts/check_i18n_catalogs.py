from __future__ import annotations

import re
import sys
from pathlib import Path

from babel.messages import pofile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LOCALES_DIR = ROOT / "app" / "locales"
DOMAIN = "messages"
SUPPORTED_LANGS = ("en", "zh")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


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


def placeholders(value: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(value))


def main() -> int:
    catalogs = {lang: load_catalog(lang) for lang in SUPPORTED_LANGS}
    base_keys = set(catalogs[SUPPORTED_LANGS[0]])
    failures: list[str] = []

    for lang in SUPPORTED_LANGS[1:]:
        keys = set(catalogs[lang])
        missing = sorted(base_keys - keys)
        extra = sorted(keys - base_keys)
        if missing:
            failures.append(f"{lang}: missing keys: {', '.join(missing[:20])}")
        if extra:
            failures.append(f"{lang}: extra keys: {', '.join(extra[:20])}")

    for key in sorted(base_keys):
        base_placeholders = placeholders(catalogs[SUPPORTED_LANGS[0]][key])
        for lang in SUPPORTED_LANGS[1:]:
            other_placeholders = placeholders(catalogs[lang].get(key, ""))
            if base_placeholders != other_placeholders:
                failures.append(
                    f"{lang}: placeholder mismatch for '{key}': "
                    f"{sorted(base_placeholders)} != {sorted(other_placeholders)}"
                )

    if failures:
        print("i18n catalog check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("i18n catalog check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

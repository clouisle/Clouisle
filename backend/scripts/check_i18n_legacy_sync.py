from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.core.i18n_legacy import TRANSLATIONS as LEGACY_TRANSLATIONS
    from scripts.i18n_catalog_utils import build_translations

    generated = build_translations()
    if LEGACY_TRANSLATIONS != generated:
        print("Legacy i18n snapshot is out of sync with Babel catalogs.")
        print("Run: uv run python scripts/sync_i18n_legacy.py")
        return 1

    print("Legacy i18n snapshot is in sync with Babel catalogs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

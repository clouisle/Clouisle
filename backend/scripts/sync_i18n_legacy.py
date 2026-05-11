from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from scripts.i18n_catalog_utils import (
        LEGACY_PATH,
        build_translations,
        render_legacy_module,
    )

    LEGACY_PATH.write_text(
        render_legacy_module(build_translations()),
        encoding="utf-8",
    )
    print(f"Wrote {LEGACY_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

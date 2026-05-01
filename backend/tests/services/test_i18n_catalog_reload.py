from pathlib import Path

from app.core import i18n


def test_load_babel_catalog_reloads_when_po_file_changes(tmp_path: Path):
    locale_dir = tmp_path / "en" / "LC_MESSAGES"
    locale_dir.mkdir(parents=True)
    po_path = locale_dir / "messages.po"
    po_path.write_text('msgid "hello"\nmsgstr "Hello"\n', encoding="utf-8")

    original_dir = i18n.LOCALES_DIR
    original_catalogs = dict(i18n._BABEL_CATALOGS)
    original_mtimes = dict(i18n._BABEL_CATALOG_MTIMES)
    try:
        i18n.LOCALES_DIR = tmp_path
        i18n._BABEL_CATALOGS.clear()
        i18n._BABEL_CATALOG_MTIMES.clear()

        assert i18n.t("hello", lang="en") == "Hello"

        po_path.write_text('msgid "hello"\nmsgstr "Hello updated"\n', encoding="utf-8")

        assert i18n.t("hello", lang="en") == "Hello updated"
    finally:
        i18n.LOCALES_DIR = original_dir
        i18n._BABEL_CATALOGS.clear()
        i18n._BABEL_CATALOGS.update(original_catalogs)
        i18n._BABEL_CATALOG_MTIMES.clear()
        i18n._BABEL_CATALOG_MTIMES.update(original_mtimes)

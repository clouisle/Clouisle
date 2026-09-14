from app.core import i18n


def test_missing_babel_catalog_returns_no_message(tmp_path, monkeypatch):
    original_catalogs = dict(i18n._BABEL_CATALOGS)
    original_mtimes = dict(i18n._BABEL_CATALOG_MTIMES)
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    i18n._BABEL_CATALOGS.clear()
    i18n._BABEL_CATALOG_MTIMES.clear()

    try:
        assert i18n._load_babel_catalog("en") is None
        assert i18n._get_babel_message("missing", "en") is None
    finally:
        i18n._BABEL_CATALOGS.clear()
        i18n._BABEL_CATALOGS.update(original_catalogs)
        i18n._BABEL_CATALOG_MTIMES.clear()
        i18n._BABEL_CATALOG_MTIMES.update(original_mtimes)


def test_babel_catalog_skips_invalid_keys_and_empty_messages(tmp_path, monkeypatch):
    po_path = tmp_path / "en" / "LC_MESSAGES" / "messages.po"
    po_path.parent.mkdir(parents=True)
    po_path.write_text("", encoding="utf-8")

    class Message:
        def __init__(self, string):
            self.string = string

    class Catalog:
        _messages = {
            None: Message("ignored"),
            "": Message("ignored"),
            "empty": Message(""),
            "greeting": Message("Hello"),
        }

    original_catalogs = dict(i18n._BABEL_CATALOGS)
    original_mtimes = dict(i18n._BABEL_CATALOG_MTIMES)
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    monkeypatch.setattr(i18n.pofile, "read_po", lambda _file_obj: Catalog())
    i18n._BABEL_CATALOGS.clear()
    i18n._BABEL_CATALOG_MTIMES.clear()

    try:
        assert i18n._load_babel_catalog("en") == {"greeting": "Hello"}
    finally:
        i18n._BABEL_CATALOGS.clear()
        i18n._BABEL_CATALOGS.update(original_catalogs)
        i18n._BABEL_CATALOG_MTIMES.clear()
        i18n._BABEL_CATALOG_MTIMES.update(original_mtimes)

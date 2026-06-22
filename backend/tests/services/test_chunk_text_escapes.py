"""
Tests for YUN-108: document chunking must interpret escape sequences
(``\\n``, ``\\r``, ``\\t``, ``\\\\``) in user-supplied separator strings.

The frontend renders separator hints as literal ``\\n`` (backslash + n), so
the API receives two characters where the user means a single newline.
LangChain's splitter does a literal match, so without decoding the escape
sequence the chunker would never split on real newlines.
"""

from app.services.document_processor import (
    _decode_separator_escapes,
    chunk_text,
)


# ---------- _decode_separator_escapes ----------


def test_decode_separator_escapes_decodes_newline():
    assert _decode_separator_escapes("\\n") == "\n"


def test_decode_separator_escapes_decodes_carriage_return():
    assert _decode_separator_escapes("\\r") == "\r"


def test_decode_separator_escapes_decodes_tab():
    assert _decode_separator_escapes("\\t") == "\t"


def test_decode_separator_escapes_decodes_double_backslash():
    assert _decode_separator_escapes("\\\\") == "\\"


def test_decode_separator_escapes_decodes_multiple_sequences():
    assert _decode_separator_escapes("\\n\\n") == "\n\n"


def test_decode_separator_escapes_leaves_unicode_punctuation_untouched():
    # Chinese punctuation should NOT be escape-decoded — it's literal text.
    assert _decode_separator_escapes("。") == "。"
    assert _decode_separator_escapes("---") == "---"


def test_decode_separator_escapes_passthrough_when_no_backslash():
    assert _decode_separator_escapes("hello") == "hello"
    # An already-real newline must not be altered.
    assert _decode_separator_escapes("\n") == "\n"


def test_decode_separator_escapes_leaves_unknown_sequences_unchanged():
    # `\x` is not in the supported set; the backslash and the next char
    # must be preserved verbatim.
    assert _decode_separator_escapes("\\x") == "\\x"
    assert _decode_separator_escapes("\\u4e2d") == "\\u4e2d"


# ---------- chunk_text integration ----------


def test_chunk_text_splits_on_literal_backslash_n_separator():
    """User types `\\n` in the UI → server should split on real newlines."""
    text = "alpha" + ("x" * 50) + "\nbeta" + ("y" * 50) + "\ngamma" + ("z" * 50)

    chunks = chunk_text(
        text,
        chunk_size=10,
        chunk_overlap=0,
        separators=["\\n"],
    )

    # Three logical segments must survive, regardless of further internal splits.
    contents = [c["content"] for c in chunks]
    assert any(c.startswith("alpha") for c in contents)
    assert any("beta" in c for c in contents)
    assert any(c.startswith("gamma") or c.endswith("gamma") for c in contents)
    # And no chunk should still contain a real newline (it has been split on it).
    assert all("\n" not in c for c in contents)


def test_chunk_text_splits_on_literal_backslash_n_n_separator():
    """User types `\\n\\n` (paragraph hint) → split on real double newlines."""
    text = (
        "first paragraph"
        + ("a" * 50)
        + "\n\n"
        + "second paragraph"
        + ("b" * 50)
        + "\n\n"
        + "third paragraph"
        + ("c" * 50)
    )

    chunks = chunk_text(
        text,
        chunk_size=10,
        chunk_overlap=0,
        separators=["\\n\\n"],
    )

    # No chunk may still contain the real ``\n\n`` separator — that's the
    # invariant the escape-sequence decode is responsible for.
    contents = [c["content"] for c in chunks]
    assert all("\n\n" not in c for c in contents), contents


def test_chunk_text_real_newline_separator_still_works():
    """Regression: passing an actual newline as the separator still splits."""
    text = "alpha" + ("x" * 50) + "\nbeta" + ("y" * 50) + "\ngamma" + ("z" * 50)

    chunks = chunk_text(
        text,
        chunk_size=10,
        chunk_overlap=0,
        separators=["\n"],
    )

    contents = [c["content"] for c in chunks]
    assert any(c.startswith("alpha") for c in contents)
    assert any("beta" in c for c in contents)
    assert any(c.startswith("gamma") or c.endswith("gamma") for c in contents)
    assert all("\n" not in c for c in contents)


def test_chunk_text_default_separators_still_split_on_newlines():
    """Regression: no custom separator → original behaviour preserved."""
    text = (
        "alpha"
        + ("x" * 50)
        + "\n\n"
        + "beta"
        + ("y" * 50)
        + "\n\n"
        + "gamma"
        + ("z" * 50)
    )

    chunks = chunk_text(
        text,
        chunk_size=10,
        chunk_overlap=0,
        separators=None,
    )

    contents = [c["content"] for c in chunks]
    assert any(c.startswith("alpha") for c in contents)
    assert any(c.startswith("beta") for c in contents)
    assert any(c.startswith("gamma") for c in contents)
    assert all("\n\n" not in c for c in contents)


def test_chunk_text_custom_separator_splits_when_text_fits_chunk_size():
    """
    Regression for YUN-108 follow-up: the user types ``\\n\\n`` and expects
    three paragraphs even when the whole document would otherwise fit in one
    chunk. Previously LangChain's splitter returned the document as a single
    chunk whenever ``len(text) <= chunk_size``, ignoring the custom separator
    entirely.
    """
    paragraph = "段落内容 " + ("lorem ipsum " * 8)
    text = "\n\n".join([paragraph, paragraph, paragraph])
    # Sanity: text is short enough to fit inside the default chunk size.
    assert len(text) < 1000

    chunks = chunk_text(
        text,
        chunk_size=1000,
        chunk_overlap=0,
        separators=["\\n\\n"],
    )

    assert len(chunks) == 3, [c["content"] for c in chunks]
    assert chunks[0]["content"].startswith("段落内容")
    assert chunks[1]["content"].startswith("段落内容")
    assert chunks[2]["content"].startswith("段落内容")
    # No chunk should still contain the real ``\n\n`` separator.
    assert all("\n\n" not in c["content"] for c in chunks)


def test_chunk_text_custom_separator_present_in_text_still_splits():
    """Custom separator absent from text → falls back to default splitter."""
    text = "alpha" + ("x" * 50) + " " + "beta" + ("y" * 50)

    chunks = chunk_text(
        text,
        chunk_size=1000,
        chunk_overlap=0,
        separators=["\n\n"],
    )

    # ``\n\n`` never appears, so we should get one chunk back, not zero.
    assert len(chunks) == 1


def test_chunk_text_custom_separator_applies_overlap():
    """Overlap is still applied on top of the pre-split pieces."""
    paragraph = "abcde" * 20
    text = "\n\n".join([paragraph, paragraph, paragraph])

    chunks = chunk_text(
        text,
        chunk_size=1000,
        chunk_overlap=10,
        separators=["\\n\\n"],
    )

    assert len(chunks) == 3
    # Overlap should appear at the start of chunk 1 and 2.
    assert chunks[1]["overlap_length"] == 10
    assert chunks[2]["overlap_length"] == 10

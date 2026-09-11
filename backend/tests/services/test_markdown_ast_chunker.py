from app.services.document_processor import (
    _is_markdown_text,
    _extract_markdown_blocks,
    chunk_markdown_ast,
    chunk_text,
)


def test_is_markdown_text():
    assert not _is_markdown_text("This is pure text without any markdown elements.")
    assert _is_markdown_text("# Heading 1\nSome text")
    assert _is_markdown_text("```python\nprint(1)\n```")
    assert _is_markdown_text("| Col 1 | Col 2 |\n|---|---|\n| A | B |")
    assert _is_markdown_text("# Title\n- Item 1\n- Item 2")


def test_extract_markdown_blocks_heading_and_section():
    markdown = """# Top Title
Paragraph 1.

## Section 1
Text in section 1.

### Subsection 1.1
Text in subsection.

## Section 2
Text in section 2.
"""
    blocks = _extract_markdown_blocks(markdown)
    # 4 headings + 4 paragraphs = 8 blocks
    assert len(blocks) == 8
    p1 = blocks[1]
    assert p1["type"] == "paragraph"
    assert p1["section"] == "Top Title"

    p2 = blocks[3]
    assert p2["type"] == "paragraph"
    assert p2["section"] == "Top Title > Section 1"

    p3 = blocks[5]
    assert p3["type"] == "paragraph"
    assert p3["section"] == "Top Title > Section 1 > Subsection 1.1"

    h4 = blocks[6]
    assert h4["type"] == "heading"
    p4 = blocks[7]
    assert p4["type"] == "paragraph"
    assert p4["section"] == "Top Title > Section 2"


def test_markdown_table_atomic_small():
    markdown = """# Financial Report
| Year | Revenue | Profit |
|---|---|---|
| 2020 | 100M | 10M |
| 2021 | 120M | 15M |
"""
    chunks = chunk_markdown_ast(markdown, chunk_size=1000, chunk_overlap=0)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert "2020" in chunk["content"]
    assert "2021" in chunk["content"]
    assert chunk["content"].startswith("# Financial Report")
    assert "| Year | Revenue | Profit |" in chunk["content"]


def test_markdown_table_large_splits_with_repeated_header():
    # Construct a 2000~2024 (25 rows) table
    rows = [
        f"| {year} | Revenue_{year} | Profit_{year} | Margin_{year} |"
        for year in range(2000, 2025)
    ]
    table_content = (
        "| Year | Revenue | Profit | Margin |\n|---|---|---|---|\n" + "\n".join(rows)
    )

    # Use small chunk_size to force splitting across multiple chunks
    chunks = chunk_markdown_ast(table_content, chunk_size=300, chunk_overlap=0)
    assert len(chunks) >= 3

    header = "| Year | Revenue | Profit | Margin |\n|---|---|---|---|"
    for idx, c in enumerate(chunks):
        content = c["content"]
        # Every single chunk MUST start with the exact table header
        assert content.startswith(header), (
            f"Chunk {idx} does not repeat header: {content}"
        )
        # Every chunk metadata marks it as a table
        assert c["metadata"]["chunk_type"] == "table"
        if idx > 0:
            assert c["metadata"].get("is_table_continuation") is True


def test_markdown_list_atomic():
    markdown = """# Project Plan
- Task 1: Initialize database
  - Subtask 1.1: Run migration
  - Subtask 1.2: Seed data
- Task 2: Implement API
- Task 3: Deploy frontend
"""
    chunks = chunk_markdown_ast(markdown, chunk_size=500, chunk_overlap=0)
    assert len(chunks) == 1
    assert "Subtask 1.1" in chunks[0]["content"]
    assert "Task 3" in chunks[0]["content"]


def test_markdown_code_block():
    markdown = """```python
def calculate_totals(years):
    return sum(years)
```"""
    chunks = chunk_markdown_ast(markdown, chunk_size=200, chunk_overlap=0)
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["chunk_type"] == "code"
    assert chunks[0]["content"].startswith("```python")
    assert chunks[0]["content"].endswith("```")


def test_markdown_code_block_oversized():
    long_code = (
        "```python\n" + "\n".join([f"line_{i} = {i}" for i in range(100)]) + "\n```"
    )
    chunks = chunk_markdown_ast(long_code, chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 1
    for c in chunks:
        assert c["content"].startswith("```python")
        assert c["content"].rstrip().endswith("```")


def test_clean_overlap_no_table_corruption():
    markdown = """Section text that introduces the table.

| Col 1 | Col 2 |
|---|---|
| A | B |
| C | D |

Ending conclusion text following the table."""
    chunks = chunk_markdown_ast(markdown, chunk_size=60, chunk_overlap=20)
    # Check that chunks do not start with broken pipe text due to overlap
    for c in chunks:
        meta = c.get("metadata") or {}
        if meta.get("chunk_type") == "table":
            assert c["content"].startswith("| Col 1 | Col 2 |")


def test_markdown_code_block_exact_chunk():
    # Test code block that flushes previous chunk and fits in its own chunk
    markdown = "Intro text before code.\n\n```python\nprint('hello')\n```"
    chunks = chunk_markdown_ast(markdown, chunk_size=30, chunk_overlap=0)
    assert len(chunks) == 2
    assert chunks[1]["metadata"]["chunk_type"] == "code"


def test_markdown_oversized_paragraph_fallback():
    # Single paragraph larger than chunk_size
    para = "Word " * 100
    chunks = chunk_markdown_ast(
        f"Short text.\n\n{para}", chunk_size=50, chunk_overlap=10
    )
    assert len(chunks) > 2


def test_markdown_text_overlap_across_paragraphs():
    markdown = (
        "Paragraph one with some sentences.\n\nParagraph two with some more sentences."
    )
    chunks = chunk_markdown_ast(markdown, chunk_size=35, chunk_overlap=10)
    assert len(chunks) >= 2
    assert chunks[1]["overlap_length"] > 0


def test_markdown_list_loose_formatting():
    markdown = """
- Item 1

  Indented line under item 1

- Item 2
"""
    blocks = _extract_markdown_blocks(markdown)
    list_blocks = [b for b in blocks if b["type"] == "list"]
    assert len(list_blocks) >= 1


def test_markdown_heading_boundary_flush():
    markdown = (
        "Intro paragraph.\n\n## Next Major Heading\n\nContent under next heading."
    )
    chunks = chunk_markdown_ast(markdown, chunk_size=1000, chunk_overlap=0)
    assert len(chunks) == 2
    assert chunks[0]["content"] == "Intro paragraph."
    assert "Next Major Heading" in chunks[1]["content"]


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_dispatches_markdown():
    markdown = """# Heading
| A | B |
|---|---|
| 1 | 2 |
"""
    chunks = chunk_text(markdown, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0].get("metadata") is not None


def test_table_continuation_flag_with_preceding_text():
    markdown = """# Introduction
This is some introductory text before the table.

| Col 1 | Col 2 |
|---|---|
| Row 1 A | Row 1 B |
| Row 2 A | Row 2 B |
| Row 3 A | Row 3 B |
| Row 4 A | Row 4 B |
"""
    chunks = chunk_markdown_ast(markdown, chunk_size=70, chunk_overlap=0)
    table_chunks = [c for c in chunks if c["metadata"].get("chunk_type") == "table"]
    assert len(table_chunks) >= 2
    # First table chunk must NOT be marked as continuation even though preceding text exists
    assert table_chunks[0]["metadata"]["is_table_continuation"] is False
    # Subsequent table chunks MUST be marked as continuation
    for tc in table_chunks[1:]:
        assert tc["metadata"]["is_table_continuation"] is True


def test_markdown_ast_unreached_branches():
    # 1. Unclosed code block (hits line 888 loop end without fence)
    unclosed_code = "```python\ndef foo():\n    return 42"
    blocks = _extract_markdown_blocks(unclosed_code)
    assert blocks[0]["type"] == "code"

    # 2. List with indented line continuation and blank line follow up
    list_text = "- Item 1\n  details of item 1\n\n  more indented details\n- Item 2"
    blocks = _extract_markdown_blocks(list_text)
    assert blocks[0]["type"] == "list"

    # 3. Code block with prior chunk_type already "table" (current_chunk_type != "text")
    mixed_content = "| A | B |\n|---|---|\n| 1 | 2 |\n\n```python\nx = 1\n```"
    chunks = chunk_markdown_ast(mixed_content, chunk_size=500, chunk_overlap=0)
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["chunk_type"] == "table"
    assert "| A | B |" in chunks[0]["content"]
    assert "```python" in chunks[0]["content"]
    assert "x = 1" in chunks[0]["content"]

    # 4. Table without section
    bare_table = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    chunks = chunk_markdown_ast(bare_table, chunk_size=20, chunk_overlap=0)
    assert len(chunks) >= 2
    assert all(c["metadata"]["chunk_type"] == "table" for c in chunks)

    # 5. List followed by non-list line (hits line 957 break)
    list_followed_by_text = "- Item 1\nRegular text immediately after"
    blocks = _extract_markdown_blocks(list_followed_by_text)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "list"
    assert blocks[0]["content"] == "- Item 1"
    assert blocks[1]["type"] == "paragraph"
    assert blocks[1]["content"] == "Regular text immediately after"

    # 6. Paragraph followed by heading, code, table, and list (hits lines 977, 978, 980, 984)
    para_heading = "Para 1\n# Heading 1"
    b1 = _extract_markdown_blocks(para_heading)
    assert len(b1) == 2
    assert [b["type"] for b in b1] == ["paragraph", "heading"]
    assert b1[0]["content"] == "Para 1"
    assert b1[1]["content"] == "# Heading 1"

    para_code = "Para 1\n```python\nx = 1\n```"
    b2 = _extract_markdown_blocks(para_code)
    assert len(b2) == 2
    assert [b["type"] for b in b2] == ["paragraph", "code"]
    assert b2[0]["content"] == "Para 1"
    assert "```python" in b2[1]["content"]

    para_table = "Para 1\n| A | B |\n|---|---|\n| 1 | 2 |"
    b3 = _extract_markdown_blocks(para_table)
    assert len(b3) == 2
    assert [b["type"] for b in b3] == ["paragraph", "table"]
    assert b3[0]["content"] == "Para 1"
    assert "| A | B |" in b3[1]["content"]

    para_list = "Para 1\n- Item 1"
    b4 = _extract_markdown_blocks(para_list)
    assert len(b4) == 2
    assert [b["type"] for b in b4] == ["paragraph", "list"]
    assert b4[0]["content"] == "Para 1"
    assert b4[1]["content"] == "- Item 1"
    assert chunk_markdown_ast("   \n\t   ") == []

    # 8. chunk_markdown_ast when _extract_markdown_blocks returns empty (line 1021)
    from unittest.mock import patch

    with patch(
        "app.services.document_processor._extract_markdown_blocks", return_value=[]
    ):
        fb_chunks = chunk_markdown_ast(
            "some text that has no blocks", chunk_size=100, chunk_overlap=0
        )
        assert len(fb_chunks) >= 1

    # 9. Table following table (line 1080->1082 where current_chunk_type is already "table")
    two_small_tables = (
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n| C | D |\n|---|---|\n| 3 | 4 |"
    )
    tbl_chunks = chunk_markdown_ast(two_small_tables, chunk_size=500, chunk_overlap=0)
    assert len(tbl_chunks) == 1
    assert tbl_chunks[0]["metadata"]["chunk_type"] == "table"
    assert len(b4) == 2
    assert all(c["metadata"]["chunk_type"] == "table" for c in chunks)

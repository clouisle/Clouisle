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

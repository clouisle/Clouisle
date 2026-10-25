import pytest

from app.services.message_split import split_message_text


def bounded(chunks, limit):
    assert all(0 < len(chunk.encode("utf-8")) <= limit for chunk in chunks)


def test_paragraphs_and_unicode_are_preserved():
    text = "第一段说明。" * 5 + "\n\n" + "第二段补充。" * 5
    chunks = split_message_text(text, limit=100)
    bounded(chunks, 100)
    assert "".join(chunks) == text
    assert chunks[0].endswith("\n\n")


def test_sentences_break_before_words_or_characters():
    sentence = "这是一个完整句子。"
    chunks = split_message_text(sentence * 8, limit=70)
    bounded(chunks, 70)
    assert "".join(chunks) == sentence * 8
    assert all(chunk.endswith("。") for chunk in chunks)


def test_table_after_prose_repeats_header_and_preserves_rows():
    header = "| 项目 | 数值 |\n| --- | ---: |\n"
    rows = [f"| 项目{i} | 数值{i} |\n" for i in range(20)]
    chunks = split_message_text(
        "统计如下：\n" + header + "".join(rows) + "\n结论。", limit=150
    )
    bounded(chunks, 150)
    tables = [chunk[chunk.index(header) :] for chunk in chunks if header in chunk]
    recovered = "".join(table[len(header) :] for table in tables)
    assert recovered.removesuffix("\n结论。") == "".join(rows)
    assert chunks[0].startswith("统计如下：\n")
    assert chunks[-1].endswith("结论。")


def test_oversized_cell_keeps_columns_and_content():
    header = "| A | B |\n| --- | --- |\n"
    value = "很长的单元格内容" * 30
    chunks = split_message_text(header + f"|{value}|end|\n", limit=100)
    bounded(chunks, 100)
    assert all(chunk.startswith(header) for chunk in chunks)
    rows = [line for chunk in chunks for line in chunk[len(header) :].splitlines()]
    assert all(
        line.startswith("|") and line.endswith("|") and line.count("|") == 3
        for line in rows
    )
    assert "".join(line.split("|")[1] for line in rows) == value
    assert "".join(line.split("|")[2] for line in rows) == "end"


def test_code_fences_preserve_blank_lines_and_language():
    body = "".join(f"print({index})\n\n" for index in range(30))
    chunks = split_message_text("```python\n" + body + "```", limit=100)
    bounded(chunks, 100)
    assert all(
        chunk.startswith("```python\n") and chunk.endswith("```") for chunk in chunks
    )
    assert "".join(chunk[len("```python\n") : -3] for chunk in chunks) == body


def test_plain_text_preserves_crlf_and_whitespace():
    text = "  wrapped line  \r\n\r\n" * 30
    chunks = split_message_text(text, limit=90)
    bounded(chunks, 90)
    assert "".join(chunks) == text


def test_oversized_header_and_unbroken_text_remain_bounded():
    text = "|" + "标题" * 100 + "|\n|---|\n|值|\n"
    chunks = split_message_text(text, limit=80)
    bounded(chunks, 80)
    assert "".join(chunks) == text
    emoji = "😀" * 40
    chunks = split_message_text(emoji, limit=81)
    bounded(chunks, 81)
    assert "".join(chunks) == emoji


def test_invalid_limit_is_rejected():
    with pytest.raises(ValueError):
        split_message_text("value", limit=0)

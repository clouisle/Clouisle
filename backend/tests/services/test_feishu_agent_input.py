import json

from app.services.feishu_agent_input import parse_message


def test_post_top_level_files_are_preserved_with_caption():
    message = {
        "message_type": "post",
        "content": json.dumps(
            {
                "title": "",
                "content": [
                    [{"tag": "text", "text": "这份文件里说了些什么？", "style": []}]
                ],
                "files": [
                    {
                        "file_key": "file_actual",
                        "file_name": "网站完整规划.docx",
                        "is_folder": False,
                    }
                ],
            }
        ),
    }
    text, attachments = parse_message(message)
    assert text == "这份文件里说了些什么？"
    assert attachments == [
        {"kind": "file", "key": "file_actual", "name": "网站完整规划.docx"}
    ]


def test_inline_and_top_level_file_reference_is_not_duplicated():
    text, attachments = parse_message(
        {
            "message_type": "post",
            "content": {
                "content": [
                    [{"tag": "file", "file_key": "same", "file_name": "a.txt"}]
                ],
                "files": [{"file_key": "same", "file_name": "a.txt"}],
            },
        }
    )
    assert attachments == [{"kind": "file", "key": "same", "name": "a.txt"}]

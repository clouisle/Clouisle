import json
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.services.retrieval_evaluation_store import MAX_IMPORT_BYTES, parse_cases


def test_parse_json_and_csv_cases():
    chunk_id = uuid4()
    document_id = uuid4()
    json_cases = parse_cases(
        json.dumps(
            [
                {
                    "query": "Where is the policy?",
                    "chunk_relevance": {str(chunk_id): 3},
                    "document_relevance": {str(document_id): 2},
                }
            ]
        ).encode(),
        "cases.json",
    )
    csv_cases = parse_cases(
        b"query,chunk_relevance,document_relevance,expected_empty\nNo answer,{},{},true\n",
        "cases.csv",
    )

    assert json_cases[0].chunk_relevance == {chunk_id: 3}
    assert csv_cases[0].expected_empty is True


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"{}", "cases.txt"),
        (b"not-json", "cases.json"),
        (b"[]", "cases.json"),
        (b"x" * (MAX_IMPORT_BYTES + 1), "cases.json"),
        (
            b'[{"query":"q","expected_empty":true,"document_relevance":{"00000000-0000-0000-0000-000000000001":1}}]',
            "cases.json",
        ),
    ],
)
def test_parse_cases_rejects_invalid_or_unbounded_imports(content, filename):
    with pytest.raises(BusinessError) as error:
        parse_cases(content, filename)

    assert error.value.msg_key == "evaluation_import_invalid"

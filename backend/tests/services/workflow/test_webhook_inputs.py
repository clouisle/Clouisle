from app.api.v1.endpoints.workflows import normalize_webhook_inputs


def test_normalize_webhook_inputs_unwraps_nested_inputs_payload():
    payload = {"inputs": {"query": "hello", "task_id": "5"}}

    assert normalize_webhook_inputs(payload) == {
        "query": "hello",
        "task_id": "5",
    }


def test_normalize_webhook_inputs_keeps_regular_payload_unchanged():
    payload = {"query": "hello", "task_id": "5"}

    assert normalize_webhook_inputs(payload) == payload


def test_normalize_webhook_inputs_does_not_unwrap_mixed_payload():
    payload = {"inputs": {"query": "hello"}, "source": "mes"}

    assert normalize_webhook_inputs(payload) == payload

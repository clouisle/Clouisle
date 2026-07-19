from app.services.workflow.cache import CacheKey, hash_content


def test_cache_key_builders_include_all_identifiers():
    assert CacheKey.workflow("workflow") == "wf:cache:workflow:workflow"
    assert CacheKey.workflow("workflow", "v2") == "wf:cache:workflow:workflow:v2"
    assert (
        CacheKey.execution_plan("workflow", "definition")
        == "wf:cache:plan:workflow:definition"
    )
    assert (
        CacheKey.node_result("node", "llm", "inputs") == "wf:cache:node:llm:node:inputs"
    )
    assert (
        CacheKey.llm_response("model", "prompt", "params")
        == "wf:cache:llm:model:prompt:params"
    )
    assert CacheKey.tool_result("tool", "inputs") == "wf:cache:tool:tool:inputs"


def test_hash_content_is_stable_for_equivalent_objects():
    assert hash_content({"a": 1, "nested": {"b": [2, 3]}}) == hash_content(
        {"nested": {"b": [2, 3]}, "a": 1}
    )


def test_hash_content_distinguishes_values_and_hashes_raw_strings():
    assert hash_content({"value": 1}) != hash_content({"value": 2})
    assert hash_content("hello") == "2cf24dba5fb0a30e"

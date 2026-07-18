from types import SimpleNamespace
from unittest.mock import patch

from app.llm.adapters.embedding.factory import create_embedding_model


def build_model(base_url: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        provider="volcengine",
        model_id="doubao-embedding-text",
        api_key="test-key",
        base_url=base_url,
        config={},
    )


def test_volcengine_embedding_uses_ark_default_base_url():
    with patch("langchain_openai.OpenAIEmbeddings") as embeddings:
        create_embedding_model(build_model())

    assert embeddings.call_args.kwargs["base_url"] == (
        "https://ark.cn-beijing.volces.com/api/v3"
    )
    assert embeddings.call_args.kwargs["check_embedding_ctx_length"] is False


def test_volcengine_embedding_preserves_custom_base_url():
    with patch("langchain_openai.OpenAIEmbeddings") as embeddings:
        create_embedding_model(build_model("https://ark-proxy.example/v3"))

    assert embeddings.call_args.kwargs["base_url"] == "https://ark-proxy.example/v3"

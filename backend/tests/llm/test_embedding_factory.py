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


def test_siliconflow_embedding_uses_default_base_url():
    model = SimpleNamespace(
        provider="siliconflow",
        model_id="BAAI/bge-m3",
        api_key="sk-siliconflow-test",
        base_url=None,
        config={},
    )
    with patch("langchain_openai.OpenAIEmbeddings") as embeddings:
        create_embedding_model(model)

    assert embeddings.call_args.kwargs["base_url"] == "https://api.siliconflow.cn/v1"
    assert embeddings.call_args.kwargs["check_embedding_ctx_length"] is False


def test_openai_responses_embedding_supported():
    model = SimpleNamespace(
        provider="openai_responses",
        model_id="text-embedding-3-small",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        config={},
    )
    with patch("langchain_openai.OpenAIEmbeddings") as embeddings:
        create_embedding_model(model)

    assert embeddings.call_args.kwargs["base_url"] == "https://api.openai.com/v1"


def test_openai_embedding_supported():
    model = SimpleNamespace(
        provider="openai",
        model_id="text-embedding-3-large",
        api_key="sk-test",
        base_url=None,
        config={},
    )
    with patch("langchain_openai.OpenAIEmbeddings") as embeddings:
        create_embedding_model(model)
    assert embeddings.call_args.kwargs["model"] == "text-embedding-3-large"


def test_azure_openai_embedding_supported():
    model = SimpleNamespace(
        provider="azure_openai",
        model_id="text-embedding-ada-002",
        api_key="sk-azure",
        base_url="https://azure.example.com",
        config={"azure": {"api_version": "2024-05-01-preview"}},
    )
    with patch("langchain_openai.AzureOpenAIEmbeddings") as embeddings:
        create_embedding_model(model)
    assert embeddings.call_args.kwargs["azure_deployment"] == "text-embedding-ada-002"
    assert embeddings.call_args.kwargs["api_version"] == "2024-05-01-preview"


def test_google_embedding_supported():
    import pytest

    model_no_key = SimpleNamespace(
        provider="google",
        model_id="embedding-001",
        api_key=None,
        base_url=None,
        config={},
    )
    with pytest.raises(ValueError, match="Google requires api_key"):
        create_embedding_model(model_no_key)

    model_with_key = SimpleNamespace(
        provider="google",
        model_id="embedding-001",
        api_key="goog-key",
        base_url=None,
        config={},
    )
    with patch("langchain_google_genai.GoogleGenerativeAIEmbeddings") as embeddings:
        create_embedding_model(model_with_key)
    assert embeddings.call_args.kwargs["model"] == "embedding-001"


def test_unsupported_provider_raises_error():
    import pytest

    model = SimpleNamespace(
        provider="unsupported_dummy_provider",
        model_id="test",
        api_key=None,
        base_url=None,
        config={},
    )
    with pytest.raises(ValueError, match="Unsupported provider for embedding"):
        create_embedding_model(model)

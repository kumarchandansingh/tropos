from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from tropos.core.adapters.embeddings.ollama import OllamaEmbeddingProvider
from tropos.core.runtime_config import load_embedding_runtime_settings


def test_ollama_settings_require_no_paid_key() -> None:
    settings = load_embedding_runtime_settings({"TROPOS_EMBEDDING_PROVIDER": "ollama"})
    assert settings.provider == "ollama"
    assert settings.model == "nomic-embed-text"
    assert settings.dimensions == 768
    assert settings.api_key is None


def test_ollama_adapter_documents_and_query_use_same_model() -> None:
    requests: list[dict[str, object]] = []

    def fake_open(req: object, timeout: int) -> io.BytesIO:
        assert timeout == 120
        data = req.data
        body = json.loads(data)
        requests.append(body)
        return io.BytesIO(json.dumps({"embeddings": [[0.5] * 768 for _ in body["input"]]}).encode())

    with patch(
        "tropos.core.adapters.embeddings.ollama.request.urlopen",
        side_effect=fake_open,
    ):
        provider = OllamaEmbeddingProvider()
        documents = provider.embed_documents(("first", "second"))
        query = provider.embed_query("question")

    assert len(documents) == 2
    assert query.dimensions == 768
    assert provider.strategy_version == "ollama:nomic-embed-text:768:v1"
    assert requests[0]["input"] == ["first", "second"]
    assert requests[1]["input"] == ["question"]


def test_ollama_rejects_wrong_dimensions() -> None:
    with (
        patch(
            "tropos.core.adapters.embeddings.ollama.request.urlopen",
            return_value=io.BytesIO(json.dumps({"embeddings": [[1.0, 2.0]]}).encode()),
        ),
        pytest.raises(RuntimeError, match="dimensions/count"),
    ):
        OllamaEmbeddingProvider().embed_query("hello")

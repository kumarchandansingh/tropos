"""Free local Ollama embedding provider."""

from __future__ import annotations

import json
from urllib import request

from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric


class OllamaEmbeddingProvider:
    def __init__(self, model: str = "nomic-embed-text", dimensions: int = 768) -> None:
        self._model = model
        self._dimensions = dimensions

    @property
    def strategy_version(self) -> str:
        return f"ollama:{self._model}:{self._dimensions}:v1"

    @property
    def model_identifier(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def similarity_metric(self) -> SimilarityMetric:
        return SimilarityMetric.COSINE

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        if not texts:
            return ()
        return self._embed(texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        return self._embed((text,))[0]

    def _embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        if any(not text.strip() for text in texts):
            raise ValueError("embedding text must not be blank")
        data = json.dumps({"model": self._model, "input": list(texts), "truncate": False}).encode()
        req = request.Request(
            "http://127.0.0.1:11434/api/embed",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                payload = json.loads(response.read())
            vectors = tuple(
                EmbeddingVector(tuple(float(x) for x in values)) for values in payload["embeddings"]
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RuntimeError(
                f"Local Ollama embedding failed. Run 'ollama pull {self._model}' "
                "and ensure Ollama is running."
            ) from exc
        if len(vectors) != len(texts) or any(
            value.dimensions != self._dimensions for value in vectors
        ):
            raise RuntimeError("Ollama embedding response dimensions/count mismatch")
        return vectors

import json
from urllib import error, request

from tropos.core.application.embeddings.models import EmbeddingVector, SimilarityMetric


class EmbeddingProviderError(RuntimeError):
    """Raised when the remote embedding provider cannot satisfy its contract."""


class OpenAIEmbeddingProvider:
    """Minimal OpenAI embedding adapter using the public embeddings API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if not model.strip():
            raise ValueError("model must not be blank")
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._model = model.strip()
        self._dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def strategy_version(self) -> str:
        return f"openai:{self._model}:{self._dimensions}:v1"

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
        if any(not text.strip() for text in texts):
            raise ValueError("embedding inputs must not contain blank text")
        return self._embed(texts)

    def embed_query(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise ValueError("query text must not be blank")
        return self._embed((text,))[0]

    def _embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        body = json.dumps(
            {
                "model": self._model,
                "input": list(texts),
                "dimensions": self._dimensions,
            }
        ).encode("utf-8")
        api_request = request.Request(
            f"{self._base_url}/embeddings",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(api_request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError("OpenAI embedding request failed") from exc

        raw_data = payload.get("data")
        if not isinstance(raw_data, list):
            raise EmbeddingProviderError("embedding response did not contain a data list")

        try:
            ordered = sorted(raw_data, key=lambda item: int(item["index"]))
            vectors = tuple(
                EmbeddingVector(tuple(float(value) for value in item["embedding"]))
                for item in ordered
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("embedding response had an invalid shape") from exc

        if len(vectors) != len(texts):
            raise EmbeddingProviderError("embedding response count did not match input count")
        if any(vector.dimensions != self._dimensions for vector in vectors):
            raise EmbeddingProviderError("embedding response dimensions did not match request")
        return vectors

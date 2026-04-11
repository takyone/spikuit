"""Embedder — pluggable text embedding with multiple provider support.

Provides an abstract Embedder interface and concrete implementations
for OpenAI-compatible APIs (LM Studio, Ollama /v1, vLLM, etc.),
Ollama native API, and a null embedder for testing.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from enum import Enum

import httpx


class EmbeddingType(str, Enum):
    """Indicates whether text is being embedded as a document or a query.

    Some embedding models (Nomic, Cohere, etc.) produce better retrieval
    results when the input is prefixed with a task-type hint. The
    ``Embedder.apply_prefix`` method uses this enum to select the
    correct prefix for the provider.
    """

    DOCUMENT = "document"
    QUERY = "query"


class Embedder(ABC):
    """Abstract base for text embedding providers.

    Subclasses must implement [`dimension`][spikuit_core.Embedder.dimension]
    and [`embed`][spikuit_core.Embedder.embed]. Override
    [`embed_batch`][spikuit_core.Embedder.embed_batch] for providers that
    support batched requests natively.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Input text to embed.

        Returns:
            Vector of floats with length equal to ``dimension``.
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Default implementation calls ``embed()`` sequentially.
        Override for providers that support native batching.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors, one per input text.
        """
        return [await self.embed(t) for t in texts]

    def apply_prefix(self, text: str, embedding_type: EmbeddingType) -> str:
        """Prepend a task-type prefix appropriate for this provider.

        The default implementation is a no-op. Subclasses whose models
        benefit from task-type prefixes (e.g. Nomic, Cohere) should
        override this or accept a ``prefix_style`` at construction time.

        Args:
            text: Raw text to embed.
            embedding_type: Whether the text is a stored document or a query.

        Returns:
            Text with the appropriate prefix prepended (or unchanged).
        """
        return text


class OpenAICompatEmbedder(Embedder):
    """Embedder using any OpenAI-compatible ``/v1/embeddings`` endpoint.

    Works with LM Studio, Ollama (``/v1``), vLLM, OpenAI, and any
    service that implements the OpenAI embeddings API.

    Example:
        ```python
        embedder = OpenAICompatEmbedder(
            base_url="http://localhost:1234/v1",
            model="text-embedding-nomic-embed-text-v1.5",
            dimension=768,
            prefix_style="nomic",
        )
        vec = await embedder.embed("hello world")
        ```

    Args:
        base_url: API base URL (without trailing slash).
        model: Model identifier.
        dimension: Expected embedding dimension.
        api_key: Bearer token (default ``"not-needed"`` for local servers).
        timeout: HTTP request timeout in seconds.
        prefix_style: Task-type prefix style.
            ``"nomic"`` → ``search_document: `` / ``search_query: ``.
            ``"cohere"`` → ``search_document: `` / ``search_query: ``.
            ``"none"`` (default) → no prefix.
    """

    PREFIX_MAP: dict[str, dict[str, str]] = {
        "nomic": {"document": "search_document: ", "query": "search_query: "},
        "cohere": {"document": "search_document: ", "query": "search_query: "},
    }

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:1234/v1",
        model: str = "text-embedding-nomic-embed-text-v1.5",
        dimension: int = 768,
        api_key: str = "not-needed",
        timeout: float = 30.0,
        prefix_style: str = "none",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._api_key = api_key
        self._timeout = timeout
        self._prefix_style = prefix_style

    def apply_prefix(self, text: str, embedding_type: EmbeddingType) -> str:
        prefixes = self.PREFIX_MAP.get(self._prefix_style)
        if prefixes is None:
            return text
        return prefixes[embedding_type.value] + text

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                json={"input": texts, "model": self._model},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        # Sort by index to preserve order
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]


class OllamaEmbedder(Embedder):
    """Embedder using Ollama's native ``/api/embed`` endpoint.

    Use this when connecting directly to Ollama without the OpenAI
    compatibility layer.

    Example:
        ```python
        embedder = OllamaEmbedder(
            base_url="http://localhost:11434",
            model="nomic-embed-text",
            dimension=768,
            prefix_style="nomic",
        )
        ```

    Args:
        base_url: Ollama server URL.
        model: Model name as shown in ``ollama list``.
        dimension: Expected embedding dimension.
        timeout: HTTP request timeout in seconds.
        prefix_style: Task-type prefix style (same as ``OpenAICompatEmbedder``).
    """

    PREFIX_MAP: dict[str, dict[str, str]] = OpenAICompatEmbedder.PREFIX_MAP

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dimension: int = 768,
        timeout: float = 30.0,
        prefix_style: str = "none",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout = timeout
        self._prefix_style = prefix_style

    def apply_prefix(self, text: str, embedding_type: EmbeddingType) -> str:
        prefixes = self.PREFIX_MAP.get(self._prefix_style)
        if prefixes is None:
            return text
        return prefixes[embedding_type.value] + text

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"input": texts, "model": self._model},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["embeddings"]


class NullEmbedder(Embedder):
    """Returns zero vectors. For testing and when no provider is configured.

    Args:
        dimension: Vector dimension (default 768).
    """

    def __init__(self, dimension: int = 768) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        return [0.0] * self._dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dimension for _ in texts]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_embedder(
    provider: str,
    *,
    base_url: str = "",
    model: str = "",
    dimension: int = 768,
    api_key: str = "not-needed",
    timeout: float = 30.0,
    prefix_style: str = "none",
) -> Embedder | None:
    """Factory: create an Embedder from config values.

    Args:
        provider: ``"openai-compat"``, ``"ollama"``, or ``"none"``.
        base_url: API base URL.
        model: Model identifier.
        dimension: Embedding dimension.
        api_key: Bearer token (OpenAI-compat only).
        timeout: HTTP timeout in seconds.
        prefix_style: Task-type prefix style (``"nomic"``, ``"cohere"``,
            or ``"none"``).

    Returns:
        An Embedder instance, or ``None`` if provider is ``"none"``.

    Raises:
        ValueError: If the provider is unknown.
    """
    if provider == "none":
        return None
    if provider == "openai-compat":
        return OpenAICompatEmbedder(
            base_url=base_url or "http://localhost:1234/v1",
            model=model or "text-embedding-nomic-embed-text-v1.5",
            dimension=dimension,
            api_key=api_key,
            timeout=timeout,
            prefix_style=prefix_style,
        )
    if provider == "ollama":
        return OllamaEmbedder(
            base_url=base_url or "http://localhost:11434",
            model=model or "nomic-embed-text",
            dimension=dimension,
            timeout=timeout,
            prefix_style=prefix_style,
        )
    raise ValueError(f"Unknown embedder provider: {provider!r}")


# ---------------------------------------------------------------------------
# Serialization helpers for sqlite-vec
# ---------------------------------------------------------------------------


def vec_to_blob(vec: list[float]) -> bytes:
    """Pack a float list into a little-endian binary blob for sqlite-vec.

    Args:
        vec: Embedding vector.

    Returns:
        Binary blob suitable for ``INSERT INTO neuron_vec``.
    """
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_vec(blob: bytes) -> list[float]:
    """Unpack a sqlite-vec binary blob into a float list.

    Args:
        blob: Binary blob from sqlite-vec.

    Returns:
        List of floats.
    """
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))

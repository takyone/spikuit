"""Embedder — pluggable text embedding with multiple provider support.

Provides an abstract Embedder interface and concrete implementations
for OpenAI-compatible APIs (LM Studio, Ollama /v1, vLLM, etc.),
Ollama native API, and a null embedder for testing.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod

import httpx


class Embedder(ABC):
    """Abstract base for text embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Default: sequential calls to embed()."""
        return [await self.embed(t) for t in texts]


class OpenAICompatEmbedder(Embedder):
    """Embedder using any OpenAI-compatible /v1/embeddings endpoint.

    Works with: LM Studio, Ollama (with /v1), vLLM, OpenAI, etc.

    Usage::

        embedder = OpenAICompatEmbedder(
            base_url="http://localhost:1234/v1",
            model="text-embedding-nomic-embed-text-v1.5",
            dimension=768,
        )
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:1234/v1",
        model: str = "text-embedding-nomic-embed-text-v1.5",
        dimension: int = 768,
        api_key: str = "not-needed",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._api_key = api_key
        self._timeout = timeout

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
    """Embedder using Ollama's native /api/embed endpoint.

    Usage::

        embedder = OllamaEmbedder(
            base_url="http://localhost:11434",
            model="nomic-embed-text",
            dimension=768,
        )
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dimension: int = 768,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout = timeout

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
    """Returns zero vectors. For testing and fallback when no provider is available."""

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
) -> Embedder | None:
    """Create an Embedder from config values. Returns None for 'none'."""
    if provider == "none":
        return None
    if provider == "openai-compat":
        return OpenAICompatEmbedder(
            base_url=base_url or "http://localhost:1234/v1",
            model=model or "text-embedding-nomic-embed-text-v1.5",
            dimension=dimension,
            api_key=api_key,
            timeout=timeout,
        )
    if provider == "ollama":
        return OllamaEmbedder(
            base_url=base_url or "http://localhost:11434",
            model=model or "nomic-embed-text",
            dimension=dimension,
            timeout=timeout,
        )
    raise ValueError(f"Unknown embedder provider: {provider!r}")


# ---------------------------------------------------------------------------
# Serialization helpers for sqlite-vec
# ---------------------------------------------------------------------------


def vec_to_blob(vec: list[float]) -> bytes:
    """Pack a float list into a binary blob for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_vec(blob: bytes) -> list[float]:
    """Unpack a sqlite-vec binary blob into a float list."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))

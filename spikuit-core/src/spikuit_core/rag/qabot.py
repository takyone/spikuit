"""QABot — read-only retrieval client for an exported Brain bundle.

QABot loads a SQLite bundle produced by `export_qabot_bundle` and offers
hybrid retrieval (semantic + keyword) with minimal dependencies. It does
not import the Circuit engine.

Example:
    ```python
    from spikuit_core import QABot

    brain = QABot.load("brain.db")  # env vars resolve embedder endpoint
    hits = await brain.retrieve("What is a monad?", limit=5)
    for h in hits:
        print(h.score, h.content[:80])
    ```
"""

from __future__ import annotations

import os
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..embedder import Embedder


# -- Public types ----------------------------------------------------------


@dataclass
class EmbedderSpec:
    """Embedder spec stored in the bundle (no API key, hint-only base URL)."""

    provider: str
    model: str | None
    dimension: int | None
    prefix_style: str | None
    original_base_url: str | None


@dataclass
class RetrievalHit:
    """A single retrieval result."""

    neuron_id: str
    content: str
    score: float
    type: str | None = None
    domain: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)


class EmbedderConfigError(RuntimeError):
    """Raised when the embedder cannot be resolved at runtime."""


# -- Vector helpers --------------------------------------------------------


def _blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    import numpy as np

    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


# -- QABot -----------------------------------------------------------------


class QABot:
    """Read-only retrieval over an exported Brain bundle.

    Use `QABot.load(path)` to open a bundle. The class is intentionally
    sync at the connection layer; only `retrieve()` is async because it
    may need to call an embedding API.
    """

    def __init__(
        self,
        path: Path,
        conn: sqlite3.Connection,
        embedder_spec: EmbedderSpec,
        embedder: "Embedder | None",
        runtime_base_url: str | None,
    ) -> None:
        self._path = path
        self._conn = conn
        self.embedder_spec = embedder_spec
        self._embedder = embedder
        self.runtime_base_url = runtime_base_url

    # -- Construction ----------------------------------------------------

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> "QABot":
        """Open a bundle and resolve the embedder.

        Resolution order for base_url and api_key:
            1. environment variable (SPIKUIT_EMBEDDER_BASE_URL / _API_KEY)
            2. constructor argument
            3. bundle hint (warning, not guaranteed reachable)
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Bundle not found: {path}")

        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row

        spec = cls._read_embedder_spec(conn)

        if spec.provider == "none":
            return cls(
                path=path,
                conn=conn,
                embedder_spec=spec,
                embedder=None,
                runtime_base_url=None,
            )

        resolved_url = (
            os.environ.get("SPIKUIT_EMBEDDER_BASE_URL")
            or base_url
            or spec.original_base_url
        )
        resolved_key = (
            os.environ.get("SPIKUIT_EMBEDDER_API_KEY")
            or api_key
            or os.environ.get("OPENAI_API_KEY")
            or "not-needed"
        )

        if not resolved_url:
            raise EmbedderConfigError(
                f"This brain uses embeddings (provider={spec.provider}, "
                f"dim={spec.dimension}, prefix={spec.prefix_style}).\n\n"
                "  Set SPIKUIT_EMBEDDER_BASE_URL or pass base_url to QABot.load()."
            )

        embedder = cls._build_embedder(spec, resolved_url, resolved_key)
        return cls(
            path=path,
            conn=conn,
            embedder_spec=spec,
            embedder=embedder,
            runtime_base_url=resolved_url,
        )

    @staticmethod
    def _read_embedder_spec(conn: sqlite3.Connection) -> EmbedderSpec:
        row = conn.execute(
            "SELECT provider, model, dimension, prefix_style, original_base_url "
            "FROM embedder_config LIMIT 1"
        ).fetchone()
        if row is None:
            return EmbedderSpec(
                provider="none",
                model=None,
                dimension=None,
                prefix_style=None,
                original_base_url=None,
            )
        return EmbedderSpec(
            provider=row["provider"],
            model=row["model"],
            dimension=row["dimension"],
            prefix_style=row["prefix_style"],
            original_base_url=row["original_base_url"],
        )

    @staticmethod
    def _build_embedder(
        spec: EmbedderSpec, base_url: str, api_key: str
    ) -> "Embedder":
        # Lazy import — keeps `spikuit_core.rag` independent of engine
        from ..embedder import create_embedder

        emb = create_embedder(
            provider=spec.provider,
            base_url=base_url,
            model=spec.model or "",
            dimension=spec.dimension or 768,
            api_key=api_key,
            prefix_style=spec.prefix_style or "none",
        )
        if emb is None:
            raise EmbedderConfigError(
                f"create_embedder returned None for provider={spec.provider!r}"
            )
        return emb

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "QABot":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Retrieval -------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        limit: int = 10,
        *,
        domain: str | None = None,
        type: str | None = None,
    ) -> list[RetrievalHit]:
        """Hybrid retrieval: semantic (if embedder available) + keyword.

        Falls back to keyword-only when no embedder is configured or the
        bundle has no stored embeddings.
        """
        semantic_scores: dict[str, float] = {}
        if self._embedder is not None and self._has_embeddings():
            semantic_scores = await self._semantic_scores(query, limit * 4)

        keyword_scores = self._keyword_scores(query, limit * 4)

        # Hybrid: weighted sum
        combined: dict[str, float] = {}
        for nid, s in semantic_scores.items():
            combined[nid] = combined.get(nid, 0.0) + s * 0.6
        for nid, s in keyword_scores.items():
            combined[nid] = combined.get(nid, 0.0) + s * 0.4

        if not combined:
            return []

        # Apply filters and rank
        rows = self._fetch_neurons(list(combined.keys()), domain=domain, type=type)
        hits: list[RetrievalHit] = []
        for row in rows:
            nid = row["id"]
            hits.append(
                RetrievalHit(
                    neuron_id=nid,
                    content=row["content"],
                    score=combined.get(nid, 0.0),
                    type=row["type"],
                    domain=row["domain"],
                    sources=self.sources(nid),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def _has_embeddings(self) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='neuron_embedding'"
        ).fetchone()
        return row is not None

    async def _semantic_scores(self, query: str, k: int) -> dict[str, float]:
        from ..embedder import EmbeddingType  # lazy import

        text = query
        if self._embedder is not None and hasattr(self._embedder, "apply_prefix"):
            try:
                text = self._embedder.apply_prefix(query, EmbeddingType.QUERY)
            except Exception:
                text = query

        assert self._embedder is not None
        query_vec = await self._embedder.embed(text)

        rows = self._conn.execute(
            "SELECT neuron_id, vec FROM neuron_embedding"
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for row in rows:
            vec = _blob_to_vec(row["vec"])
            scored.append((row["neuron_id"], _cosine(query_vec, vec)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return {nid: s for nid, s in scored[:k]}

    def _keyword_scores(self, query: str, k: int) -> dict[str, float]:
        # Simple LIKE-based scoring: count case-insensitive substring matches
        # of each query term, weighted by inverse term length.
        terms = [t for t in query.lower().split() if len(t) >= 2]
        if not terms:
            # Fall back to whole query
            terms = [query.lower().strip()]
            terms = [t for t in terms if t]
        if not terms:
            return {}

        scores: dict[str, float] = {}
        for term in terms:
            like = f"%{term}%"
            rows = self._conn.execute(
                "SELECT id, content FROM neuron WHERE LOWER(content) LIKE ? LIMIT ?",
                (like, k * 4),
            ).fetchall()
            for row in rows:
                # Count occurrences for a rough TF
                tf = row["content"].lower().count(term)
                scores[row["id"]] = scores.get(row["id"], 0.0) + float(tf)

        if not scores:
            return {}

        # Normalize to [0, 1]
        max_s = max(scores.values()) or 1.0
        return {nid: s / max_s for nid, s in scores.items()}

    def _fetch_neurons(
        self,
        ids: list[str],
        *,
        domain: str | None = None,
        type: str | None = None,
    ) -> list[sqlite3.Row]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        sql = f"SELECT id, content, type, domain FROM neuron WHERE id IN ({placeholders})"
        params: list[Any] = list(ids)
        if domain is not None:
            sql += " AND domain = ?"
            params.append(domain)
        if type is not None:
            sql += " AND type = ?"
            params.append(type)
        return self._conn.execute(sql, params).fetchall()

    # -- Inspection ------------------------------------------------------

    def system_prompt(self) -> str:
        """Concatenate `_meta` domain neurons into a system prompt.

        Returns an empty string if no `_meta` neurons exist (until #34
        lands, this is the expected MVP behavior).
        """
        rows = self._conn.execute(
            "SELECT content FROM neuron WHERE domain = '_meta' ORDER BY created_at"
        ).fetchall()
        if not rows:
            return ""
        return "\n\n".join(row["content"] for row in rows)

    def domains(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT domain FROM neuron WHERE domain IS NOT NULL ORDER BY domain"
        ).fetchall()
        return [row["domain"] for row in rows]

    def stats(self) -> dict[str, int]:
        n = self._conn.execute("SELECT COUNT(*) FROM neuron").fetchone()[0]
        s = self._conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]
        syn = self._conn.execute("SELECT COUNT(*) FROM synapse").fetchone()[0]
        return {"neurons": n, "sources": s, "synapses": syn}

    def neuron(self, neuron_id: str) -> RetrievalHit | None:
        row = self._conn.execute(
            "SELECT id, content, type, domain FROM neuron WHERE id = ?",
            (neuron_id,),
        ).fetchone()
        if row is None:
            return None
        return RetrievalHit(
            neuron_id=row["id"],
            content=row["content"],
            score=0.0,
            type=row["type"],
            domain=row["domain"],
            sources=self.sources(row["id"]),
        )

    def sources(self, neuron_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT s.id, s.url, s.title, s.author "
            "FROM source s "
            "JOIN neuron_source ns ON ns.source_id = s.id "
            "WHERE ns.neuron_id = ?",
            (neuron_id,),
        ).fetchall()
        return [dict(row) for row in rows]

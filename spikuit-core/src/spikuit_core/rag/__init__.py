"""RAG client — read-only access to exported Brain bundles.

This module is intentionally **lightweight**. It does not import the
Circuit engine and only depends on `embedder.py`, `sqlite3` (stdlib),
and `numpy`. A minimal `pip install spikuit-core` (without `[engine]`
extras) is enough to run a QABot retrieval server.
"""

from .qabot import EmbedderConfigError, EmbedderSpec, QABot, RetrievalHit

__all__ = ["QABot", "RetrievalHit", "EmbedderSpec", "EmbedderConfigError"]

"""Export utilities — write Brain data to portable formats.

`export_qabot_bundle` writes a read-only SQLite bundle that downstream
`QABot` clients can load without the full Spikuit engine. The bundle is
self-describing: it carries an `embedder_config` row so the client knows
which embedding model produced the stored vectors.

API keys are never written to the bundle. Runtime connection info is
resolved separately (env var / constructor arg / bundle hint).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .circuit import Circuit
    from .config import BrainConfig


_QABOT_SCHEMA = """
CREATE TABLE neuron (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    type TEXT,
    domain TEXT,
    community_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE synapse (
    pre_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    co_fires INTEGER DEFAULT 0,
    PRIMARY KEY (pre_id, post_id)
);
CREATE TABLE source (
    id TEXT PRIMARY KEY,
    url TEXT,
    title TEXT,
    author TEXT,
    filterable TEXT,
    searchable TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE neuron_source (
    neuron_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    PRIMARY KEY (neuron_id, source_id)
);
CREATE TABLE embedder_config (
    provider TEXT NOT NULL,
    model TEXT,
    dimension INTEGER,
    prefix_style TEXT,
    original_base_url TEXT
);
"""


async def export_qabot_bundle(
    circuit: "Circuit",
    config: "BrainConfig",
    output: Path,
) -> None:
    """Write a read-only QABot SQLite bundle.

    Args:
        circuit: A connected Circuit to export from.
        config: BrainConfig providing embedder spec (no API key is written).
        output: Target path. Overwritten if it already exists.
    """
    output = Path(output)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(str(output))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_QABOT_SCHEMA)

        # embedder_config — spec only, no api_key
        emb = config.embedder
        conn.execute(
            "INSERT INTO embedder_config "
            "(provider, model, dimension, prefix_style, original_base_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                emb.provider,
                emb.model or None,
                emb.dimension,
                emb.prefix_style,
                emb.base_url or None,
            ),
        )

        neurons = await circuit.list_neurons(limit=100_000)
        for n in neurons:
            cid = circuit.get_community(n.id)
            conn.execute(
                "INSERT INTO neuron VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    n.id,
                    n.content,
                    n.type,
                    n.domain,
                    cid,
                    str(n.created_at),
                    str(n.updated_at),
                ),
            )

        for u, v, data in circuit.graph.edges(data=True):
            conn.execute(
                "INSERT INTO synapse VALUES (?, ?, ?, ?, ?)",
                (
                    u,
                    v,
                    data.get("type", "relates_to"),
                    data.get("weight", 0.5),
                    data.get("co_fires", 0),
                ),
            )

        sources = await circuit.list_sources(limit=100_000)
        for s in sources:
            conn.execute(
                "INSERT INTO source VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    s.id,
                    s.url,
                    s.title,
                    s.author,
                    json.dumps(s.filterable) if s.filterable else None,
                    json.dumps(s.searchable) if s.searchable else None,
                    str(s.created_at),
                ),
            )

        for n in neurons:
            nsources = await circuit.get_sources_for_neuron(n.id)
            for s in nsources:
                conn.execute(
                    "INSERT INTO neuron_source VALUES (?, ?)",
                    (n.id, s.id),
                )

        # Copy embeddings if present
        try:
            src_db = circuit._db
            rows = await src_db.conn.execute_fetchall(
                "SELECT neuron_id FROM neuron_vec_map"
            )
            if rows:
                conn.execute(
                    """CREATE TABLE neuron_embedding (
                        neuron_id TEXT PRIMARY KEY,
                        vec BLOB NOT NULL
                    )"""
                )
                for row in rows:
                    nid = row["neuron_id"]
                    vec_rows = await src_db.conn.execute_fetchall(
                        "SELECT vec FROM neuron_vec "
                        "WHERE rowid IN (SELECT rowid FROM neuron_vec_map WHERE neuron_id = ?)",
                        (nid,),
                    )
                    if vec_rows:
                        conn.execute(
                            "INSERT INTO neuron_embedding VALUES (?, ?)",
                            (nid, vec_rows[0]["vec"]),
                        )
        except Exception:
            pass  # No embeddings stored — keyword-only retrieval still works

        conn.execute("PRAGMA application_id = 1936158836")  # 'spkt'
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

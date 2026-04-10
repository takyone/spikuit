"""Spikuit Core database — async SQLite persistence layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from .models import Grade, Neuron, Spike, Synapse, SynapseType

DEFAULT_DB_PATH = Path.home() / ".spikuit" / "spikuit.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS neuron (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    type TEXT,
    domain TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synapse (
    pre TEXT NOT NULL REFERENCES neuron(id),
    post TEXT NOT NULL REFERENCES neuron(id),
    type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.5,
    co_fires INTEGER NOT NULL DEFAULT 0,
    last_co_fire TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (pre, post, type)
);

CREATE TABLE IF NOT EXISTS fsrs_state (
    neuron_id TEXT PRIMARY KEY REFERENCES neuron(id),
    stability REAL,
    difficulty REAL,
    retrievability REAL,
    last_review TEXT,
    next_review TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    lapse_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS spike (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neuron_id TEXT NOT NULL REFERENCES neuron(id),
    grade INTEGER NOT NULL,
    fired_at TEXT NOT NULL,
    session_id TEXT
);

CREATE TABLE IF NOT EXISTS retrieve_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    neuron_ids TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_neuron_type ON neuron(type);
CREATE INDEX IF NOT EXISTS idx_neuron_domain ON neuron(domain);
CREATE INDEX IF NOT EXISTS idx_synapse_pre ON synapse(pre);
CREATE INDEX IF NOT EXISTS idx_synapse_post ON synapse(post);
CREATE INDEX IF NOT EXISTS idx_fsrs_next_review ON fsrs_state(next_review);
CREATE INDEX IF NOT EXISTS idx_spike_neuron ON spike(neuron_id);
CREATE INDEX IF NOT EXISTS idx_spike_session ON spike(session_id);
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class Database:
    """Async SQLite wrapper for Spikuit persistence."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    # -- Neuron CRUD --------------------------------------------------------

    async def insert_neuron(self, neuron: Neuron) -> None:
        await self.conn.execute(
            """INSERT INTO neuron (id, content, type, domain, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                neuron.id,
                neuron.content,
                neuron.type,
                neuron.domain,
                neuron.source,
                _ts(neuron.created_at),
                _ts(neuron.updated_at),
            ),
        )
        await self.conn.commit()

    async def get_neuron(self, neuron_id: str) -> Neuron | None:
        row = await self.conn.execute_fetchall(
            "SELECT * FROM neuron WHERE id = ?", (neuron_id,)
        )
        return _row_to_neuron(row[0]) if row else None

    async def list_neurons(
        self,
        *,
        type: str | None = None,
        domain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Neuron]:
        clauses = []
        params: list = []
        if type:
            clauses.append("type = ?")
            params.append(type)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = await self.conn.execute_fetchall(
            f"SELECT * FROM neuron {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
        return [_row_to_neuron(r) for r in rows]

    async def update_neuron(self, neuron: Neuron) -> None:
        neuron.updated_at = datetime.now(timezone.utc)
        await self.conn.execute(
            """UPDATE neuron SET content=?, type=?, domain=?, source=?, updated_at=?
               WHERE id=?""",
            (
                neuron.content,
                neuron.type,
                neuron.domain,
                neuron.source,
                _ts(neuron.updated_at),
                neuron.id,
            ),
        )
        await self.conn.commit()

    async def delete_neuron(self, neuron_id: str) -> None:
        await self.conn.execute("DELETE FROM synapse WHERE pre=? OR post=?", (neuron_id, neuron_id))
        await self.conn.execute("DELETE FROM fsrs_state WHERE neuron_id=?", (neuron_id,))
        await self.conn.execute("DELETE FROM spike WHERE neuron_id=?", (neuron_id,))
        await self.conn.execute("DELETE FROM neuron WHERE id=?", (neuron_id,))
        await self.conn.commit()

    async def count_neurons(self) -> int:
        rows = await self.conn.execute_fetchall("SELECT COUNT(*) FROM neuron")
        return rows[0][0]

    # -- Synapse CRUD -------------------------------------------------------

    async def insert_synapse(self, synapse: Synapse) -> None:
        await self.conn.execute(
            """INSERT OR IGNORE INTO synapse
               (pre, post, type, weight, co_fires, last_co_fire, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                synapse.pre,
                synapse.post,
                synapse.type.value,
                synapse.weight,
                synapse.co_fires,
                _ts(synapse.last_co_fire) if synapse.last_co_fire else None,
                _ts(synapse.created_at),
                _ts(synapse.updated_at),
            ),
        )
        await self.conn.commit()

    async def get_synapse(self, pre: str, post: str, type: SynapseType) -> Synapse | None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM synapse WHERE pre=? AND post=? AND type=?",
            (pre, post, type.value),
        )
        return _row_to_synapse(rows[0]) if rows else None

    async def get_synapses_from(self, neuron_id: str) -> list[Synapse]:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM synapse WHERE pre=?", (neuron_id,)
        )
        return [_row_to_synapse(r) for r in rows]

    async def get_synapses_to(self, neuron_id: str) -> list[Synapse]:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM synapse WHERE post=?", (neuron_id,)
        )
        return [_row_to_synapse(r) for r in rows]

    async def get_all_synapses(self) -> list[Synapse]:
        rows = await self.conn.execute_fetchall("SELECT * FROM synapse")
        return [_row_to_synapse(r) for r in rows]

    async def update_synapse(self, synapse: Synapse) -> None:
        synapse.updated_at = datetime.now(timezone.utc)
        await self.conn.execute(
            """UPDATE synapse SET weight=?, co_fires=?, last_co_fire=?, updated_at=?
               WHERE pre=? AND post=? AND type=?""",
            (
                synapse.weight,
                synapse.co_fires,
                _ts(synapse.last_co_fire) if synapse.last_co_fire else None,
                _ts(synapse.updated_at),
                synapse.pre,
                synapse.post,
                synapse.type.value,
            ),
        )
        await self.conn.commit()

    async def delete_synapse(self, pre: str, post: str, type: SynapseType) -> None:
        await self.conn.execute(
            "DELETE FROM synapse WHERE pre=? AND post=? AND type=?",
            (pre, post, type.value),
        )
        await self.conn.commit()

    # -- Spike --------------------------------------------------------------

    async def insert_spike(self, spike: Spike) -> int:
        cursor = await self.conn.execute(
            """INSERT INTO spike (neuron_id, grade, fired_at, session_id)
               VALUES (?, ?, ?, ?)""",
            (
                spike.neuron_id,
                spike.grade.value,
                _ts(spike.fired_at),
                spike.session_id,
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_spikes_for(
        self, neuron_id: str, *, limit: int = 50
    ) -> list[Spike]:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM spike WHERE neuron_id=? ORDER BY fired_at DESC LIMIT ?",
            (neuron_id, limit),
        )
        return [_row_to_spike(r) for r in rows]

    # -- Retrieve log -------------------------------------------------------

    async def log_retrieve(self, query: str, neuron_ids: list[str]) -> None:
        await self.conn.execute(
            "INSERT INTO retrieve_log (query, neuron_ids, retrieved_at) VALUES (?, ?, ?)",
            (query, json.dumps(neuron_ids), _ts(datetime.now(timezone.utc))),
        )
        await self.conn.commit()


# ---------------------------------------------------------------------------
# Row converters
# ---------------------------------------------------------------------------

def _row_to_neuron(row: aiosqlite.Row) -> Neuron:
    return Neuron(
        id=row["id"],
        content=row["content"],
        type=row["type"],
        domain=row["domain"],
        source=row["source"],
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


def _row_to_synapse(row: aiosqlite.Row) -> Synapse:
    return Synapse(
        pre=row["pre"],
        post=row["post"],
        type=SynapseType(row["type"]),
        weight=row["weight"],
        co_fires=row["co_fires"],
        last_co_fire=_parse_ts(row["last_co_fire"]) if row["last_co_fire"] else None,
        created_at=_parse_ts(row["created_at"]),
        updated_at=_parse_ts(row["updated_at"]),
    )


def _row_to_spike(row: aiosqlite.Row) -> Spike:
    return Spike(
        neuron_id=row["neuron_id"],
        grade=Grade(row["grade"]),
        fired_at=_parse_ts(row["fired_at"]),
        session_id=row["session_id"],
    )


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)

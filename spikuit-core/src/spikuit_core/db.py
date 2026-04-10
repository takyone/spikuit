"""Spikuit Core database — async SQLite persistence layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import sqlite_vec

from .models import Grade, Neuron, QuizItem, QuizItemRole, ScaffoldLevel, Spike, Synapse, SynapseType

DEFAULT_DB_PATH: Path = Path.home() / ".spikuit" / "spikuit.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA: str = """
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
    card_json TEXT NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_spike_neuron ON spike(neuron_id);
CREATE INDEX IF NOT EXISTS idx_spike_session ON spike(session_id);

CREATE TABLE IF NOT EXISTS retrieval_boost (
    neuron_id TEXT PRIMARY KEY REFERENCES neuron(id),
    boost REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_item (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    hints TEXT NOT NULL DEFAULT '[]',
    grading_criteria TEXT NOT NULL DEFAULT '',
    scaffold_level TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_item_neuron (
    quiz_item_id TEXT NOT NULL REFERENCES quiz_item(id) ON DELETE CASCADE,
    neuron_id TEXT NOT NULL REFERENCES neuron(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (quiz_item_id, neuron_id)
);

CREATE INDEX IF NOT EXISTS idx_quiz_item_neuron_nid ON quiz_item_neuron(neuron_id);
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """Async SQLite wrapper for Spikuit persistence."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        *,
        embedding_dimension: int | None = None,
    ) -> None:
        self.db_path: Path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._embedding_dimension = embedding_dimension

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        # Load sqlite-vec extension and create vec table if dimension is set
        if self._embedding_dimension is not None:
            await self._init_vec_table(self._embedding_dimension)

    async def _init_vec_table(self, dimension: int) -> None:
        """Initialize sqlite-vec virtual table for embeddings."""

        def _load_extension():
            """Load sqlite-vec in the worker thread (same thread as the connection)."""
            raw = self.conn._conn  # sqlite3.Connection in worker thread
            raw.enable_load_extension(True)
            sqlite_vec.load(raw)
            raw.enable_load_extension(False)

        # Run in aiosqlite's worker thread where the connection lives
        await self.conn._execute(_load_extension)
        await self.conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS neuron_vec "
            f"USING vec0(embedding float[{dimension}])"
        )
        # Mapping table: rowid ↔ neuron_id (vec0 uses integer rowids)
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS neuron_vec_map (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                neuron_id TEXT NOT NULL UNIQUE REFERENCES neuron(id)
            );
        """)
        await self.conn.commit()

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
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM neuron WHERE id = ?", (neuron_id,)
        )
        return _row_to_neuron(rows[0]) if rows else None

    async def list_neurons(
        self,
        *,
        type: str | None = None,
        domain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Neuron]:
        clauses: list[str] = []
        params: list[Any] = []
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
        await self.conn.execute(
            "DELETE FROM synapse WHERE pre=? OR post=?", (neuron_id, neuron_id)
        )
        await self.conn.execute("DELETE FROM fsrs_state WHERE neuron_id=?", (neuron_id,))
        await self.conn.execute("DELETE FROM spike WHERE neuron_id=?", (neuron_id,))
        await self.delete_quiz_items_for_neuron(neuron_id)
        if self._embedding_dimension is not None:
            await self.delete_embedding(neuron_id)
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

    async def get_synapse(
        self, pre: str, post: str, type: SynapseType
    ) -> Synapse | None:
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

    # -- FSRS state ---------------------------------------------------------

    async def upsert_fsrs_card(self, neuron_id: str, card_json: str) -> None:
        await self.conn.execute(
            """INSERT INTO fsrs_state (neuron_id, card_json) VALUES (?, ?)
               ON CONFLICT(neuron_id) DO UPDATE SET card_json=excluded.card_json""",
            (neuron_id, card_json),
        )
        await self.conn.commit()

    async def get_fsrs_card_json(self, neuron_id: str) -> str | None:
        rows = await self.conn.execute_fetchall(
            "SELECT card_json FROM fsrs_state WHERE neuron_id=?", (neuron_id,)
        )
        return rows[0]["card_json"] if rows else None

    async def get_due_neurons(self, *, now: datetime | None = None, limit: int = 20) -> list[str]:
        """Return neuron IDs whose FSRS card is due for review."""
        if now is None:
            now = datetime.now(timezone.utc)
        rows = await self.conn.execute_fetchall(
            "SELECT neuron_id, card_json FROM fsrs_state"
        )
        due_ids: list[str] = []
        for row in rows:
            card_data = json.loads(row["card_json"])
            due_str = card_data.get("due")
            if due_str:
                due_dt = datetime.fromisoformat(due_str)
                if due_dt <= now:
                    due_ids.append(row["neuron_id"])
            if len(due_ids) >= limit:
                break
        return due_ids

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

    # -- Embeddings ---------------------------------------------------------

    async def upsert_embedding(self, neuron_id: str, blob: bytes) -> None:
        """Insert or replace an embedding vector for a neuron."""
        # Get or create the rowid mapping
        rows = await self.conn.execute_fetchall(
            "SELECT rowid FROM neuron_vec_map WHERE neuron_id = ?", (neuron_id,)
        )
        if rows:
            rid = rows[0]["rowid"]
            # Update: delete old vec row and re-insert
            await self.conn.execute(
                "DELETE FROM neuron_vec WHERE rowid = ?", (rid,)
            )
            await self.conn.execute(
                "INSERT INTO neuron_vec(rowid, embedding) VALUES (?, ?)",
                (rid, blob),
            )
        else:
            # Insert mapping first
            cursor = await self.conn.execute(
                "INSERT INTO neuron_vec_map (neuron_id) VALUES (?)", (neuron_id,)
            )
            rid = cursor.lastrowid
            await self.conn.execute(
                "INSERT INTO neuron_vec(rowid, embedding) VALUES (?, ?)",
                (rid, blob),
            )
        await self.conn.commit()

    async def delete_embedding(self, neuron_id: str) -> None:
        """Remove an embedding for a neuron."""
        rows = await self.conn.execute_fetchall(
            "SELECT rowid FROM neuron_vec_map WHERE neuron_id = ?", (neuron_id,)
        )
        if rows:
            rid = rows[0]["rowid"]
            await self.conn.execute("DELETE FROM neuron_vec WHERE rowid = ?", (rid,))
            await self.conn.execute("DELETE FROM neuron_vec_map WHERE rowid = ?", (rid,))
            await self.conn.commit()

    async def knn_search(self, query_blob: bytes, *, limit: int = 20) -> list[tuple[str, float]]:
        """Find nearest neighbors. Returns (neuron_id, distance) pairs."""
        rows = await self.conn.execute_fetchall(
            """
            SELECT m.neuron_id, v.distance
            FROM neuron_vec v
            JOIN neuron_vec_map m ON m.rowid = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (query_blob, limit),
        )
        return [(row["neuron_id"], row["distance"]) for row in rows]

    @property
    def has_embeddings(self) -> bool:
        """Whether embedding support is enabled."""
        return self._embedding_dimension is not None

    # -- Retrieval boost ----------------------------------------------------

    async def get_retrieval_boost(self, neuron_id: str) -> float:
        rows = await self.conn.execute_fetchall(
            "SELECT boost FROM retrieval_boost WHERE neuron_id = ?", (neuron_id,)
        )
        return rows[0]["boost"] if rows else 0.0

    async def set_retrieval_boost(self, neuron_id: str, boost: float) -> None:
        await self.conn.execute(
            """INSERT INTO retrieval_boost (neuron_id, boost, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(neuron_id) DO UPDATE SET boost=excluded.boost, updated_at=excluded.updated_at""",
            (neuron_id, boost, _ts(datetime.now(timezone.utc))),
        )
        await self.conn.commit()

    async def batch_set_retrieval_boosts(self, updates: dict[str, float]) -> None:
        """Set multiple retrieval boosts in a single transaction."""
        now = _ts(datetime.now(timezone.utc))
        for nid, boost in updates.items():
            await self.conn.execute(
                """INSERT INTO retrieval_boost (neuron_id, boost, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(neuron_id) DO UPDATE SET boost=excluded.boost, updated_at=excluded.updated_at""",
                (nid, boost, now),
            )
        await self.conn.commit()

    async def get_all_retrieval_boosts(self) -> dict[str, float]:
        rows = await self.conn.execute_fetchall("SELECT neuron_id, boost FROM retrieval_boost")
        return {row["neuron_id"]: row["boost"] for row in rows}

    # -- Quiz items ---------------------------------------------------------

    async def insert_quiz_item(self, item: QuizItem) -> None:
        await self.conn.execute(
            """INSERT INTO quiz_item (id, question, answer, hints, grading_criteria,
               scaffold_level, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.question,
                item.answer,
                json.dumps(item.hints),
                item.grading_criteria,
                item.scaffold_level.value if item.scaffold_level else None,
                _ts(item.created_at),
            ),
        )
        for nid, role in item.neuron_ids.items():
            await self.conn.execute(
                "INSERT INTO quiz_item_neuron (quiz_item_id, neuron_id, role) VALUES (?, ?, ?)",
                (item.id, nid, role.value),
            )
        await self.conn.commit()

    async def get_quiz_items(
        self,
        neuron_id: str,
        *,
        role: QuizItemRole | None = None,
        scaffold_level: ScaffoldLevel | None = None,
    ) -> list[QuizItem]:
        """Get quiz items associated with a neuron.

        Args:
            neuron_id: The neuron to look up.
            role: Filter by role (primary/supporting). None = any role.
            scaffold_level: Filter by scaffold level. None = any level.
        """
        clauses = ["qin.neuron_id = ?"]
        params: list[str] = [neuron_id]
        if role is not None:
            clauses.append("qin.role = ?")
            params.append(role.value)
        where = " AND ".join(clauses)

        rows = await self.conn.execute_fetchall(
            f"""SELECT qi.* FROM quiz_item qi
                JOIN quiz_item_neuron qin ON qin.quiz_item_id = qi.id
                WHERE {where}
                ORDER BY qi.created_at DESC""",
            params,
        )

        items: list[QuizItem] = []
        for row in rows:
            item = await self._hydrate_quiz_item(row)
            if scaffold_level is not None and item.scaffold_level != scaffold_level:
                continue
            items.append(item)
        return items

    async def get_quiz_item(self, item_id: str) -> QuizItem | None:
        rows = await self.conn.execute_fetchall(
            "SELECT * FROM quiz_item WHERE id = ?", (item_id,)
        )
        if not rows:
            return None
        return await self._hydrate_quiz_item(rows[0])

    async def delete_quiz_item(self, item_id: str) -> None:
        # quiz_item_neuron rows deleted by ON DELETE CASCADE
        await self.conn.execute("DELETE FROM quiz_item WHERE id = ?", (item_id,))
        await self.conn.commit()

    async def delete_quiz_items_for_neuron(self, neuron_id: str) -> int:
        """Delete all quiz items where this neuron is primary. Returns count."""
        rows = await self.conn.execute_fetchall(
            """SELECT quiz_item_id FROM quiz_item_neuron
               WHERE neuron_id = ? AND role = 'primary'""",
            (neuron_id,),
        )
        ids = [r["quiz_item_id"] for r in rows]
        for qid in ids:
            await self.conn.execute("DELETE FROM quiz_item WHERE id = ?", (qid,))
        await self.conn.commit()
        return len(ids)

    async def _hydrate_quiz_item(self, row: aiosqlite.Row) -> QuizItem:
        """Build a QuizItem from a quiz_item row, loading neuron associations."""
        assoc_rows = await self.conn.execute_fetchall(
            "SELECT neuron_id, role FROM quiz_item_neuron WHERE quiz_item_id = ?",
            (row["id"],),
        )
        neuron_ids = {r["neuron_id"]: QuizItemRole(r["role"]) for r in assoc_rows}
        return QuizItem(
            id=row["id"],
            question=row["question"],
            answer=row["answer"],
            hints=json.loads(row["hints"]),
            grading_criteria=row["grading_criteria"],
            scaffold_level=ScaffoldLevel(row["scaffold_level"]) if row["scaffold_level"] else None,
            neuron_ids=neuron_ids,
            created_at=_parse_ts(row["created_at"]),
        )

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

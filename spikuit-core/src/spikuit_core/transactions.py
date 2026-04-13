"""Transaction wrapper + event buffering for AMKB plumbing (v0.7.0).

This module does NOT import from ``amkb``. It exposes Spikuit-native
primitives (``SpikuitTransaction``, ``PendingEvent``, event op
constants) that later layers (the v0.7.1 adapter) translate into AMKB
types at the boundary.

Design notes
------------
- A transaction owns an in-memory buffer of ``PendingEvent`` objects.
- On commit, the buffer is flushed to the ``event`` table and the
  ``changeset`` row's ``committed_at``/``status`` columns are set.
- On abort, the buffer is discarded and the changeset row is marked
  ``aborted``. Row-level rollback of underlying writes is the caller's
  responsibility for now — ``Circuit`` wraps the block in a SQLite
  transaction at §3.1 in a follow-up commit.
- Nesting is not supported in v0.7.0. Entering a transaction while
  another is active on the same ``Circuit`` raises
  ``TransactionNestingError``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

ActorKind = Literal["human", "agent", "system"]


# Event op strings — stable identifiers emitted into the event log.
OP_NEURON_ADD = "neuron.add"
OP_NEURON_UPDATE = "neuron.update"
OP_NEURON_RETIRE = "neuron.retire"
OP_NEURON_MERGE = "neuron.merge"
OP_SYNAPSE_ADD = "synapse.add"
OP_SYNAPSE_UPDATE = "synapse.update"
OP_SYNAPSE_RETIRE = "synapse.retire"


class SpikuitError(Exception):
    """Base class for Spikuit core errors."""


class TransactionNestingError(SpikuitError):
    """Raised when a transaction is started while another is active."""


class TransactionAbortedError(SpikuitError):
    """Raised by callers who need to explicitly abort an active tx."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class PendingEvent:
    """One buffered mutation, flushed to the event table on commit."""

    op: str
    target_kind: str  # "neuron" | "synapse"
    target_id: str
    before_json: str | None = None
    after_json: str | None = None
    at: str = field(default_factory=_now)


@dataclass
class SpikuitTransaction:
    """In-flight changeset. Created by ``Circuit.transaction()``.

    Not thread-safe. Assumes a single async task at a time per Circuit.
    """

    id: str
    tag: str | None
    actor_id: str
    actor_kind: ActorKind
    started_at: str
    events: list[PendingEvent] = field(default_factory=list)
    status: Literal["open", "committed", "aborted"] = "open"

    def emit(
        self,
        op: str,
        target_kind: str,
        target_id: str,
        *,
        before_json: str | None = None,
        after_json: str | None = None,
    ) -> None:
        """Append an event to the in-memory buffer."""
        if self.status != "open":
            raise TransactionAbortedError(
                f"cannot emit on {self.status} transaction {self.id}"
            )
        self.events.append(
            PendingEvent(
                op=op,
                target_kind=target_kind,
                target_id=target_id,
                before_json=before_json,
                after_json=after_json,
            )
        )

    @classmethod
    def open(
        cls,
        *,
        tag: str | None,
        actor_id: str,
        actor_kind: ActorKind,
    ) -> SpikuitTransaction:
        return cls(
            id=_new_id("cs"),
            tag=tag,
            actor_id=actor_id,
            actor_kind=actor_kind,
            started_at=_now(),
        )

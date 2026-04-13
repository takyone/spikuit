# AMKB Core Plumbing Spec — Spikuit v0.7.0

**Status.** Draft. Companion to `amkb-integration-plan.md`. Defines
the concrete `spikuit-core` changes required before the v0.7.1
adapter can satisfy AMKB L1/L2/L4a/L4b conformance.

**Audience.** Reviewers of the v0.7.0 PR. Nothing in this doc
touches `spikuit-agents/amkb/` — the adapter is v0.7.1.

**Ground rule restated.** Nothing named in this spec is allowed to
import from `amkb.*`. The adapter reads these primitives and
translates. If a primitive cannot be explained in pure
Spikuit/neuroscience vocabulary, it does not belong here.

## 1. Summary of additions

| # | Addition | Layer | Tables / Modules touched |
|---|---|---|---|
| 1 | Soft-retire for Neuron/Synapse (sole delete path) | core | `neuron`, `synapse` (+ column), `db.py`, `circuit.py` |
| 2 | Event log | core | `changeset`, `event` (new), `db.py`, `circuit.py` |
| 3 | Transaction wrapper | core | `circuit.py` (new `transaction()` cm) |
| 4 | Predecessor junction | core | `neuron_predecessor` (new), merge path |
| 5 | Canonical exception classes | core | `spikuit_core/errors.py` (new or extended) |
| 6 | Read APIs for adapter | core | `circuit.events()`, `circuit.predecessors_of_lineage()` |
| 7 | `_live_neurons_sql` query fragment + audit | core | `db.py`, all SELECT sites |
| 8 | `spkt history prune` physical purge | cli | `spikuit_cli/commands/history.py` |

All six are additive. None rename, drop, or repurpose existing
columns. Existing code paths that do not opt in keep behaving
exactly as today.

## 2. DB migrations

Migration file: `spikuit-core/src/spikuit_core/migrations/0007_amkb_plumbing.sql`
(filename reflects current migration counter — adjust at PR time).
Runs idempotently via the existing migration runner in `db.py`.

### 2.1 `neuron.retired_at`

```sql
ALTER TABLE neuron ADD COLUMN retired_at REAL;  -- nullable UNIX seconds
CREATE INDEX idx_neuron_retired_at ON neuron(retired_at);
```

Semantics:
- `retired_at IS NULL` → live neuron. Existing rows get NULL by
  default on migration.
- `retired_at IS NOT NULL` → soft-retired. The row stays in
  `neuron`, its FSRS columns stay intact, but **every** live-path
  query in `circuit.py` / `db.py` / propagation / community
  detection MUST filter it out. See §7 on the query-fragment
  discipline that enforces this.
- **Soft-retire is the only delete path.** `remove_neuron` no
  longer physically deletes. `spkt neuron remove` routes to the
  soft path. Physical purging is a separate, explicit operation
  exposed as `spkt history prune` (§3.5) — never implicit in a
  remove call.
- **Vector index is physically cleaned on retire.** Retiring a
  neuron deletes its row from the `sqlite-vec` virtual table in
  the same SQLite transaction. The `neuron` row stays for event
  history and lineage; the vector does not. Rationale: keep ANN
  recall undegraded regardless of how many retired nodes
  accumulate. See §5.

### 2.2 `synapse.retired_at`

Same shape:

```sql
ALTER TABLE synapse ADD COLUMN retired_at REAL;
CREATE INDEX idx_synapse_retired_at ON synapse(retired_at);
```

Retiring a neuron cascade-retires its synapses in the same
transaction (sets `retired_at`, does not DELETE). Synapses also
disappear from the NetworkX graph used by APPNP and community
detection — see §7.

### 2.3 `changeset`

```sql
CREATE TABLE changeset (
    id            TEXT PRIMARY KEY,     -- ULID
    tag           TEXT,                 -- caller-supplied label
    actor_id      TEXT NOT NULL,        -- free-form, "cli:takyone" etc.
    actor_kind    TEXT NOT NULL,        -- "human" | "agent" | "system"
    started_at    REAL NOT NULL,
    committed_at  REAL,                 -- NULL while in-flight
    status        TEXT NOT NULL         -- "open" | "committed" | "aborted"
);
CREATE INDEX idx_changeset_committed_at ON changeset(committed_at);
```

One row per `async with circuit.transaction(...)` block. Auto-commit
paths (existing `add_neuron` etc.) still insert one `changeset` row
per call — the wrapper is just implicit there.

### 2.4 `event`

```sql
CREATE TABLE event (
    id             TEXT PRIMARY KEY,    -- ULID
    changeset_id   TEXT NOT NULL REFERENCES changeset(id),
    seq            INTEGER NOT NULL,    -- order within changeset
    op             TEXT NOT NULL,       -- "neuron.add" | "neuron.retire"
                                        -- | "neuron.merge" | "neuron.update"
                                        -- | "synapse.add" | "synapse.retire"
                                        -- | "synapse.update"
    target_kind    TEXT NOT NULL,       -- "neuron" | "synapse"
    target_id      TEXT NOT NULL,
    before_json    TEXT,                -- snapshot or NULL on create
    after_json     TEXT,                -- snapshot or NULL on retire
    at             REAL NOT NULL
);
CREATE INDEX idx_event_changeset ON event(changeset_id, seq);
CREATE INDEX idx_event_target ON event(target_kind, target_id);
CREATE INDEX idx_event_at ON event(at);
```

Snapshots are JSON blobs with exactly the Spikuit row shape (id,
content, type, domain, stability, …). The adapter reshapes them
into AMKB `Node`/`Edge` snapshots — `spikuit-core` never learns the
AMKB schema.

### 2.5 `neuron_predecessor`

```sql
CREATE TABLE neuron_predecessor (
    child_id   TEXT NOT NULL REFERENCES neuron(id),
    parent_id  TEXT NOT NULL REFERENCES neuron(id),
    at         REAL NOT NULL,
    PRIMARY KEY (child_id, parent_id)
);
CREATE INDEX idx_neuron_predecessor_parent ON neuron_predecessor(parent_id);
```

Populated by `merge_neurons`: for target `T` with sources
`S1…Sn`, insert `(T, S1)…(T, Sn)`. This is **lineage**, distinct
from graph adjacency returned by `circuit.predecessors(id)` (which
walks synapses). To avoid confusion the new read API is named
`predecessors_of_lineage(id)` — see §4.

Existing neurons get no rows; `ancestors(id)` returning the empty
set for them is the correct answer (they have no recorded
lineage). No backfill.

## 3. API additions

### 3.1 `circuit.transaction()`

```python
# spikuit_core/circuit.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def transaction(
    self,
    *,
    tag: str | None = None,
    actor_id: str,
    actor_kind: Literal["human", "agent", "system"] = "agent",
):
    ...
```

Behavior:
- On entry: insert `changeset` row with `status='open'`.
- All mutations inside the block append to an in-memory event
  buffer keyed by the changeset id.
- On exit without exception: a single SQLite transaction writes
  all `event` rows, sets `changeset.committed_at`, sets
  `status='committed'`. One atomic commit.
- On exit with exception: discard the buffer, set
  `status='aborted'`. Underlying row writes that already hit
  SQLite are rolled back via a BEGIN/ROLLBACK that wraps the full
  block.
- Nested `transaction()` calls: not supported in v0.7.0. Raise
  `TransactionNestingError`. AMKB spec does not require nesting.

Auto-commit path (existing callers): `add_neuron`, `add_synapse`,
`remove_neuron`, `update_neuron`, `merge_neurons`, `fire` each wrap
their work in a one-op `transaction(actor_id="system",
actor_kind="system", tag=None)` if no transaction is already
active. Their return values and signatures do not change.

**Critical:** `fire` (FSRS update + APPNP propagation + STDP edge
weight changes) is an existing hot path. Wrapping it in a
changeset must not measurably slow it down. Mitigation: the
implicit wrapper uses a fast path that skips event emission for
pure-pressure updates. AMKB only cares about structural
mutations, not pressure/weight drift. This is formalized in §5.

### 3.2 `circuit.remove_neuron(neuron_id)` — soft only

```python
async def remove_neuron(self, neuron_id: str) -> None:
```

Single code path:
1. Set `neuron.retired_at = now()`
2. Cascade: set `retired_at` on every synapse where `pre_id =
   neuron_id` or `post_id = neuron_id`
3. Delete the neuron's row from the `sqlite-vec` virtual table
4. Emit `neuron.retire` + N × `synapse.retire` events in the
   current (or auto-commit) changeset

No `hard` kwarg. No `DELETE FROM neuron`. `spkt neuron remove`
routes here. Existing behavioral differences between CLI and
adapter disappear — both go through this one path.

Physical deletion is only reachable through `spkt history
prune` (§3.5), which is an explicit, operator-driven operation
separate from removal semantics.

### 3.3 `circuit.merge_neurons(...)` — always soft

Today `merge_neurons` calls `remove_neuron(source_id)` internally
at circuit.py:500 (hard-delete). Change:

1. Create the merged target neuron (unchanged)
2. Insert one `neuron_predecessor` row per source pointing at
   the target
3. Call the new soft `remove_neuron` for each source (retires
   row, cascades synapses, cleans vector index, emits events)
4. All of the above runs inside one changeset so the merge
   appears as a single atomic event sequence

No `soft` kwarg. CLI `spkt neuron merge` routes here.

### 3.4 Read APIs

```python
async def events(
    self,
    *,
    since: float | None = None,
    target_id: str | None = None,
    limit: int = 1000,
) -> list[EventRow]: ...

async def predecessors_of_lineage(self, neuron_id: str) -> list[str]: ...
```

These are adapter-only. They do not appear in `spkt` output and
are not documented in the user-facing CLI manual. They exist so
the adapter can implement `Store.events()` and lineage queries
without reaching into `db.py` directly.

`EventRow` is a plain `msgspec.Struct` in `spikuit_core/models.py`
— not an AMKB type.

### 3.5 `spkt history prune`

New CLI command; core API `circuit.prune_retired(before: float)`.

```bash
spkt history prune --before 2026-01-01    # purge retired-before-date
spkt history prune --all                  # purge every retired row
spkt history prune --dry-run              # preview counts, no writes
```

Behavior:
- Hard-delete every `neuron` row with `retired_at < before` and
  every `synapse` row with `retired_at < before`
- Delete matching `neuron_predecessor` rows (child or parent
  physically gone)
- Delete matching `event` rows whose `target_id` is purged, to
  avoid dangling references
- Never touches live (`retired_at IS NULL`) rows
- Runs inside its own changeset with `actor_kind="system"`,
  `tag="prune"`; the prune itself emits no per-row events (it's
  garbage collection, not a protocol mutation)
- Requires confirmation at the CLI unless `--yes` is passed

Included in v0.7.0 scope so soft-retire has a physical escape
hatch from day one. Retention policy (auto-prune) stays out of
scope — operator-driven only.

## 4. Canonical exceptions

File: `spikuit-core/src/spikuit_core/errors.py` (may already exist
with `ReadOnlyError` — extend it).

```python
class SpikuitError(Exception): ...
class NotFoundError(SpikuitError): ...
class ConflictError(SpikuitError): ...       # version / optimistic concurrency
class InvariantError(SpikuitError): ...      # cross-layer, self-loop, empty content
class TransactionNestingError(SpikuitError): ...
class TransactionAbortedError(SpikuitError): ...
class ReadOnlyError(SpikuitError): ...       # existing, re-parented
```

The adapter maps these to `amkb.errors.*` codes at the boundary.
`spikuit-core` does not import `amkb.errors` — same one-way rule.

Mapping table (lives in the adapter, shown here for reference only):

| Spikuit | AMKB code |
|---|---|
| `NotFoundError` | `E_NOT_FOUND` |
| `ConflictError` | `E_CONFLICT` |
| `InvariantError` | `E_INVALID` (+ subcode from message) |
| `TransactionNestingError` | `E_INVALID` |
| `TransactionAbortedError` | `E_TX_ABORTED` |
| `ReadOnlyError` | `E_READONLY` |

## 5. Hot-path cost containment

The event log must not regress `fire` latency. Rules:

1. `fire` does not emit events for pressure/weight drift. Those
   are not AMKB-visible state — AMKB consumers see nodes and
   edges, not pressure scalars.
2. `fire`'s FSRS update (stability/difficulty/due) does not emit
   an event in v0.7.0. Rationale: FSRS numbers live in the
   `Node.attrs` dict from the adapter's point of view, and we
   have not yet decided whether attr drift should appear in the
   event stream. When we decide, it becomes a v0.7.2 addition.
3. STDP edge-weight updates do not emit `synapse.update` events.
   Same reason.

Net effect: `fire` appends **zero** event rows and spends only
the fixed cost of ensuring a one-op changeset row exists. A
micro-benchmark (added under `spikuit-core/tests/bench/`) must
show ≤5% overhead vs. v0.6.2 for 1000 sequential fires. If it
fails, the implicit wrapper is made lazy (insert `changeset` row
only when the first event would be emitted).

## 6. Test strategy

Goal: **every test passing on v0.6.2 must still pass, byte-identical, on the v0.7.0 branch.**

### 6.1 Regression guards

- `uv run --package spikuit-core pytest spikuit-core/tests/ -v`
  must be green at every commit in the v0.7.0 series, not just at
  the tip.
- `uv run --package spikuit-cli pytest spikuit-cli/tests/ -v`
  must be green — CLI output format, JSON shape, exit codes.
- Run `spkt` against a golden fixture Brain before/after each
  commit; diff `spkt stats --json`, `spkt neuron list --json`,
  `spkt retrieve "foo" --json`. Expected diff: empty.

### 6.2 New tests (v0.7.0 only)

Per addition:

1. **Soft-retire** — `test_retire_soft.py`: retire a neuron, confirm
   it disappears from `retrieve`, `list`, `due`, and from
   propagation; confirm the row still exists in the DB with
   `retired_at` set; confirm its synapses are cascade-retired.
2. **Event log** — `test_event_log.py`: wrap mutations in a
   transaction, assert the event rows exist in order, before/after
   snapshots round-trip via JSON, aborted transactions leave no
   committed rows.
3. **Transaction wrapper** — `test_transaction.py`: auto-commit
   path produces a single changeset per call; explicit block
   produces one changeset for N ops; exception inside block
   rolls back all row writes and marks status aborted; nested
   call raises `TransactionNestingError`.
4. **Predecessor** — `test_predecessor.py`: `merge_neurons(...,
   soft=True)` inserts lineage rows; `predecessors_of_lineage`
   returns them; `soft=False` (default) leaves the table empty so
   existing merge tests are unaffected.
5. **Errors** — `test_errors.py`: `NotFoundError`, `ConflictError`,
   `InvariantError` are raised in the documented cases; the legacy
   `ReadOnlyError` still derives from `SpikuitError`.
6. **Hot path benchmark** — `bench_fire.py`: 1000 fires on a
   fixture Brain, assert wall time within 5% of the v0.6.2
   baseline (checked in as JSON).

### 6.3 Adapter tests (v0.7.1, noted here for context)

The v0.7.1 PR adds `spikuit-agents/amkb/tests/` with
`test_conformance.py` that wires `SpikuitStore` into
`amkb.conformance`. Not in scope for this spec, but the design
above is what makes that test file trivial to write: every
AMKB primitive maps directly to a read API defined in §3-4.

## 7. Live-query discipline (mandatory)

Because soft-retire is the only delete path, **every** read path
in `spikuit-core` must exclude retired rows or we regress
behavior. This section is the audit checklist — a PR that
misses any of these is a bug.

### 7.1 Query fragment

Add to `spikuit_core/db.py`:

```python
# Canonical "live row" SQL fragments. Every SELECT on neuron /
# synapse that serves live behavior MUST use these.
LIVE_NEURON = "n.retired_at IS NULL"
LIVE_SYNAPSE = "s.retired_at IS NULL"
```

Every SELECT in `db.py` / `circuit.py` is audited to use one of
these fragments. Exceptions (event log reads, lineage reads,
`history prune`) are explicit and commented.

### 7.2 NetworkX graph construction

`propagation.py` builds a NetworkX DiGraph from `synapse` rows
before running APPNP. The SQL that feeds it MUST join with
`neuron` on both endpoints and apply `LIVE_NEURON` on both plus
`LIVE_SYNAPSE` on the edge. A retired neuron must not appear as
a node; a retired synapse must not appear as an edge.

Same rule for community detection — it consumes the same graph.

### 7.3 sqlite-vec

Because retire physically removes the vector row (§2.1), ANN
top-k results never contain retired neurons. No post-filter
needed. A unit test verifies this invariant by retiring N
neurons and asserting `retrieve` never returns them even at
large k.

### 7.4 FSRS due queue

`circuit.neuron_due()` joins `neuron` and must apply
`LIVE_NEURON`. Retired neurons never become due.

### 7.5 Content re-add

If a user adds a neuron with content identical to a retired
one, it is created as a fresh row with a new id. The retired
row is untouched. This is the resurrection non-goal expressed
concretely: no attempt is made to detect or reuse retired
content. Duplicate detection is a separate concern handled at
ingest time, not at retire boundary.

### 7.6 Stats

`spkt stats` adds two fields to the existing JSON output:

```json
{
  "neurons": 123,        // existing, now = live count
  "neurons_retired": 45, // new
  ...
}
```

This is the one deliberate break from v0.6.2 byte-identical
CLI output. The `neurons` field keeps its semantics
(user-visible knowledge count), and `neurons_retired` is purely
additive. `integration-plan.md` success criteria is updated to
reflect this.

## 8. Open questions

These are called out for review, not decided.

1. **FSRS current values on `Node.attrs`.** Plan: expose
   `fsrs_stability`, `fsrs_due`, `fsrs_difficulty`,
   `fsrs_last_review` as attrs in the v0.7.1 mapping layer. No
   eventing of drift. Confirmed direction; formalize in
   mapping.py design when v0.7.1 starts.
2. **Lineage for pre-v0.7.0 neurons.** No backfill. Empty
   ancestor set is the correct answer for neurons that predate
   this feature.
3. **Naming of `predecessors_of_lineage`.** Still ugly.
   Alternatives: `lineage_parents`, `merge_parents`. Kept the
   long name for now to avoid colliding with the existing
   graph-adjacency `predecessors()` used by APPNP.
4. **Prune confirmation UX.** `spkt history prune` asks for
   confirmation by default. Should `--yes` also be required for
   scripted adapters? Probably yes — prune is irreversible.

## 9. Review checklist

- [ ] No `amkb` import in `spikuit-core/` after this PR
- [ ] Every new column is nullable or has a default
- [ ] Every new table is additive (no FK changes to existing
      tables beyond the junction table)
- [ ] Every existing test in `spikuit-core/tests/` passes
      unchanged (CLI tests may need updating only for the new
      `neurons_retired` field in `spkt stats`)
- [ ] `spkt` CLI output diff against v0.6.2 golden fixtures is
      empty **except** for the two new additive fields in
      `spkt stats --json` (`neurons_retired`, any related
      counts). No other field changes semantics.
- [ ] `fire` hot path within 5% of v0.6.2 baseline
- [ ] `retrieve` recall@k unchanged vs v0.6.2 for a fixture
      with 0 retired nodes, and within noise for a fixture
      where 30% of nodes are retired
- [ ] Every SELECT on `neuron` / `synapse` in `circuit.py` /
      `db.py` / `propagation.py` uses `LIVE_NEURON` /
      `LIVE_SYNAPSE` fragments (grep-audited in CI)
- [ ] Migration is idempotent (runs twice with no error)
- [ ] Error classes mapped one-to-one in the adapter table (§4)

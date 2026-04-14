# spikuit-agents — AMKB adapter

Synchronous [AMKB Protocol] adapter backed by a Spikuit
`Circuit`. Lets any `amkb.Store`/`amkb.Transaction` consumer
(tests, tooling, cross-store federation) drive a real Spikuit
Brain without importing `spikuit-core` directly.

[AMKB Protocol]: https://github.com/takyone/amkb

```python
from amkb import Actor
from spikuit_agents.amkb import SpikuitStore
from spikuit_core import Circuit

circuit = Circuit(db_path="brain.db")
store = SpikuitStore.open(circuit)

# Reads (no transaction needed)
node = store.get_node(some_node_ref)
hits = store.retrieve("functor", k=5)

# Writes — always inside a transaction
actor = Actor(id="alice", kind="human")
with store.begin(tag="note", actor=actor) as tx:
    ref = tx.create(
        kind="concept",
        layer="L_concept",
        content="# Monad\n\nA monoid in the category of endofunctors.",
        attrs={"spk:type": "concept", "domain": "math"},
    )

store.close()
```

## Status — v0.7.1

**Conformance.** Passes the `amkb-sdk` conformance suite at
L1 (core), L2 (lineage), L4a (structural), and L4b (intent).
L3 (transactional capability matrix) is out of scope — see
[the design doc][design] §1.4.

| Level | Tests | Status |
|---|---|---|
| L1 — core | `create`, `retire`, `merge`, `link`, `unlink`, `history`, `abort` | ✅ |
| L2 — lineage | ancestor/descendant, diff, merge events | ✅ |
| L4a — structural | `get_node`, `get_edge`, `find_by_attr`, `neighbors` | ✅ |
| L4b — intent | `retrieve(intent)` with score monotonicity | ✅ |
| L3 — transactional | nested, resurrection, capability flags | ⏭️ deferred |

Run the suite locally from the repo root:

```bash
uv run --package spikuit-agents pytest spikuit-agents/tests/conformance/
```

[design]: https://github.com/takyone/spikuit/blob/main/docs/design/amkb-adapter-v0.7.1.md

## Capability flags

`SpikuitStore` advertises the following AMKB capabilities:

| Flag | Value | Why |
|---|---|---|
| `supports_merge_revert` | `False` | `revert` is L3. v0.7.1 raises `EConstraint`. |
| `supports_resurrection` | `False` | Soft-retire is terminal in Spikuit today. |
| `supports_nested_transactions` | `False` | `Circuit.transaction()` is single-level. |
| `supports_concurrent_writers` | `False` | Single-process, single-writer. aiosqlite serialises. |

## Architecture

```
amkb.Store ─────┐
amkb.Transaction┘
      │
      ▼
SpikuitStore (sync façade)
      │   owns an AsyncBridge with one asyncio loop
      ▼
Circuit (async, from spikuit-core)
      │
      ▼
aiosqlite + sqlite-vec
```

- **`store.py`** — `SpikuitStore`: read-side + session entry.
  Every Circuit call runs through `AsyncBridge`; every exception
  is translated at the boundary (`errors.boundary`).
- **`transaction.py`** — `SpikuitTransaction`: drives
  `Circuit.transaction()` (an `@asynccontextmanager`) manually
  via `__aenter__`/`__aexit__`. Abort uses a private
  `_AbortSignal(BaseException)` sentinel so the core context
  manager marks the changeset `status="aborted"` without
  surfacing the sentinel to callers.
- **`mapping.py`** — Neuron ↔ Node / Synapse ↔ Edge /
  Source ↔ Node codecs. Stable EdgeRef hashing over
  `(pre, post, type, created_at)`; junction EdgeRef over
  `(neuron_id, source_id)`.
- **`_events.py`** — event log → `amkb.Event` translator.
  Routes every row through the mapping codecs so the snapshot
  shape stays in one place.
- **`errors.py`** — `boundary()` contextmanager that translates
  typed `spikuit_core` exceptions into `amkb.AmkbError`
  subclasses. Unknown exceptions wrap in `EInternal`.
- **`_bridge.py`** — `AsyncBridge`: owns one
  `asyncio.new_event_loop()`; used by both `SpikuitStore` and
  `SpikuitTransaction` so every call hits the same loop.

## Mapping highlights

### Nodes

| Spikuit | AMKB |
|---|---|
| `Neuron` | `Node(kind="concept", layer="L_concept")` |
| `Source` | `Node(kind="source", layer="L_source")` |
| `neuron.retired_at` | `state="retired"` |
| `neuron.content` | `content` |
| `neuron.type` | `attrs["spk:type"]` |
| `neuron.domain` | `attrs["domain"]` |

### Edges

| Spikuit | AMKB rel |
|---|---|
| `SynapseType.REQUIRES` | `requires` |
| `SynapseType.EXTENDS` | `extends` |
| `SynapseType.CONTRASTS` | `contrasts` |
| `SynapseType.RELATES_TO` | `relates_to` |
| `neuron_source` junction | `derived_from` |
| `SynapseType.SUMMARIZES` | *(hidden — §4.3.A)* |

Currently `attested_by` and `contradicted_by` collapse onto the
same junction table as `derived_from`. A dedicated rel column
lands in v0.7.2+ (see design §9.2).

## Known gaps (v0.7.1)

Tracked in [design doc §9.2][design-gaps]. None block conformance;
daily-use work in v0.8.x picks them up.

- `synapse.id` stable column (EdgeRefs are currently hashes).
- `neuron_source.created_at` column (junction timestamps are
  synthesised from the concept neuron).
- `filterable`/`searchable`/`extractor` attribute publishing.
- Async Store protocol (`SpikuitAsyncStore`) — blocked on
  `amkb-sdk 0.2.0`.
- Arbitrary attr bag on `Neuron` (L4b `retrieve` test that
  filters on custom `attrs` is not exercised).

[design-gaps]: https://github.com/takyone/spikuit/blob/main/docs/design/amkb-adapter-v0.7.1.md#92-tracked-for-v072-or-daily-use

## Import discipline

`spikuit_agents.amkb` is the only place in the repo allowed to
`import amkb`. `spikuit-core` and `spikuit-cli` stay
protocol-ignorant. If a concept can only be expressed by reaching
back into `amkb.*` internals, it does not belong here — file an
`amkb-sdk` issue instead.

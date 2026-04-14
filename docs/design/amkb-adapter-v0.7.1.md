# AMKB Adapter — Spikuit v0.7.1

**Status.** Draft skeleton. Sections are stubs to be filled during
design review. Companion to `amkb-integration-plan.md` and
`amkb-core-plumbing-spec.md`. Defines the `spikuit-agents/amkb/`
package that lets Spikuit satisfy AMKB L1/L2/L3/L4a/L4b conformance
against `amkb-sdk >= 0.1.0`.

**Audience.** Reviewers of the v0.7.1 PR. Assumes the v0.7.0 core
plumbing (soft-retire, changeset/event log, `Circuit.transaction()`,
merge lineage, `history prune`) is already shipped.

**Ground rule.** The adapter is the only place allowed to import
`amkb.*`. `spikuit-core` and `spikuit-cli` stay protocol-ignorant.
Every mapping translates a Spikuit/neuroscience primitive into an
AMKB term; if a concept can only be expressed by reaching back into
`amkb.*` internals, it does not belong here.

**Release coupling.** v0.7.1 ships together with `amkb-sdk 0.1.0`.
Neither can be cut independently — the conformance suite lives in
the SDK and the adapter is the reference implementation.

---

## 1. Scope & Non-goals

### 1.1 In scope

- `spikuit_agents.amkb.Store` implementing `amkb.Store` Protocol.
- `spikuit_agents.amkb.Transaction` implementing `amkb.Transaction`
  Protocol, wrapping `Circuit.transaction()`.
- Mapping modules (`mapping.py`) for Neuron↔Node and Synapse↔Edge.
- Error translation (`errors.py`) from `spikuit_core` exceptions to
  AMKB canonical error codes.
- Conformance wiring: `conftest.py` that injects a Spikuit-backed
  `store` fixture into `amkb.conformance` L1 / L2 / L4a / L4b.
- `spikuit-agents` gains a hard dependency on `amkb>=0.1.0`.

### 1.2 Targeted conformance levels

| Level | Name | v0.7.1 | Notes |
|---|---|---|---|
| L1 | Core (create/retire/merge/link/unlink/history/revert/abort) | ✅ yes | Full pass required. Backed directly by v0.7.0 plumbing. |
| L2 | Lineage (ancestry / descendant traversal) | ✅ yes | Backed by `Circuit.predecessors_of_lineage()`. |
| L3 | Transactional (capability flags, nested semantics, resurrection) | ❌ **deferred** | See §1.4. |
| L4a | Structural (`get`, `find_by_attr`, `neighbors`) | ✅ yes | Straight read path. |
| L4b | Intent (`retrieve(intent)`) | ✅ yes | Backed by `Circuit.retrieve()`. Hit result shape decided in §7. |

### 1.3 Out of scope

The following are explicit non-goals for v0.7.1. They neither get
implemented nor get stub implementations that raise `NotImplemented`
in a user-visible way; they simply do not appear in the adapter
surface.

- Any change to `spikuit-core` or its public API. If a gap surfaces
  during adapter implementation, it is logged in §9 and pushed to a
  future v0.7.x point release, not fixed inside this PR.
- New `spkt` CLI subcommands. The CLI keeps its current surface.
- Revisions to `amkb-spec` (v0.2.0 is frozen for this release cycle).
- Additions to the SDK's conformance suite beyond what amkb-sdk
  0.1.0 already ships.

### 1.4 Deferred (tracked, not forgotten)

Not implemented in v0.7.1, but **recorded here so the next planning
pass picks them up**. Each item lists the reason for deferral and
the earliest version where it can reasonably land.

| Item | Reason deferred | Earliest target |
|---|---|---|
| **L3 Transactional conformance** | `Circuit.transaction()` exists but the full L3 suite exercises nested / resurrection / capability-matrix behavior that Spikuit does not use in daily operation. Advertising partial L3 risks shipping a subtly-wrong contract. | v0.7.2 or later, once daily use surfaces a concrete need. |
| **Resurrection of retired neurons** | Spikuit treats soft-retire as terminal. No current use case. AMKB spec allows implementations to opt out via L3 capability flag. | Revisit only if a real workflow demands it. |
| **Multi-process / concurrent transaction safety** | Spikuit today targets single-process, single-Brain, single-writer. SQLite + aiosqlite already serialize writes. Adding multi-writer semantics here would bloat v0.7.1 by an order of magnitude. | No fixed target. Reopens if a daemon / server mode is planned. |
| **Sync-over-async wrapper hardening** | v0.7.1 uses the minimum wrapper needed to expose Circuit's async API through the SDK Protocol. Edge cases (signal handling, cancellation, loop ownership) are not audited. | v0.7.2 if conformance reveals flakes; otherwise during v0.8.x daily use. |
| **Adapter-side caching / read-through** | No premature optimization. Retrieval and get calls hit `Circuit` directly every time. | Revisit if profiling shows a hot path. |

Each deferred item is cross-referenced from §9 so the implementation
PR does not silently drop them.

### 1.5 Guarantees the v0.7.1 adapter makes

- Single process. Single Brain. Single writer at a time.
- Sync façade over Circuit's async API, implemented with a
  minimal bridge (details in §5).
- Conformance: L1 + L2 + L4a + L4b pass against `amkb-sdk 0.1.0`.
- No `amkb.*` imports leak into `spikuit-core` or `spikuit-cli`.
- Error translation is total for every exception `spikuit-core`
  raises today; future new exceptions require a translation table
  update before release.

## 2. Package Layout

### 2.1 Directory tree

The adapter lives entirely under `spikuit-agents/`. `spikuit-core`
and `spikuit-cli` are untouched.

```
spikuit-agents/
├── pyproject.toml
├── src/spikuit_agents/
│   ├── __init__.py
│   ├── tutor/                    # existing, untouched
│   └── amkb/                     # new
│       ├── __init__.py
│       ├── store.py              # SpikuitStore(amkb.Store)
│       ├── transaction.py        # SpikuitTransaction(amkb.Transaction)
│       ├── mapping.py            # Neuron↔Node, Synapse↔Edge codecs
│       ├── errors.py             # exception → AMKB error translation
│       └── _bridge.py            # sync/async bridge helper (see §5)
└── tests/
    ├── test_agent_grader.py      # existing
    ├── conftest.py               # new — top-level fixtures shared across tests
    └── amkb/                     # new — adapter-specific tests
        ├── __init__.py
        ├── test_mapping.py       # unit tests for mapping round-trips
        ├── test_errors.py        # unit tests for error translation
        ├── test_store.py         # smoke tests for SpikuitStore beyond conformance
        └── test_conformance.py   # driver that runs amkb.conformance L1/L2/L4a/L4b
```

Rationale:

- **Tests live under `spikuit-agents/tests/amkb/`**, not co-located
  with source. This matches the existing `tests/test_agent_grader.py`
  layout and keeps the package tree build-clean (`hatchling` only
  packages `src/spikuit_agents`).
- `_bridge.py` is prefixed with `_` to signal it is private to the
  adapter. Nothing outside `spikuit_agents.amkb` imports from it.
- Separate `test_store.py` exists alongside `test_conformance.py`
  because conformance is black-box contract testing; unit tests
  still have value for Spikuit-specific edge cases (e.g. retired
  neuron visibility, FSRS attr round-trip).

### 2.2 `pyproject.toml` delta

```toml
[project]
name = "spikuit-agents"
version = "0.7.1"            # bump from 0.7.0
dependencies = [
    "spikuit-core",
    "spikuit-cli",
    "amkb>=0.1.0,<0.2.0",    # new — upper bound locks against SDK breaks
]
```

- Upper bound `<0.2.0` follows the assumption that AMKB 0.x minors
  are allowed to be breaking until 1.0.0. Revisit at AMKB 1.0.0.
- No new dev dependencies; `pytest` / `pytest-asyncio` already come
  from the workspace root.

### 2.3 Public re-exports

`src/spikuit_agents/amkb/__init__.py` exports the minimal surface a
downstream user needs to wire Spikuit into AMKB tooling.

```python
from spikuit_agents.amkb.store import SpikuitStore
from spikuit_agents.amkb.transaction import SpikuitTransaction

__all__ = ["SpikuitStore", "SpikuitTransaction"]
```

Not re-exported (kept implementation-private):
- `mapping.py` internals — callers must go through `SpikuitStore`.
- `errors.py` — the SDK's canonical exceptions are raised instead.
- `_bridge.py` — private by prefix convention.

### 2.4 Import discipline

- `spikuit_agents.amkb.*` is **the only place** in the entire
  monorepo allowed to `import amkb`. A CI check (ripgrep one-liner,
  or a small pytest-importchecker) enforces this.
- `spikuit_agents.amkb.*` imports from `spikuit_core.*` and
  `spikuit_cli.*` (for CLI-facing helpers, if any) but never the
  other way around.
- `spikuit_agents.tutor.*` is independent and MUST NOT import from
  `spikuit_agents.amkb.*` in v0.7.1. A future session layer may
  choose to talk to Spikuit through the AMKB adapter instead of
  `Circuit` directly, but that is out of scope here (§1.3).

### 2.5 Conformance fixture discovery (brief)

Conformance tests live in the installed `amkb.conformance` package
and expect a `store` fixture. How that fixture is discovered
(root `conftest.py` vs pytest plugin entry-point vs explicit
parametrization in `test_conformance.py`) is a §7 decision. For
the purpose of §2 it is enough that the fixture provider lives
somewhere under `spikuit-agents/tests/` and does not leak into
the packaged wheel.

## 3. Mapping: Spikuit Nodes ↔ AMKB Node

### 3.1 Scope of this section

Spikuit has two entity types that surface as AMKB `Node` values:

- **`Neuron`** (`spikuit-core/src/spikuit_core/models.py:78`) →
  `kind="concept"`, `layer="L_concept"` (§3.2–§3.4).
- **`Source`** (`spikuit-core/src/spikuit_core/models.py:397`) →
  `kind="source"`, `layer="L_source"` (§3.5).

Both follow the same soft-retire rules (§3.6). Open questions
that surface from this section are logged in §3.7.

Every field-level translation in this section is **decided** —
§3.3 records the rationale for the non-obvious choices. §3.5
contains a small set of Source-specific decisions that are
defaulted but marked as reviewable.

### 3.2 Neuron: mechanical mappings

| Spikuit `Neuron` field | AMKB `Node` location | Notes |
|---|---|---|
| `id: str` (`n-<hex12>`) | `ref: NodeRef` | `ref` is opaque per spec §2.1. Adapter wraps the raw id as a `NodeRef`; the format stays internal. |
| `content: str` | `content: str` | Spec §2.2.5 requires non-empty content for live concept nodes — Spikuit already guarantees this. Frontmatter handling: see §3.3.A. |
| `domain: str \| None` | `attrs["domain"]: str` | Reserved key per spec §2.2.7. Only present when non-null. |
| `created_at: datetime` | `created_at: Timestamp` | Direct copy. |
| `updated_at: datetime` | `updated_at: Timestamp` | Direct copy. |
| `retired_at: datetime \| None` (DB column, not in msgspec) | `retired_at: Timestamp \| None` + `state` | `state = "retired"` iff `retired_at` is not null. Soft-retire is the sole delete path. Retired neurons remain resolvable by `ref` but are filtered out of live queries and retrieval (spec §2.2.8, §2.2.9). |
| Embedding vector (sqlite-vec) | **not surfaced in `attrs`** | Spec §2.7 forbids relevance-estimation state under canonical attrs. Kept entirely inside `Circuit` and its retrieval layer. |
| `pressure`, community assignment, propagation state (DB-side) | **not surfaced** | Internal to `Circuit`. Never published through the adapter. |

### 3.3 Neuron: decisions (resolved)

Five non-obvious Neuron mapping choices were resolved during design
review. Each is recorded here with the chosen option, the rationale,
and (where relevant) the alternatives considered and rejected.

#### 3.3.A Content and hash — decided: raw publish, stripped hash

- **`Node.content`**: publish Spikuit's raw Markdown verbatim,
  frontmatter included. Preserves authoring intent and round-trips
  losslessly.
- **`content_hash` in events**: when `Node.content` changes, the
  event's `content_hash` (spec §2.6.5) is computed over
  `strip_frontmatter(content)` — the exact string Spikuit feeds
  into its embedder (`models.py:478`).
- **Why**: keeps the externally-visible contract ("a changed
  `content_hash` implies stale embedding") accurate. Hashing the
  raw form would flag frontmatter-only edits as stale even though
  Spikuit's embedding does not move.
- **1.0.0-bound**: the definition of "what is hashed" is part of
  the public event contract. Frozen at AMKB 1.0.0.
- **Rejected alternatives**: hashing raw content (breaks staleness
  contract); publishing stripped content (lossy for authoring
  intent, round-trip loses frontmatter).

#### 3.3.B Kind and layer — decided: uniform `concept` / `L_concept`

- Every Spikuit Neuron becomes `kind="concept"`, `layer="L_concept"`.
- The original `Neuron.type` goes into `attrs["spk:type"]` when
  non-null.
- **Why**: matches AMKB's semantic definition of `concept` (atomic
  knowledge unit), preserves retrieval-space semantics (spec §2.2.9),
  and uses `find_by_attr("spk:type", ...)` for type-level filtering.
- **Forward-compat**: the v0.8.x daily-use phase is planned to
  promote Spikuit Communities to `kind="category"` Nodes. Concepts
  stay concepts; categories are added alongside as a new kind.
  This is the same plan that §4.3.A relies on for activating
  `SUMMARIZES → contains` — see §4.6.
- **1.0.0-bound**: the "uniform concept kind for Neurons" decision
  is frozen. Spikuit will not introduce `ext:*` kinds for Neuron
  types post-1.0.0.
- **Rejected alternatives**: per-type `ext:*` kinds would require
  inventing per-type layers (spec §2.2.3) or conflating ext kinds
  with `L_concept`; both messy.

#### 3.3.C Source exposure — decided: Sources are first-class Nodes

- v0.7.1 exposes Spikuit `Source` as AMKB Nodes with `kind="source"`,
  `layer="L_source"`. Full mapping in §3.5.
- Concept→Source attestation uses the reserved `derived_from` edge
  (covered in §4).
- **Why**: without Sources in the AMKB view, attestation lineage
  is invisible to downstream tools, which is a core AMKB promise.
  Shipping Source exposure in v0.7.1 means the first release has a
  complete concept-attestation loop.
- **Rejected alternative**: defer Sources to v0.7.2 — would leave
  `L_source` empty in the first release and block derivation
  lineage.

#### 3.3.D Scheduler attributes — decided: semantic, FSRS-agnostic

FSRS is treated as a private implementation of a scheduler,
mirroring how spec §2.7 treats retrieval (embeddings / similarity)
as implementation-opaque. The AMKB surface publishes only
scheduler-agnostic role information.

**Published (attrs on every Neuron Node):**

| Attribute | Type | Role |
|---|---|---|
| `spk:last_reviewed_at` | Timestamp \| null | When the neuron was last fired (any scheduler). |
| `spk:due_at` | Timestamp \| null | When the scheduler thinks it is next due (any scheduler). |

**Not published:**

- FSRS `stability`, `difficulty` — implementation-specific
  parameters. A future switch to SM-2 / Leitner / custom scheduler
  would need different internal state, and we do not want to leak
  FSRS terminology into the AMKB contract.
- LIF `pressure`, APPNP propagation state, STDP co-fire counters —
  internal to Spikuit's learning dynamics.

- **Why**: `spk:due_at` and `spk:last_reviewed_at` are universal
  scheduler concepts that hold regardless of implementation. If
  Spikuit later gains a second scheduler, the public attrs do not
  need to change.
- **1.0.0-bound**: `spk:due_at` and `spk:last_reviewed_at` are
  frozen at AMKB 1.0.0.
- **Deferred to §3.7**: publishing an opaque
  `spk:scheduler_kind: "fsrs"` tag for diagnostics — nice-to-have,
  not load-bearing.
- **Rejected alternatives**: publishing four FSRS-specific attrs
  (`spk:fsrs_*`) leaks implementation into the public surface;
  publishing under `ext:` prefix understates that Spikuit is the
  reference implementation.

#### 3.3.E `Neuron.source` field — decided: drop from adapter

- The adapter does not publish `Neuron.source` at all. No
  `spk:source_ref` attribute.
- **Why**: `Neuron.source` is a pre-Source-table legacy field.
  Publishing it would freeze legacy behavior into the AMKB surface
  and force perpetual maintenance of a field Spikuit wants to
  deprecate. Since daily use has not started, no meaningful data
  is at stake.
- **Core field lifecycle (§3.7)**: removing `Neuron.source` from
  `spikuit-core` is out of v0.7.1 scope per §1.3, but logged as a
  candidate for v0.7.2 or later. The adapter silently ignoring the
  field creates no dependency either way.
- **Rejected alternatives**: publishing as `spk:source_ref` (locks
  legacy into the public surface); publishing as deprecated
  read-only attr (adds complexity for data that does not exist).

### 3.4 Neuron → Node: final mapping table

| Source (Spikuit Neuron) | Target (AMKB Node) | Frozen at 1.0.0? |
|---|---|---|
| `id` | `ref` (opaque NodeRef) | — (format internal) |
| `content` (raw, frontmatter included) | `content` | — |
| hash of `strip_frontmatter(content)` | `content_hash` in events | ✅ yes |
| `type` (non-null) | `attrs["spk:type"]` | ✅ yes |
| `domain` (non-null) | `attrs["domain"]` (spec-reserved) | ✅ spec-reserved |
| `source` (legacy free text) | — (dropped, see §3.3.E) | — |
| `created_at` | `created_at` | — |
| `updated_at` | `updated_at` | — |
| `retired_at` (DB column) | `retired_at` + `state` | — |
| uniform | `kind="concept"` | ✅ yes |
| uniform | `layer="L_concept"` | ✅ yes |
| DB: last fire time | `attrs["spk:last_reviewed_at"]` | ✅ yes |
| DB: next due time | `attrs["spk:due_at"]` | ✅ yes |
| FSRS stability / difficulty | — (private) | — |
| LIF pressure, STDP, APPNP state | — (private) | — |
| embedding vector | — (private, spec §2.7) | — |

### 3.5 Source ↔ Node

#### 3.5.1 Overview

Spikuit `Source` (`models.py:397`) is a distinct entity with a 1:N
relationship to Neurons via the source-junction table. It represents
an external attestation artifact (URL, file, snapshot). AMKB
`kind="source"` Nodes cover the same role.

The adapter surfaces Sources as `kind="source"`, `layer="L_source"`
Nodes. Concept→Source edges use the reserved `derived_from` relation
(§4 covers the edge side).

#### 3.5.2 Mechanical mappings

Fields that translate without judgment:

| Spikuit `Source` field | AMKB `Node` location | Notes |
|---|---|---|
| `id: str` (`s-<hex12>`) | `ref: NodeRef` | Opaque per spec §2.1. |
| `content_hash` | `attrs["content_hash"]` | Reserved key (spec §2.2.7). |
| `fetched_at` | `attrs["fetched_at"]` | Reserved key. |
| `created_at` | `created_at` | Direct copy. |
| `retired_at` (DB column, from v0.7.0 plumbing) | `retired_at` + `state` | Same soft-retire rules as Neurons — see §3.6. |
| uniform | `kind="source"` | Required for L_source pairing (spec §2.2.4). |
| uniform | `layer="L_source"` | — |

#### 3.5.3 Source-specific decisions (defaulted, open to review)

These decisions are smaller in blast radius than §3.3 and can be
adjusted without reshaping the v0.7.1 design. Defaults are listed
below; flag any for review during design sign-off.

**S1: `Node.content` for Sources.** AMKB spec §2.2.5 allows
`kind="source"` content to carry either inline text or an external
reference. Spikuit Sources have `title`, `url`, and `excerpt` but no
long-form body.

- **Default**: `content = title` when present, falling back to `url`,
  falling back to `"Untitled source"`. A short human-readable label.
  The full pointer lives in `attrs["content_ref"]` (see S2).
- **Why**: gives debugging / display tools something to render
  without shoving a full URL into `content`.

**S2: `content_ref` pointer selection.** Both `url` and `storage_uri`
can point at original content.

- **Default**: `attrs["content_ref"]` = `url` when present, otherwise
  `storage_uri`. When both exist and differ, `storage_uri` goes into
  `attrs["spk:storage_uri"]` (see S3).
- **Why**: `url` is the canonical upstream identity; `storage_uri` is
  a local cache reference.

**S3: Spikuit-specific metadata.** `title`, `author`, `section`,
`excerpt`, `notes`, `status`, `http_etag`, `http_last_modified`,
`accessed_at`, `storage_uri` have no reserved AMKB keys.

- **Default**: publish each under the `spk:` prefix when non-null:
  `spk:title`, `spk:author`, `spk:section`, `spk:excerpt`,
  `spk:notes`, `spk:status`, `spk:http_etag`,
  `spk:http_last_modified`, `spk:accessed_at`, `spk:storage_uri`.
- **1.0.0-bound**: each name is part of the public surface and
  frozen at AMKB 1.0.0.

**S4: `filterable` / `searchable` nested dicts.** Spikuit stores
arbitrary user-level key-value metadata in two nested dicts —
`filterable` (strict match) and `searchable` (soft embedding-input).

- **Default**: not published in v0.7.1. Logged as §3.7 item.
- **Why defer**: user-level metadata is not blocking any conformance
  level; nested-dict attrs add 1.0.0-freeze surface and
  `searchable` interacts with §3.3.A embedding semantics.

**S5: Reserved `extractor` attr.** Spec §2.2.7 reserves
`attrs["extractor"]` (extractor name/version used at ingest).
Spikuit does not currently track extractor identity per Source.

- **Default**: `extractor` attr is omitted from v0.7.1.
- **§3.7**: plumb extractor identity through ingest so this can be
  populated in a later version.

#### 3.5.4 Source → Node: final mapping table

| Source (Spikuit Source) | Target (AMKB Node) | Frozen at 1.0.0? |
|---|---|---|
| `id` | `ref` | — |
| `title` / `url` / `"Untitled source"` (fallback chain) | `content` | ✅ yes (fallback order) |
| `url` or (if null) `storage_uri` | `attrs["content_ref"]` (spec-reserved) | ✅ spec-reserved |
| `content_hash` | `attrs["content_hash"]` (spec-reserved) | ✅ spec-reserved |
| `fetched_at` | `attrs["fetched_at"]` (spec-reserved) | ✅ spec-reserved |
| `title` | `attrs["spk:title"]` | ✅ yes |
| `author` | `attrs["spk:author"]` | ✅ yes |
| `section` | `attrs["spk:section"]` | ✅ yes |
| `excerpt` | `attrs["spk:excerpt"]` | ✅ yes |
| `notes` | `attrs["spk:notes"]` | ✅ yes |
| `status` | `attrs["spk:status"]` | ✅ yes |
| `http_etag` | `attrs["spk:http_etag"]` | ✅ yes |
| `http_last_modified` | `attrs["spk:http_last_modified"]` | ✅ yes |
| `accessed_at` | `attrs["spk:accessed_at"]` | ✅ yes |
| `storage_uri` (when distinct from `url`) | `attrs["spk:storage_uri"]` | ✅ yes |
| `created_at` | `created_at` | — |
| `retired_at` | `retired_at` + `state` | — |
| `filterable` | — (deferred, §3.7) | — |
| `searchable` | — (deferred, §3.7) | — |
| `extractor` identity | — (Spikuit does not track, §3.7) | — |
| uniform | `kind="source"`, `layer="L_source"` | ✅ yes |

### 3.6 Retired Nodes: uniform handling

Both Neuron and Source use the v0.7.0 soft-retire plumbing. The
adapter rules are identical for both kinds:

- A retired Node has `state = "retired"` and `retired_at` populated.
- Retired Nodes MUST remain resolvable via `ref` (spec §2.2.8).
- Retired Nodes MUST NOT appear in live retrieval or in live
  `find_by_attr` results (spec §2.2.9).
- Retired Nodes remain visible to lineage traversal (spec §2.2.8).

`Circuit`'s `_live_neurons_sql` fragment filters retired rows at
query time. The adapter's `get(ref)` path needs a bypass so that
lookup by a specific `ref` returns the tombstoned entity even when
retired. This is a §5 Store implementation concern and surfaces
from §3 only because it is forced by the `retired_at` / `state`
translation.

### 3.7 Open questions for §9

Items that cannot be resolved inside §3 and are logged for §9:

- **Retired-node resolve-by-ref bypass.** `get(ref)` must read
  retired rows without using the `_live_neurons_sql` fragment.
  §5 implementation detail.
- **`filterable` / `searchable` attribute publishing.** Spikuit
  Source carries user-level metadata dicts that v0.7.1 does not
  publish. Revisit in v0.7.2+.
- **Extractor identity tracking.** `attrs["extractor"]` is a
  reserved AMKB key but Spikuit does not currently record
  extractor name/version per Source. Aligned with the planned
  v0.8.x "daily use + extractor expansion" phase: once
  `Source.extractor` is added to core and populated by
  `spkt source ingest`, the adapter picks it up with a one-line
  mapping change.
- **`Neuron.source` core field removal.** The adapter already
  drops the field. Removing it from `spikuit-core` is a separate
  point release in v0.7.2+ under §1.3's out-of-scope rule.
- **Diagnostic `spk:scheduler_kind` tag.** Nice-to-have opaque
  attribute identifying which scheduler is active (currently
  always `"fsrs"`). Not blocking.

## 4. Mapping: Spikuit Edges ↔ AMKB Edge

### 4.1 Scope

The adapter publishes two kinds of AMKB Edge, drawn from two
different Spikuit tables:

- **Intra-concept edges** from the `synapse` table
  (`models.py:140`). Cover `requires`, `extends`, `contrasts`,
  `relates_to`. Spikuit's `SUMMARIZES` is **hidden** in v0.7.1
  (see §4.3.A). See §4.2–§4.4.
- **Concept→Source attestation edges** from the `neuron_source`
  junction table (`db.py:111`). Rendered as `derived_from` edges.
  See §4.5.

The adapter treats both as first-class edges in the AMKB surface.
Consumers iterating edges via the Store Protocol see one unified
stream. Decisions are either mechanical (forced by spec + Spikuit
shape) or small enough to be decided inline with a brief rationale;
no options-tables this section.

### 4.2 Synapse: mechanical mappings

| Spikuit `Synapse` field | AMKB `Edge` location | Notes |
|---|---|---|
| `pre: str` | `src: NodeRef` | Concept Node ref. |
| `post: str` | `dst: NodeRef` | Concept Node ref. |
| `created_at: datetime` | `created_at: Timestamp` | Direct copy. |
| `updated_at: datetime` | — (AMKB Edge has no `updated_at`) | STDP updates to weight do not bump Edge updated_at on the AMKB surface; events still cover the mutation. |
| `retired_at` (DB column, v0.7.0 plumbing) | `retired_at` + `state` | Soft-retire rules match §3.6. Edge retirement cascades from Node retirement (spec §2.3.5). |
| (synthetic) `ref: EdgeRef` | `ref: EdgeRef` | Spikuit has no stable Edge id today — see §4.4.A. |

### 4.3 Synapse: decisions

#### 4.3.A Rel type mapping — decided

| `SynapseType` | AMKB `rel` | Notes |
|---|---|---|
| `REQUIRES` | `requires` (reserved) | Directed, spec §2.3.2. |
| `EXTENDS` | `extends` (reserved) | Directed. |
| `CONTRASTS` | `contrasts` (reserved) | Symmetric in meaning; see §4.3.B for storage. |
| `RELATES_TO` | `relates_to` (reserved) | Symmetric in meaning; see §4.3.B. |
| `SUMMARIZES` | **(hidden in v0.7.1)** | See below. |

- **Why the four reserved mappings are direct**: each Spikuit type
  has an identical-meaning AMKB reserved rel. Mechanical.
- **Why `SUMMARIZES` is hidden**: AMKB's closest reserved rel is
  `contains` (`L_category` → `L_concept`), but Spikuit's
  `SUMMARIZES` today connects two concept-layer neurons (a
  Community summary neuron to its member neurons), not a
  category-layer node. Publishing as `contains` would lie about
  the layer pairing. Publishing as `ext:summarizes` would create a
  provisional name that we'd need to rename at the moment
  Communities become `kind="category"` Nodes — either an AMKB
  protocol-level rename or a Spikuit-side migration emitting
  retire+add events for every existing summary edge. Neither is
  free, and pre-release is exactly when we should avoid creating
  future migration debt.
- **Decision**: the adapter **filters out** `SynapseType.SUMMARIZES`
  rows from the edge stream in v0.7.1. They remain in Spikuit's
  database untouched, continue to drive APPNP propagation and
  retrieval, and simply don't appear on the AMKB surface.
- **Forward-compat plan (aligned with §3.3.B)**: the daily-use
  phase (v0.8.x) promotes Spikuit Communities to `kind="category"`
  Nodes. At that point `SUMMARIZES` is re-enabled in the adapter,
  mapped directly to the reserved `contains` rel
  (`L_category` → `L_concept`) — no rename, no provisional name,
  clean migration. Existing summary edges surface via a one-time
  backfill of `contains` edges emitted against the event log.
- **1.0.0-bound**: the four reserved mappings are frozen. No
  provisional ext: rel is committed to. §4.6 tracks the v0.8.x
  activation.

#### 4.3.B Directionality and bidirectional storage — decided

Spikuit stores symmetric synapses (`CONTRASTS`, `RELATES_TO`) as
**two directed rows**, one per direction, possibly with asymmetric
weights. The adapter publishes them as **two AMKB Edges**, one per
row. Consumers that want symmetric interpretation deduplicate at
their end; the adapter makes no attempt to fold them.

- **Why**: lossless round-trip. AMKB spec §2.3.4 allows multiple
  edges between the same pair with the same rel, so this is
  spec-legal. Folding to a single edge would force the adapter to
  pick one weight (averaging? max? leaves round-trip broken).
- **Consumer impact**: a reader iterating edges sees two
  `contrasts` edges between A and B, with potentially different
  `spk:weight` values. This is the accurate picture of Spikuit's
  internal state.

#### 4.3.C Weight and STDP state — decided: semantic, STDP-agnostic

Mirroring §3.3.D (scheduler-agnostic neuron state), STDP is treated
as a private plasticity rule. Only the universal concept
"connection strength" surfaces.

**Published (attrs on every Synapse-derived Edge):**

| Attribute | Type | Role |
|---|---|---|
| `spk:weight` | float (range: `[weight_floor, weight_ceiling]`) | Connection strength. Universal concept — any edge-based KB has one. |

**Not published:**

- `co_fires` (STDP co-fire counter)
- `last_co_fire` (STDP timing bookkeeping)
- Plasticity parameters (`tau_stdp`, `a_plus`, `a_minus`, etc.)
  — these live on the Circuit, not per-edge, and are
  implementation-specific.

- **Why**: if Spikuit later adopts a different plasticity rule
  (symmetric Hebbian, BCM, oja), the public weight concept still
  holds. STDP-specific bookkeeping would leak into the AMKB
  contract and force renames at AMKB 1.0.0.
- **1.0.0-bound**: `spk:weight` name frozen at AMKB 1.0.0.

#### 4.3.D Confidence publication — decided

Spikuit's `SynapseConfidence` enum (EXTRACTED / INFERRED / AMBIGUOUS)
and `confidence_score` float capture how the synapse came into
being. They are not redundant with AMKB Actor attribution: an `llm`
Actor can create an `EXTRACTED` synapse during ingest and a later
consolidation pass can downgrade it to `INFERRED` or flag it
`AMBIGUOUS` for review.

**Published (attrs on every Synapse-derived Edge):**

| Attribute | Type | Role |
|---|---|---|
| `spk:confidence` | `"extracted" \| "inferred" \| "ambiguous"` | Provenance class. |
| `spk:confidence_score` | float | Numeric confidence, [0.0, 1.0]. |

- **1.0.0-bound**: both names frozen at AMKB 1.0.0.

### 4.4 Synapse → Edge: final mapping table

| Source (Spikuit Synapse) | Target (AMKB Edge) | Frozen at 1.0.0? |
|---|---|---|
| synthesized from (pre, post, type, created_at) | `ref` | see §4.4.A |
| `pre` | `src` | — |
| `post` | `dst` | — |
| `type` | `rel` (see §4.3.A); `SUMMARIZES` rows filtered out | ✅ four reserved mappings frozen |
| `weight` | `attrs["spk:weight"]` | ✅ yes |
| `confidence` | `attrs["spk:confidence"]` | ✅ yes |
| `confidence_score` | `attrs["spk:confidence_score"]` | ✅ yes |
| `co_fires` | — (private) | — |
| `last_co_fire` | — (private) | — |
| `created_at` | `created_at` | — |
| `retired_at` (DB column) | `retired_at` + `state` | — |

#### 4.4.A EdgeRef synthesis — §9 item

Spikuit's `synapse` table does not today have a stable primary key.
Identity is `(pre, post, type)` (composite). AMKB's `EdgeRef` is
opaque and MUST remain valid for the lifetime of the Edge
(spec §2.1), including across STDP weight updates. The adapter
therefore synthesizes an `EdgeRef` from the composite key:
`ref = f"e-{hash(pre, post, type)}"` or similar, deterministic.

- This is stable as long as the composite key is stable.
- It breaks if a synapse is retired and a new one with the same
  (pre, post, type) is later created — the new one would collide.
- §9 item: add a stable `synapse.id` column in v0.7.2+ to make
  EdgeRef synthesis trivial and collision-free.

### 4.5 Concept→Source edges (`neuron_source` junction)

The `neuron_source` junction table (`db.py:111`) is a minimal M:N
link between neurons and sources:

```sql
CREATE TABLE neuron_source (
    neuron_id TEXT NOT NULL REFERENCES neuron(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES source(id) ON DELETE CASCADE,
    PRIMARY KEY (neuron_id, source_id)
);
```

It carries no metadata beyond the pairing. The adapter renders each
row as an AMKB Edge:

| AMKB Edge field | Value |
|---|---|
| `rel` | `derived_from` (reserved, spec §2.3.2) |
| `src` | concept Node ref (`neuron_id`) |
| `dst` | source Node ref (`source_id`) |
| `attrs` | `{}` (junction carries no metadata) |
| `created_at` | Not stored in junction — **synthesized from concept Neuron's `created_at`**. §9 item. |
| `state` | Derived from endpoint state — when either endpoint is retired, the link is effectively retired. |
| `ref` | Synthesized from `(neuron_id, source_id)`. |

#### 4.5.A Why `derived_from` and not `attested_by` or `contradicted_by`

AMKB spec §2.3.2 offers three concept→source rels:

| `rel` | Meaning |
|---|---|
| `derived_from` | Concept was **extracted** from the source. |
| `attested_by` | Source **independently supports** the concept (corroboration). |
| `contradicted_by` | Source **contradicts** the concept (disputed). |

Spikuit's `neuron_source` junction represents "this neuron was
ingested from this source" — that is **derivation**, not
independent corroboration or contradiction. `derived_from` is the
only correct mapping.

- **1.0.0-bound**: frozen.
- **Forward-compat**: if Spikuit later adds an explicit
  "this source corroborates this neuron" link (e.g., via the
  `SynapseConfidence` pipeline), that would use `attested_by`.
  Not in v0.7.1 scope.

#### 4.5.B Cascade-retire implication

Spikuit's `neuron_source` uses `ON DELETE CASCADE` at the SQL level.
This is for hard-delete paths that no longer exist post-v0.7.0
(soft-retire is the sole delete path). The cascade is effectively
dead code in normal operation, but remains for `spkt history prune`
which physically removes tombstoned rows.

When a Neuron is soft-retired:
- The `neuron_source` row is NOT deleted (soft-retire does not
  trigger the CASCADE).
- The adapter MUST hide the corresponding `derived_from` edge from
  live queries (spec §2.3.5: retiring a Node retires its edges).
- Lineage / history paths still see it.

This is a §5 Store implementation concern and is logged in §4.6.

### 4.6 Open questions for §9

- **EdgeRef stability (§4.4.A).** Spikuit needs a stable
  `synapse.id` column to make EdgeRef synthesis robust. v0.7.2+
  additive migration.
- **`created_at` for junction-derived edges (§4.5).** Junction
  rows have no timestamp. Adapter currently synthesizes from
  endpoint Neuron's `created_at`. Consider adding a
  `neuron_source.created_at` column in v0.7.2+.
- **`SUMMARIZES` activation in v0.8.x.** Currently hidden from the
  adapter (§4.3.A). When daily-use phase promotes Communities to
  `kind="category"` Nodes (§3.3.B), re-enable the mapping as
  `SUMMARIZES → contains` and emit a one-time backfill of
  `contains` edges for existing summary synapses. No provisional
  name to unwind.
- **Edge-retirement cascade in adapter read path.** When a Neuron
  is soft-retired, all Edges (both Synapse- and junction-derived)
  where the Neuron is an endpoint must be filtered from live
  queries. §5 Store implementation concern.
- **`neuron_source` hard cascade.** The legacy `ON DELETE CASCADE`
  should stay in place for `spkt history prune` but not interfere
  with soft-retire. Verify during §5 implementation.

## 5. Store / Transaction Implementation

§3 and §4 defined *what* the adapter publishes. §5 defines *how*
the adapter realizes the SDK `Store` / `Transaction` Protocols on
top of `Circuit`. It also resolves every "§5 concern" logged in
§3.7 / §4.6.

### 5.1 Shape of the adapter surface

The SDK (`amkb-sdk` 0.1.0, `store.py`) defines two structural
Protocols: `Store` (session entry, read queries, history, events)
and `Transaction` (mutation surface, context manager). Both are
`typing.Protocol` with `@runtime_checkable`, so the adapter
classes do **not** inherit — any shape that matches is a valid
`Store`.

The adapter ships two concrete classes:

| Class | SDK Protocol | Backs onto |
|---|---|---|
| `SpikuitStore` | `amkb.Store` | `spikuit_core.Circuit` |
| `SpikuitTransaction` | `amkb.Transaction` | `Circuit.transaction()` context |

Both live in `spikuit_agents/amkb/store.py`. Imports from
`amkb` are structural — `SpikuitStore` imports `amkb.types`,
`amkb.errors`, `amkb.refs`, `amkb.store.RetrievalHit` but **not**
`amkb.store.Store` (no subclassing).

### 5.2 Async/sync bridging — decided: sync wrapper in v0.7.1

**Problem.** The SDK `Store` Protocol is synchronous (see
`store.py` docstring: *"This module defines the synchronous
surface. An async variant may be added later as ``AsyncStore``…"*).
Spikuit's `Circuit` is fully async (aiosqlite). The adapter must
bridge.

**Options considered:**

1. **Sync wrapper (chosen).** `SpikuitStore` methods are sync;
   each one runs the matching `Circuit` coroutine on a dedicated
   event loop owned by the store. Callers that are themselves
   async must not call `SpikuitStore` methods from inside a
   running loop — use a thread offload instead. v0.7.1 ships
   this.
2. Add `AsyncStore` / `AsyncTransaction` Protocols to
   `amkb-sdk` 0.1.0. Rejected for v0.7.1: expands `amkb-sdk`
   0.1.0 scope significantly, adds a second conformance surface,
   and pins Spikuit's release on SDK-side design that we have
   not yet done. Logged as `amkb-sdk` 0.2.0 candidate.
3. Sync-reimplement the read path against the DB directly.
   Rejected: duplicates `Circuit` logic, forks divergence risk,
   bypasses in-memory graph state.

**Implementation sketch:**

```python
class SpikuitStore:
    def __init__(self, circuit: Circuit) -> None:
        self._circuit = circuit
        self._loop = asyncio.new_event_loop()
        self._owns_connection = False

    @classmethod
    def open(cls, circuit: Circuit) -> "SpikuitStore":
        """Build a store and drive Circuit.connect() on the owned loop.

        Use this when the caller hands over an unconnected Circuit.
        The store takes responsibility for connect/close. Tests and
        conformance fixtures use this path.
        """
        store = cls(circuit)
        store._run(circuit.connect())
        store._owns_connection = True
        return store

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def close(self) -> None:
        if self._owns_connection:
            self._run(self._circuit.close())
        self._loop.close()

    def get_node(self, ref):
        return self._run(self._get_node_async(ref))
```

`SpikuitStore(circuit)` (direct constructor) is reserved for callers
who already manage Circuit lifecycle externally and run on a
compatible loop — rare, and out of v0.7.1 conformance path.
`SpikuitStore.open(circuit)` is the supported shape for v0.7.1.

**Caveats:**

- `SpikuitStore` is **not** safe to call from inside a running
  asyncio loop. The adapter docstring MUST state this. Callers
  inside async code use `await loop.run_in_executor(None, store.get_node, ref)`
  or open an `amkb.AsyncStore` in a future v0.7.2 (once the SDK
  adds the async Protocol).
- The owned loop is closed on `SpikuitStore.close()`. The
  underlying `Circuit` is **not** closed by the adapter —
  lifecycle stays with the caller.
- **1.0.0-bound**: this is a v0.7.1 bridge, **not** a frozen
  decision. Once `amkb-sdk` ships `AsyncStore`, Spikuit's adapter
  exposes both (`SpikuitStore` sync, `SpikuitAsyncStore` async),
  and the sync wrapper becomes a thin shim over the async one.
  Logged in §8 as not-frozen.

### 5.3 SpikuitStore: method-by-method delegation

| SDK method | Circuit backing | Notes |
|---|---|---|
| `begin(tag, actor)` | `Circuit.transaction()` context | Returns `SpikuitTransaction`. See §5.4. |
| `get_node(ref)` | `Circuit.get_neuron` / `Circuit.get_source` | Dispatches on the ref prefix (`n:` vs `src:`). MUST resolve retired (§5.5). Emits `ENodeNotFound` otherwise. |
| `get_edge(ref)` | `Circuit.get_synapse` / `neuron_source` lookup | Dispatches on EdgeRef shape. §5.5 bypass applies. |
| `find_by_attr(attrs, kind, layer, ...)` | `Circuit.list_neurons` + in-memory filter | L4a. For v0.7.1 the adapter runs `list_neurons` then filters in Python (scans the in-memory graph). Logged as optimization item when brains exceed ~10k neurons. |
| `neighbors(ref, rel, direction, depth, ...)` | `Circuit.neighbors` / `Circuit.predecessors` + iteration | L4a. BFS at the adapter level; filters by rel / direction / retired state. Cross-kind: source Nodes are skipped in traversal (matching DictStore, §3.5-derived contract). |
| `retrieve(intent, k, layer, filters)` | `Circuit.retrieve` | L4b. See §5.9 for hit mapping. |
| `history(since, until, actor, tag, ...)` | `db.list_changesets(since=, until=, actor_id=, tag=)` (landed in `75eebb0`), then `db.list_events(changeset_id=…)` per row to hydrate | §5.8. The `changeset` table carries every needed column (see `db.py:124`), so the helper is a pure SELECT with no schema change. Tracked as §9.1 prerequisite #4. |
| `get_changeset(ref)` | `db.get_changeset` + `db.list_events(changeset_id=…)` | Rebuilds the `ChangeSet` struct from the event log. |
| `diff(from_ts, to_ts)` | `db.list_events` range query | L2. Maps rows → AMKB `Event` structs. |
| `revert(target, reason, actor)` | **stub** — raises `EConstraint("revert requires L3; Spikuit v0.7.1 sets supports_merge_revert=False")` | **L3-gated.** `revert` is only exercised by `amkb.conformance.test_l3_transactional` — L1 and L2 suites never call it. Since v0.7.1 opts out of all four L3 capability flags (§7.4), the stub is never triggered by conformance. Shipping real inverse logic would duplicate ~100 LOC of `DictStore._apply_inverse`-style code that has no consumer today. Deferred to the dedicated L3 milestone (§7.8 / §9.2) where concurrency detection, commit-time constraints, and merge-revert resurrection land together. |
| `events(since, follow)` | `db.list_events` + tail follow | `follow=False` trivially iterates committed events. `follow=True` polls the event table — deferred to v0.7.2 (not needed by conformance). |

### 5.4 SpikuitTransaction: wrapping `Circuit.transaction()`

The adapter cannot use `Circuit.transaction()` directly as an SDK
Transaction because the SDK shape is synchronous and requires
`__enter__` / `__exit__`, not `__aenter__` / `__aexit__`.

**Shape:**

```python
class SpikuitTransaction:
    ref: TransactionRef
    tag: str
    actor: ActorId

    def __init__(self, store, *, tag, actor):
        self._store = store
        self._tx_ctx = None   # the Circuit.transaction() async context
        self._tx = None       # the SpikuitTransaction from core
        self.tag = tag
        self.actor = actor.id

    def __enter__(self):
        self._tx_ctx = self._store._circuit.transaction(
            tag=self.tag, actor_id=self.actor, actor_kind=_map_actor_kind(...)
        )
        self._tx = self._store._run(self._tx_ctx.__aenter__())
        self.ref = TransactionRef(self._tx.id)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._tx.status == "open":
            self._store._run(self._tx_ctx.__aexit__(exc_type, exc, tb))
```

- `commit()` calls `__exit__(None, None, None)` under the hood
  and returns a `ChangeSet` rebuilt from the committed events.
- `abort()` drives the core tx's abort path through the
  asynccontextmanager protocol: it calls
  `__aexit__(_AbortSignal, _AbortSignal(reason), None)` with an
  adapter-private sentinel exception class. `Circuit.transaction()`
  sees any `BaseException` and takes its `except BaseException`
  branch (`circuit.py:163`), which marks the tx aborted and calls
  `db.abort_changeset`. The adapter catches the sentinel on the
  way back out so it never escapes to the caller. This is the
  standard way to drive an `asynccontextmanager` down its
  exception path — `Circuit` has no public `tx.abort()` method
  today, so routing abort through `__aexit__` is both
  spec-compliant for asynccontextmanager and the least invasive
  shape. If a future `Circuit.transaction()` grows an explicit
  `tx.abort()` API, the adapter switches to it in a v0.7.2 patch.

**Mutation delegation:**

| SDK tx method | Circuit call | Note |
|---|---|---|
| `create(kind, layer, content, attrs)` | `Circuit.add_neuron` or `Circuit.add_source` depending on `kind` | Translates AMKB attrs → Spikuit fields before the call. Validation (kind/layer/content) runs first via `amkb.validation.*`. |
| `rewrite(ref, content, reason)` | `Circuit.update_neuron` | Only `kind=concept` is meaningful; rewriting a source is L4a-scope but Spikuit v0.7.1 does not support source content rewrite → raises `EConstraint`. |
| `retire(ref, reason)` | `Circuit.remove_neuron` (soft-retire) or source retire | Incident-edge cascade is handled inside `Circuit.remove_neuron` (v0.7.0 plumbing), so the adapter does not re-emit per-edge events. |
| `merge(refs, content, attrs, reason)` | `Circuit.merge_neurons` | v0.7.0 lineage junction is already populated; the adapter just surfaces the resulting ChangeSet. |
| `link(src, dst, rel, attrs)` | `Circuit.add_synapse` | `rel` must be one of the four reserved intra-concept rels, or `derived_from` for concept→source. `ext:*` rels are rejected in v0.7.1 (no Spikuit surface to store them — see §5.4.A). |
| `unlink(ref, reason)` | `Circuit.remove_synapse` or `detach_source` | Dispatches on EdgeRef shape. |
| `get_node` / `get_edge` | as in §5.3, but aware of pending writes in the active core tx | v0.7.0 `SpikuitTransaction.events` is append-only; staged-read is implemented by merging the buffer with committed state. |

#### 5.4.A `ext:*` rel rejection — risk note

Rejecting `ext:*` rels at `link()` time is safe for v0.7.1 because
no current consumer emits them: Spikuit CLI paths never call
them, and amkb-sdk 0.1.0 itself does not synthesize `ext:*` edges.
The concrete risks to watch during daily use:

- **Import round-trip.** If a future `spikuit import` path ever
  ingests an AMKB dump from another store that uses `ext:*`
  edges, the adapter would silently drop them (or raise). Out
  of v0.7.1 scope — flagged for the import work in v0.8.x.
- **Curator / learn session extensions.** If daily use surfaces
  a natural edge kind that does not fit the four reserved
  intra-concept rels (e.g., "prerequisite chain", "exemplifies",
  "worked-example-of"), the right answer is to either
  (a) propose a new reserved rel to `amkb-spec`, or
  (b) add a generic `ext_edge` side table in `spikuit-core` and
  wire the adapter to round-trip through it. Both are additive.
  v0.7.1 does not need either.
- **Error message contract.** The `EConstraint` raised for
  `ext:*` rels should say *"Spikuit v0.7.1 does not store
  `ext:*` rels; file an issue if you need this"* rather than
  implying the spec forbids it. Documentation detail, logged
  in §6.

None of these are blocking. Logged in §5.11 / §9 as daily-use
watch items.

### 5.5 Retired-ref resolution (resolves §3.7 / §4.6 item)

SDK spec §3.4.1: "Retired Nodes MUST resolve". Spikuit's
`Circuit.get_neuron` defaults to the `_live_neurons_sql` predicate
which excludes retired rows. The adapter therefore needs an
opt-in path that returns retired rows as well.

**Approach (landed in 4d5db68).** `Circuit.get_neuron` and
`Circuit.get_synapse` now accept an `include_retired: bool = False`
keyword. The flag already existed on the `db` layer; the patch
just surfaces it one level up so the adapter never has to reach
into `circuit._db`. The adapter calls
`get_neuron(ref.id, include_retired=True)` from
`SpikuitStore.get_node` (and symmetrically for edges). CLI paths
keep the default and continue to see live-only rows.

This is a ~20-line addition to `spikuit_core.db`, not a schema
change. Logged as a v0.7.1 prerequisite patch, not a v0.7.0
retrofit.

### 5.6 Edge-retirement cascade in the read path (resolves §4.6)

When a Neuron is soft-retired, its incident synapses are also
marked retired in v0.7.0 plumbing (see
`amkb-core-plumbing-spec.md` §3.3). For `neuron_source`
junction rows, v0.7.0 plumbing does **not** soft-retire the
junction — the link row stays.

The adapter `SpikuitStore.neighbors` and `get_edge` filter
`derived_from` edges by endpoint liveness at read time:

```python
def _derived_from_is_live(neuron_id, source_id) -> bool:
    neuron = await circuit.get_neuron(neuron_id, include_retired=True)
    source = await circuit.get_source(source_id, include_retired=True)
    return neuron.retired_at is None and source.retired_at is None
```

`include_retired=True` paths skip this filter. This is a pure
read-path concern; no schema change is required.

### 5.7 Event surfacing: `db.list_events` → `Store.events()`

The v0.7.0 event log stores rows with
`(id, changeset_id, seq, op, target_kind, target_id, before_json, after_json, at)`.
The adapter maps each row to an `amkb.Event`:

| Spikuit event field | AMKB `Event` field | Notes |
|---|---|---|
| `op` (`OP_NEURON_ADD`, etc.) | `kind` (`"node.created"`, etc.) | Translation table in §6-adjacent appendix. SUMMARIZES synapse events are **filtered out** here too (§4.3.A). |
| `target_kind` + `target_id` | `target: NodeRef \| EdgeRef` | Synapse target_ids use the hash-synthesized EdgeRef (§4.4.A); the adapter keeps a small reverse-lookup table so synapse events can be rehydrated. |
| `before_json` | `before: Snapshot \| None` | Parsed to the AMKB snapshot dict format via the same translator used by §3/§4 mappings. Reuse avoids divergence. |
| `after_json` | `after: Snapshot \| None` | Same. |
| `at` | (implicit through ChangeSet.committed_at) | |

`follow=True` is **not** supported in v0.7.1 (see §5.3). The
conformance suite for L1 events does not require follow.

### 5.8 Lineage: `Circuit.predecessors_of_lineage` → history API

`Circuit.predecessors_of_lineage(neuron_id)` returns the direct
parents (merge ancestors) of a neuron. The SDK's lineage tests
walk predecessors transitively; the adapter's `SpikuitStore`
exposes this via the `merge` event shape (`meta.ancestors`) and
the `node_predecessors` table backing `predecessors_of_lineage`.
L2 conformance covers the transitive walk through pure
`Store.diff` + `get_changeset` calls — the adapter does not need
a dedicated lineage query method because `amkb.lineage.would_cycle`
(`amkb-sdk/src/amkb/lineage.py`) already operates over a
predecessor-of callable. The adapter passes
`Circuit.predecessors_of_lineage` as that callable in the merge
path (see `SpikuitTransaction.merge` in §5.4).

### 5.9 Retrieval: `Circuit.retrieve` → `Store.retrieve` (L4b)

The SDK surface:

```python
def retrieve(intent, *, k=10, layer=None, filters=None) -> list[RetrievalHit]
```

`Circuit.retrieve`:

```python
async def retrieve(query, *, limit=10, filters=None) -> list[Neuron]
```

Mapping:

| SDK param | Circuit call | Notes |
|---|---|---|
| `intent: str` | `query: str` | Pass-through. |
| `k: int` | `limit: int` | Pass-through. |
| `layer: str \| list[str] \| None` | (post-filter) | Spikuit has no layer column; adapter post-filters Neurons whose mapped AMKB layer is in the requested set. In v0.7.1 this only excludes Sources (Sources are not retrievable per spec §2.2.9). |
| `filters: amkb.Filter \| None` | (translated) | AMKB `Filter` AST is translated to Spikuit's `{"key": "val"}` equality filters where possible. Richer AST cases (AND/OR/comparisons) are post-evaluated in Python using `amkb.filters.evaluate`. |

**Hit construction — decided: publish the raw score as opaque float.**

`Circuit.retrieve` already computes a ranking score internally
(`score = max(keyword_sim, semantic_sim) × (1 + retrievability +
centrality + pressure + boost)`, `circuit.py:1134`). The adapter
surfaces this score on `RetrievalHit.score` as-is. Spec §3.4.4
requires only that `score` be a real number **consistent with
list order** — it does not require probability / similarity /
any normalized shape. Spikuit's score is already monotone with
list order by construction, so it satisfies the contract.

```python
hits = [
    RetrievalHit(
        ref=NodeRef(neuron.id),
        score=neuron._spikuit_score,  # raw graph-weighted product
    )
    for neuron in circuit_results
]
```

- **Semantics contract (documented on the adapter, not frozen
  in the SDK):** the published score is an *opaque relevance
  indicator* — higher means more relevant, but the number is
  **not** a probability, **not** a cosine similarity, and **not**
  comparable across different `retrieve` calls (centrality and
  boost state drift over time). Consumers that want portable
  comparability SHOULD rely on list order only.
- **Wiring prerequisite (landed in `bd76a21`).** `Circuit.retrieve`
  originally returned `list[Neuron]` without exposing the per-hit
  score. The patch splits the method in two: `retrieve_scored`
  is now the primitive and returns `list[tuple[Neuron, float]]`;
  `retrieve` is a thin shim that drops scores so existing callers
  (`spkt retrieve`, RAG sessions) keep their current shape. The
  adapter's L4b path calls `retrieve_scored` directly.
- **Why not hide the score**: originally considered, because
  spec §2.7 keeps retrieval implementation-opaque and §3.3.D /
  §4.3.C hid FSRS/STDP internals. But a *single monotone
  float* is not the same as leaking scheduler/plasticity
  parameters — it is the one thing every retrieval implementation
  has in some form, and the SDK's `RetrievalHit` already
  exposes it optionally. Surfacing it costs nothing in future
  flexibility: if a future scheduler changes the formula, the
  contract ("opaque, monotone, non-comparable") still holds.
- **1.0.0-bound**: the decision *to publish a score*, and the
  "opaque / non-comparable / monotone-with-list-order" contract,
  are frozen at AMKB 1.0.0. The specific formula is **not**
  frozen.

### 5.10 Concurrency and re-entrancy

- **One active transaction at a time.** `Circuit.transaction()`
  already enforces this (raises `TransactionNestingError`). The
  adapter surfaces the nesting attempt as
  `EConstraint("transaction already active")`.
- **Mixing adapter and raw Circuit calls.** Allowed but the user
  owns the consequences. A raw `Circuit.add_neuron()` between
  two adapter reads will surface as a node that appears outside
  any adapter-driven ChangeSet — the v0.7.0 `_auto_tx` wraps the
  raw call in a system-actor tx, so the event still shows up
  in the event log. Adapter consumers see it on the next
  `Store.events()` iteration.
- **No multi-threading guarantees.** `SpikuitStore` owns a single
  event loop; concurrent calls from multiple threads are not
  supported in v0.7.1. Logged as §9 item.

### 5.11 Open questions for §9

- **AsyncStore Protocol in `amkb-sdk` 0.2.0.** Promoted from
  §5.2 option 2. Track against Spikuit v0.7.2.
- **`SpikuitStore.events(follow=True)`.** Polling the event
  table. Not needed for v0.7.1 conformance; add with tail-follow
  semantics in v0.7.2+.
- **`find_by_attr` scan cost.** In-memory linear scan is fine
  for current Brain sizes. Add a secondary attr index once a
  Brain exceeds ~10k neurons.
- **Thread-safety of the owned event loop.** Single-loop
  assumption in §5.10. Document the constraint and revisit if a
  consumer needs multi-thread access.
- **Source content rewrite.** `SpikuitTransaction.rewrite` on a
  `kind="source"` node raises `EConstraint` in v0.7.1. If the
  daily-use phase surfaces a legitimate use (e.g., re-fetch
  updates the stored excerpt), re-enable selectively.
- **`ext:*` rel round-trip (§5.4.A).** Watch for daily-use edge
  kinds that do not fit the reserved rels. Fix is additive:
  either propose a new reserved rel or add a generic `ext_edge`
  side table in `spikuit-core`.
- ~~**Prerequisite: `Circuit.retrieve_scored` (§5.9).**~~
  Landed in `bd76a21`; moved to §9.1 for traceability.

## 6. Error Translation Table

### 6.1 Strategy

Every exception that escapes `SpikuitStore` / `SpikuitTransaction`
MUST be an `amkb.AmkbError` subclass. Per AMKB spec §5.1, callers
are contractually allowed to catch by canonical code
(`EConstraint`) or by category (`StateError`) — so anything that
leaks as a raw `ValueError` or `RuntimeError` is a conformance
break.

The adapter applies translation in two places:

1. **Pre-translation** (at the adapter boundary). Validation that
   the SDK already ships (`amkb.validation.*`) is called
   *before* delegating to `Circuit`, so kind/layer/content/rel
   violations raise the right `AmkbError` subclass directly
   without touching Spikuit code. This is the same pattern used
   by `DictStore` in `tests/impls/dict_store.py`.
2. **Post-translation** (around the `Circuit` call). Anything
   that `Circuit` or `db` raises is caught and re-raised as the
   matching `AmkbError`. The mapping is deterministic and
   recorded in §6.3.

### 6.2 Prerequisite: typed Spikuit exceptions (landed in `eda08ec`)

Spikuit v0.7.0 raised bare `ValueError` / `RuntimeError` at
several call sites in `circuit.py` / `db.py`. Catching
`ValueError` broadly to translate at the adapter boundary would
also catch unrelated bugs and mask them as `EConstraint`. The
typed-exception module in `spikuit-core/errors.py` is the fix,
landed as the prerequisite patch for the adapter PR.

**Shipped classes** (all subclass `SpikuitError`):

```python
# spikuit_core/errors.py
class SpikuitError(Exception):
    """Base for all spikuit-core raised exceptions."""

class NeuronNotFound(SpikuitError): ...
class SynapseNotFound(SpikuitError): ...
class SourceNotFound(SpikuitError): ...
class NeuronAlreadyRetired(SpikuitError): ...
class InvalidMergeTarget(SpikuitError): ...   # into_id in source_ids, etc.
class DBNotConnected(SpikuitError): ...
# TransactionNestingError / TransactionAbortedError stay in
# spikuit_core/transactions.py and now re-export SpikuitError
# from this module as their shared base.
```

The patch replaced the generic raises in `circuit.py` / `db.py`
with these typed classes. The remaining `ValueError` raises
(QuizItem validation, fire-of-unknown-id, consolidate brain-state
hash) are out of adapter scope and stayed as-is. The full set is
re-exported from `spikuit_core` so adapters import from the
top-level namespace. §1.3's out-of-scope rule does not apply:
this was additive inside `spikuit-core`, no CLI / public API
regressions.

### 6.3 Translation table: Spikuit → AMKB

| Spikuit exception | AMKB canonical error | Trigger |
|---|---|---|
| `NeuronNotFound` | `ENodeNotFound` | `get_node` / neighbors / retire / rewrite target missing. |
| `SourceNotFound` | `ENodeNotFound` | `get_node` on a `kind="source"` ref that does not exist. |
| `SynapseNotFound` | `EEdgeNotFound` | `get_edge` / `unlink` target missing. |
| (junction row missing) | `EEdgeNotFound` | Derived `derived_from` EdgeRef does not resolve. |
| `NeuronAlreadyRetired` | `ENodeAlreadyRetired` | `rewrite` / `link` endpoint is retired. |
| `InvalidMergeTarget` | `EConstraint` | `into_id` in `source_ids`, or target not found. Structural impossibility, not a validation input error. |
| (merge kind/layer mismatch) | `EMergeConflict` | Caught by `amkb.validation.validate_merge_uniform` before hitting Spikuit. Pre-translated (§6.4). |
| (merge cycle) | `ELineageCycle` | Caught by `amkb.lineage.would_cycle` before hitting Spikuit. Pre-translated (§6.4). |
| `TransactionNestingError` | `EConstraint` | `message="transaction already active"`. |
| `TransactionAbortedError` | `ETransactionClosed` | Caller issued a mutation against a tx whose status is not `"open"`. |
| `ReadOnlyError` | `EConstraint` | Circuit is in read-only mode; mutations forbidden. See §6.3.A. |
| `DBNotConnected` | `EInternal` | Caller forgot to `Circuit.connect()`. Implementation-side. |
| (sqlite3 integrity / operational error) | `EInternal` | Database-level failure. Callers MAY retry. |
| (aiosqlite disconnect mid-tx) | `EConcurrentModification` | Only if we can detect the specific case; otherwise `EInternal`. See §6.6. |
| any other unhandled | `EInternal` | Catch-all at the adapter boundary. Preserves `__cause__`. |

**Notes:**

- `EConstraint` is used as the general "Spikuit-side structural
  no" code. Spec §5 treats `EConstraint` as a state error that
  aborts the transaction — matches Spikuit's semantics for
  invalid merge targets and nested tx.
- `EConcurrentModification` is **not** raised by v0.7.1 in
  practice. Spikuit v0.7.0 uses a single aiosqlite connection
  per Circuit and does not detect concurrent writes at commit
  time. The row is in the table so the L3 conformance suite
  knows the adapter does not advertise concurrency detection;
  see §7.
- `E_SOURCE_IN_RETRIEVAL` (`ESourceInRetrieval`) is enforced by
  the adapter *before* calling `Circuit.retrieve` — the adapter
  filters Source nodes out of the layer set, so the invariant
  cannot trip. Defense-in-depth only.

#### 6.3.A Why `ReadOnlyError → EConstraint` (not `EInternal`)

Initially considered `EInternal` on the reasoning that
read-only is a *configuration* choice rather than runtime
state. The decisive factor is the "MAY retry" clause on each
category:

- `EInternal` semantics: "Implementation-side failure. Callers
  MAY retry." — a caller reading this is told blind retry is
  acceptable. But retrying a mutation against a read-only
  Circuit will fail identically every time. Misleading.
- `EConstraint` semantics: "A protocol invariant would be
  violated at commit. Tx is aborted." — the caller is told to
  fix the situation before retrying (reopen the Circuit in
  write mode). Correct actionable signal.

The "state" category arguably feels wrong because the
read-only flag is immutable for a given Circuit instance, not
a drifting runtime state like retired-ness. But `StateError`
is defined as "store state is incompatible with the operation"
(`errors.py:70`), and an immutable config flag is still
"store state" from the caller's perspective. `EConstraint` is
the right catch-all.

### 6.4 Validation pre-translation

The adapter calls `amkb.validation.*` helpers at the top of
every mutation method *before* touching Spikuit. These helpers
raise the correct `AmkbError` subclass directly:

| Adapter method | Pre-translation helpers | Raises |
|---|---|---|
| `create` | `validate_kind_layer`, `validate_concept_content` | `EInvalidKind`, `EInvalidLayer`, `ECrossLayerInvalid`, `EEmptyContent` |
| `rewrite` | `validate_concept_content` | `EEmptyContent` |
| `merge` | `validate_merge_uniform`, `would_cycle` | `EMergeConflict`, `ELineageCycle` |
| `link` | `validate_edge_rel` | `EInvalidRel`, `EReservedRelMisuse`, `EConceptToNonsourceAttest`, `ESelfLoop` |

By the time `Circuit` is called, the inputs are already
protocol-valid. Spikuit's own invariants (foreign-key existence,
idempotency, etc.) are all that remain to translate.

### 6.5 Reverse direction: AMKB errors inside Spikuit

When an adapter consumer (actor-driven SDK code) triggers an
`AmkbError`, the error surfaces on the SDK side, not in the
Spikuit CLI. The CLI paths do not call the adapter — they call
`Circuit` directly — so AMKB errors simply do not appear in CLI
logs.

Exceptions: any internal use of the adapter from Spikuit's own
CLI (none in v0.7.1) would need to catch `AmkbError` at the
boundary and translate back to Spikuit user-facing messages.
Logged in §9 as an item for v0.8.x if a CLI feature grows on
top of the adapter.

### 6.6 Unhandled exceptions → `EInternal`

A single `try/except Exception` at the boundary of every
adapter method catches anything not matched above and re-raises
as `EInternal`, preserving `__cause__` for debugging. Without
it, a stray `KeyError` from a dict lookup would leak as itself
and break the "every raise is an `AmkbError`" contract.

```python
def get_node(self, ref):
    try:
        return self._get_node_impl(ref)
    except AmkbError:
        raise
    except SpikuitError as e:
        raise _translate(e) from e
    except Exception as e:
        _log_internal(e, op="get_node", ref=ref)
        raise EInternal(
            f"unhandled: {type(e).__name__}: {e}",
            underlying_type=type(e).__name__,
            underlying_message=str(e),
            op="get_node",
        ) from e
```

#### 6.6.A Debuggability: keep `EInternal` rare and loud

`EInternal` is the fall-through; every time it fires, it means
the §6.3 translation table is incomplete or a real bug escaped.
Three rules keep it from becoming a debugging black hole:

1. **`__cause__` is mandatory.** Every `EInternal` MUST be
   raised `from e` so tracebacks preserve the original line.
   Never `raise EInternal("...")` without a cause when one
   exists.
2. **Structured `details` on the `AmkbError`.** The adapter
   populates `details["underlying_type"]`,
   `details["underlying_message"]`, and
   `details["op"]` on every fall-through translation. Callers
   can log these structured fields without parsing `str(e)`
   (spec §5.1 forbids message parsing, but `details` is fair
   game).
3. **Logger side channel.** The adapter's `_log_internal(e, ...)`
   writes the full traceback and op metadata at `ERROR` level to
   a dedicated `spikuit.adapter.amkb` logger *before* raising.
   This means even if the caller swallows `AmkbError`, the
   original stack is already in the logs.

**Policy for closing the gap.** When daily use surfaces a
recurring `EInternal`, the fix is not to add another generic
catch — it is to:

(a) add a typed `SpikuitError` subclass in `spikuit-core` for
    the specific condition, then
(b) add a row to §6.3 mapping it to the correct canonical code.

The `details["underlying_type"]` field on existing `EInternal`
raises tells us exactly which Spikuit-internal exception we
need to promote. The fall-through is a migration path, not a
permanent home.

**Opt-out for local debugging.** The adapter accepts
`SpikuitStore(circuit, reraise_internal=True)`. When set, the
fall-through re-raises the original exception instead of
wrapping it as `EInternal`. Conformance tests MUST run with
the default (`False`) so the "every raise is `AmkbError`"
contract is verified.

### 6.7 `1.0.0-bound` marker

- **Frozen at AMKB 1.0.0:** the 22 canonical error codes are
  part of the spec. The translation *table* (which Spikuit
  exception goes to which code) is frozen on the adapter side
  once Spikuit v1.0.0 ships — before then, rows may be refined
  as typed exceptions replace generic raises in `spikuit-core`.
- **Not frozen:** the specific message strings. Spec §5.1
  explicitly says callers MUST NOT parse `message`.
- **Not frozen:** the set of Spikuit-side exception classes.
  New typed exceptions may be added in `spikuit-core` as
  additive changes; the adapter table is updated alongside.

### 6.8 Open questions for §9

- **Concurrency detection.** v0.7.1 never raises
  `EConcurrentModification`. If daily use surfaces a need
  (multi-agent brains), add optimistic-concurrency bookkeeping
  to the changeset flush path.
- **Custom Spikuit exceptions inside the CLI.** Replacing
  generic `ValueError` raises with `spikuit_core.errors.*`
  affects CLI error messages. Verify no UX regression during
  the prerequisite patch.

## 7. Conformance Wiring

### 7.1 Goal

`amkb-sdk` ships an executable conformance suite
(`amkb.conformance.test_l1_core`, `_l2_lineage`, `_l3_transactional`,
`_l4a_structural`, `_l4b_intent`). An implementation proves
conformance at a given level by running the suite with its own
`store` fixture and passing the corresponding test files.

v0.7.1 ships green runs at **L1, L2, L4a, L4b**; L3 tests are
gated on capability flags and v0.7.1 opts out of
concurrency/commit-time-constraint flags (§7.4).

### 7.2 Fixture provisioning

The suite requests two fixtures per test: `actor` (provided by
`amkb.conformance.fixtures` as a default human actor) and
`store`. The `store` fixture is **not** provided by the SDK —
each implementation must supply it in its own `conftest.py`.

The adapter repo layout for this:

```
spikuit-agents/
├── src/spikuit_agents/amkb/
│   ├── __init__.py
│   └── store.py           # SpikuitStore, SpikuitTransaction
├── tests/
│   └── amkb/
│       ├── conftest.py    # provides `store` fixture, re-exports actor
│       ├── test_unit.py   # adapter-internal unit tests
│       └── (no files under test_l1_… etc — those live in the SDK)
```

**`tests/amkb/conftest.py`** (sketch):

```python
import pytest
from amkb.conformance.fixtures import actor  # noqa: F401 (re-export)

from spikuit_core import Circuit
from spikuit_agents.amkb import SpikuitStore


@pytest.fixture
def store():
    # Unconnected Circuit; SpikuitStore drives connect/close on its
    # own owned event loop so the test never touches asyncio directly.
    circuit = Circuit(db_path=":memory:")
    store = SpikuitStore.open(circuit)
    yield store
    store.close()
```

**Why no `asyncio.run()` in the fixture.** `SpikuitStore` owns a
dedicated event loop (§5.2). Calling `asyncio.run(circuit.connect())`
outside that loop would attach aiosqlite's connection objects to a
*different* loop; the next `store._run(...)` call would fail with
"RuntimeError: got Future attached to a different loop". The
`SpikuitStore.open` classmethod runs `connect()` on the owned loop
during construction, and `close()` symmetrically runs
`circuit.close()` on the same loop before tearing it down. Tests
see a pure-sync surface.

### 7.3 Fixture lifecycle — decided: fresh in-memory Circuit per test

Each test gets a fresh `Circuit` backed by an **in-memory**
SQLite database (`":memory:"`). Not `tmp_path`, not a shared
on-disk brain.

- **Why `:memory:` over on-disk `tmp_path`**: the design
  initially leaned toward on-disk for "production parity"
  (WAL, file locks, `PRAGMA journal_mode`). Revisiting: the
  conformance suite checks the AMKB protocol surface, not
  SQLite engine behavior. Production-parity tests live in
  `spikuit-core/tests/` and are Spikuit's own responsibility.
  `sqlite-vec` loads against `:memory:` without issue.
  Switching to `:memory:` cuts per-test setup from ~50 ms to
  ~3–5 ms and brings the full run under 1 s.
- **Why fresh per test, not fresh per module**: conformance
  tests are independent; a test that retires a node must not
  affect the next test's state. Fresh-per-test matches
  `DictStore`'s trivial `DictStore()` fixture pattern. A
  module-scoped fixture with transaction-rollback teardown
  would be faster still but fights Spikuit's changeset
  semantics (the adapter's `Transaction` is a commit-and-flush
  layer, not a rollbackable DB tx). Not worth the complexity.
- **Why not a shared `.spikuit/`**: no risk of bleed between
  the conformance run and the developer's working Brain.

Cost budget at v0.7.1: ~100 conformance tests × ~5 ms ≈ 0.5–1 s
total wall clock. Leaves headroom for pytest-xdist if the
suite grows.

#### 7.3.A Further speedups (not implemented in v0.7.1)

If L3 opt-in work and daily-use maturation expand the suite
past ~300 tests, consider:

- **SQLite `.backup` snapshot/restore.** Open one Circuit
  per module, take a `.backup` to bytes after `connect()`,
  `.backup` back between tests. Needs the adapter to re-run
  `Circuit._load_graph` / `_load_cards` after restore.
  ~sub-ms restore, breaks the per-test independence story
  only if restore is buggy.
- **`pytest-xdist` process parallelism.** Orthogonal;
  `:memory:` per test is process-local, so no coordination
  needed. Worth enabling once CI starts noticing the runtime.
- **Warm Circuit pool.** Pre-spin N empty Circuits and hand
  them out. Only buys setup cost back; not worth it unless
  `connect()` itself becomes expensive.

None of these ship in v0.7.1. Logged in §7.8.

### 7.4 Capability flags — decided

L3 tests gate on four capability flags
(`test_l3_transactional.py:10-24`). The adapter sets them as
class-level attributes on `SpikuitStore`:

| Flag | v0.7.1 value | Rationale |
|---|---|---|
| `supports_concurrency_detection` | `False` | Spikuit v0.7.0 uses a single aiosqlite connection per Circuit; conflicting commits from two `.begin()` calls are serialized by the tx nesting guard, not detected at commit time. Advertising `True` would lie. |
| `supports_merge_revert` | `False` | `revert` of a merge would need to resurrect retired source Neurons. Spikuit's soft-retire is one-way in v0.7.0; resurrection is a v0.8.x candidate. |
| `supports_revert_conflict_detection` | `False` | Follows from the above — no conflict detection on revert without resurrection. |
| `supports_commit_time_constraints` | `False` | v0.7.0 plumbing validates at mutation time, not commit time. Changing this would require staging all mutations and re-running invariants at flush; deferred. |

**Also:** the `setup_required_attribute_pair` helper used by
one L3 test (`test_l3_transactional.py:148`) is **not**
provided by `SpikuitStore`. That test skips cleanly.

L3 is therefore **skip-clean**, not fail: running the L3
suite against the adapter produces ~4 `SKIPPED` lines and no
failures. Spec-compliant — the SDK explicitly defines this
opt-out shape.

#### 7.4.A L2 merge-revert clarification

`amkb.conformance.test_l2_lineage` does not require
merge-revert (that is an L3-only concern). L2 only requires
that `merge` records lineage and that `diff` / `get_changeset`
can reconstruct the merge event. Spikuit v0.7.0's
`neuron_predecessor` junction and merge event in the changeset
log cover this. L2 runs green.

### 7.5 Running the suite

From `spikuit-agents/`:

```bash
uv run --package spikuit-agents pytest \
    --pyargs amkb.conformance \
    -c tests/amkb/pytest.ini
```

The `--pyargs` flag tells pytest to discover test files from
the installed `amkb.conformance` package rather than the local
tree. The `-c` flag points at an adapter-local `pytest.ini`
that adds `tests/amkb/` to `rootdir` so the `store` fixture in
`tests/amkb/conftest.py` is picked up.

**Make target** (in `spikuit-agents/Makefile` or the repo root
justfile, TBD):

```makefile
conformance:
	uv run --package spikuit-agents pytest --pyargs amkb.conformance \
	  -c tests/amkb/pytest.ini
```

### 7.6 CI integration — two-tier

The PR-gate vs. SDK-drift tension is resolved by splitting CI
into two tiers.

| Tier | Trigger | SDK version | Purpose |
|---|---|---|---|
| **PR gate** | every PR to `main` | `amkb==<exact>` from `uv.lock` | Reproducible signal: if this run is red, the PR broke something. Never red "by surprise" from an upstream SDK bump. |
| **Nightly drift** | scheduled daily + on push to `main` | `amkb>=<pinned minor>` resolved fresh | Early-warning signal: new SDK release tightened or added a test. Opens a Spikuit issue automatically; does not block PRs. |

- **PR gate is locked.** `uv.lock` freezes the exact `amkb`
  version used in CI. Dependabot-style bumps of the lock file
  are themselves PRs that run conformance against the new
  version before merging — the bump either passes or surfaces
  exactly which L1/L2 contract changed. No PR ever goes red
  "because someone published amkb 0.1.3 overnight."
- **Nightly drift catches SDK evolution.** A scheduled workflow
  resolves `amkb` fresh within the `>=0.1.0,<0.2.0` range and
  runs conformance. Failures file a Spikuit issue labeled
  `amkb-drift` with the failing test names. This is the signal
  that tells Spikuit maintainers "v0.1.3 added L4a.06 and we
  don't satisfy it yet" without blocking unrelated PRs.
- **Upgrade workflow.** Bumping the pinned `amkb` version is
  its own PR. It runs conformance against the new SDK; either
  it passes (pin bump merges), or the failing rows guide
  adapter work on the same branch.

This pattern is how most projects bridge "stable PR signal"
and "early drift detection" against an actively-evolving
upstream. It directly answers the question raised when L3
was deferred: drift is detectable without creating flaky PR
gates.

### 7.7 L4b retrieval test interop

`test_l4b_intent.py` checks that `retrieve(intent)` returns
hits in monotone score order and that source Nodes never
appear in results. The adapter satisfies both:

- **Monotone order**: `Circuit.retrieve` already sorts
  internally; the adapter preserves list order.
- **No sources**: adapter-level layer filter (§5.9) excludes
  `L_source`.

One L4b test skips cleanly when fewer than 2 scored hits are
produced (`test_l4b_intent.py:55`). Not an issue — we always
seed enough neurons in the conformance flow.

Note the decision in §5.9 to **publish** numeric scores rather
than `None`. The L4b suite accepts either shape per spec
§3.4.4, so the choice is invisible to the test matrix. The
prerequisite `Circuit.retrieve_scored` patch (§5.11) must
land before this test passes — until it does, the adapter
falls back to `score=None` and the monotone-order check still
holds via list position.

### 7.8 Open questions for §9

- **L3 full-capability release.** v0.7.1 opts out of all four
  L3 flags (§7.4). Rather than flipping them one by one, the
  plan is to deliver L3 in a dedicated milestone (candidate:
  v0.8.x or later daily-use phase) where concurrency
  detection, commit-time constraints, and merge-revert
  resurrection ship together. Sequence with daily-use needs.
- **Scaling the fixture past ~300 tests.** §7.3.A lists the
  three options (`.backup` snapshot/restore, `pytest-xdist`,
  warm Circuit pool). Pick one when wall time starts being a
  problem. Not needed at v0.7.1 size.
- **`sqlite-vec` availability in CI.** The extension loads via
  the Spikuit `Circuit` constructor. CI image must have it
  installed. Document in the CI setup alongside the `make
  conformance` target.
- **`amkb-drift` issue automation.** Nightly drift tier
  (§7.6) needs a GitHub Action that files an issue on first
  failure and closes it once the condition clears. Off-the-
  shelf tooling exists; pick one during CI setup.

## 8. 1.0.0-bound Decisions

### 8.1 Purpose of this section

Three things are written down here, together, so that future
readers have a single place to confirm the frozen surface
before cutting AMKB 1.0.0:

1. **The inventory** — every decision in §3–§7 that is intended
   to be frozen at AMKB 1.0.0, pulled into one table.
2. **What is NOT frozen** — decisions that look permanent from
   §3–§7 but are explicitly pre-release-only.
3. **Release sequencing** — how `amkb-spec` / `amkb-sdk` /
   Spikuit 1.0.0 relate and which one freezes first.

### 8.2 Frozen surface inventory

Grouped by the category of contract, each row cites the
section where the decision was made.

#### 8.2.A Node surface (§3)

| Decision | Section | Frozen surface |
|---|---|---|
| Neuron kind/layer = `concept` / `L_concept`, uniform | §3.3.B | Spikuit will never introduce `ext:*` kinds for Neurons. |
| `spk:type` attribute name (on Neuron Nodes) | §3.3.B | Attribute key frozen. Values may be extended additively. |
| Content published verbatim (frontmatter included) | §3.3.A | Round-trip contract frozen. |
| `content_hash` computed over `strip_frontmatter(content)` | §3.3.A | Hash input contract frozen — staleness semantics depend on it. |
| Scheduler attrs `spk:due_at`, `spk:last_reviewed_at` | §3.3.D | Names and semantics frozen. Scheduler implementation is NOT. |
| `Neuron.source` legacy field NOT published | §3.3.E | Permanent omission. |
| Source kind/layer = `source` / `L_source` | §3.5 | Layer and kind pairing frozen. |
| Source attribute names: `spk:title`, `spk:author`, `spk:url`, `spk:section`, `spk:excerpt`, `spk:storage_uri`, `spk:notes`, `spk:accessed_at`, `fetched_at`, `content_hash` | §3.5 | Each key is part of the public surface (see §3.5 ~line 421). |
| Sources never in retrieval (layer filter) | §3.5 / §5.9 | AMKB spec §2.2.9 alignment, frozen. |

#### 8.2.B Edge surface (§4)

| Decision | Section | Frozen surface |
|---|---|---|
| `REQUIRES/EXTENDS/CONTRASTS/RELATES_TO` → reserved AMKB rels | §4.3.A | Four-way mapping frozen. |
| `SUMMARIZES` hidden in v0.7.1, activated as `contains` in v0.8.x | §4.3.A | "Clean activation, no provisional `ext:` name" strategy frozen. |
| Bidirectional synapses published as two directed edges | §4.3.B | Lossless round-trip contract frozen. |
| `spk:weight` attribute name | §4.3.C | Name frozen. STDP internals stay private. |
| `spk:confidence`, `spk:confidence_score` attribute names | §4.3.D | Names frozen. |
| `neuron_source` junction → `derived_from` edges | §4.5 / §4.5.A | Rel choice frozen. |

#### 8.2.C Store / Transaction surface (§5)

| Decision | Section | Frozen surface |
|---|---|---|
| Structural Protocol conformance (no inheritance from `amkb.Store`) | §5.1 | Pattern frozen; applies to all future adapter classes. |
| `RetrievalHit.score` published as opaque monotone float | §5.9 | "Publish a score; contract is opaque / non-comparable across calls / monotone with list order" frozen. The **formula** is NOT frozen. |
| Sources filtered out of retrieval at the adapter (defense-in-depth) | §5.9 | Frozen. |

#### 8.2.D Error surface (§6)

| Decision | Section | Frozen surface |
|---|---|---|
| 22 canonical AMKB error codes | §6.7 / AMKB spec §5 | Frozen in `amkb-spec`, consumed here. |
| Two-stage translation: pre-translate via `amkb.validation`, post-translate from typed `SpikuitError` | §6.1 / §6.4 | Pattern frozen. |
| `EInternal` catch-all with mandatory `__cause__` and structured `details` | §6.6 / §6.6.A | Pattern frozen. Specific rows in §6.3 may evolve additively. |
| Translation table (Spikuit → AMKB) frozen at **Spikuit v1.0.0**, not at adapter v0.7.1 | §6.7 | See §8.4 — adapter rows refinable until daily use matures. |

### 8.3 NOT frozen — pre-release-only mechanics

These look like permanent decisions in §3–§7 but are
explicitly bridges. Calling them out prevents future readers
from mistaking them for part of the 1.0.0 surface.

| Mechanism | Section | Why it is not frozen |
|---|---|---|
| Sync-only `SpikuitStore` wrapping an owned event loop | §5.2 | Bridge until `amkb-sdk` 0.2.0 ships `AsyncStore`. When that lands, `SpikuitAsyncStore` becomes the primary surface and the sync variant is a thin shim. |
| `EdgeRef` synthesized by hashing `(pre, post, type, created_at)` | §4.4.A | v0.7.1 collision mitigation. Replaced by a stable `synapse.id` column in v0.7.2+. Consumers MUST treat `EdgeRef` as opaque and will be unaffected by the switch. |
| `ext:*` rels rejected at `link()` time | §5.4 / §5.4.A | v0.7.1 has no storage surface for them. If daily use surfaces a need, either a new reserved rel is proposed or `spikuit-core` adds a generic `ext_edge` side table. |
| `supports_*` L3 capability flags all `False` | §7.4 | L3 is scheduled for a dedicated milestone (v0.8.x candidate) — §7.8. |
| `derived_from` edge `created_at` synthesized from neuron's `created_at` | §4.5 | v0.7.2+ adds `neuron_source.created_at` column. |
| `Source.extractor` not populated / not published | §3.7 | Aligned with v0.8.x "daily use + extractor expansion" phase. |
| Individual rows in §6.3 translation table | §6.7 | Table shape is frozen; rows are refinable until Spikuit v1.0.0. |

### 8.4 Release sequencing — three 1.0.0s, not one

Three artifacts ship 1.0.0 independently:

| Artifact | What freezing means | When |
|---|---|---|
| **`amkb-spec` 1.0.0** | 22 canonical errors, reserved kinds/layers/rels, attestation edges, conformance level definitions are frozen. Post-1.0.0 evolution is strictly additive (new reserved rels allowed, renames forbidden). | **First.** The spec should outrun both implementations by design — freezing the protocol before consumers depend on it is safer than freezing it after. Target: once Spikuit has been in daily use against the SDK for ~2–3 months and no gaps are surfacing. |
| **`amkb-sdk` 1.0.0** | Store / Transaction Protocols, conformance suite, error classes, validation helpers frozen. Matches `amkb-spec` 1.0.0 one-to-one. | **Concurrent with or shortly after `amkb-spec` 1.0.0.** The SDK is a code expression of the spec; they should move together. A small lag is acceptable if conformance suite refinement is still happening. |
| **Spikuit 1.0.0 ("Daily Use Ready")** | CLI surface, Brain format, core engine semantics frozen. Adapter translation table (§6.3) frozen. Adapter feature parity at L1+L2+L4a+L4b confirmed against SDK 1.0.0. | **Last, and not gated on AMKB 1.0.0.** Spikuit's 1.0.0 criteria (memory `project_spikuit_roadmap_v06plus.md`) are user-facing daily-use readiness, not protocol alignment. An `amkb` pre-1.0.0 dependency is acceptable if the adapter is on a `<1.0.0` pin — Spikuit 1.0.0 can ship before AMKB 1.0.0. |

**Ordering rule.** `amkb-spec` freezes first because every
consumer (including Spikuit) needs a stable protocol before
their own 1.0.0 can mean anything. `amkb-sdk` and Spikuit
both depend on the spec, so spec movement is the expensive
one. The SDK is cheaper to bump because it has one
reference implementation (`DictStore`) inside its own tests;
Spikuit is the expensive downstream consumer.

**Back-sequencing (breaking order).** If we discover at
Spikuit 0.9.x that a decision in §8.2 is wrong, the order of
operations is:

1. File an `amkb-spec` RFC with the problem, proposed change,
   and migration path.
2. Land the change as a **pre-1.0.0 breaking release** of
   `amkb-spec` (e.g. `v0.3.0`), since we are still in the
   `0.x` window where breaking is allowed (CLAUDE.md:102).
3. Bump `amkb-sdk` to match, update the conformance suite.
4. Update Spikuit's adapter rows in §3–§6.
5. Emit one-time migration events in the Spikuit event log
   if existing Brains were affected.

This is why freezing before daily-use maturity is premature,
and why §8.5 insists on a `N months in production` criterion
before any of these are actually frozen.

### 8.5 "Ready to freeze" criteria and calendar

#### 8.5.A Criteria

A decision in §8.2 is not frozen until **all** of these hold:

1. **Daily-use time.** Spikuit has been the primary knowledge
   store for at least one user (the author) for **≥ 3 months**,
   with active writes and retrievals across all four reserved
   intra-concept rel types and `derived_from`. Importantly:
   the clock on this criterion starts **when daily use
   actually begins**, not when v0.7.1 ships.
2. **No open issues touching this surface.** If a decision is
   under discussion in an issue or branch, it is not frozen.
3. **At least one independent consumer.** The adapter has been
   exercised by at least one caller that is not Spikuit's own
   CLI — e.g., an external `amkb-sdk` consumer, a notebook
   driving the adapter directly, or another reference
   implementation. One caller is enough; this is an "is the
   surface shape usable" check, not a scale test. Note:
   Spikuit's own tutor / quiz / graph features (v0.8.x
   improvements) consume `Circuit` directly, not the adapter,
   so they do NOT satisfy this criterion.
4. **Spec + SDK alignment confirmed.** The decision exists in
   the spec, is tested by conformance, and the adapter row
   matches the test's expectations.

#### 8.5.B Calendar — phased roadmap

Daily use is **gated on pre-daily-use UX work**, not on
v0.7.1 landing. The realistic sequence:

| Phase | Spikuit version | Duration (rough) | What happens | Adapter daily-use clock |
|---|---|---|---|---|
| **Adapter land** | v0.7.1 | — | AMKB adapter + amkb-sdk 0.1.0 co-release. CI turns green on L1/L2/L4a/L4b. | Not started. |
| **Pre-daily-use UX** | v0.8.x | ~2–4 months | Tutor session improvements, quiz UI, neuron graph improvements, extractor expansion. The Spikuit CLI becomes pleasant enough to use as a primary knowledge store. These features consume `Circuit` directly, not the adapter. | Still not started — criterion 1 clock is paused, criterion 3 does not progress. |
| **Daily-use soak** | v0.8.x late → v0.9.x | **≥ 3 months** | Spikuit is the author's primary knowledge store. Adapter is exercised by at least one independent consumer (notebook, external SDK caller, second impl). | Running. All four criteria tracked. |
| **Freeze candidates** | v0.9.x | ~1 month | Every §8.2 row is explicitly checked against the four criteria. Rough edges file `amkb-spec` RFCs. | Closing. |
| **1.0.0 cut** | v1.0.0 | — | `amkb-spec` 1.0.0 → `amkb-sdk` 1.0.0 → Spikuit 1.0.0 ("Daily Use Ready"). | Frozen per §8.2. |

**Optimistic calendar from v0.7.1:** ~2–4 months v0.8.x UX
work + ≥ 3 months soak + ~1 month freeze = **~6–8 months
minimum** until any 1.0.0 cut, and realistically longer if
UX or soak phases surface unexpected work. Faster is unlikely
without skipping criteria.

**What this means for v0.7.1 scope.** The adapter ships green
and conformance-tested, but it is explicitly NOT exercised in
production during v0.8.x. That is fine — it is the stable
target that v0.8.x UX features can start depending on once
they need AMKB semantics (event log, lineage, etc.) rather
than raw `Circuit` calls. The adapter existing before daily
use gives v0.8.x features the option to build against it;
nothing forces them to.

#### 8.5.C Risk: adapter rot during v0.8.x

The adapter will sit without a production consumer for
months while v0.8.x UX work happens. Two safeguards keep it
from rotting:

- **Conformance on every PR (§7.6).** The SDK's own test
  suite is the baseline signal — if any Spikuit change to
  `Circuit` or `db.py` breaks a protocol guarantee, PR CI
  catches it. No adapter feature regression can land
  silently.
- **Nightly drift tier (§7.6).** Picks up SDK bumps even
  when no Spikuit code changes.

If a `Circuit` API change during v0.8.x requires an adapter
update, that update lands in the same PR. The adapter is
never left in a "doesn't compile" state — it is first-class
code from v0.7.1 onward, just without a production user
yet.

### 8.6 Escape hatches (additive-only evolution post-1.0.0)

Once any of the three 1.0.0s ships, the only allowed changes
are additive:

- **New reserved rels** — may be added to `amkb-spec` with a
  minor bump. Existing rels MUST NOT be renamed or removed.
- **New error codes** — may be added, but the category
  taxonomy (validation / not_found / state / invariant /
  internal) is frozen.
- **New capability flags** — may be added. Existing flags
  MUST keep their semantics; removing a flag is equivalent to
  removing a conformance level and is forbidden.
- **New Node / Edge attribute keys** — may be added. Existing
  `spk:*` keys are frozen; their values may be extended only
  if the schema is additive.
- **New conformance levels** (`L5`, `L6`, …) — may be added,
  but existing levels MUST NOT gain new tests. A passing L1
  impl today MUST still pass L1 after any future SDK release.

**What additive is NOT.** Changing a `SHOULD` to a `MUST`,
tightening a precondition, or adding a required attribute to
an existing kind/layer is a breaking change and needs a
major-version bump — which cannot happen once any consumer
is pinned on `<N.0.0`.

## 9. Open Questions

This section consolidates every item logged in §3.7, §4.6,
§5.11, §6.8, and §7.8. Two priority tags:

- **[blocking]** — must resolve before v0.7.1 coding starts.
- **[tracked]** — deferred to a later release; no blocker for
  v0.7.1.

### 9.1 Blocking for v0.7.1 coding

Items 1-4 were prerequisite `spikuit-core` patches that had to
land before the adapter PR could start. All four are now merged.
Items 5-6 are contract confirmations (no code) that the first
adapter PR pins down.

| # | Question | Origin | Disposition |
|---|---|---|---|
| 1 | **Retired-ref resolve bypass.** `Store.get_node` / `get_edge` must satisfy spec §3.4.1 ("retired MUST resolve"). | §3.7, §5.5 | ✅ Landed in `4d5db68`. `Circuit.get_neuron` / `Circuit.get_synapse` now take `include_retired: bool = False`, surfacing the existing db-layer flag. CLI paths keep the default. |
| 2 | **Typed Spikuit exceptions.** Replace bare `ValueError` / `RuntimeError` raises in `circuit.py` and `db.py` with typed classes so the adapter can pattern-match at its boundary. | §6.2 | ✅ Landed in `eda08ec`. New `spikuit_core/errors.py` houses `SpikuitError` base plus `NeuronNotFound` / `SynapseNotFound` / `SourceNotFound` / `NeuronAlreadyRetired` / `InvalidMergeTarget` / `DBNotConnected`. `transactions.py` re-exports the base. |
| 3 | **`Circuit.retrieve_scored` prerequisite.** `Circuit.retrieve` must expose per-hit scores so the adapter can populate `RetrievalHit.score`. | §5.9, §5.11 | ✅ Landed in `bd76a21`. New `Circuit.retrieve_scored(...) -> list[tuple[Neuron, float]]`; `retrieve` is now a thin shim that drops scores. Scores are documented as opaque / monotone-with-order. |
| 4 | **`db.list_changesets` helper for `Store.history`.** The adapter needs time-range / actor / tag filtered iteration over committed changesets. The `changeset` table already carries every needed column; no schema change. | §5.3 | ✅ Landed in `75eebb0`. `db.list_changesets(since=, until=, actor_id=, tag=, status="committed", limit=1000)` — ISO-8601 lexical comparison, ordered by `committed_at`. |
| 5 | **`EdgeRef` synthesis vs. `synapse.id` column.** v0.7.1 uses hash synthesis; v0.7.2+ adds a stable `synapse.id` column. Confirm the hash-synthesis shape in the first adapter PR so consumers know the key is opaque. | §4.4.A | Hash of `(pre, post, type, created_at)`. Opaque EdgeRef contract documented in the adapter README. |
| 6 | **`derived_from.created_at` synthesis.** Junction rows carry no timestamp; v0.7.1 derives from the concept neuron's `created_at`. Confirm consumers accept this in the L2 diff view. | §4.5, §4.6 | Document in §5.7 event mapping. Revisit when adding `neuron_source.created_at` column in v0.7.2+. |

**Non-blocking clarification — `revert` is L3-only.** A naive
reading of §5.3 might classify adapter `revert` as blocking
because the SDK `Store` Protocol defines it. It is not:
`amkb.conformance.test_l2_lineage` never calls `revert`, and L3
tests gate on `supports_merge_revert`, which v0.7.1 sets to
`False`. The adapter ships `revert` as a 1-line stub raising
`EConstraint` (see §5.3). No inverse logic, no `DictStore`
duplication. Tracked in §9.2 under the L3 milestone.

### 9.2 Tracked for v0.7.2+ or daily use

These are flagged and deferred with a clear reason. No
v0.7.1 blocker.

**Core / adapter surface (v0.7.2 range):**

- **`AsyncStore` Protocol in `amkb-sdk` 0.2.0.** The sync
  wrapper (§5.2) is a bridge. Once `amkb-sdk` ships
  `AsyncStore`, `SpikuitAsyncStore` becomes primary and
  `SpikuitStore` is a thin shim. Tracked against Spikuit
  v0.7.2.
- **`SpikuitStore.events(follow=True)`.** Tail-follow
  polling of the event table. Not required by conformance.
  Add with semantics in v0.7.2+. (§5.11)
- **Stable `synapse.id` column.** v0.7.2+ additive migration,
  replaces hash-synthesized EdgeRefs. (§4.6)
- **`neuron_source.created_at` column.** v0.7.2+ additive
  migration, replaces synthesis from neuron timestamp. (§4.6)
- **`Neuron.source` core field removal.** Adapter already
  drops the field (§3.3.E). Removing it from `spikuit-core`
  is a separate point release in v0.7.2+ per §1.3. (§3.7)
- **Edge-retirement cascade in adapter read path.** §5.6
  resolves the policy for v0.7.1; verify in first
  implementation PR and during soak that no live `derived_from`
  edges leak past a retired endpoint. (§4.6)
- **`neuron_source` hard cascade.** Verify the legacy
  `ON DELETE CASCADE` does not interfere with soft-retire
  during §5 implementation. (§4.6)

**Source metadata & extractor (v0.8.x daily-use phase):**

- **`filterable` / `searchable` attribute publishing.**
  Spikuit Source carries user-level metadata dicts that
  v0.7.1 does not publish. Revisit when daily use surfaces
  a need. (§3.7)
- **Extractor identity tracking.** `attrs["extractor"]` is
  a reserved AMKB key. Aligned with v0.8.x "daily use +
  extractor expansion" phase: once `Source.extractor` is
  added to core and populated by `spkt source ingest`, the
  adapter picks it up with a one-line mapping change. (§3.7)
- **Diagnostic `spk:scheduler_kind` tag.** Nice-to-have
  opaque attribute identifying which scheduler is active
  (currently always `"fsrs"`). Not blocking. (§3.7)
- **`SUMMARIZES` activation in v0.8.x.** Currently hidden
  from the adapter. When daily-use phase promotes
  Communities to `kind="category"` Nodes, re-enable as
  `SUMMARIZES → contains` with a one-time backfill. (§4.6)
- **Source content rewrite.** `SpikuitTransaction.rewrite`
  on a `kind="source"` node raises `EConstraint` in v0.7.1.
  Re-enable selectively if daily use surfaces a legitimate
  case. (§5.11)
- **`ext:*` rel round-trip.** Watch for daily-use edge
  kinds that do not fit the reserved rels. Fix is additive:
  propose a new reserved rel or add a generic `ext_edge`
  side table. (§5.11, §5.4.A)

**Performance & scale (triggered by growth):**

- **`find_by_attr` scan cost.** In-memory linear scan is
  fine for current Brain sizes. Add a secondary attr index
  once a Brain exceeds ~10k neurons. (§5.11)
- **Thread-safety of the owned event loop.** Single-loop
  assumption in §5.10. Document the constraint; revisit if
  a consumer needs multi-thread access. (§5.11)
- **Scaling the conformance fixture past ~300 tests.**
  §7.3.A lists three options (`.backup` snapshot/restore,
  `pytest-xdist`, warm Circuit pool). Pick one when wall
  time becomes a problem. (§7.8)

**Errors & CI (ongoing):**

- **Concurrency detection.** v0.7.1 never raises
  `EConcurrentModification`. If daily use surfaces a need
  (multi-agent brains), add optimistic-concurrency
  bookkeeping to the changeset flush path. Tied to the L3
  capability milestone (§8.3 / §7.8). (§6.8)
- **CLI UX regression during typed-exception patch.**
  Verify no user-facing error message changes badly when
  `spikuit-core` replaces bare `ValueError` with typed
  classes. (§6.8)
- **`sqlite-vec` availability in CI.** Extension must be
  installed on the CI image. Document alongside the `make
  conformance` target. (§7.8)
- **`amkb-drift` issue automation.** Nightly drift tier
  (§7.6) needs a GitHub Action that files an issue on first
  failure and closes it once the condition clears. (§7.8)

**Release milestones (aligned with §8):**

- **L3 full-capability release.** v0.7.1 opts out of all
  four L3 flags. Plan to deliver L3 in a dedicated
  milestone (v0.8.x or later) with concurrency detection,
  commit-time constraints, and merge-revert resurrection
  shipping together. (§7.8)

### 9.3 Questions not captured elsewhere

- **Adapter package rename.** Current layout
  (`spikuit-agents/amkb/`) couples the adapter to the
  `spikuit-agents` package. Consider a standalone
  `spikuit-amkb` package if a consumer wants the adapter
  without the full `spikuit-agents` dependency tree. Not
  urgent — defer until a concrete request.
- **Versioning of the adapter independently from
  `spikuit-core`.** Today they move together (§2.2 pins
  both to 0.7.1). An independent version number would let
  adapter bug-fix releases ship without a core bump. Low
  priority.

---

## Appendix A. Cross-references

- `amkb-integration-plan.md` — the v0.7.x rollout plan.
- `amkb-core-plumbing-spec.md` — what v0.7.0 shipped inside
  `spikuit-core`. This adapter consumes those primitives.
- `amkb-spec/spec/` — AMKB Protocol v0.2.0 reference.
- `amkb-sdk/src/amkb/` — SDK Protocol classes and conformance suite
  that this adapter targets.

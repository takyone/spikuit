"""SpikuitTransaction — synchronous ``amkb.Transaction`` over ``Circuit.transaction()``.

Drives :meth:`spikuit_core.Circuit.transaction` (an
``@asynccontextmanager``) manually via ``__aenter__``/``__aexit__`` on
the store's owned event loop. The :class:`_AbortSignal` sentinel pushes
the context manager down its except branch so aborted transactions mark
``status="aborted"`` in the changeset table without surfacing the
sentinel to AMKB callers.

Mutation surface
----------------

| AMKB op | Spikuit call |
|---------|--------------|
| ``create(kind=concept)`` | ``Circuit.add_neuron`` |
| ``create(kind=source)`` | raises ``EConstraint`` (§5.4 known gap — v0.7.0 does not emit source lifecycle events) |
| ``rewrite`` | ``Circuit.update_neuron`` (source rewrite → ``EConstraint``) |
| ``retire`` | ``Circuit.remove_neuron`` (source retire → ``EConstraint``) |
| ``merge`` | ``Circuit.merge_neurons`` then ``update_neuron`` to replace content |
| ``link`` (reserved rel) | ``Circuit.add_synapse`` |
| ``link(derived_from)`` | ``Circuit.attach_source`` (junction edge) |
| ``link(ext:*)`` | raises ``EConstraint`` — v0.7.1 only ships reserved rels |
| ``unlink(e-*)`` | ``Circuit.remove_synapse`` |
| ``unlink(j-*)`` | ``Circuit.detach_source`` |

Per design doc §5.4, ``get_node``/``get_edge`` inside a transaction
delegate back to the store. Spikuit's auto-tx writes land in SQLite
immediately (autocommit), so staged reads see through the buffer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import TYPE_CHECKING, Any


def _hex12() -> str:
    return uuid.uuid4().hex[:12]

from amkb.errors import EConstraint, ETransactionClosed
from amkb.refs import EdgeRef, NodeRef, TransactionRef
from amkb.types import (
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    REL_ATTESTED_BY,
    REL_CONTRADICTED_BY,
    REL_DERIVED_FROM,
)
from amkb.validation import (
    validate_concept_content,
    validate_edge_rel,
    validate_kind_layer,
    validate_merge_uniform,
)

import msgspec

from spikuit_core.models import Neuron, Source, SynapseType

from spikuit_agents.amkb._events import OP_SOURCE_ADD, OP_SOURCE_RETIRE
from spikuit_agents.amkb.errors import boundary
from spikuit_agents.amkb.mapping import (
    SYNAPSE_TYPE_TO_REL,
    edge_ref_for_synapse,
    junction_edge_ref,
    neuron_node_ref,
    source_node_ref,
)

if TYPE_CHECKING:
    import amkb

    from spikuit_agents.amkb.store import SpikuitStore


_REL_TO_SYNAPSE_TYPE: dict[str, SynapseType] = {
    rel: stype for stype, rel in SYNAPSE_TYPE_TO_REL.items()
}


class _AbortSignal(BaseException):
    """Adapter-private sentinel that drives ``Circuit.transaction()`` down
    its abort path via ``asynccontextmanager.__aexit__``.

    Never escapes the adapter — :meth:`SpikuitTransaction.abort` catches
    it in its own ``__aexit__`` bridge so callers only ever see
    :class:`amkb.AmkbError` subclasses.
    """


class SpikuitTransaction:
    """AMKB Transaction implementation backed by ``Circuit.transaction()``.

    Construct via :meth:`SpikuitStore.begin`; do not instantiate directly.
    Usage mirrors :class:`amkb.Transaction`: enter the context manager,
    perform mutations, either ``commit()`` explicitly or let the
    ``__exit__`` hook decide (abort on exception, commit on clean exit).
    """

    ref: TransactionRef  # set in __enter__ once the core tx is opened

    def __init__(
        self,
        store: "SpikuitStore",
        *,
        tag: str,
        actor: "amkb.Actor",
    ) -> None:
        self._store = store
        self.tag = tag
        self.actor = actor.id
        self._actor_obj = actor
        self._tx_ctx: Any = None  # @asynccontextmanager instance
        self._tx: Any = None  # core SpikuitTransaction
        self._closed = False

    # -- Context manager -----------------------------------------------

    def __enter__(self) -> "SpikuitTransaction":
        if self._closed:
            raise ETransactionClosed(f"transaction {self.ref} is already closed")
        if self._tx_ctx is not None:
            # Idempotent — store.begin() already opened the core tx so
            # the ``with`` block's enter is a no-op.
            return self
        # Spikuit core only accepts "human" | "agent" | "system". Anything
        # else (LLM, automation, composite) collapses to "agent" so the
        # event row still carries the original actor.id verbatim.
        actor_kind = self._actor_obj.kind
        if actor_kind not in ("human", "agent", "system"):
            actor_kind = "agent"
        with boundary():
            self._tx_ctx = self._store._circuit.transaction(
                tag=self.tag,
                actor_id=str(self.actor),
                actor_kind=actor_kind,  # type: ignore[arg-type]
            )
            self._tx = self._store._bridge.run(self._tx_ctx.__aenter__())
        self.ref = TransactionRef(self._tx.id)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._closed:
            return
        if exc is not None:
            # Propagate the user exception through the core tx's abort
            # branch so the changeset row is marked "aborted".
            self._drive_exit(exc_type, exc, tb)
        else:
            # Implicit commit on clean exit, matching amkb.Transaction
            # §3.5 semantics.
            try:
                self.commit()
            except ETransactionClosed:
                pass

    # -- Explicit lifecycle --------------------------------------------

    def commit(self) -> "amkb.ChangeSet":
        self._require_open()
        cs_id = self._tx.id
        with boundary():
            self._store._bridge.run(self._tx_ctx.__aexit__(None, None, None))
        self._closed = True
        # Re-read the committed changeset from the event log — this is
        # the canonical source for the returned AMKB ChangeSet.
        from amkb.refs import ChangeSetRef

        cs_ref = ChangeSetRef(cs_id)
        with boundary():
            return self._store._bridge.run(
                self._store._get_changeset_async(cs_ref)
            )

    def abort(self) -> None:
        if self._closed:
            return
        self._drive_exit(_AbortSignal, _AbortSignal(), None)

    def _drive_exit(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Drive the core ``@asynccontextmanager`` down its abort branch.

        Swallows the sentinel :class:`_AbortSignal`; lets any other
        exception propagate (wrapped as an AMKB error at the boundary).
        """
        try:
            with boundary():
                self._store._bridge.run(
                    self._tx_ctx.__aexit__(exc_type, exc, tb)
                )
        except _AbortSignal:
            pass
        finally:
            self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise ETransactionClosed(
                f"transaction {self.ref} is already closed"
            )
        if self._tx is None:
            raise ETransactionClosed(
                "transaction was never entered (use `with store.begin(...) as tx:`)"
            )

    # -- Node mutations ------------------------------------------------

    def create(
        self,
        *,
        kind: str,
        layer: str,
        content: str,
        attrs: dict[str, Any] | None = None,
    ) -> NodeRef:
        self._require_open()
        validate_kind_layer(kind, layer)
        validate_concept_content(kind, content)
        attrs = attrs or {}

        if kind == KIND_CONCEPT:
            neuron_kwargs: dict[str, Any] = {}
            spk_type = attrs.get("spk:type")
            if spk_type is not None:
                neuron_kwargs["type"] = spk_type
            domain = attrs.get("domain")
            if domain is not None:
                neuron_kwargs["domain"] = domain
            neuron = Neuron.create(content, **neuron_kwargs)
            with boundary():
                self._store._bridge.run(
                    self._store._circuit.add_neuron(neuron)
                )
            return neuron_node_ref(neuron.id)

        if kind == KIND_SOURCE:
            source = self._build_source(content=content, attrs=attrs)
            with boundary():
                self._store._bridge.run(
                    self._store._circuit.add_source(source)
                )
            # Core's add_source is event-log-silent in v0.7.0; we
            # inject a "source.add" event into the in-flight changeset
            # ourselves so the adapter's rehydrator (which now
            # recognises target_kind="source") sees it at commit time.
            self._emit_source_event(
                OP_SOURCE_ADD,
                source.id,
                after=source,
            )
            return source_node_ref(source.id)

        raise EConstraint(f"unsupported kind for Spikuit: {kind!r}")

    def _build_source(self, *, content: str, attrs: dict[str, Any]) -> Source:
        """Translate AMKB Source attrs back onto a :class:`spikuit_core.Source`.

        Inverse of :func:`spikuit_agents.amkb.mapping.source_to_node`.
        AMKB-reserved keys (``content_ref``, ``content_hash``,
        ``fetched_at``) promote to their native Source fields, while
        ``spk:*`` keys drop their prefix. Unknown keys are dropped in
        v0.7.1 (Source has no arbitrary-attr bag).
        """
        url = attrs.get("content_ref") or attrs.get("spk:storage_uri")
        title = attrs.get("spk:title") or content or None
        kwargs: dict[str, Any] = {}
        if url and isinstance(url, str) and url.startswith(("http://", "https://")):
            kwargs["url"] = url
        elif url is not None:
            kwargs["storage_uri"] = url
        if title is not None:
            kwargs["title"] = title
        for amkb_key, spk_attr in (
            ("spk:author", "author"),
            ("spk:section", "section"),
            ("spk:excerpt", "excerpt"),
            ("spk:notes", "notes"),
            ("spk:http_etag", "http_etag"),
            ("spk:http_last_modified", "http_last_modified"),
            ("spk:status", "status"),
        ):
            if amkb_key in attrs:
                kwargs[spk_attr] = attrs[amkb_key]
        if "content_hash" in attrs:
            kwargs["content_hash"] = attrs["content_hash"]
        source = Source(id=f"s-{_hex12()}", **kwargs)
        return source

    def _emit_source_event(
        self,
        op: str,
        source_id: str,
        *,
        before: Source | None = None,
        after: Source | None = None,
    ) -> None:
        """Append a source lifecycle event onto the in-flight core tx."""
        core_tx = self._store._circuit.current_transaction
        if core_tx is None:  # pragma: no cover — should never happen
            raise EConstraint("no active core transaction to emit source event")
        core_tx.emit(
            op,
            "source",
            source_id,
            before_json=msgspec.json.encode(before).decode() if before else None,
            after_json=msgspec.json.encode(after).decode() if after else None,
        )

    def rewrite(
        self, ref: NodeRef, *, content: str, reason: str,
    ) -> NodeRef:
        self._require_open()
        raw = str(ref)
        if not raw.startswith("n-"):
            raise EConstraint(
                "Spikuit v0.7.1 only supports rewriting concept nodes"
            )
        validate_concept_content(KIND_CONCEPT, content)
        with boundary():
            async def _do():
                neuron = await self._store._circuit.get_neuron(
                    raw, include_retired=True,
                )
                if neuron is None:
                    from amkb.errors import ENodeNotFound

                    raise ENodeNotFound(f"node not found: {ref}", ref=ref)
                if neuron.retired_at is not None:
                    from amkb.errors import ENodeAlreadyRetired

                    raise ENodeAlreadyRetired(
                        f"node {ref} is retired", ref=ref,
                    )
                neuron.content = content
                await self._store._circuit.update_neuron(neuron)

            self._store._bridge.run(_do())
        return ref

    def retire(self, ref: NodeRef, *, reason: str) -> None:
        self._require_open()
        raw = str(ref)
        if raw.startswith("n-"):
            with boundary():
                self._store._bridge.run(
                    self._store._circuit.remove_neuron(raw)
                )
            return
        if raw.startswith("s-"):
            with boundary():
                async def _do():
                    source = await self._store._circuit.get_source(raw)
                    if source is None or source.retired_at is not None:
                        return  # idempotent
                    before_snapshot = msgspec.structs.replace(source)
                    retired_at = datetime.now(timezone.utc)
                    # Core's ``update_source`` deliberately does not
                    # touch retired_at (soft-retire is not part of its
                    # public surface); write it directly so the event
                    # snapshot and subsequent reads see ``state=retired``.
                    from spikuit_core.db import _ts

                    await self._store._circuit._db.conn.execute(
                        "UPDATE source SET retired_at=? WHERE id=?",
                        (_ts(retired_at), source.id),
                    )
                    await self._store._circuit._db.conn.commit()
                    source.retired_at = retired_at
                    self._emit_source_event(
                        OP_SOURCE_RETIRE,
                        source.id,
                        before=before_snapshot,
                        after=source,
                    )

                self._store._bridge.run(_do())
            return
        raise EConstraint(f"unrecognized node ref prefix: {ref}")

    def merge(
        self,
        refs: list[NodeRef],
        *,
        content: str,
        attrs: dict[str, Any] | None = None,
        reason: str,
    ) -> NodeRef:
        self._require_open()
        if len(refs) < 2:
            raise EConstraint("merge requires at least two refs")
        raws = [str(r) for r in refs]
        if any(not r.startswith("n-") for r in raws):
            raise EConstraint(
                "Spikuit v0.7.1 only supports merging concept nodes"
            )

        # Spec §3.2.4: all merge candidates MUST share kind/layer.
        with boundary():
            async def _fetch() -> list[Any]:
                nodes = []
                for r in refs:
                    nodes.append(await self._store._get_node_async(r))
                return nodes

            fetched = self._store._bridge.run(_fetch())
        validate_merge_uniform(fetched)
        validate_concept_content(KIND_CONCEPT, content)

        # AMKB spec §3.2.4: merge MUST retire all k input refs and
        # create a new target node. Spikuit's native merge picks one
        # survivor, so the adapter creates a new neuron first and uses
        # that as into_id — every original (including what would have
        # been the survivor) ends up tombstoned. ``merge_neurons``
        # appends the source contents onto the target, so we rewrite
        # the final content back to ``content`` after the merge.
        target_neuron = Neuron.create(content)

        with boundary():
            async def _do():
                await self._store._circuit.add_neuron(target_neuron)
                await self._store._circuit.merge_neurons(
                    source_ids=raws, into_id=target_neuron.id,
                )
                merged = await self._store._circuit.get_neuron(target_neuron.id)
                if merged is not None and merged.content != content:
                    merged.content = content
                    await self._store._circuit.update_neuron(merged)

            self._store._bridge.run(_do())
        return neuron_node_ref(target_neuron.id)

    # -- Edge mutations ------------------------------------------------

    def link(
        self,
        src: NodeRef,
        dst: NodeRef,
        *,
        rel: str,
        attrs: dict[str, Any] | None = None,
    ) -> EdgeRef:
        self._require_open()
        with boundary():
            src_node = self._store._bridge.run(self._store._get_node_async(src))
            dst_node = self._store._bridge.run(self._store._get_node_async(dst))
        validate_edge_rel(rel, src_node, dst_node)

        # Spikuit has one junction table (neuron↔source). All three
        # concept→source rels (derived_from, attested_by,
        # contradicted_by) land on attach_source — the rel distinction
        # is v0.7.2+ work when we add a rel column to the junction.
        if rel in (REL_DERIVED_FROM, REL_ATTESTED_BY, REL_CONTRADICTED_BY):
            if src_node.layer != LAYER_CONCEPT or dst_node.layer != LAYER_SOURCE:
                raise EConstraint(
                    f"rel={rel!r} requires concept→source endpoints"
                )
            with boundary():
                self._store._bridge.run(
                    self._store._circuit.attach_source(str(src), str(dst))
                )
            return junction_edge_ref(str(src), str(dst))

        stype = _REL_TO_SYNAPSE_TYPE.get(rel)
        if stype is None:
            # ext:* and any non-reserved rel — v0.7.1 only ships the
            # four reserved concept rels.
            raise EConstraint(
                f"rel={rel!r} has no Spikuit mapping in v0.7.1; "
                f"supported rels: {sorted(_REL_TO_SYNAPSE_TYPE)} + 'derived_from'"
            )

        weight = 0.5
        if attrs is not None and "spk:weight" in attrs:
            weight = float(attrs["spk:weight"])

        with boundary():
            created = self._store._bridge.run(
                self._store._circuit.add_synapse(
                    str(src), str(dst), stype, weight=weight,
                )
            )
        # Bidirectional types return two synapses; the AMKB-facing ref
        # is the forward one to match what find_by_attr / get_edge will
        # return.
        return edge_ref_for_synapse(created[0])

    def unlink(self, ref: EdgeRef, *, reason: str) -> None:
        self._require_open()
        raw = str(ref)
        if raw.startswith("e-"):
            with boundary():
                async def _do():
                    edge = await self._store._find_synapse_edge_by_ref(ref)
                    if edge is None:
                        from amkb.errors import EEdgeNotFound

                        raise EEdgeNotFound(f"edge not found: {ref}", ref=ref)
                    # Recover (pre, post, type) from the raw synapse row.
                    rows = await self._store._circuit._db.get_all_synapses(
                        include_retired=True,
                    )
                    for syn in rows:
                        if syn.type == SynapseType.SUMMARIZES:
                            continue
                        if edge_ref_for_synapse(syn) == ref:
                            await self._store._circuit.remove_synapse(
                                syn.pre, syn.post, syn.type,
                            )
                            return

                self._store._bridge.run(_do())
            return

        if raw.startswith("j-"):
            with boundary():
                async def _do():
                    # Walk sources→neurons until we find the hash match.
                    sources = await self._store._circuit.list_sources(limit=10_000)
                    for source in sources:
                        neuron_ids = (
                            await self._store._circuit._db.get_neurons_for_source(
                                source.id,
                            )
                        )
                        for nid in neuron_ids:
                            if junction_edge_ref(nid, source.id) == ref:
                                await self._store._circuit.detach_source(
                                    nid, source.id,
                                )
                                return
                    from amkb.errors import EEdgeNotFound

                    raise EEdgeNotFound(f"edge not found: {ref}", ref=ref)

                self._store._bridge.run(_do())
            return

        raise EConstraint(f"unrecognized edge ref prefix: {ref}")

    # -- In-transaction queries ----------------------------------------

    def get_node(self, ref: NodeRef) -> "amkb.Node":
        # v0.7.1 staged-read gap: auto_tx writes land in SQLite
        # immediately, so the store's read path already sees them.
        return self._store.get_node(ref)

    def get_edge(self, ref: EdgeRef) -> "amkb.Edge":
        return self._store.get_edge(ref)


__all__ = ["SpikuitTransaction"]

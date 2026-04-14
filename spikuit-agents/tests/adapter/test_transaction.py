"""Integration tests for SpikuitTransaction against a real Circuit.

These tests drive :class:`SpikuitTransaction` through the sync surface,
covering commit/abort lifecycles plus every mutation operation listed
in design doc §5.4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from amkb.errors import EConstraint, EEdgeNotFound, ENodeNotFound
from amkb.types import (
    Actor,
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    REL_DERIVED_FROM,
    REL_REQUIRES,
)

from spikuit_agents.amkb.store import SpikuitStore
from spikuit_core import Circuit


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SpikuitStore]:
    circuit = Circuit(db_path=str(tmp_path / "circuit.db"))
    store = SpikuitStore.open(circuit)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def actor() -> Actor:
    return Actor(id="actor-test", kind="agent")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_commit_returns_changeset_with_events(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="test.create", actor=actor) as tx:
        ref = tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# Functor",
            attrs={"spk:type": "concept", "domain": "math"},
        )
        cs = tx.commit()

    assert cs.tag == "test.create"
    assert str(cs.actor) == "actor-test"
    assert any(e.kind == "node.created" for e in cs.events)
    # Node round-trip
    node = store.get_node(ref)
    assert node.content == "# Functor"
    assert node.attrs["domain"] == "math"


def test_context_manager_auto_commits_on_clean_exit(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="test.auto", actor=actor) as tx:
        tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# Monad",
            attrs={"spk:type": "concept"},
        )
    assert len(store.history()) == 1


def test_abort_rolls_back_changeset_status(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="test.abort", actor=actor) as tx:
        tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# Throwaway",
            attrs={"spk:type": "concept"},
        )
        tx.abort()
    # The changeset row still exists but is marked "aborted"; history()
    # only returns committed changesets, so an aborted tx is invisible.
    assert store.history() == []


def test_exception_inside_block_drives_abort(
    store: SpikuitStore, actor: Actor,
) -> None:
    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with store.begin(tag="test.raise", actor=actor) as tx:
            tx.create(
                kind=KIND_CONCEPT,
                layer=LAYER_CONCEPT,
                content="# Short-lived",
                attrs={"spk:type": "concept"},
            )
            raise Boom()
    assert store.history() == []


# ---------------------------------------------------------------------------
# Node mutations
# ---------------------------------------------------------------------------


def test_create_concept_round_trips(store: SpikuitStore, actor: Actor) -> None:
    with store.begin(tag="t", actor=actor) as tx:
        ref = tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# A",
            attrs={"spk:type": "concept", "domain": "math"},
        )
    node = store.get_node(ref)
    assert node.kind == KIND_CONCEPT
    assert node.attrs["domain"] == "math"


def test_create_source_raises_econstraint(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="t", actor=actor) as tx:
        with pytest.raises(EConstraint):
            tx.create(
                kind=KIND_SOURCE,
                layer=LAYER_SOURCE,
                content="Paper",
                attrs={"content_ref": "https://x.com/a"},
            )
        tx.abort()


def test_rewrite_updates_content_and_emits_event(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="t", actor=actor) as tx:
        ref = tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# Before",
            attrs={"spk:type": "concept"},
        )
    with store.begin(tag="t.rewrite", actor=actor) as tx:
        tx.rewrite(ref, content="# After", reason="correction")
        cs = tx.commit()
    assert any(e.kind == "node.rewritten" for e in cs.events)
    assert store.get_node(ref).content == "# After"


def test_retire_soft_retires_and_emits_event(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="t", actor=actor) as tx:
        ref = tx.create(
            kind=KIND_CONCEPT,
            layer=LAYER_CONCEPT,
            content="# Doomed",
            attrs={"spk:type": "concept"},
        )
    with store.begin(tag="t.retire", actor=actor) as tx:
        tx.retire(ref, reason="obsolete")
        cs = tx.commit()
    assert any(e.kind == "node.retired" for e in cs.events)
    assert store.get_node(ref).state == "retired"


def test_retire_source_ref_raises_econstraint(
    store: SpikuitStore, actor: Actor,
) -> None:
    from amkb.refs import NodeRef

    with store.begin(tag="t", actor=actor) as tx:
        with pytest.raises(EConstraint):
            tx.retire(NodeRef("s-nope"), reason="x")
        tx.abort()


def test_merge_collapses_concepts_and_replaces_content(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="seed", actor=actor) as tx:
        a = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept", "domain": "math"},
        )
        b = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# B", attrs={"spk:type": "concept", "domain": "math"},
        )
    with store.begin(tag="merge", actor=actor) as tx:
        survivor = tx.merge(
            [a, b], content="# Unified", reason="dup",
        )
    assert survivor == a
    node = store.get_node(survivor)
    assert node.content == "# Unified"
    assert store.get_node(b).state == "retired"


# ---------------------------------------------------------------------------
# Edge mutations
# ---------------------------------------------------------------------------


def test_link_requires_emits_edge_created(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="seed", actor=actor) as tx:
        a = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept"},
        )
        b = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# B", attrs={"spk:type": "concept"},
        )
    with store.begin(tag="link", actor=actor) as tx:
        edge_ref = tx.link(a, b, rel=REL_REQUIRES, attrs={"spk:weight": 0.9})
        cs = tx.commit()
    assert any(e.kind == "edge.created" for e in cs.events)
    edge = store.get_edge(edge_ref)
    assert edge.rel == REL_REQUIRES
    assert edge.attrs["spk:weight"] == pytest.approx(0.9)


def test_link_ext_rel_raises_econstraint(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="seed", actor=actor) as tx:
        a = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept"},
        )
        b = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# B", attrs={"spk:type": "concept"},
        )
    with store.begin(tag="link", actor=actor) as tx:
        with pytest.raises(EConstraint):
            tx.link(a, b, rel="ext:custom")
        tx.abort()


def test_unlink_retires_synapse(
    store: SpikuitStore, actor: Actor,
) -> None:
    with store.begin(tag="seed", actor=actor) as tx:
        a = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept"},
        )
        b = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# B", attrs={"spk:type": "concept"},
        )
        edge_ref = tx.link(a, b, rel=REL_REQUIRES)
    with store.begin(tag="unlink", actor=actor) as tx:
        tx.unlink(edge_ref, reason="bad data")
        cs = tx.commit()
    assert any(e.kind == "edge.retired" for e in cs.events)
    assert store.get_edge(edge_ref).state == "retired"


def test_link_derived_from_via_existing_source(
    store: SpikuitStore, actor: Actor,
) -> None:
    # Sources cannot be created through Transaction.create in v0.7.1,
    # so seed one directly on the Circuit.
    from spikuit_core.models import Source

    source = Source(title="Paper", url="https://x.com/a")
    store._bridge.run(store._circuit.add_source(source))

    with store.begin(tag="seed-concept", actor=actor) as tx:
        concept = tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept"},
        )
    from amkb.refs import NodeRef

    source_ref = NodeRef(source.id)
    with store.begin(tag="attach", actor=actor) as tx:
        edge_ref = tx.link(concept, source_ref, rel=REL_DERIVED_FROM)
    edge = store.get_edge(edge_ref)
    assert edge.rel == REL_DERIVED_FROM
    assert str(edge.src) == str(concept)
    assert str(edge.dst) == source.id


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_double_commit_raises(store: SpikuitStore, actor: Actor) -> None:
    from amkb.errors import ETransactionClosed

    with store.begin(tag="t", actor=actor) as tx:
        tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# A", attrs={"spk:type": "concept"},
        )
        tx.commit()
        with pytest.raises(ETransactionClosed):
            tx.commit()


def test_use_after_commit_raises(store: SpikuitStore, actor: Actor) -> None:
    from amkb.errors import ETransactionClosed

    tx = store.begin(tag="t", actor=actor)
    tx.__enter__()
    tx.create(
        kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
        content="# A", attrs={"spk:type": "concept"},
    )
    tx.commit()
    with pytest.raises(ETransactionClosed):
        tx.create(
            kind=KIND_CONCEPT, layer=LAYER_CONCEPT,
            content="# B", attrs={"spk:type": "concept"},
        )

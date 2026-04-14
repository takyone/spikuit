"""Tests for Circuit.transaction() — AMKB v0.7.0 plumbing."""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core.circuit import Circuit
from spikuit_core.transactions import (
    OP_NEURON_ADD,
    SpikuitTransaction,
    TransactionAbortedError,
    TransactionNestingError,
)


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "tx.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_transaction_commit_no_events(circuit):
    async with circuit.transaction(actor_id="tester") as tx:
        assert circuit.current_transaction is tx
        assert tx.status == "open"
    assert tx.status == "committed"
    assert circuit.current_transaction is None

    row = await circuit._db.get_changeset(tx.id)
    assert row is not None
    assert row["status"] == "committed"
    assert row["committed_at"] is not None
    assert row["actor_id"] == "tester"
    assert row["actor_kind"] == "agent"


@pytest.mark.asyncio
async def test_transaction_commit_with_events(circuit):
    async with circuit.transaction(
        actor_id="tester", actor_kind="human", tag="ingest:test",
    ) as tx:
        tx.emit(OP_NEURON_ADD, "neuron", "n1", after_json='{"id":"n1"}')
        tx.emit(OP_NEURON_ADD, "neuron", "n2", after_json='{"id":"n2"}')

    events = await circuit._db.list_events(changeset_id=tx.id)
    assert len(events) == 2
    assert [e["target_id"] for e in events] == ["n1", "n2"]
    assert [e["seq"] for e in events] == [0, 1]
    assert events[0]["op"] == OP_NEURON_ADD
    assert events[0]["after_json"] == '{"id":"n1"}'

    row = await circuit._db.get_changeset(tx.id)
    assert row["tag"] == "ingest:test"
    assert row["actor_kind"] == "human"


@pytest.mark.asyncio
async def test_transaction_abort_on_exception(circuit):
    captured: SpikuitTransaction | None = None
    with pytest.raises(RuntimeError, match="boom"):
        async with circuit.transaction(actor_id="tester") as tx:
            captured = tx
            tx.emit(OP_NEURON_ADD, "neuron", "n1")
            raise RuntimeError("boom")

    assert captured is not None
    assert captured.status == "aborted"
    assert circuit.current_transaction is None

    row = await circuit._db.get_changeset(captured.id)
    assert row["status"] == "aborted"
    assert row["committed_at"] is None

    # No event rows were flushed.
    events = await circuit._db.list_events(changeset_id=captured.id)
    assert events == []


@pytest.mark.asyncio
async def test_nested_transaction_raises(circuit):
    async with circuit.transaction(actor_id="tester") as outer:
        with pytest.raises(TransactionNestingError):
            async with circuit.transaction(actor_id="tester"):
                pass
        # outer is still active and usable
        assert circuit.current_transaction is outer
    assert outer.status == "committed"


@pytest.mark.asyncio
async def test_emit_after_abort_raises(circuit):
    captured: SpikuitTransaction | None = None
    with pytest.raises(RuntimeError):
        async with circuit.transaction(actor_id="tester") as tx:
            captured = tx
            raise RuntimeError("boom")

    assert captured is not None
    with pytest.raises(TransactionAbortedError):
        captured.emit(OP_NEURON_ADD, "neuron", "n1")


@pytest.mark.asyncio
async def test_two_sequential_transactions(circuit):
    async with circuit.transaction(actor_id="t1") as tx1:
        tx1.emit(OP_NEURON_ADD, "neuron", "n1")
    async with circuit.transaction(actor_id="t2") as tx2:
        tx2.emit(OP_NEURON_ADD, "neuron", "n2")

    assert tx1.id != tx2.id
    all_events = await circuit._db.list_events()
    assert {e["target_id"] for e in all_events} == {"n1", "n2"}


@pytest.mark.asyncio
async def test_list_changesets_filters(circuit):
    async with circuit.transaction(actor_id="alice", tag="ingest:a") as tx_a:
        tx_a.emit(OP_NEURON_ADD, "neuron", "n1")
    async with circuit.transaction(actor_id="bob", tag="ingest:b") as tx_b:
        tx_b.emit(OP_NEURON_ADD, "neuron", "n2")
    async with circuit.transaction(actor_id="alice", tag="review") as tx_c:
        tx_c.emit(OP_NEURON_ADD, "neuron", "n3")

    # Open an uncommitted tx via an abort to confirm the default
    # status="committed" filter hides it.
    with pytest.raises(RuntimeError):
        async with circuit.transaction(actor_id="alice") as tx_d:
            raise RuntimeError("rollback")
    assert tx_d.status == "aborted"

    all_committed = await circuit._db.list_changesets()
    ids = {c["id"] for c in all_committed}
    assert ids == {tx_a.id, tx_b.id, tx_c.id}
    assert all(c["status"] == "committed" for c in all_committed)
    # Ordered by committed_at ascending.
    committed_order = [c["id"] for c in all_committed]
    assert committed_order == [tx_a.id, tx_b.id, tx_c.id]

    by_actor = await circuit._db.list_changesets(actor_id="alice")
    assert {c["id"] for c in by_actor} == {tx_a.id, tx_c.id}

    by_tag = await circuit._db.list_changesets(tag="ingest:b")
    assert {c["id"] for c in by_tag} == {tx_b.id}

    with_aborted = await circuit._db.list_changesets(status=None)
    assert tx_d.id in {c["id"] for c in with_aborted}

    # Time range: pick the middle row's committed_at as a lower bound.
    middle = all_committed[1]["committed_at"]
    since_middle = await circuit._db.list_changesets(since=middle)
    assert {c["id"] for c in since_middle} == {tx_b.id, tx_c.id}

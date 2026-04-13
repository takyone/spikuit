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

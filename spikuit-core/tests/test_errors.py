"""Tests for the typed Spikuit exception module (errors.py).

Verifies:
- Every typed error is a subclass of SpikuitError (adapter-side pattern
  matching depends on the common base).
- SpikuitError is importable from both spikuit_core.errors and
  spikuit_core.transactions (transactions re-exports for back-compat).
- The classes that ``circuit.py`` / ``db.py`` raise are actually
  importable from the public namespace.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from spikuit_core import (
    DBNotConnected,
    InvalidMergeTarget,
    NeuronAlreadyRetired,
    NeuronNotFound,
    SourceNotFound,
    SpikuitError,
    SynapseNotFound,
)
from spikuit_core.circuit import Circuit
from spikuit_core.models import Neuron, SynapseType


def test_all_typed_errors_inherit_spikuit_error():
    for cls in (
        NeuronNotFound,
        SynapseNotFound,
        SourceNotFound,
        NeuronAlreadyRetired,
        InvalidMergeTarget,
        DBNotConnected,
    ):
        assert issubclass(cls, SpikuitError)
        assert issubclass(cls, Exception)


def test_transactions_module_reexports_base():
    # transactions.py's TransactionNestingError subclasses the same base,
    # so a blanket `except SpikuitError` at the adapter boundary catches
    # every Spikuit-raised exception.
    from spikuit_core.transactions import (
        SpikuitError as TxBase,
        TransactionNestingError,
    )

    assert TxBase is SpikuitError
    assert issubclass(TransactionNestingError, SpikuitError)


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "errors.db")
    await c.connect()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_add_synapse_raises_neuron_not_found(circuit):
    a = Neuron.create("A")
    await circuit.add_neuron(a)

    # b does not exist.
    with pytest.raises(NeuronNotFound):
        await circuit.add_synapse(a.id, "n-missing", SynapseType.RELATES_TO)


@pytest.mark.asyncio
async def test_set_synapse_weight_raises_synapse_not_found(circuit):
    a = Neuron.create("A")
    b = Neuron.create("B")
    await circuit.add_neuron(a)
    await circuit.add_neuron(b)

    with pytest.raises(SynapseNotFound):
        await circuit.set_synapse_weight(
            a.id, b.id, SynapseType.RELATES_TO, 0.5,
        )


@pytest.mark.asyncio
async def test_merge_into_in_sources_raises_invalid_merge_target(circuit):
    t = Neuron.create("T")
    await circuit.add_neuron(t)

    with pytest.raises(InvalidMergeTarget):
        await circuit.merge_neurons([t.id], t.id)


@pytest.mark.asyncio
async def test_merge_missing_target_raises_invalid_merge_target(circuit):
    a = Neuron.create("A")
    await circuit.add_neuron(a)

    with pytest.raises(InvalidMergeTarget):
        await circuit.merge_neurons([a.id], "n-missing")


@pytest.mark.asyncio
async def test_merge_missing_source_raises_neuron_not_found(circuit):
    t = Neuron.create("T")
    await circuit.add_neuron(t)

    with pytest.raises(NeuronNotFound):
        await circuit.merge_neurons(["n-missing"], t.id)


@pytest.mark.asyncio
async def test_db_not_connected_raises_typed_error(tmp_path):
    c = Circuit(db_path=tmp_path / "disconnected.db")
    # Intentionally skip connect(). Accessing the conn property must
    # surface the typed DBNotConnected error rather than a bare
    # RuntimeError so the adapter can pattern-match.
    with pytest.raises(DBNotConnected):
        _ = c._db.conn

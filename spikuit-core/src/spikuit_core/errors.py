"""Typed Spikuit core exceptions.

This module houses every exception class that ``spikuit-core`` raises
to its callers. The AMKB adapter (``spikuit-agents``) catches these
typed classes and translates each to the matching ``amkb.AmkbError``
canonical code at the boundary — see
``docs/design/amkb-adapter-v0.7.1.md`` §6 for the full table.

Design intent
-------------
Before these typed classes existed, several call sites in
``circuit.py`` / ``db.py`` raised bare ``ValueError`` / ``RuntimeError``.
Catching those broadly at the adapter boundary would also catch
unrelated bugs and mask them as ``EConstraint`` / ``EInternal``. Each
condition therefore gets its own class so the adapter can dispatch
deterministically.

``SpikuitError`` is the common base. ``transactions.py`` re-exports
it and defines its own tx-specific subclasses
(``TransactionNestingError``, ``TransactionAbortedError``) to keep the
transaction module self-contained.
"""

from __future__ import annotations


class SpikuitError(Exception):
    """Base class for every Spikuit core exception."""


class NeuronNotFound(SpikuitError):
    """A referenced Neuron ID does not resolve to a live row.

    Use ``Circuit.get_neuron(id, include_retired=True)`` when the
    caller needs retired rows to resolve as well.
    """


class SynapseNotFound(SpikuitError):
    """A referenced ``(pre, post, type)`` synapse does not exist."""


class SourceNotFound(SpikuitError):
    """A referenced Source ID does not resolve."""


class NeuronAlreadyRetired(SpikuitError):
    """Operation rejected because the target Neuron is already retired.

    Raised by mutation paths (``update_neuron``, ``add_synapse``, etc.)
    when one of the endpoints is no longer live. Idempotent retires
    (re-retiring an already-retired neuron) do **not** raise this —
    see ``Circuit.remove_neuron`` for the idempotent contract.
    """


class InvalidMergeTarget(SpikuitError):
    """``Circuit.merge_neurons`` called with a structurally invalid target.

    Covers two conditions:

    * ``into_id`` is also in ``source_ids`` (merging a neuron into
      itself is ill-defined).
    * ``into_id`` does not resolve to a live neuron.

    Both are structural impossibilities rather than input validation
    problems, so the adapter maps this to ``EConstraint``.
    """


class DBNotConnected(SpikuitError):
    """``Database.conn`` accessed before ``Database.connect()`` completed.

    Indicates a Circuit lifecycle bug on the caller side (forgot to
    ``await circuit.connect()``). The adapter surfaces this as
    ``EInternal`` — there is no useful retry for it, but the caller
    may want to surface a distinct "forgot to connect" error in their
    own logs.
    """


__all__ = [
    "SpikuitError",
    "NeuronNotFound",
    "SynapseNotFound",
    "SourceNotFound",
    "NeuronAlreadyRetired",
    "InvalidMergeTarget",
    "DBNotConnected",
]

"""AMKB adapter for Spikuit.

Exposes a :class:`~amkb.Store` / :class:`~amkb.Transaction` Protocol
implementation that sits on top of :class:`spikuit_core.Circuit`.
Downstream AMKB tooling (e.g., ``amkb.conformance``) consumes Spikuit
through this namespace, not through ``spikuit_core`` directly.

Only :class:`SpikuitStore` and :class:`SpikuitTransaction` are public.
Mapping helpers, the sync/async bridge, and error-translation tables
are implementation details kept under the package's internal modules.
"""

from __future__ import annotations

from spikuit_agents.amkb.store import SpikuitStore
from spikuit_agents.amkb.transaction import SpikuitTransaction

__all__ = ["SpikuitStore", "SpikuitTransaction"]

"""AMKB protocol adapter for Spikuit.

Exposes a `SpikuitStore` that satisfies `amkb.Store`, backed by the
`spikuit_core.Circuit` engine. Sync Store/Transaction Protocols are
bridged to async Circuit calls via a persistent background event loop.
"""

from spikuit_agents.amkb.store import SpikuitStore
from spikuit_agents.amkb.transaction import SpikuitStoreTransaction

__all__ = ["SpikuitStore", "SpikuitStoreTransaction"]

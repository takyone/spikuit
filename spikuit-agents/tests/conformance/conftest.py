"""Wire ``amkb.conformance`` tests against :class:`SpikuitStore`.

The sibling ``test_l*.py`` modules re-export the test functions from
``amkb.conformance``; pytest then drives each one against the
``store`` fixture defined here (a fresh in-memory Circuit per test).
The ``actor`` fixture is re-exported from the SDK's own default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

# Re-export the default actor fixture so collected test functions can
# request it without importing it explicitly.
from amkb.conformance.fixtures import actor  # noqa: F401

from spikuit_agents.amkb.store import SpikuitStore
from spikuit_core import Circuit


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SpikuitStore]:
    circuit = Circuit(db_path=str(tmp_path / "conformance.db"))
    store = SpikuitStore.open(circuit)
    try:
        yield store
    finally:
        store.close()

"""Pytest fixtures for the spikuit-agents test suite.

Re-exports `actor` from `amkb.conformance.fixtures` and provides a
`store` fixture backed by `SpikuitStore`. `tests/test_amkb_conformance.py`
re-imports the conformance test functions, so the AMKB matrix runs
against this adapter instead of the SDK's reference dict store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amkb.conformance.fixtures import actor  # noqa: F401  (re-export)
from spikuit_agents.amkb.store import SpikuitStore


@pytest.fixture
def store(tmp_path: Path):
    """Fresh SpikuitStore backed by a temporary SQLite Brain."""
    db_path = tmp_path / "amkb-conformance.db"
    s = SpikuitStore.open(str(db_path))
    try:
        yield s
    finally:
        s.close()

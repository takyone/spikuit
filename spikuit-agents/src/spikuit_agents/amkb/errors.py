"""Spikuit → AMKB exception translation.

The adapter catches typed :class:`spikuit_core.SpikuitError` subclasses
raised by Circuit/db and re-raises the matching
:class:`amkb.AmkbError` canonical code. See design doc §6.3 for the
full translation table.

Unhandled exceptions fall through to :class:`amkb.EInternal` with
``__cause__`` preserved so callers can still see the original failure
during debugging.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from amkb.errors import (
    AmkbError,
    EConstraint,
    EEdgeNotFound,
    EInternal,
    ENodeAlreadyRetired,
    ENodeNotFound,
    ETransactionClosed,
)
from spikuit_core import (
    DBNotConnected,
    InvalidMergeTarget,
    NeuronAlreadyRetired,
    NeuronNotFound,
    SourceNotFound,
    SpikuitError,
    SynapseNotFound,
)
from spikuit_core.circuit import ReadOnlyError
from spikuit_core.transactions import (
    TransactionAbortedError,
    TransactionNestingError,
)

T = TypeVar("T")


def translate(exc: BaseException) -> AmkbError | None:
    """Map a Spikuit exception to the matching AMKB error, or ``None``.

    Returns ``None`` when the caller should re-raise the original
    exception unchanged (e.g., it already is an ``AmkbError`` or a
    system-level ``BaseException`` like ``KeyboardInterrupt``).
    """
    if isinstance(exc, AmkbError):
        return None
    if isinstance(exc, (NeuronNotFound, SourceNotFound)):
        return ENodeNotFound(str(exc))
    if isinstance(exc, SynapseNotFound):
        return EEdgeNotFound(str(exc))
    if isinstance(exc, NeuronAlreadyRetired):
        return ENodeAlreadyRetired(str(exc))
    if isinstance(exc, InvalidMergeTarget):
        return EConstraint(str(exc))
    if isinstance(exc, TransactionNestingError):
        return EConstraint(f"transaction already active: {exc}")
    if isinstance(exc, TransactionAbortedError):
        return ETransactionClosed(str(exc))
    if isinstance(exc, ReadOnlyError):
        return EConstraint(f"circuit is read-only: {exc}")
    if isinstance(exc, DBNotConnected):
        return EInternal(str(exc))
    if isinstance(exc, SpikuitError):
        # Unknown SpikuitError subclass — surface as EInternal so the
        # adapter never silently drops a core-raised error category.
        return EInternal(f"unhandled SpikuitError: {exc}")
    return None


@contextmanager
def boundary():
    """Catch Spikuit exceptions and re-raise as AMKB canonical errors.

    Use at every method that crosses from adapter code into
    ``spikuit_core``. Keeps ``__cause__`` so the original traceback
    survives in logs.
    """
    try:
        yield
    except AmkbError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        translated = translate(exc)
        if translated is None:
            # Non-Spikuit, non-AMKB exception (e.g. sqlite3 error). Wrap
            # as EInternal so adapter consumers always see a canonical
            # code at the boundary.
            raise EInternal(f"unexpected error: {exc}") from exc
        raise translated from exc


def translating(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator form of :func:`boundary` for method-level use."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        with boundary():
            return func(*args, **kwargs)

    return wrapper


__all__ = ["boundary", "translate", "translating"]

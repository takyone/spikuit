"""EdgeRef encoding.

Spikuit keys synapses by the triple `(pre, post, type)`; AMKB addresses
edges by a single `EdgeRef` string. We encode the triple with a
separator unlikely to appear in neuron IDs. Keep encode/decode in one
place so the format is never duplicated.
"""

from __future__ import annotations

from amkb.refs import EdgeRef

_SEP = "|"


def encode_edge_ref(pre: str, post: str, rel: str) -> EdgeRef:
    return EdgeRef(f"{pre}{_SEP}{post}{_SEP}{rel}")


def decode_edge_ref(ref: EdgeRef) -> tuple[str, str, str]:
    parts = str(ref).split(_SEP)
    if len(parts) != 3:
        raise ValueError(f"invalid EdgeRef: {ref!r}")
    return parts[0], parts[1], parts[2]

"""Unit tests for spikuit_agents.amkb.mapping codecs.

These tests exercise the pure Spikuit ↔ AMKB translation without
touching a Circuit or SQLite. They pin the mapping decisions recorded
in design doc §3 / §4 so that a future edit to the codec table is
forced to update the corresponding test.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from amkb.types import (
    KIND_CONCEPT,
    KIND_SOURCE,
    LAYER_CONCEPT,
    LAYER_SOURCE,
    REL_CONTRASTS,
    REL_DERIVED_FROM,
    REL_EXTENDS,
    REL_RELATES_TO,
    REL_REQUIRES,
)
from spikuit_agents.amkb.mapping import (
    SYNAPSE_TYPE_TO_REL,
    datetime_to_timestamp,
    edge_ref_for_synapse,
    junction_edge,
    neuron_to_node,
    source_to_node,
    synapse_to_edge,
)
from spikuit_core import Neuron, Source, Synapse
from spikuit_core.models import SynapseConfidence, SynapseType


# ---------------------------------------------------------------------------
# Timestamp conversion
# ---------------------------------------------------------------------------


def test_datetime_to_timestamp_microseconds():
    dt = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    ts = datetime_to_timestamp(dt)
    assert ts == int(dt.timestamp() * 1_000_000)


def test_datetime_to_timestamp_none():
    assert datetime_to_timestamp(None) is None


def test_datetime_to_timestamp_monotonic_on_microsecond_bumps():
    a = datetime(2026, 4, 14, 12, 0, 0, 100, tzinfo=timezone.utc)
    b = datetime(2026, 4, 14, 12, 0, 0, 200, tzinfo=timezone.utc)
    assert datetime_to_timestamp(a) < datetime_to_timestamp(b)


# ---------------------------------------------------------------------------
# neuron_to_node
# ---------------------------------------------------------------------------


def test_neuron_to_node_uniform_kind_and_layer():
    n = Neuron(id="n-aaa", content="# Functor\n\nbody", type="concept", domain="math")
    node = neuron_to_node(n)
    assert node.kind == KIND_CONCEPT
    assert node.layer == LAYER_CONCEPT
    assert node.ref == "n-aaa"


def test_neuron_to_node_content_is_raw_with_frontmatter():
    content = "---\ntype: concept\n---\n# Functor"
    n = Neuron.create(content)
    node = neuron_to_node(n)
    assert node.content == content  # §3.3.A: raw publish


def test_neuron_to_node_attrs_spk_type_and_domain():
    n = Neuron(id="n-1", content="x", type="procedure", domain="math")
    node = neuron_to_node(n)
    assert node.attrs["spk:type"] == "procedure"
    assert node.attrs["domain"] == "math"


def test_neuron_to_node_omits_null_attrs():
    n = Neuron(id="n-1", content="x")
    node = neuron_to_node(n)
    assert "spk:type" not in node.attrs
    assert "domain" not in node.attrs
    assert "spk:last_reviewed_at" not in node.attrs
    assert "spk:due_at" not in node.attrs


def test_neuron_to_node_fsrs_attrs_injected_by_store():
    n = Neuron(id="n-1", content="x")
    reviewed = datetime(2026, 4, 1, tzinfo=timezone.utc)
    due = datetime(2026, 4, 20, tzinfo=timezone.utc)
    node = neuron_to_node(n, last_reviewed_at=reviewed, due_at=due)
    assert node.attrs["spk:last_reviewed_at"] == datetime_to_timestamp(reviewed)
    assert node.attrs["spk:due_at"] == datetime_to_timestamp(due)


def test_neuron_to_node_retired_state_and_timestamp():
    retired = datetime(2026, 4, 10, tzinfo=timezone.utc)
    n = Neuron(id="n-1", content="x", retired_at=retired)
    node = neuron_to_node(n)
    assert node.state == "retired"
    assert node.retired_at == datetime_to_timestamp(retired)


def test_neuron_to_node_live_has_no_retired_at():
    n = Neuron(id="n-1", content="x")
    node = neuron_to_node(n)
    assert node.state == "live"
    assert node.retired_at is None


def test_neuron_to_node_drops_legacy_source_field():
    n = Neuron(id="n-1", content="x", source="https://legacy.example")
    node = neuron_to_node(n)
    assert "spk:source_ref" not in node.attrs
    assert "source" not in node.attrs


# ---------------------------------------------------------------------------
# source_to_node
# ---------------------------------------------------------------------------


def test_source_to_node_uniform_kind_and_layer():
    s = Source(id="s-abc", title="Paper")
    node = source_to_node(s)
    assert node.kind == KIND_SOURCE
    assert node.layer == LAYER_SOURCE
    assert node.ref == "s-abc"


def test_source_to_node_content_prefers_title():
    s = Source(id="s-abc", title="Paper", url="https://x.com/a")
    assert source_to_node(s).content == "Paper"


def test_source_to_node_content_falls_back_to_url():
    s = Source(id="s-abc", url="https://x.com/a")
    assert source_to_node(s).content == "https://x.com/a"


def test_source_to_node_content_falls_back_to_untitled():
    s = Source(id="s-abc")
    assert source_to_node(s).content == "Untitled source"


def test_source_to_node_content_ref_prefers_url():
    s = Source(id="s-abc", url="https://x.com/a", storage_uri="file:///tmp/a")
    assert source_to_node(s).attrs["content_ref"] == "https://x.com/a"


def test_source_to_node_content_ref_falls_back_to_storage_uri():
    s = Source(id="s-abc", storage_uri="file:///tmp/a")
    assert source_to_node(s).attrs["content_ref"] == "file:///tmp/a"


def test_source_to_node_storage_uri_published_when_distinct():
    s = Source(id="s-abc", url="https://x.com/a", storage_uri="file:///tmp/a")
    assert source_to_node(s).attrs["spk:storage_uri"] == "file:///tmp/a"


def test_source_to_node_storage_uri_hidden_when_equal_to_url():
    s = Source(id="s-abc", url="file:///tmp/a", storage_uri="file:///tmp/a")
    assert "spk:storage_uri" not in source_to_node(s).attrs


def test_source_to_node_reserved_attrs_promoted():
    s = Source(
        id="s-abc",
        title="T",
        content_hash="sha256:deadbeef",
        fetched_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    node = source_to_node(s)
    assert node.attrs["content_hash"] == "sha256:deadbeef"
    assert node.attrs["fetched_at"] == datetime_to_timestamp(s.fetched_at)


def test_source_to_node_spk_namespace_covers_all_metadata():
    s = Source(
        id="s-abc",
        title="T",
        author="A",
        section="§1",
        excerpt="ex",
        notes="n",
        status="active",
        http_etag="etag-1",
        http_last_modified="Mon, 01 Apr 2026 00:00:00 GMT",
        accessed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    attrs = source_to_node(s).attrs
    for key in [
        "spk:title",
        "spk:author",
        "spk:section",
        "spk:excerpt",
        "spk:notes",
        "spk:status",
        "spk:http_etag",
        "spk:http_last_modified",
        "spk:accessed_at",
    ]:
        assert key in attrs, f"missing {key}"


def test_source_to_node_retired_state():
    retired = datetime(2026, 4, 10, tzinfo=timezone.utc)
    s = Source(id="s-abc", title="T", retired_at=retired)
    node = source_to_node(s)
    assert node.state == "retired"
    assert node.retired_at == datetime_to_timestamp(retired)


# ---------------------------------------------------------------------------
# synapse_to_edge
# ---------------------------------------------------------------------------


def test_synapse_type_to_rel_table_covers_four_reserved():
    assert SYNAPSE_TYPE_TO_REL[SynapseType.REQUIRES] == REL_REQUIRES
    assert SYNAPSE_TYPE_TO_REL[SynapseType.EXTENDS] == REL_EXTENDS
    assert SYNAPSE_TYPE_TO_REL[SynapseType.CONTRASTS] == REL_CONTRASTS
    assert SYNAPSE_TYPE_TO_REL[SynapseType.RELATES_TO] == REL_RELATES_TO
    assert SynapseType.SUMMARIZES not in SYNAPSE_TYPE_TO_REL


@pytest.mark.parametrize(
    ("type_", "rel"),
    [
        (SynapseType.REQUIRES, REL_REQUIRES),
        (SynapseType.EXTENDS, REL_EXTENDS),
        (SynapseType.CONTRASTS, REL_CONTRASTS),
        (SynapseType.RELATES_TO, REL_RELATES_TO),
    ],
)
def test_synapse_to_edge_rel_mapping(type_, rel):
    syn = Synapse(pre="n-a", post="n-b", type=type_, weight=0.7)
    edge = synapse_to_edge(syn)
    assert edge.rel == rel
    assert edge.src == "n-a"
    assert edge.dst == "n-b"


def test_synapse_to_edge_publishes_weight_and_confidence():
    syn = Synapse(
        pre="n-a",
        post="n-b",
        type=SynapseType.REQUIRES,
        weight=0.42,
        confidence=SynapseConfidence.INFERRED,
        confidence_score=0.65,
    )
    edge = synapse_to_edge(syn)
    assert edge.attrs["spk:weight"] == 0.42
    assert edge.attrs["spk:confidence"] == "inferred"
    assert edge.attrs["spk:confidence_score"] == 0.65


def test_synapse_to_edge_summarizes_rejected():
    syn = Synapse(pre="n-a", post="n-b", type=SynapseType.SUMMARIZES)
    with pytest.raises(ValueError, match="SUMMARIZES"):
        synapse_to_edge(syn)


def test_synapse_to_edge_hides_stdp_state():
    syn = Synapse(
        pre="n-a",
        post="n-b",
        type=SynapseType.REQUIRES,
        co_fires=5,
        last_co_fire=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    attrs = synapse_to_edge(syn).attrs
    assert "spk:co_fires" not in attrs
    assert "spk:last_co_fire" not in attrs
    assert "co_fires" not in attrs


def test_synapse_to_edge_retired_state():
    retired = datetime(2026, 4, 10, tzinfo=timezone.utc)
    syn = Synapse(
        pre="n-a", post="n-b", type=SynapseType.REQUIRES, retired_at=retired
    )
    edge = synapse_to_edge(syn)
    assert edge.state == "retired"
    assert edge.retired_at == datetime_to_timestamp(retired)


def test_edge_ref_stable_under_weight_bump():
    created = datetime(2026, 4, 1, tzinfo=timezone.utc)
    a = Synapse(
        pre="n-a", post="n-b", type=SynapseType.REQUIRES, weight=0.3, created_at=created
    )
    b = Synapse(
        pre="n-a", post="n-b", type=SynapseType.REQUIRES, weight=0.9, created_at=created
    )
    assert edge_ref_for_synapse(a) == edge_ref_for_synapse(b)


def test_edge_ref_distinguishes_recreated_synapse_on_same_composite_key():
    old = Synapse(
        pre="n-a",
        post="n-b",
        type=SynapseType.REQUIRES,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    new = Synapse(
        pre="n-a",
        post="n-b",
        type=SynapseType.REQUIRES,
        created_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    assert edge_ref_for_synapse(old) != edge_ref_for_synapse(new)


def test_edge_ref_differs_by_type():
    created = datetime(2026, 4, 1, tzinfo=timezone.utc)
    a = Synapse(pre="n-a", post="n-b", type=SynapseType.REQUIRES, created_at=created)
    b = Synapse(pre="n-a", post="n-b", type=SynapseType.EXTENDS, created_at=created)
    assert edge_ref_for_synapse(a) != edge_ref_for_synapse(b)


# ---------------------------------------------------------------------------
# junction_edge (neuron_source → derived_from)
# ---------------------------------------------------------------------------


def test_junction_edge_is_derived_from():
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    edge = junction_edge(neuron_id="n-a", source_id="s-1", created_at=ts)
    assert edge.rel == REL_DERIVED_FROM
    assert edge.src == "n-a"
    assert edge.dst == "s-1"
    assert edge.state == "live"
    assert edge.created_at == datetime_to_timestamp(ts)


def test_junction_edge_retired_flag_cascades_state():
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    edge = junction_edge(
        neuron_id="n-a", source_id="s-1", created_at=ts, retired=True
    )
    assert edge.state == "retired"
    assert edge.retired_at == datetime_to_timestamp(ts)


def test_junction_edge_ref_and_synapse_ref_dont_collide():
    from spikuit_agents.amkb.mapping import junction_edge_ref

    syn = Synapse(
        pre="n-a",
        post="s-1",
        type=SynapseType.REQUIRES,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    assert junction_edge_ref("n-a", "s-1") != edge_ref_for_synapse(syn)

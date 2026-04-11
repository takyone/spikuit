"""Tests for Source model, DB schema, and CRUD operations."""

import pytest
import pytest_asyncio

from spikuit_core import Circuit, Neuron, Source, strip_frontmatter
from spikuit_core.db import Database


# -- Fixtures ---------------------------------------------------------------


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(tmp_path / "test.db")
    await d.connect()
    yield d
    await d.close()


@pytest_asyncio.fixture
async def circuit(tmp_path):
    c = Circuit(db_path=tmp_path / "test.db")
    await c.connect()
    yield c
    await c.close()


# -- Source model -----------------------------------------------------------


def test_source_auto_id():
    s = Source()
    assert s.id.startswith("s-")
    assert len(s.id) == 14  # "s-" + 12 hex chars


def test_source_explicit_id():
    s = Source(id="s-custom123456")
    assert s.id == "s-custom123456"


def test_source_all_fields():
    s = Source(
        url="https://example.com/paper.pdf",
        title="A Great Paper",
        author="Alice",
        section="3.2",
        excerpt="Key finding...",
        storage_uri="file:///tmp/sources/s-abc.md",
        content_hash="abc123",
        notes="Focus on section 3",
    )
    assert s.url == "https://example.com/paper.pdf"
    assert s.content_hash == "abc123"
    assert s.notes == "Focus on section 3"


# -- DB Source CRUD ---------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_and_get_source(db):
    s = Source(url="https://example.com", title="Example")
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.id == s.id
    assert got.url == "https://example.com"
    assert got.title == "Example"


@pytest.mark.asyncio
async def test_find_source_by_url(db):
    s = Source(url="https://example.com/unique", title="Unique")
    await db.insert_source(s)

    found = await db.find_source_by_url("https://example.com/unique")
    assert found is not None
    assert found.id == s.id

    not_found = await db.find_source_by_url("https://nonexistent.com")
    assert not_found is None


@pytest.mark.asyncio
async def test_attach_and_get_sources_for_neuron(db):
    # Create neuron and source
    n = Neuron.create("# Test neuron")
    await db.insert_neuron(n)
    s1 = Source(url="https://a.com", title="A")
    s2 = Source(url="https://b.com", title="B")
    await db.insert_source(s1)
    await db.insert_source(s2)

    # Attach both
    await db.attach_source(n.id, s1.id)
    await db.attach_source(n.id, s2.id)

    sources = await db.get_sources_for_neuron(n.id)
    assert len(sources) == 2
    urls = {s.url for s in sources}
    assert "https://a.com" in urls
    assert "https://b.com" in urls


@pytest.mark.asyncio
async def test_attach_idempotent(db):
    n = Neuron.create("# Test")
    await db.insert_neuron(n)
    s = Source(url="https://a.com")
    await db.insert_source(s)

    await db.attach_source(n.id, s.id)
    await db.attach_source(n.id, s.id)  # Should not raise

    sources = await db.get_sources_for_neuron(n.id)
    assert len(sources) == 1


@pytest.mark.asyncio
async def test_detach_source(db):
    n = Neuron.create("# Test")
    await db.insert_neuron(n)
    s = Source(url="https://a.com")
    await db.insert_source(s)

    await db.attach_source(n.id, s.id)
    await db.detach_source(n.id, s.id)

    sources = await db.get_sources_for_neuron(n.id)
    assert len(sources) == 0


@pytest.mark.asyncio
async def test_get_neurons_for_source(db):
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await db.insert_neuron(n1)
    await db.insert_neuron(n2)
    s = Source(url="https://shared.com")
    await db.insert_source(s)

    await db.attach_source(n1.id, s.id)
    await db.attach_source(n2.id, s.id)

    nids = await db.get_neurons_for_source(s.id)
    assert set(nids) == {n1.id, n2.id}


@pytest.mark.asyncio
async def test_cascade_delete_neuron(db):
    """Deleting a neuron should remove neuron_source rows but keep the source."""
    n = Neuron.create("# Test")
    await db.insert_neuron(n)
    s = Source(url="https://a.com")
    await db.insert_source(s)
    await db.attach_source(n.id, s.id)

    await db.delete_neuron(n.id)

    # Source still exists
    got = await db.get_source(s.id)
    assert got is not None
    # But no neurons linked
    nids = await db.get_neurons_for_source(s.id)
    assert len(nids) == 0


# -- Community IDs ----------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_update_community_ids(db):
    n1 = Neuron.create("# A")
    n2 = Neuron.create("# B")
    await db.insert_neuron(n1)
    await db.insert_neuron(n2)

    await db.batch_update_community_ids({n1.id: 0, n2.id: 1})

    cids = await db.get_community_ids()
    assert cids[n1.id] == 0
    assert cids[n2.id] == 1


# -- strip_frontmatter -----------------------------------------------------


def test_strip_frontmatter_with_fm():
    content = "---\ntype: concept\nsource: s-abc\n---\n# Functor\n\nA mapping."
    body = strip_frontmatter(content)
    assert body == "# Functor\n\nA mapping."
    assert "type:" not in body
    assert "source:" not in body


def test_strip_frontmatter_without_fm():
    content = "# Functor\n\nA mapping."
    body = strip_frontmatter(content)
    assert body == content


def test_strip_frontmatter_incomplete():
    content = "---\ntype: concept\nno closing fence"
    body = strip_frontmatter(content)
    assert body == content  # Returns original if no closing ---


# -- Content hash and storage URI -------------------------------------------


@pytest.mark.asyncio
async def test_source_content_hash_persists(db):
    """content_hash should roundtrip through DB."""
    import hashlib
    text = "# Functor\n\nA mapping between categories."
    expected_hash = hashlib.sha256(text.encode()).hexdigest()

    s = Source(
        url="https://example.com/functor",
        title="Functor",
        content_hash=expected_hash,
    )
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.content_hash == expected_hash


@pytest.mark.asyncio
async def test_source_storage_uri_persists(db):
    """storage_uri should roundtrip through DB."""
    s = Source(
        url="https://example.com/article",
        title="Article",
        storage_uri="file:///tmp/.spikuit/sources/s-abc123.html",
    )
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.storage_uri == "file:///tmp/.spikuit/sources/s-abc123.html"


@pytest.mark.asyncio
async def test_source_filterable_roundtrip(db):
    """filterable dict should serialize to JSON and roundtrip through DB."""
    s = Source(
        url="https://example.com/paper",
        title="Paper",
        filterable={"year": "2017", "venue": "NeurIPS", "type": "survey"},
    )
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.filterable == {"year": "2017", "venue": "NeurIPS", "type": "survey"}


@pytest.mark.asyncio
async def test_source_searchable_roundtrip(db):
    """searchable dict should serialize to JSON and roundtrip through DB."""
    s = Source(
        url="https://example.com/article",
        title="Article",
        searchable={"abstract": "We propose a novel approach...", "keywords": "GNN, attention"},
    )
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.searchable == {"abstract": "We propose a novel approach...", "keywords": "GNN, attention"}


@pytest.mark.asyncio
async def test_source_null_filterable_searchable(db):
    """None filterable/searchable should persist as NULL."""
    s = Source(url="https://example.com/plain", title="Plain")
    await db.insert_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.filterable is None
    assert got.searchable is None


@pytest.mark.asyncio
async def test_update_source(db):
    """update_source should update mutable fields."""
    s = Source(url="https://old.com", title="Old Title")
    await db.insert_source(s)

    s.url = "https://new.com"
    s.title = "New Title"
    s.filterable = {"corrected": "true"}
    await db.update_source(s)

    got = await db.get_source(s.id)
    assert got is not None
    assert got.url == "https://new.com"
    assert got.title == "New Title"
    assert got.filterable == {"corrected": "true"}


@pytest.mark.asyncio
async def test_list_sources(db):
    """list_sources should return all sources."""
    s1 = Source(url="https://a.com", title="A")
    s2 = Source(url="https://b.com", title="B")
    await db.insert_source(s1)
    await db.insert_source(s2)

    sources = await db.list_sources()
    assert len(sources) == 2


@pytest.mark.asyncio
async def test_get_meta_keys(db):
    """get_meta_keys should return distinct keys across sources."""
    s1 = Source(
        url="https://a.com",
        filterable={"year": "2017", "venue": "ICML"},
        searchable={"abstract": "..."},
    )
    s2 = Source(
        url="https://b.com",
        filterable={"year": "2020", "author": "Alice"},
    )
    await db.insert_source(s1)
    await db.insert_source(s2)

    keys = await db.get_meta_keys()
    key_names = {k["key"] for k in keys}
    assert "year" in key_names
    assert "venue" in key_names
    assert "author" in key_names
    assert "abstract" in key_names

    # year should have count=2
    year_entry = next(k for k in keys if k["key"] == "year")
    assert year_entry["count"] == 2
    assert year_entry["layer"] == "filterable"


@pytest.mark.asyncio
async def test_get_domain_counts(db):
    """get_domain_counts should return domain names with counts."""
    n1 = Neuron.create("# A", type="concept", domain="math")
    n2 = Neuron.create("# B", type="concept", domain="math")
    n3 = Neuron.create("# C", type="concept", domain="cs")
    await db.insert_neuron(n1)
    await db.insert_neuron(n2)
    await db.insert_neuron(n3)

    domains = await db.get_domain_counts()
    domain_map = {d["domain"]: d["count"] for d in domains}
    assert domain_map["math"] == 2
    assert domain_map["cs"] == 1


def test_content_hash_should_be_of_extracted_text():
    """Verify that the hash of extracted text differs from hash of raw HTML."""
    import hashlib
    raw_html = "<html><body><h1>Functor</h1><p>A mapping.</p></body></html>"
    extracted_text = "# Functor\n\nA mapping."

    hash_html = hashlib.sha256(raw_html.encode()).hexdigest()
    hash_text = hashlib.sha256(extracted_text.encode()).hexdigest()

    # They must differ — we want the text hash, not the HTML hash
    assert hash_html != hash_text

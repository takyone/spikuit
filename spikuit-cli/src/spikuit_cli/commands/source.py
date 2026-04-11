"""Source management commands: spkt source {learn,list,inspect,update,refresh}."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from spikuit_core import Circuit, Source
from spikuit_core.config import BrainConfig

from ..helpers import _extract_title, _get_circuit, _load_brain_config, _out, _run

source_app = typer.Typer(help="Manage sources.")


@source_app.command(name="learn")
def source_learn(
    path_or_url: str = typer.Argument(..., help="File path, directory, or URL to ingest"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain tag"),
    title: Optional[str] = typer.Option(None, "--title", help="Source title override"),
    force: bool = typer.Option(False, "--force", help="Force ingest (truncate oversized searchable)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Ingest a source file, directory, or URL for agent-driven chunking.

    For directories, reads all text files and optionally loads metadata
    from a ``metadata.jsonl`` sidecar file. Each line in metadata.jsonl
    maps ``file_name`` to ``filterable`` and ``searchable`` dicts.

    Pre-flight validates searchable sizes. Use ``--force`` to truncate
    oversized searchable fields instead of aborting.
    """

    async def _learn():
        config = _load_brain_config(brain)
        max_searchable = config.embedder.max_searchable_chars
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            p = Path(path_or_url)
            is_url = path_or_url.startswith(("http://", "https://"))

            if is_url:
                await _learn_url(circuit, config, path_or_url, domain, title, as_json)
            elif p.is_dir():
                await _learn_dir(circuit, config, p, domain, max_searchable, force, as_json)
            elif p.is_file():
                result = await _learn_file(circuit, p, domain, title, as_json=False)
                if result:
                    if as_json:
                        _out(result, use_json=True)
                    else:
                        _emit_learn_result_from_dict(result)
            else:
                typer.echo(f"Not found: {path_or_url}", err=True)
                raise typer.Exit(1)
        finally:
            await circuit.close()

    _run(_learn())


@source_app.command(name="list")
def source_list(
    limit: int = typer.Option(100, "--limit", "-n", help="Max sources to show"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """List sources with neuron counts."""

    async def _source_list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            sources = await circuit.list_sources(limit=limit)
            if as_json:
                out = []
                for s in sources:
                    nids = await circuit.get_neurons_for_source(s.id)
                    out.append({
                        "id": s.id,
                        "url": s.url,
                        "title": s.title,
                        "neuron_count": len(nids),
                        "content_hash": s.content_hash,
                        "filterable": s.filterable,
                        "searchable": s.searchable,
                        "created_at": str(s.created_at),
                    })
                _out(out, use_json=True)
            else:
                if not sources:
                    typer.echo("No sources found.")
                    return
                typer.echo(f"{len(sources)} source(s):")
                for s in sources:
                    nids = await circuit.get_neurons_for_source(s.id)
                    typer.echo(f"  {s.id}  {s.title or '-':30s}  {len(nids)} neurons  {s.url or '-'}")
        finally:
            await circuit.close()

    _run(_source_list())


@source_app.command(name="inspect")
def source_inspect(
    source_id: str = typer.Argument(..., help="Source ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Show source details and attached neurons."""

    async def _source_inspect():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            src = await circuit.get_source(source_id)
            if not src:
                typer.echo(f"Source not found: {source_id}", err=True)
                raise typer.Exit(1)

            nids = await circuit.get_neurons_for_source(source_id)

            if as_json:
                _out({
                    "id": src.id,
                    "url": src.url,
                    "title": src.title,
                    "author": src.author,
                    "section": src.section,
                    "excerpt": src.excerpt,
                    "storage_uri": src.storage_uri,
                    "content_hash": src.content_hash,
                    "notes": src.notes,
                    "filterable": src.filterable,
                    "searchable": src.searchable,
                    "accessed_at": str(src.accessed_at) if src.accessed_at else None,
                    "created_at": str(src.created_at),
                    "neuron_ids": nids,
                }, use_json=True)
            else:
                typer.echo(f"Source: {src.id}")
                typer.echo(f"  URL:          {src.url or '-'}")
                typer.echo(f"  Title:        {src.title or '-'}")
                typer.echo(f"  Author:       {src.author or '-'}")
                typer.echo(f"  Content hash: {src.content_hash or '-'}")
                typer.echo(f"  Storage:      {src.storage_uri or '-'}")
                if src.filterable:
                    typer.echo(f"  Filterable:   {json.dumps(src.filterable)}")
                if src.searchable:
                    typer.echo(f"  Searchable:   {json.dumps(src.searchable)}")
                typer.echo(f"  Neurons:      {len(nids)}")
                for nid in nids:
                    n = await circuit.get_neuron(nid)
                    title = _extract_title(n.content) if n else nid
                    typer.echo(f"    {nid}  {title}")
        finally:
            await circuit.close()

    _run(_source_inspect())


@source_app.command(name="update")
def source_update(
    source_id: str = typer.Argument(..., help="Source ID"),
    url: Optional[str] = typer.Option(None, "--url", help="New URL"),
    title: Optional[str] = typer.Option(None, "--title", help="New title"),
    author: Optional[str] = typer.Option(None, "--author", help="New author"),
    notes: Optional[str] = typer.Option(None, "--notes", help="New notes"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Update source metadata fields."""

    async def _source_update():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            src = await circuit.get_source(source_id)
            if not src:
                typer.echo(f"Source not found: {source_id}", err=True)
                raise typer.Exit(1)

            if url is not None:
                src.url = url
            if title is not None:
                src.title = title
            if author is not None:
                src.author = author
            if notes is not None:
                src.notes = notes

            await circuit.update_source(src)

            if as_json:
                _out({"id": src.id, "url": src.url, "title": src.title, "author": src.author, "notes": src.notes}, use_json=True)
            else:
                typer.echo(f"Updated source {src.id}")
        finally:
            await circuit.close()

    _run(_source_update())


@source_app.command(name="refresh")
def source_refresh(
    source_id: Optional[str] = typer.Argument(None, help="Source ID to refresh"),
    stale: Optional[int] = typer.Option(None, "--stale", help="Refresh sources older than N days"),
    all_sources: bool = typer.Option(False, "--all", help="Refresh all URL sources"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Re-fetch URL sources and re-embed if content changed.

    Checks HTTP ETag/Last-Modified headers first (conditional GET).
    Updates content hash, flags unreachable sources.
    """

    async def _refresh():
        import hashlib
        import urllib.request

        config = _load_brain_config(brain)
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            # Determine which sources to refresh
            targets: list = []
            if source_id:
                src = await circuit.get_source(source_id)
                if not src:
                    typer.echo(f"Source not found: {source_id}", err=True)
                    raise typer.Exit(1)
                if not src.url or not src.url.startswith(("http://", "https://")):
                    typer.echo(f"Source {source_id} is not a URL source", err=True)
                    raise typer.Exit(1)
                targets = [src]
            elif stale is not None:
                targets = await circuit.get_stale_sources(stale)
            elif all_sources:
                all_src = await circuit.list_sources(limit=100_000)
                targets = [s for s in all_src if s.url and s.url.startswith(("http://", "https://"))]
            else:
                typer.echo("Specify a source ID, --stale N, or --all", err=True)
                raise typer.Exit(1)

            if not targets:
                if as_json:
                    _out({"refreshed": 0, "changed": 0, "unreachable": 0}, use_json=True)
                else:
                    typer.echo("No sources to refresh.")
                return

            now = datetime.now(timezone.utc)
            results = {"refreshed": 0, "changed": 0, "unreachable": 0, "details": []}

            for src in targets:
                detail = {"id": src.id, "url": src.url, "status": "unchanged"}

                # Try conditional GET first
                req = urllib.request.Request(src.url, method="GET")
                if src.http_etag:
                    req.add_header("If-None-Match", src.http_etag)
                if src.http_last_modified:
                    req.add_header("If-Modified-Since", src.http_last_modified)

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        if resp.status == 304:
                            src.fetched_at = now
                            await circuit.update_source(src)
                            detail["status"] = "not_modified"
                            results["refreshed"] += 1
                            results["details"].append(detail)
                            continue

                        raw_bytes = resp.read()
                        raw = raw_bytes.decode("utf-8", errors="replace")
                        new_etag = resp.headers.get("ETag")
                        new_last_modified = resp.headers.get("Last-Modified")

                except urllib.error.HTTPError as e:
                    if e.code == 304:
                        src.fetched_at = now
                        await circuit.update_source(src)
                        detail["status"] = "not_modified"
                        results["refreshed"] += 1
                        results["details"].append(detail)
                        continue
                    elif e.code in (404, 410):
                        src.status = "unreachable"
                        src.fetched_at = now
                        await circuit.update_source(src)
                        detail["status"] = "unreachable"
                        results["unreachable"] += 1
                        results["refreshed"] += 1
                        results["details"].append(detail)
                        continue
                    else:
                        detail["status"] = f"error_{e.code}"
                        results["details"].append(detail)
                        continue
                except Exception:
                    src.status = "unreachable"
                    src.fetched_at = now
                    await circuit.update_source(src)
                    detail["status"] = "unreachable"
                    results["unreachable"] += 1
                    results["refreshed"] += 1
                    results["details"].append(detail)
                    continue

                # Compare content hash
                new_hash = hashlib.sha256(raw.encode()).hexdigest()
                src.fetched_at = now
                src.http_etag = new_etag
                src.http_last_modified = new_last_modified
                src.status = "active"

                if new_hash != src.content_hash:
                    src.content_hash = new_hash
                    detail["status"] = "changed"
                    results["changed"] += 1

                    # Save updated raw content
                    sources_dir = config.spikuit_dir / "sources"
                    sources_dir.mkdir(exist_ok=True)
                    html_path = sources_dir / f"{src.id}.html"
                    html_path.write_text(raw, encoding="utf-8")
                    src.storage_uri = f"file://{html_path.resolve()}"

                await circuit.update_source(src)
                results["refreshed"] += 1
                results["details"].append(detail)

            if as_json:
                _out(results, use_json=True)
            else:
                typer.echo(f"Refreshed {results['refreshed']} source(s)")
                if results["changed"]:
                    typer.echo(f"  Changed:     {results['changed']}")
                if results["unreachable"]:
                    typer.echo(f"  Unreachable: {results['unreachable']}")
                for d in results["details"]:
                    if d["status"] not in ("unchanged", "not_modified"):
                        typer.echo(f"  {d['id']}  {d['status']}  {d['url']}")
        finally:
            await circuit.close()

    _run(_refresh())


# -------------------------------------------------------------------
# Internal helpers for learn
# -------------------------------------------------------------------


async def _learn_url(
    circuit: Circuit,
    config: BrainConfig,
    url: str,
    domain: str | None,
    title_override: str | None,
    as_json: bool,
) -> None:
    """Ingest a single URL."""
    import hashlib
    import urllib.request

    now = datetime.now(timezone.utc)
    etag: str | None = None
    last_modified: str | None = None

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw_bytes = resp.read()
            raw = raw_bytes.decode("utf-8", errors="replace")
            raw_html = raw
            etag = resp.headers.get("ETag")
            last_modified = resp.headers.get("Last-Modified")
    except Exception as e:
        typer.echo(f"Failed to fetch URL: {e}", err=True)
        raise typer.Exit(1)

    content_hash = hashlib.sha256(raw.encode()).hexdigest()

    existing = await circuit.find_source_by_url(url)
    if existing:
        src = existing
    else:
        src = Source(
            url=url,
            title=title_override or url[:80],
            content_hash=content_hash,
            fetched_at=now,
            http_etag=etag,
            http_last_modified=last_modified,
            status="active",
        )
        # Save raw HTML to .spikuit/sources/
        sources_dir = config.spikuit_dir / "sources"
        sources_dir.mkdir(exist_ok=True)
        html_path = sources_dir / f"{src.id}.html"
        html_path.write_text(raw_html, encoding="utf-8")
        src.storage_uri = f"file://{html_path.resolve()}"
        await circuit.add_source(src)

    _emit_learn_result(src, raw, domain, as_json)


async def _learn_file(
    circuit: Circuit,
    p: Path,
    domain: str | None,
    title_override: str | None,
    as_json: bool,
    filterable: dict | None = None,
    searchable: dict | None = None,
) -> dict | None:
    """Ingest a single local file. Returns result dict for batch use."""
    import hashlib

    raw = p.read_text(encoding="utf-8")
    source_url = f"file://{p.resolve()}"
    content_hash = hashlib.sha256(raw.encode()).hexdigest()

    existing = await circuit.find_source_by_url(source_url)
    if existing:
        src = existing
    else:
        src = Source(
            url=source_url,
            title=title_override or p.stem,
            content_hash=content_hash,
            filterable=filterable,
            searchable=searchable,
        )
        await circuit.add_source(src)

    result = {
        "source_id": src.id,
        "source_url": src.url,
        "source_title": src.title,
        "content_hash": src.content_hash,
        "storage_uri": src.storage_uri,
        "domain": domain,
        "content_length": len(raw),
        "content": raw,
    }
    if filterable:
        result["filterable"] = filterable
    if searchable:
        result["searchable"] = searchable
    return result


async def _learn_dir(
    circuit: Circuit,
    config: BrainConfig,
    dir_path: Path,
    domain: str | None,
    max_searchable: int,
    force: bool,
    as_json: bool,
) -> None:
    """Ingest all text files in a directory with optional metadata.jsonl."""
    # Collect text files (skip metadata.jsonl itself)
    text_exts = {".md", ".txt", ".rst", ".html", ".htm", ".json", ".yaml", ".yml", ".csv", ".xml"}
    files = sorted(
        f for f in dir_path.iterdir()
        if f.is_file() and f.name != "metadata.jsonl" and f.suffix.lower() in text_exts
    )
    if not files:
        typer.echo(f"No ingestible files found in {dir_path}", err=True)
        raise typer.Exit(1)

    # Load metadata.jsonl if present
    meta_map: dict[str, dict] = {}
    meta_path = dir_path / "metadata.jsonl"
    if meta_path.exists():
        for line_no, line in enumerate(meta_path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                typer.echo(f"metadata.jsonl line {line_no}: invalid JSON \u2014 {e}", err=True)
                raise typer.Exit(1)
            fname = entry.get("file_name")
            if not fname:
                typer.echo(f"metadata.jsonl line {line_no}: missing 'file_name'", err=True)
                raise typer.Exit(1)
            meta_map[fname] = entry

    # Pre-flight: validate searchable sizes
    violations: list[str] = []
    for f in files:
        meta = meta_map.get(f.name, {})
        searchable = meta.get("searchable")
        if searchable:
            total = sum(len(f"[{k}: {v}]") for k, v in searchable.items())
            if total > max_searchable:
                violations.append(f"  {f.name}: {total} chars (max {max_searchable})")

    if violations and not force:
        typer.echo("Searchable metadata exceeds max_searchable_chars:", err=True)
        for v in violations:
            typer.echo(v, err=True)
        typer.echo("Use --force to truncate, or reduce searchable content.", err=True)
        raise typer.Exit(1)

    # Ingest each file
    results: list[dict] = []
    for f in files:
        meta = meta_map.get(f.name, {})
        filterable = meta.get("filterable")
        searchable = meta.get("searchable")
        file_title = meta.get("title")

        result = await _learn_file(
            circuit, f, domain, file_title, as_json=False,
            filterable=filterable, searchable=searchable,
        )
        if result:
            results.append(result)

    if as_json:
        _out({"files": results, "count": len(results)}, use_json=True)
    else:
        typer.echo(f"Ingested {len(results)} file(s) from {dir_path}")
        for r in results:
            typer.echo(f"  {r['source_id']} \u2014 {r['source_title']} ({r['content_length']} chars)")
        if meta_map:
            typer.echo(f"  metadata.jsonl: {len(meta_map)} entries applied")
        typer.echo("\nUse the /spkt-teach agent skill to chunk content into neurons.")


def _emit_learn_result_from_dict(result: dict) -> None:
    """Output learn result for a single file from result dict."""
    typer.echo(f"Source: {result['source_id']} ({result['source_url']})")
    typer.echo(f"Content: {result['content_length']} chars")
    typer.echo(f"Domain: {result.get('domain') or '-'}")
    typer.echo("\nUse the /spkt-teach agent skill to chunk this content into neurons.")


def _emit_learn_result(src: Source, raw: str, domain: str | None, as_json: bool) -> None:
    """Output learn result for a single source."""
    if as_json:
        _out({
            "source_id": src.id,
            "source_url": src.url,
            "source_title": src.title,
            "content_hash": src.content_hash,
            "storage_uri": src.storage_uri,
            "domain": domain,
            "content_length": len(raw),
            "content": raw,
        }, use_json=True)
    else:
        typer.echo(f"Source: {src.id} ({src.url})")
        typer.echo(f"Content: {len(raw)} chars")
        typer.echo(f"Domain: {domain or '-'}")
        typer.echo("\nUse the /spkt-teach agent skill to chunk this content into neurons.")

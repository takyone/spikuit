"""Entry point for the spkt CLI."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from spikuit_core import Circuit, Flashcard, Grade, Neuron, Plasticity, Source, Spike, SynapseType
from spikuit_core.config import BrainConfig, find_spikuit_root, init_brain, load_config
from spikuit_core.embedder import create_embedder

app = typer.Typer(
    name="spkt",
    help="Spikuit — neural knowledge graph with spaced repetition.",
    no_args_is_help=True,
)


def _load_brain_config(brain: Path | None = None) -> BrainConfig:
    """Load config from .spikuit/ or use explicit brain root."""
    return load_config(brain)


def _get_circuit(brain: Path | None = None) -> Circuit:
    """Create a Circuit from brain config."""
    config = load_config(brain)
    embedder = create_embedder(
        config.embedder.provider,
        base_url=config.embedder.base_url,
        model=config.embedder.model,
        dimension=config.embedder.dimension,
        api_key=config.embedder.api_key,
        timeout=config.embedder.timeout,
        prefix_style=config.embedder.prefix_style,
    )
    return Circuit(db_path=config.db_path, embedder=embedder)


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _out(data: object, *, use_json: bool) -> None:
    """Output data as JSON or human-readable text."""
    if use_json:
        typer.echo(json.dumps(data, ensure_ascii=False, default=str))
    elif isinstance(data, str):
        typer.echo(data)
    elif isinstance(data, list):
        for item in data:
            typer.echo(item)
    elif isinstance(data, dict):
        for k, v in data.items():
            typer.echo(f"{k}: {v}")


def _neuron_dict(n: Neuron, circuit: Circuit) -> dict:
    """Serialize a Neuron + its graph state to a dict."""
    card = circuit.get_card(n.id)
    pressure = circuit.get_pressure(n.id)
    d: dict = {
        "id": n.id,
        "title": _extract_title(n.content),
        "content": n.content,
        "type": n.type,
        "domain": n.domain,
        "pressure": pressure,
    }
    if card:
        d["fsrs"] = {
            "stability": card.stability,
            "difficulty": card.difficulty,
            "state": card.state.name,
            "due": str(card.due),
        }
    return d


# -------------------------------------------------------------------
# init
# -------------------------------------------------------------------


_VALID_PROVIDERS = ("openai-compat", "ollama")

_PROVIDER_DEFAULTS = {
    "openai-compat": {
        "base_url": "http://localhost:1234/v1",
        "model": "text-embedding-nomic-embed-text-v1.5",
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "nomic-embed-text",
    },
}


@app.command()
def init(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Brain name (defaults to directory name)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Embedder: none|openai-compat|ollama"),
    base_url: str = typer.Option("", "--base-url", help="Embedder API base URL"),
    model: str = typer.Option("", "--model", "-m", help="Embedding model name"),
    dimension: int = typer.Option(768, "--dimension", "-d", help="Embedding dimension"),
    as_json: bool = typer.Option(False, "--json", help="Non-interactive JSON output"),
) -> None:
    """Initialize a new brain in the current directory.

    Without flags, starts an interactive wizard.
    With --json or explicit --provider, runs non-interactively.
    """
    interactive = not as_json and provider is None

    if interactive:
        default_name = Path.cwd().name
        name = typer.prompt("Brain name", default=default_name)

        if typer.confirm("Configure embeddings?", default=False):
            typer.echo(f"  Providers: {', '.join(_VALID_PROVIDERS)}")
            while True:
                emb_provider = typer.prompt("  Provider", default="openai-compat")
                if emb_provider in _VALID_PROVIDERS:
                    break
                typer.echo(f"  Invalid provider. Choose from: {', '.join(_VALID_PROVIDERS)}")

            defaults = _PROVIDER_DEFAULTS[emb_provider]
            base_url = typer.prompt("  Base URL", default=defaults["base_url"])
            model = typer.prompt("  Model", default=defaults["model"])
            dimension = int(typer.prompt("  Dimension", default="768"))
            provider = emb_provider
        else:
            provider = "none"

        typer.echo("")
        typer.echo("--- Summary ---")
        typer.echo(f"Brain:    {name}")
        typer.echo(f"Location: {Path.cwd() / '.spikuit/'}")
        typer.echo(f"Embedder: {provider}")
        if provider != "none":
            typer.echo(f"  URL:    {base_url}")
            typer.echo(f"  Model:  {model}")
            typer.echo(f"  Dim:    {dimension}")

        if not typer.confirm("\nCreate brain?", default=True):
            raise typer.Abort()
    else:
        if provider is None:
            provider = "none"

    try:
        config = init_brain(
            name=name,
            embedder_provider=provider,
            embedder_base_url=base_url,
            embedder_model=model,
            embedder_dimension=dimension,
        )
    except FileExistsError:
        typer.echo(".spikuit/ already exists in this directory.", err=True)
        raise typer.Exit(1)

    if as_json:
        _out({
            "root": str(config.root),
            "db": str(config.db_path),
            "config": str(config.config_path),
            "embedder": config.embedder.provider,
            "name": config.name,
        }, use_json=True)
    else:
        typer.echo(f"\nInitialized brain '{config.name}' at {config.spikuit_dir}/")
        typer.echo(f"  config: {config.config_path}")
        typer.echo(f"  db:     {config.db_path}")
        if config.embedder.provider != "none":
            typer.echo(f"  embedder: {config.embedder.provider} ({config.embedder.model})")
        else:
            typer.echo(f"  embedder: none (edit config.toml to enable)")

        # Agent CLI skills installation
        if interactive:
            typer.echo("")
            if typer.confirm("Install skills for an Agent CLI? (/tutor, /learn, /qabot)", default=False):
                _install_agent_skills(config.root)


# -------------------------------------------------------------------
# config
# -------------------------------------------------------------------


@app.command()
def config(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show current brain configuration."""
    cfg = load_config()
    root = find_spikuit_root()

    if as_json:
        _out({
            "root": str(cfg.root),
            "name": cfg.name,
            "db": str(cfg.db_path),
            "found": root is not None,
            "embedder": {
                "provider": cfg.embedder.provider,
                "base_url": cfg.embedder.base_url,
                "model": cfg.embedder.model,
                "dimension": cfg.embedder.dimension,
            },
        }, use_json=True)
    else:
        if root is None:
            typer.echo("No .spikuit/ found (using ~/.spikuit/ fallback)")
        else:
            typer.echo(f"Brain: {cfg.name}")
            typer.echo(f"Root:  {cfg.root}")
        typer.echo(f"DB:    {cfg.db_path}")
        typer.echo(f"Embedder: {cfg.embedder.provider}")
        if cfg.embedder.provider != "none":
            typer.echo(f"  url:   {cfg.embedder.base_url}")
            typer.echo(f"  model: {cfg.embedder.model}")
            typer.echo(f"  dim:   {cfg.embedder.dimension}")


# -------------------------------------------------------------------
# embed-all
# -------------------------------------------------------------------


@app.command(name="embed-all")
def embed_all(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Embed all neurons that don't have embeddings yet (backfill).

    Shows a plan (neuron count, estimated tokens) before proceeding.
    Use ``--yes`` to skip the confirmation prompt.
    """

    async def _embed_all():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            if circuit._embedder is None:
                typer.echo("No embedder configured. Edit .spikuit/config.toml to enable.", err=True)
                raise typer.Exit(1)

            # Calculate plan: how many neurons need embedding
            all_neurons = await circuit.list_neurons(limit=100_000)
            to_embed = []
            for n in all_neurons:
                rows = await circuit._db.conn.execute_fetchall(
                    "SELECT 1 FROM neuron_vec_map WHERE neuron_id = ?", (n.id,)
                )
                if not rows:
                    to_embed.append(n)

            if not to_embed:
                if as_json:
                    _out({"embedded": 0, "message": "All neurons already have embeddings"}, use_json=True)
                else:
                    typer.echo("All neurons already have embeddings.")
                return

            total_chars = sum(len(n.content) for n in to_embed)
            est_tokens = total_chars // 4

            if as_json and not yes:
                # JSON mode with plan — output plan and proceed
                _out({
                    "plan": {
                        "total_neurons": len(all_neurons),
                        "to_embed": len(to_embed),
                        "estimated_chars": total_chars,
                        "estimated_tokens": est_tokens,
                    }
                }, use_json=True)
                # In JSON mode, still require --yes for non-interactive use
                return

            if not yes:
                typer.echo("Embed-all plan:")
                typer.echo(f"  Total neurons:    {len(all_neurons)}")
                typer.echo(f"  To embed:         {len(to_embed)}")
                typer.echo(f"  Estimated chars:  {total_chars:,}")
                typer.echo(f"  Estimated tokens: ~{est_tokens:,}")
                if not typer.confirm("Proceed?", default=True):
                    typer.echo("Aborted.")
                    return

            count = await circuit.embed_all()
            if as_json:
                _out({"embedded": count}, use_json=True)
            else:
                typer.echo(f"Embedded {count} neuron(s).")
        finally:
            await circuit.close()

    _run(_embed_all())


# -------------------------------------------------------------------
# add
# -------------------------------------------------------------------


@app.command()
def add(
    content: str = typer.Argument(..., help="Markdown content for the neuron"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Neuron type"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain tag"),
    source_url: Optional[str] = typer.Option(None, "--source-url", help="Source URL for citation"),
    source_title: Optional[str] = typer.Option(None, "--source-title", help="Source title"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Add a new Neuron to the circuit."""

    async def _add():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            real_content = content.encode().decode("unicode_escape")
            neuron = Neuron.create(real_content, type=type, domain=domain)
            await circuit.add_neuron(neuron)

            # Attach source if URL provided
            source_attached = None
            if source_url:
                existing = await circuit.find_source_by_url(source_url)
                if existing:
                    await circuit.attach_source(neuron.id, existing.id)
                    source_attached = existing
                else:
                    src = Source(url=source_url, title=source_title)
                    await circuit.add_source(src)
                    await circuit.attach_source(neuron.id, src.id)
                    source_attached = src

            if as_json:
                d = _neuron_dict(neuron, circuit)
                if source_attached:
                    d["source_id"] = source_attached.id
                    d["source_url"] = source_attached.url
                _out(d, use_json=True)
            else:
                typer.echo(f"Added neuron {neuron.id}")
                if source_attached:
                    typer.echo(f"  source: {source_attached.id} ({source_attached.url})")
        finally:
            await circuit.close()

    _run(_add())


# -------------------------------------------------------------------
# fire
# -------------------------------------------------------------------

_GRADE_MAP = {
    "miss": Grade.MISS,
    "weak": Grade.WEAK,
    "fire": Grade.FIRE,
    "strong": Grade.STRONG,
}


@app.command()
def fire(
    neuron_id: str = typer.Argument(..., help="Neuron ID to fire"),
    grade: str = typer.Option("fire", "--grade", "-g", help="Grade: miss|weak|fire|strong"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Fire a spike (record a review) on a Neuron."""
    g = _GRADE_MAP.get(grade.lower())
    if g is None:
        typer.echo(f"Invalid grade: {grade}. Use: miss, weak, fire, strong", err=True)
        raise typer.Exit(1)

    async def _fire():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            neuron = await circuit.get_neuron(neuron_id)
            if neuron is None:
                typer.echo(f"Neuron {neuron_id} not found", err=True)
                raise typer.Exit(1)
            now = datetime.now(timezone.utc)
            spike = Spike(neuron_id=neuron_id, grade=g, fired_at=now)
            card = await circuit.fire(spike)
            if as_json:
                _out({
                    "neuron_id": neuron_id,
                    "grade": grade,
                    "stability": card.stability,
                    "difficulty": card.difficulty,
                    "due": str(card.due),
                    "state": card.state.name,
                }, use_json=True)
            else:
                typer.echo(f"Fired {grade} on {neuron_id}")
                typer.echo(f"  stability={card.stability:.2f}  difficulty={card.difficulty:.2f}  due={card.due}")
        finally:
            await circuit.close()

    _run(_fire())


# -------------------------------------------------------------------
# due
# -------------------------------------------------------------------


@app.command()
def due(
    limit: int = typer.Option(20, "--limit", "-n", help="Max neurons to show"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Show neurons due for review."""

    async def _due():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            ids = await circuit.due_neurons(limit=limit)
            if as_json:
                items = []
                for nid in ids:
                    neuron = await circuit.get_neuron(nid)
                    if neuron:
                        items.append(_neuron_dict(neuron, circuit))
                _out(items, use_json=True)
            else:
                if not ids:
                    typer.echo("No neurons due for review.")
                    return
                typer.echo(f"{len(ids)} neuron(s) due:")
                for nid in ids:
                    neuron = await circuit.get_neuron(nid)
                    pressure = circuit.get_pressure(nid)
                    title = _extract_title(neuron.content) if neuron else nid
                    p_indicator = f"  pressure={pressure:.2f}" if pressure > 0 else ""
                    typer.echo(f"  {nid}  {title}{p_indicator}")
        finally:
            await circuit.close()

    _run(_due())


# -------------------------------------------------------------------
# retrieve
# -------------------------------------------------------------------


@app.command()
def retrieve(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    filter: Optional[list[str]] = typer.Option(None, "--filter", "-f", help="Filter as key=value (repeatable)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Retrieve neurons matching a query (graph-weighted scoring).

    Use --filter to restrict results by neuron fields (type, domain)
    or source filterable metadata. Example: --filter domain=math --filter year=2020
    """

    async def _retrieve():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            # Parse filters
            filters: dict[str, str] | None = None
            if filter:
                filters = {}
                for f in filter:
                    if "=" not in f:
                        typer.echo(f"Invalid filter format: {f} (expected key=value)", err=True)
                        raise typer.Exit(1)
                    k, v = f.split("=", 1)
                    filters[k] = v
            results = await circuit.retrieve(query, limit=limit, filters=filters)
            if as_json:
                _out([_neuron_dict(n, circuit) for n in results], use_json=True)
            else:
                if not results:
                    typer.echo("No matching neurons found.")
                    return
                typer.echo(f"{len(results)} result(s):")
                for n in results:
                    pressure = circuit.get_pressure(n.id)
                    title = _extract_title(n.content)
                    p_str = f"  p={pressure:.2f}" if pressure > 0 else ""
                    typer.echo(f"  {n.id}  {title}{p_str}")
        finally:
            await circuit.close()

    _run(_retrieve())


# -------------------------------------------------------------------
# list
# -------------------------------------------------------------------


@app.command(name="list")
def list_neurons(
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Filter by domain"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max neurons to show"),
    meta_keys: bool = typer.Option(False, "--meta-keys", help="List filterable/searchable metadata keys"),
    meta_values: Optional[str] = typer.Option(None, "--meta-values", help="List distinct values for a metadata key"),
    domains: bool = typer.Option(False, "--domains", help="List domains with neuron counts"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """List neurons, metadata keys, or domains."""

    async def _list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            # Meta-key discovery mode
            if meta_keys:
                keys = await circuit.get_meta_keys()
                if as_json:
                    _out(keys, use_json=True)
                else:
                    if not keys:
                        typer.echo("No metadata keys found.")
                        return
                    typer.echo("Metadata keys:")
                    for k in keys:
                        samples = ", ".join(k["sample_values"][:3])
                        typer.echo(f"  {k['key']}  [{k['layer']}]  ({k['count']} sources)  e.g. {samples}")
                return

            # Meta-values mode
            if meta_values:
                values = await circuit.get_meta_values(meta_values)
                if as_json:
                    _out(values, use_json=True)
                else:
                    if not values:
                        typer.echo(f"No values found for key '{meta_values}'.")
                        return
                    typer.echo(f"Values for '{meta_values}':")
                    for v in values:
                        typer.echo(f"  {v['value']}  [{v['layer']}]  ({v['count']})")
                return

            # Domain discovery mode
            if domains:
                counts = await circuit.get_domain_counts()
                if as_json:
                    _out(counts, use_json=True)
                else:
                    if not counts:
                        typer.echo("No domains found.")
                        return
                    typer.echo("Domains:")
                    for c in counts:
                        typer.echo(f"  {c['domain']:20s}  {c['count']} neurons")
                return

            # Default: list neurons
            kwargs = {"limit": limit}
            if type:
                kwargs["type"] = type
            if domain:
                kwargs["domain"] = domain
            neurons = await circuit.list_neurons(**kwargs)
            if as_json:
                _out([_neuron_dict(n, circuit) for n in neurons], use_json=True)
            else:
                if not neurons:
                    typer.echo("No neurons found.")
                    return
                typer.echo(f"{len(neurons)} neuron(s):")
                for n in neurons:
                    title = _extract_title(n.content)
                    meta = ""
                    if n.type:
                        meta += f"  [{n.type}]"
                    if n.domain:
                        meta += f"  @{n.domain}"
                    typer.echo(f"  {n.id}  {title}{meta}")
        finally:
            await circuit.close()

    _run(_list())


# -------------------------------------------------------------------
# link
# -------------------------------------------------------------------


@app.command()
def link(
    pre: str = typer.Argument(..., help="Source neuron ID"),
    post: str = typer.Argument(..., help="Target neuron ID"),
    type: str = typer.Option("relates_to", "--type", "-t", help="Synapse type: requires|extends|contrasts|relates_to"),
    weight: float = typer.Option(0.5, "--weight", "-w", help="Initial weight"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Create a synapse between two neurons."""
    try:
        syn_type = SynapseType(type)
    except ValueError:
        typer.echo(f"Invalid type: {type}. Use: requires, extends, contrasts, relates_to", err=True)
        raise typer.Exit(1)

    async def _link():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            created = await circuit.add_synapse(pre, post, syn_type, weight=weight)
            if as_json:
                _out([{"pre": s.pre, "post": s.post, "type": s.type.value, "weight": s.weight} for s in created], use_json=True)
            else:
                for s in created:
                    typer.echo(f"Linked {s.pre} --{s.type.value}--> {s.post}")
        finally:
            await circuit.close()

    _run(_link())


# -------------------------------------------------------------------
# stats
# -------------------------------------------------------------------


@app.command()
def stats(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Show circuit statistics."""

    async def _stats():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            s = await circuit.stats()
            if as_json:
                _out(s, use_json=True)
            else:
                typer.echo(f"Neurons:      {s['neurons']}")
                typer.echo(f"Synapses:     {s['synapses']}")
                typer.echo(f"Density:      {s['graph_density']:.4f}")
                typer.echo(f"Cards:        {s['cards_loaded']}")
                typer.echo(f"Communities:  {s['communities']}")
        finally:
            await circuit.close()

    _run(_stats())


# -------------------------------------------------------------------
# communities
# -------------------------------------------------------------------


@app.command()
def communities(
    detect: bool = typer.Option(False, "--detect", help="Force re-detection of communities"),
    resolution: float = typer.Option(1.0, "--resolution", "-r", help="Louvain resolution parameter"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Show or detect communities in the knowledge graph."""

    async def _communities():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            if detect:
                result = await circuit.detect_communities(resolution=resolution)
                if as_json:
                    # Convert to JSON-friendly format
                    _out({
                        "detected": True,
                        "count": len(result),
                        "communities": {str(k): v for k, v in result.items()},
                    }, use_json=True)
                else:
                    if not result:
                        typer.echo("No communities detected (empty graph).")
                        return
                    typer.echo(f"Detected {len(result)} community(ies):")
                    for cid, members in sorted(result.items()):
                        labels = []
                        for nid in members[:5]:
                            n = await circuit.get_neuron(nid)
                            labels.append(_extract_title(n.content) if n else nid)
                        suffix = f" (+{len(members) - 5} more)" if len(members) > 5 else ""
                        typer.echo(f"  [{cid}] {len(members)} neurons: {', '.join(labels)}{suffix}")
            else:
                cmap = circuit.community_map()
                if as_json:
                    # Group by community
                    groups: dict[int, list[str]] = {}
                    for nid, cid in cmap.items():
                        groups.setdefault(cid, []).append(nid)
                    _out({
                        "count": len(groups),
                        "communities": {str(k): v for k, v in groups.items()},
                    }, use_json=True)
                else:
                    if not cmap:
                        typer.echo("No communities assigned yet. Run: spkt communities --detect")
                        return
                    groups = {}
                    for nid, cid in cmap.items():
                        groups.setdefault(cid, []).append(nid)
                    typer.echo(f"{len(groups)} community(ies):")
                    for cid, members in sorted(groups.items()):
                        labels = []
                        for nid in members[:5]:
                            n = await circuit.get_neuron(nid)
                            labels.append(_extract_title(n.content) if n else nid)
                        suffix = f" (+{len(members) - 5} more)" if len(members) > 5 else ""
                        typer.echo(f"  [{cid}] {len(members)} neurons: {', '.join(labels)}{suffix}")
        finally:
            await circuit.close()

    _run(_communities())


# -------------------------------------------------------------------
# inspect
# -------------------------------------------------------------------


@app.command()
def inspect(
    neuron_id: str = typer.Argument(..., help="Neuron ID to inspect"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Inspect a neuron: content, FSRS state, pressure, neighbors."""

    async def _inspect():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            neuron = await circuit.get_neuron(neuron_id)
            if neuron is None:
                typer.echo(f"Neuron {neuron_id} not found", err=True)
                raise typer.Exit(1)

            sources = await circuit.get_sources_for_neuron(neuron_id)
            community_id = circuit.get_community(neuron_id)

            if as_json:
                d = _neuron_dict(neuron, circuit)
                d["neighbors_out"] = circuit.neighbors(neuron_id)
                d["neighbors_in"] = circuit.predecessors(neuron_id)
                d["community_id"] = community_id
                d["sources"] = [
                    {"id": s.id, "url": s.url, "title": s.title}
                    for s in sources
                ]
                _out(d, use_json=True)
            else:
                typer.echo(f"ID:       {neuron.id}")
                typer.echo(f"Type:     {neuron.type or '-'}")
                typer.echo(f"Domain:   {neuron.domain or '-'}")
                typer.echo(f"Created:  {neuron.created_at}")

                card = circuit.get_card(neuron_id)
                if card:
                    stab = f"{card.stability:.2f}" if card.stability is not None else "-"
                    diff = f"{card.difficulty:.2f}" if card.difficulty is not None else "-"
                    typer.echo(f"FSRS:     stability={stab}  difficulty={diff}  state={card.state.name}  due={card.due}")

                pressure = circuit.get_pressure(neuron_id)
                typer.echo(f"Pressure: {pressure:.4f}")

                if community_id is not None:
                    typer.echo(f"Community: {community_id}")

                if sources:
                    typer.echo(f"Sources ({len(sources)}):")
                    for s in sources:
                        label = s.title or s.url or s.id
                        typer.echo(f"  {s.id}  {label}")

                neighbors = circuit.neighbors(neuron_id)
                preds = circuit.predecessors(neuron_id)
                if neighbors:
                    typer.echo(f"Out ({len(neighbors)}): {', '.join(neighbors)}")
                if preds:
                    typer.echo(f"In  ({len(preds)}):  {', '.join(preds)}")

                typer.echo(f"\n{neuron.content}")
        finally:
            await circuit.close()

    _run(_inspect())


# -------------------------------------------------------------------
# quiz (interactive flashcard session)
# -------------------------------------------------------------------


@app.command()
def quiz(
    limit: int = typer.Option(10, "--limit", "-n", help="Max neurons per session"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON (non-interactive, dump quiz items)"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Run an interactive flashcard review session."""

    async def _quiz():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            fc = Flashcard(circuit)
            due_ids = await fc.select(limit=limit)

            if not due_ids:
                if as_json:
                    _out({"status": "no_due", "reviewed": 0}, use_json=True)
                else:
                    typer.echo("No neurons due for review.")
                return

            # JSON mode: dump all quiz items non-interactively (for agent use)
            if as_json:
                items = []
                for nid in due_ids:
                    scaffold = fc.scaffold(nid)
                    item = await fc.present(nid, scaffold)
                    neuron = await circuit.get_neuron(nid)
                    items.append({
                        "neuron_id": nid,
                        "title": _extract_title(neuron.content) if neuron else nid,
                        "scaffold_level": scaffold.level.value,
                        "question": item.question,
                        "answer": item.answer,
                        "hints": item.hints,
                        "context": scaffold.context,
                        "gaps": scaffold.gaps,
                    })
                _out({"status": "due", "count": len(items), "items": items}, use_json=True)
                return

            # Interactive mode
            reviewed = 0
            grades: dict[str, int] = {"miss": 0, "weak": 0, "fire": 0, "strong": 0}

            typer.echo(f"\n{len(due_ids)} neuron(s) due for review.\n")

            for i, nid in enumerate(due_ids, 1):
                scaffold = fc.scaffold(nid)
                item = await fc.present(nid, scaffold)
                neuron = await circuit.get_neuron(nid)
                title = _extract_title(neuron.content) if neuron else nid

                typer.echo(f"--- [{i}/{len(due_ids)}] {title} (scaffold: {scaffold.level.value}) ---")
                typer.echo(f"\n{item.question}\n")

                if item.hints:
                    for hint in item.hints:
                        typer.echo(f"  hint: {hint}")

                # Wait for self-grade
                grade_input = typer.prompt(
                    "Grade (miss/weak/fire/strong or 1-4, 'a' for answer, 'q' to quit)"
                )

                if grade_input.lower() == "q":
                    typer.echo("Session stopped.")
                    break

                if grade_input.lower() == "a":
                    typer.echo(f"\n{item.answer}\n")
                    grade_input = typer.prompt("Now grade (miss/weak/fire/strong or 1-4)")

                grade = fc.evaluate(nid, item, grade_input)
                await fc.record(nid, grade)
                grades[grade.name.lower()] += 1
                reviewed += 1

                card = circuit.get_card(nid)
                stab = f"{card.stability:.1f}" if card and card.stability else "-"
                due_str = str(card.due) if card else "-"
                typer.echo(f"  -> {grade.name}  stability={stab}  next_due={due_str}\n")

            # Summary
            typer.echo(f"\nSession complete: {reviewed} reviewed")
            for g, count in grades.items():
                if count > 0:
                    typer.echo(f"  {g}: {count}")

        finally:
            await circuit.close()

    _run(_quiz())


# -------------------------------------------------------------------
# learn
# -------------------------------------------------------------------


@app.command(name="learn")
def learn_cmd(
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
        import hashlib

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
                typer.echo(f"metadata.jsonl line {line_no}: invalid JSON — {e}", err=True)
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
            typer.echo(f"  {r['source_id']} — {r['source_title']} ({r['content_length']} chars)")
        if meta_map:
            typer.echo(f"  metadata.jsonl: {len(meta_map)} entries applied")
        typer.echo("\nUse the /spkt-learn agent skill to chunk content into neurons.")


def _emit_learn_result_from_dict(result: dict) -> None:
    """Output learn result for a single file from result dict."""
    typer.echo(f"Source: {result['source_id']} ({result['source_url']})")
    typer.echo(f"Content: {result['content_length']} chars")
    typer.echo(f"Domain: {result.get('domain') or '-'}")
    typer.echo("\nUse the /spkt-learn agent skill to chunk this content into neurons.")


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
        typer.echo("\nUse the /spkt-learn agent skill to chunk this content into neurons.")


# -------------------------------------------------------------------
# refresh
# -------------------------------------------------------------------


@app.command()
def refresh(
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
                            # Not modified
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
                except Exception as e:
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
# export / import
# -------------------------------------------------------------------


@app.command(name="export")
def export_cmd(
    output: Path = typer.Option(..., "--output", "-o", help="Output file path"),
    format: str = typer.Option("tar", "--format", help="Export format: tar, json, qabot"),
    include_embeddings: bool = typer.Option(False, "--include-embeddings", help="Include embeddings in JSON export"),
    as_json: bool = typer.Option(False, "--json", help="Output result as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Export the brain for backup or deployment.

    Formats:
      tar   — Full .spikuit/ archive (default)
      json  — Portable JSON bundle (neurons, synapses, sources)
      qabot — Read-only SQLite for QABot deployment
    """

    async def _export():
        config = _load_brain_config(brain)

        if format == "tar":
            _export_tar(config, output)
        elif format == "json":
            await _export_json(config, output, include_embeddings, brain)
        elif format == "qabot":
            await _export_qabot(config, output, brain)
        else:
            typer.echo(f"Unknown format: {format}", err=True)
            raise typer.Exit(1)

        if as_json:
            _out({"format": format, "output": str(output), "size": output.stat().st_size}, use_json=True)
        else:
            size_kb = output.stat().st_size / 1024
            typer.echo(f"Exported ({format}) → {output} ({size_kb:.1f} KB)")

    _run(_export())


def _export_tar(config: BrainConfig, output: Path) -> None:
    """Export .spikuit/ as a tar.gz archive."""
    import tarfile

    spikuit_dir = config.spikuit_dir
    if not spikuit_dir.exists():
        typer.echo(f".spikuit/ not found at {config.root}", err=True)
        raise typer.Exit(1)

    with tarfile.open(output, "w:gz") as tar:
        tar.add(spikuit_dir, arcname=".spikuit")


async def _export_json(config: BrainConfig, output: Path, include_embeddings: bool, brain_path: Path | None) -> None:
    """Export brain as a JSON bundle."""
    import struct

    circuit = _get_circuit(brain_path)
    await circuit.connect()
    try:
        neurons = await circuit.list_neurons(limit=100_000)
        sources = await circuit.list_sources(limit=100_000)

        # Collect synapses from graph
        synapses = []
        for u, v, data in circuit.graph.edges(data=True):
            synapses.append({
                "pre_id": u,
                "post_id": v,
                "type": data.get("type", "relates_to"),
                "weight": data.get("weight", 0.5),
                "co_fires": data.get("co_fires", 0),
            })

        # Collect neuron-source links
        neuron_sources = []
        for n in neurons:
            nsources = await circuit.get_sources_for_neuron(n.id)
            for s in nsources:
                neuron_sources.append({"neuron_id": n.id, "source_id": s.id})

        bundle: dict = {
            "version": "0.4.0",
            "brain_name": config.name,
            "neurons": [
                {
                    "id": n.id,
                    "content": n.content,
                    "type": n.type,
                    "domain": n.domain,
                    "created_at": str(n.created_at),
                    "updated_at": str(n.updated_at),
                }
                for n in neurons
            ],
            "synapses": synapses,
            "sources": [
                {
                    "id": s.id,
                    "url": s.url,
                    "title": s.title,
                    "author": s.author,
                    "content_hash": s.content_hash,
                    "filterable": s.filterable,
                    "searchable": s.searchable,
                    "status": s.status,
                    "created_at": str(s.created_at),
                }
                for s in sources
            ],
            "neuron_sources": neuron_sources,
            "communities": circuit.community_map(),
        }

        if include_embeddings:
            emb_map = {}
            for n in neurons:
                rows = await circuit._db.conn.execute_fetchall(
                    "SELECT vec FROM neuron_vec WHERE rowid IN (SELECT rowid FROM neuron_vec_map WHERE neuron_id = ?)",
                    (n.id,),
                )
                if rows:
                    blob = rows[0]["vec"]
                    dim = len(blob) // 4
                    vec = list(struct.unpack(f"{dim}f", blob))
                    emb_map[n.id] = vec
            bundle["embeddings"] = emb_map

        output.write_text(json.dumps(bundle, ensure_ascii=False, default=str, indent=2))
    finally:
        await circuit.close()


async def _export_qabot(config: BrainConfig, output: Path, brain_path: Path | None) -> None:
    """Export a read-only QABot SQLite bundle."""
    import shutil
    import sqlite3

    circuit = _get_circuit(brain_path)
    await circuit.connect()
    try:
        # Create a new SQLite DB with only what QABot needs
        if output.exists():
            output.unlink()

        conn = sqlite3.connect(str(output))
        conn.execute("PRAGMA journal_mode=WAL")

        # Create tables
        conn.executescript("""
            CREATE TABLE neuron (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT,
                domain TEXT,
                community_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE synapse (
                pre_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL DEFAULT 0.5,
                co_fires INTEGER DEFAULT 0,
                PRIMARY KEY (pre_id, post_id)
            );
            CREATE TABLE source (
                id TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                author TEXT,
                filterable TEXT,
                searchable TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE neuron_source (
                neuron_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                PRIMARY KEY (neuron_id, source_id)
            );
        """)

        # Copy neurons
        neurons = await circuit.list_neurons(limit=100_000)
        for n in neurons:
            cid = circuit.get_community(n.id)
            conn.execute(
                "INSERT INTO neuron VALUES (?, ?, ?, ?, ?, ?, ?)",
                (n.id, n.content, n.type, n.domain, cid, str(n.created_at), str(n.updated_at)),
            )

        # Copy synapses
        for u, v, data in circuit.graph.edges(data=True):
            conn.execute(
                "INSERT INTO synapse VALUES (?, ?, ?, ?, ?)",
                (u, v, data.get("type", "relates_to"), data.get("weight", 0.5), data.get("co_fires", 0)),
            )

        # Copy sources (citation-only: no raw content, no freshness)
        sources = await circuit.list_sources(limit=100_000)
        for s in sources:
            conn.execute(
                "INSERT INTO source VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    s.id, s.url, s.title, s.author,
                    json.dumps(s.filterable) if s.filterable else None,
                    json.dumps(s.searchable) if s.searchable else None,
                    str(s.created_at),
                ),
            )

        # Copy neuron-source links
        for n in neurons:
            nsources = await circuit.get_sources_for_neuron(n.id)
            for s in nsources:
                conn.execute(
                    "INSERT INTO neuron_source VALUES (?, ?)",
                    (n.id, s.id),
                )

        # Copy embeddings if they exist
        try:
            src_db = circuit._db
            # Read all embeddings from source
            rows = await src_db.conn.execute_fetchall(
                "SELECT neuron_id FROM neuron_vec_map"
            )
            if rows:
                # Copy vec data via raw SQL
                import struct
                conn.execute("""CREATE TABLE neuron_embedding (
                    neuron_id TEXT PRIMARY KEY,
                    vec BLOB NOT NULL
                )""")
                for row in rows:
                    nid = row["neuron_id"]
                    vec_rows = await src_db.conn.execute_fetchall(
                        "SELECT vec FROM neuron_vec WHERE rowid IN (SELECT rowid FROM neuron_vec_map WHERE neuron_id = ?)",
                        (nid,),
                    )
                    if vec_rows:
                        conn.execute(
                            "INSERT INTO neuron_embedding VALUES (?, ?)",
                            (nid, vec_rows[0]["vec"]),
                        )
        except Exception:
            pass  # No embeddings, that's fine

        # Mark as QABot bundle
        conn.execute("PRAGMA application_id = 1936158836")  # 'spkt' as int
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
    finally:
        await circuit.close()


@app.command(name="import")
def import_cmd(
    input_path: Path = typer.Argument(..., help="Archive file to import (.tar.gz)"),
    target: Optional[Path] = typer.Option(None, "--target", help="Target directory (default: CWD)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Import a brain from a tar.gz archive."""
    import tarfile

    if not input_path.exists():
        typer.echo(f"File not found: {input_path}", err=True)
        raise typer.Exit(1)

    dest = target or Path.cwd()
    spikuit_dir = dest / ".spikuit"

    if spikuit_dir.exists():
        typer.echo(f".spikuit/ already exists at {dest}. Remove it first or use a different target.", err=True)
        raise typer.Exit(1)

    with tarfile.open(input_path, "r:gz") as tar:
        tar.extractall(path=dest)

    if as_json:
        _out({"imported": str(input_path), "target": str(dest)}, use_json=True)
    else:
        typer.echo(f"Imported {input_path} → {dest}/.spikuit/")


# -------------------------------------------------------------------
# domain (subcommand group)
# -------------------------------------------------------------------

domain_app = typer.Typer(help="Manage domains.")
app.add_typer(domain_app, name="domain")


@domain_app.command(name="rename")
def domain_rename(
    old: str = typer.Argument(..., help="Current domain name"),
    new: str = typer.Argument(..., help="New domain name"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Rename a domain (batch update all neurons)."""

    async def _rename():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            count = await circuit.rename_domain(old, new)
            if as_json:
                _out({"old": old, "new": new, "updated": count}, use_json=True)
            else:
                typer.echo(f"Renamed '{old}' → '{new}' ({count} neurons updated)")
        finally:
            await circuit.close()

    _run(_rename())


@domain_app.command(name="merge")
def domain_merge(
    domains: list[str] = typer.Argument(..., help="Domains to merge"),
    into: str = typer.Option(..., "--into", help="Target domain name"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Merge multiple domains into one target domain."""

    async def _merge():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            count = await circuit.merge_domains(domains, into)
            if as_json:
                _out({"merged": domains, "into": into, "updated": count}, use_json=True)
            else:
                typer.echo(f"Merged {domains} → '{into}' ({count} neurons updated)")
        finally:
            await circuit.close()

    _run(_merge())


# -------------------------------------------------------------------
# source (subcommand group)
# -------------------------------------------------------------------

source_app = typer.Typer(help="Manage sources.")
app.add_typer(source_app, name="source")


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


# -------------------------------------------------------------------
# visualize
# -------------------------------------------------------------------


@app.command()
def visualize(
    output: Path = typer.Option("circuit.html", "--output", "-o", help="Output HTML path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open in browser"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Generate an interactive graph visualization (HTML)."""
    from pyvis.network import Network as PyvisNetwork

    async def _visualize():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            graph = circuit.graph
            if graph.number_of_nodes() == 0:
                typer.echo("Circuit is empty — nothing to visualize.")
                return

            net = PyvisNetwork(
                height="100vh",
                width="100%",
                directed=True,
                bgcolor="#1a1a2e",
                font_color="#e0e0e0",
                select_menu=True,
                cdn_resources="in_line",
            )

            net.set_options("""{
                "physics": {
                    "forceAtlas2Based": {
                        "gravitationalConstant": -80,
                        "centralGravity": 0.01,
                        "springLength": 120,
                        "springConstant": 0.08,
                        "damping": 0.4
                    },
                    "solver": "forceAtlas2Based",
                    "stabilization": {"iterations": 150}
                },
                "edges": {
                    "arrows": {"to": {"enabled": true, "scaleFactor": 0.6}},
                    "smooth": {"type": "curvedCW", "roundness": 0.15},
                    "color": {"inherit": false}
                },
                "interaction": {
                    "hover": true,
                    "tooltipDelay": 100,
                    "multiselect": true
                }
            }""")

            _DOMAIN_COLORS = {
                "math": "#e74c3c",
                "cs": "#3498db",
                "language": "#2ecc71",
                "philosophy": "#9b59b6",
            }
            _COMMUNITY_PALETTE = [
                "#e74c3c", "#3498db", "#2ecc71", "#9b59b6", "#f39c12",
                "#1abc9c", "#e67e22", "#e91e63", "#00bcd4", "#8bc34a",
                "#ff5722", "#607d8b", "#cddc39", "#795548", "#03a9f4",
            ]
            _DEFAULT_NODE_COLOR = "#5dade2"

            # Determine coloring strategy: communities first, fallback to domain
            cmap = circuit.community_map()
            use_community_colors = len(cmap) > 0

            # Compute degree centrality for node sizing
            centrality_map: dict[str, float] = {}
            if graph.number_of_nodes() > 1:
                import networkx as nx_local
                centrality_map = nx_local.degree_centrality(graph)

            for nid in graph.nodes:
                node_data = graph.nodes[nid]
                neuron = await circuit.get_neuron(nid)
                title = _extract_title(neuron.content) if neuron else nid
                domain = node_data.get("domain")
                pressure = node_data.get("pressure", 0.0)
                community_id = node_data.get("community_id")

                # Size: base + stability + centrality (not just pressure)
                card = circuit.get_card(nid)
                stability = card.stability if card and card.stability else 0.0
                centrality = centrality_map.get(nid, 0.0)
                size = 12 + stability * 3 + centrality * 20 + min(pressure, 1.0) * 10

                # Color: community-based or domain-based
                if use_community_colors and community_id is not None:
                    color = _COMMUNITY_PALETTE[community_id % len(_COMMUNITY_PALETTE)]
                    group = community_id  # pyvis physics clustering
                elif domain:
                    color = _DOMAIN_COLORS.get(domain, _DEFAULT_NODE_COLOR)
                    group = None
                else:
                    color = _DEFAULT_NODE_COLOR
                    group = None

                tooltip = f"<b>{title}</b><br>ID: {nid}"
                if community_id is not None:
                    tooltip += f"<br>community: {community_id}"
                if card:
                    if card.stability is not None:
                        tooltip += f"<br>stability: {card.stability:.1f}"
                    if card.difficulty is not None:
                        tooltip += f"<br>difficulty: {card.difficulty:.1f}"
                    tooltip += f"<br>state: {card.state.name}"
                if pressure > 0:
                    tooltip += f"<br>pressure: {pressure:.3f}"

                kwargs = {"label": title, "title": tooltip, "size": size, "color": color, "font": {"size": 12}}
                if group is not None:
                    kwargs["group"] = group
                net.add_node(nid, **kwargs)

            _EDGE_STYLES = {
                "requires": {"color": "#e74c3c", "dashes": False},
                "extends": {"color": "#f39c12", "dashes": False},
                "contrasts": {"color": "#9b59b6", "dashes": [5, 5]},
                "relates_to": {"color": "#95a5a6", "dashes": [2, 4]},
            }

            for u, v, data in graph.edges(data=True):
                syn_type = data.get("type", "relates_to")
                weight = data.get("weight", 0.5)
                co_fires = data.get("co_fires", 0)
                style = _EDGE_STYLES.get(syn_type, _EDGE_STYLES["relates_to"])
                edge_width = 1 + weight * 4
                tooltip = f"{syn_type}<br>weight: {weight:.2f}<br>co_fires: {co_fires}"
                net.add_edge(u, v, title=tooltip, width=edge_width, color=style["color"], dashes=style.get("dashes", False))

            net.save_graph(str(output))

            html = output.read_text()
            css_inject = "<style>html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; }</style>"

            # Build legend HTML
            legend_items = ""
            if use_community_colors:
                # Group by community
                groups: dict[int, int] = {}
                for nid, cid in cmap.items():
                    groups[cid] = groups.get(cid, 0) + 1
                for cid in sorted(groups):
                    c = _COMMUNITY_PALETTE[cid % len(_COMMUNITY_PALETTE)]
                    legend_items += (
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:12px;height:12px;border-radius:50%;background:{c};display:inline-block"></span>'
                        f'<span>Community {cid} ({groups[cid]})</span></div>'
                    )
            else:
                for domain_name, c in _DOMAIN_COLORS.items():
                    legend_items += (
                        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
                        f'<span style="width:12px;height:12px;border-radius:50%;background:{c};display:inline-block"></span>'
                        f'<span>{domain_name}</span></div>'
                    )

            legend_html = (
                '<div id="legend" style="position:fixed;top:10px;right:10px;background:rgba(26,26,46,0.9);'
                'padding:12px 16px;border-radius:8px;color:#e0e0e0;font:13px monospace;z-index:1000;'
                f'max-height:50vh;overflow-y:auto">{legend_items}</div>'
            )

            html = html.replace("<head>", f"<head>{css_inject}", 1)
            html = html.replace("</body>", f"{legend_html}</body>", 1)
            output.write_text(html)

            typer.echo(f"Saved to {output} ({graph.number_of_nodes()} neurons, {graph.number_of_edges()} synapses)")

            if open_browser:
                import webbrowser
                webbrowser.open(f"file://{output.resolve()}")
        finally:
            await circuit.close()

    _run(_visualize())


# -------------------------------------------------------------------
# skills
# -------------------------------------------------------------------

skills_app = typer.Typer(help="Manage Spikuit skills for Agent CLIs.")
app.add_typer(skills_app, name="skills")


@skills_app.command(name="install")
def skills_install(
    target: Optional[Path] = typer.Option(None, "--target", "-t", help="Target directory (default: .claude/skills/)"),
) -> None:
    """Install Spikuit skills (SKILL.md) for Agent CLIs.

    Copies /tutor, /learn, and /qabot skill definitions into the target
    directory so they can be invoked from Agent CLIs like Claude Code.
    """
    import importlib.resources
    import shutil

    # Determine source: bundled skills inside this package
    skills_pkg = importlib.resources.files("spikuit_cli") / "skills"

    # Determine target
    if target is None:
        target = Path.cwd() / ".claude" / "skills"

    target = Path(target)
    skill_names = ["tutor", "learn", "qabot"]

    installed = 0
    for name in skill_names:
        src = skills_pkg / name / "SKILL.md"
        if not src.is_file():
            typer.echo(f"  skip {name}: SKILL.md not found in package", err=True)
            continue

        dest_dir = target / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / "SKILL.md"

        # Read from package resources and write to target
        content = src.read_text(encoding="utf-8")
        dest_file.write_text(content, encoding="utf-8")
        installed += 1

    if installed > 0:
        typer.echo(f"Installed {installed} skill(s) to {target}/")
        for name in skill_names:
            if (target / name / "SKILL.md").exists():
                typer.echo(f"  /{name}")
    else:
        typer.echo("No skills installed.", err=True)
        raise typer.Exit(1)


@skills_app.command(name="list")
def skills_list() -> None:
    """List available Spikuit skills."""
    import importlib.resources

    skills_pkg = importlib.resources.files("spikuit_cli") / "skills"
    skill_names = ["tutor", "learn", "qabot"]

    typer.echo("Available skills:")
    for name in skill_names:
        src = skills_pkg / name / "SKILL.md"
        if src.is_file():
            # Read first description line from frontmatter
            content = src.read_text(encoding="utf-8")
            desc = ""
            in_frontmatter = False
            for line in content.splitlines():
                if line.strip() == "---":
                    in_frontmatter = not in_frontmatter
                    continue
                if in_frontmatter and line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()[:80]
                    break
            typer.echo(f"  /{name:8s} {desc}")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _install_agent_skills(brain_root: Path) -> None:
    """Interactive Agent CLI selection and skills installation."""
    import importlib.resources

    agents = {
        "1": ("Claude Code", ".claude/skills"),
        "2": ("Cursor", ".cursor/skills"),
        "3": ("Codex", ".codex/skills"),
    }

    typer.echo("Which Agent CLI do you use?")
    for key, (name, _) in agents.items():
        typer.echo(f"  {key}) {name}")

    choice = typer.prompt("Select", default="1")
    if choice not in agents:
        typer.echo(f"Invalid choice: {choice}", err=True)
        return

    agent_name, skills_rel = agents[choice]
    target = brain_root / skills_rel

    skills_pkg = importlib.resources.files("spikuit_cli") / "skills"
    skill_names = ["tutor", "learn", "qabot"]

    installed = 0
    for name in skill_names:
        src = skills_pkg / name / "SKILL.md"
        if not src.is_file():
            continue
        dest_dir = target / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        content = src.read_text(encoding="utf-8")
        (dest_dir / "SKILL.md").write_text(content, encoding="utf-8")
        installed += 1

    if installed > 0:
        typer.echo(f"\nInstalled {installed} skill(s) for {agent_name} at {target}/")
        for name in skill_names:
            if (target / name / "SKILL.md").exists():
                typer.echo(f"  /{name}")
    else:
        typer.echo("No skills installed.", err=True)


def _extract_title(content: str) -> str:
    """Extract first heading or first line as title."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line and not line.startswith("---"):
            return line[:60]
    return "(untitled)"


def main() -> None:
    app()


if __name__ == "__main__":
    main()

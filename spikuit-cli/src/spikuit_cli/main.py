"""Entry point for the spkt CLI."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from spikuit_core import Circuit, Flashcard, Grade, Neuron, Plasticity, Spike, SynapseType
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
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Embed all neurons that don't have embeddings yet (backfill)."""

    async def _embed_all():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            if circuit._embedder is None:
                typer.echo("No embedder configured. Edit .spikuit/config.toml to enable.", err=True)
                raise typer.Exit(1)
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
            if as_json:
                _out(_neuron_dict(neuron, circuit), use_json=True)
            else:
                typer.echo(f"Added neuron {neuron.id}")
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
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Retrieve neurons matching a query (graph-weighted scoring)."""

    async def _retrieve():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            results = await circuit.retrieve(query, limit=limit)
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
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """List neurons in the circuit."""

    async def _list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
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
                typer.echo(f"Neurons:   {s['neurons']}")
                typer.echo(f"Synapses:  {s['synapses']}")
                typer.echo(f"Density:   {s['graph_density']:.4f}")
                typer.echo(f"Cards:     {s['cards_loaded']}")
        finally:
            await circuit.close()

    _run(_stats())


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

            if as_json:
                d = _neuron_dict(neuron, circuit)
                d["neighbors_out"] = circuit.neighbors(neuron_id)
                d["neighbors_in"] = circuit.predecessors(neuron_id)
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
            _DEFAULT_NODE_COLOR = "#5dade2"

            for nid in graph.nodes:
                node_data = graph.nodes[nid]
                neuron = await circuit.get_neuron(nid)
                title = _extract_title(neuron.content) if neuron else nid
                domain = node_data.get("domain")
                pressure = node_data.get("pressure", 0.0)
                size = 15 + min(pressure, 1.0) * 25
                color = _DOMAIN_COLORS.get(domain, _DEFAULT_NODE_COLOR) if domain else _DEFAULT_NODE_COLOR

                card = circuit.get_card(nid)
                tooltip = f"<b>{title}</b><br>ID: {nid}"
                if card:
                    if card.stability is not None:
                        tooltip += f"<br>stability: {card.stability:.1f}"
                    if card.difficulty is not None:
                        tooltip += f"<br>difficulty: {card.difficulty:.1f}"
                    tooltip += f"<br>state: {card.state.name}"
                if pressure > 0:
                    tooltip += f"<br>pressure: {pressure:.3f}"

                net.add_node(nid, label=title, title=tooltip, size=size, color=color, font={"size": 12})

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
            html = html.replace("<head>", f"<head>{css_inject}", 1)
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

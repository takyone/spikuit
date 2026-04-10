"""Entry point for the spkt CLI."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from spikuit_core import Circuit, Grade, Neuron, Plasticity, Spike, SynapseType

app = typer.Typer(
    name="spkt",
    help="Spikuit — neural knowledge graph with spaced repetition.",
    no_args_is_help=True,
)

# Default DB path
DEFAULT_DB = Path.home() / ".spikuit" / "circuit.db"


def _get_circuit(db: Path) -> Circuit:
    return Circuit(db_path=db)


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
# add
# -------------------------------------------------------------------


@app.command()
def add(
    content: str = typer.Argument(..., help="Markdown content for the neuron"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Neuron type"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain tag"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Add a new Neuron to the circuit."""

    async def _add():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Fire a spike (record a review) on a Neuron."""
    g = _GRADE_MAP.get(grade.lower())
    if g is None:
        typer.echo(f"Invalid grade: {grade}. Use: miss, weak, fire, strong", err=True)
        raise typer.Exit(1)

    async def _fire():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Show neurons due for review."""

    async def _due():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Retrieve neurons matching a query (graph-weighted scoring)."""

    async def _retrieve():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """List neurons in the circuit."""

    async def _list():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Create a synapse between two neurons."""
    try:
        syn_type = SynapseType(type)
    except ValueError:
        typer.echo(f"Invalid type: {type}. Use: requires, extends, contrasts, relates_to", err=True)
        raise typer.Exit(1)

    async def _link():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Show circuit statistics."""

    async def _stats():
        circuit = _get_circuit(db)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Inspect a neuron: content, FSRS state, pressure, neighbors."""

    async def _inspect():
        circuit = _get_circuit(db)
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
# visualize
# -------------------------------------------------------------------


@app.command()
def visualize(
    output: Path = typer.Option("circuit.html", "--output", "-o", help="Output HTML path"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open in browser"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Generate an interactive graph visualization (HTML)."""
    from pyvis.network import Network as PyvisNetwork

    async def _visualize():
        circuit = _get_circuit(db)
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
# Helpers
# -------------------------------------------------------------------


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

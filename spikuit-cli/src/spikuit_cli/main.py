"""Entry point for the spkt CLI."""

from __future__ import annotations

import asyncio
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


# -------------------------------------------------------------------
# add
# -------------------------------------------------------------------


@app.command()
def add(
    content: str = typer.Argument(..., help="Markdown content for the neuron"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Neuron type"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain tag"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Add a new Neuron to the circuit."""

    async def _add():
        circuit = _get_circuit(db)
        await circuit.connect()
        try:
            # Interpret escape sequences from CLI input
            real_content = content.encode().decode("unicode_escape")
            neuron = Neuron.create(real_content, type=type, domain=domain)
            await circuit.add_neuron(neuron)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Show neurons due for review."""

    async def _due():
        circuit = _get_circuit(db)
        await circuit.connect()
        try:
            ids = await circuit.due_neurons(limit=limit)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Retrieve neurons matching a query (graph-weighted scoring)."""

    async def _retrieve():
        circuit = _get_circuit(db)
        await circuit.connect()
        try:
            results = await circuit.retrieve(query, limit=limit)
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
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Show circuit statistics."""

    async def _stats():
        circuit = _get_circuit(db)
        await circuit.connect()
        try:
            s = await circuit.stats()
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

            typer.echo(f"ID:       {neuron.id}")
            typer.echo(f"Type:     {neuron.type or '-'}")
            typer.echo(f"Domain:   {neuron.domain or '-'}")
            typer.echo(f"Created:  {neuron.created_at}")

            card = circuit.get_card(neuron_id)
            if card:
                typer.echo(f"FSRS:     stability={card.stability:.2f}  difficulty={card.difficulty:.2f}  state={card.state.name}  due={card.due}")

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

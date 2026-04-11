"""Synapse management commands: spkt synapse {add,remove,weight,list}."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from spikuit_core import SynapseType

from ..helpers import _get_circuit, _out, _run

synapse_app = typer.Typer(help="Manage synapses.")


@synapse_app.command(name="add")
def synapse_add(
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

    async def _add():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            created = await circuit.add_synapse(pre, post, syn_type, weight=weight)
            if as_json:
                _out([{
                    "pre": s.pre, "post": s.post, "type": s.type.value,
                    "weight": s.weight, "confidence": s.confidence.value,
                    "confidence_score": s.confidence_score,
                } for s in created], use_json=True)
            else:
                for s in created:
                    typer.echo(f"Linked {s.pre} --{s.type.value}--> {s.post}")
        finally:
            await circuit.close()

    _run(_add())


@synapse_app.command(name="remove")
def synapse_remove(
    pre: str = typer.Argument(..., help="Source neuron ID"),
    post: str = typer.Argument(..., help="Target neuron ID"),
    type: str = typer.Option("relates_to", "--type", "-t", help="Synapse type"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Remove a synapse between two neurons."""
    try:
        syn_type = SynapseType(type)
    except ValueError:
        typer.echo(f"Invalid type: {type}. Use: requires, extends, contrasts, relates_to", err=True)
        raise typer.Exit(1)

    async def _remove():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            await circuit.remove_synapse(pre, post, syn_type)
            if as_json:
                _out({"removed": {"pre": pre, "post": post, "type": type}}, use_json=True)
            else:
                typer.echo(f"Removed {pre} --{type}--> {post}")
        finally:
            await circuit.close()

    _run(_remove())


@synapse_app.command(name="weight")
def synapse_weight(
    pre: str = typer.Argument(..., help="Source neuron ID"),
    post: str = typer.Argument(..., help="Target neuron ID"),
    weight: float = typer.Argument(..., help="New weight value"),
    type: str = typer.Option("relates_to", "--type", "-t", help="Synapse type"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Set the weight of a synapse."""
    try:
        syn_type = SynapseType(type)
    except ValueError:
        typer.echo(f"Invalid type: {type}. Use: requires, extends, contrasts, relates_to", err=True)
        raise typer.Exit(1)

    async def _weight():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            synapse = await circuit.set_synapse_weight(pre, post, syn_type, weight)
            if as_json:
                _out({
                    "pre": synapse.pre, "post": synapse.post, "type": synapse.type.value,
                    "weight": synapse.weight, "confidence": synapse.confidence.value,
                    "confidence_score": synapse.confidence_score,
                }, use_json=True)
            else:
                typer.echo(f"Set weight {pre} --{type}--> {post} = {weight}")
        finally:
            await circuit.close()

    _run(_weight())


@synapse_app.command(name="list")
def synapse_list(
    neuron_id: Optional[str] = typer.Option(None, "--neuron", "-n", help="Filter by neuron ID"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by synapse type"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """List synapses, optionally filtered by neuron or type."""
    syn_type = None
    if type:
        try:
            syn_type = SynapseType(type)
        except ValueError:
            typer.echo(f"Invalid type: {type}. Use: requires, extends, contrasts, relates_to", err=True)
            raise typer.Exit(1)

    async def _list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            synapses = await circuit.list_synapses(neuron_id=neuron_id, type=syn_type)
            if as_json:
                _out([{
                    "pre": s.pre, "post": s.post, "type": s.type.value,
                    "weight": s.weight, "confidence": s.confidence.value,
                    "confidence_score": s.confidence_score,
                } for s in synapses], use_json=True)
            else:
                if not synapses:
                    typer.echo("No synapses found.")
                    return
                typer.echo(f"{len(synapses)} synapse(s):")
                for s in synapses:
                    conf = f"  [{s.confidence.value}]" if s.confidence.value != "extracted" else ""
                    typer.echo(f"  {s.pre} --{s.type.value}--> {s.post}  w={s.weight:.2f}{conf}")
        finally:
            await circuit.close()

    _run(_list())

"""Community management commands: spkt community {detect,list}."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..helpers import _extract_title, _get_circuit, _out, _run

community_app = typer.Typer(help="Manage graph communities.")


@community_app.command(name="detect")
def community_detect(
    resolution: float = typer.Option(1.0, "--resolution", "-r", help="Louvain resolution parameter"),
    summarize: bool = typer.Option(False, "--summarize", "-s", help="Generate summary neurons for each community"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Run community detection on the knowledge graph."""

    async def _detect():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            result = await circuit.detect_communities(resolution=resolution)
            summaries = []
            if summarize and result:
                summaries = await circuit.generate_community_summaries()
            if as_json:
                out = {
                    "detected": True,
                    "count": len(result),
                    "communities": {str(k): v for k, v in result.items()},
                }
                if summaries:
                    out["summaries"] = summaries
                _out(out, use_json=True)
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
                if summaries:
                    typer.echo(f"\nGenerated {len(summaries)} community summary neuron(s).")
        finally:
            await circuit.close()

    _run(_detect())


@community_app.command(name="list")
def community_list(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Show current community assignments."""

    async def _list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            cmap = circuit.community_map()
            if as_json:
                groups: dict[int, list[str]] = {}
                for nid, cid in cmap.items():
                    groups.setdefault(cid, []).append(nid)
                _out({
                    "count": len(groups),
                    "communities": {str(k): v for k, v in groups.items()},
                }, use_json=True)
            else:
                if not cmap:
                    typer.echo("No communities assigned yet. Run: spkt community detect")
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

    _run(_list())

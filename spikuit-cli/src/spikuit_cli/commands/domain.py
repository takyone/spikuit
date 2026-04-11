"""Domain management commands: spkt domain {list,rename,merge}."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..helpers import _get_circuit, _out, _run

domain_app = typer.Typer(help="Manage domains.")


@domain_app.command(name="list")
def domain_list(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """List domains with neuron counts."""

    async def _list():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
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
        finally:
            await circuit.close()

    _run(_list())


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
                typer.echo(f"Renamed '{old}' \u2192 '{new}' ({count} neurons updated)")
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
                typer.echo(f"Merged {domains} \u2192 '{into}' ({count} neurons updated)")
        finally:
            await circuit.close()

    _run(_merge())


@domain_app.command(name="audit")
def domain_audit(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
) -> None:
    """Analyze domain ↔ community alignment and suggest actions."""

    async def _audit():
        circuit = _get_circuit(brain)
        await circuit.connect()
        try:
            result = await circuit.domain_audit()
            if as_json:
                _out(result, use_json=True)
            else:
                domains = result["domains"]
                suggestions = result["suggestions"]
                keywords = result["community_keywords"]

                if not domains:
                    typer.echo("No domains found. Run 'spkt community detect' first.")
                    return

                typer.echo("Domain ↔ Community Alignment\n")
                for d in domains:
                    comms = ", ".join(
                        f"c{c['community_id']} ({c['count']})"
                        for c in d["communities"]
                    )
                    typer.echo(f"  {d['domain']:20s}  {d['neuron_count']} neurons  [{comms}]")

                if keywords:
                    typer.echo("\nCommunity Keywords:")
                    for cid, kws in sorted(keywords.items(), key=lambda x: x[0]):
                        if kws:
                            typer.echo(f"  c{cid}: {', '.join(kws)}")

                if suggestions:
                    typer.echo(f"\nSuggestions ({len(suggestions)}):")
                    for s in suggestions:
                        if s["action"] == "split":
                            comms_str = ", ".join(
                                f"c{c['community_id']} ({c['count']} neurons, keywords: {', '.join(c.get('keywords', []))})"
                                for c in s["communities"]
                            )
                            typer.echo(f"  SPLIT '{s['domain']}': spans {len(s['communities'])} communities")
                            typer.echo(f"         {comms_str}")
                        elif s["action"] == "merge":
                            doms = ", ".join(
                                f"{d['domain']} ({d['count']})"
                                for d in s["domains"]
                            )
                            typer.echo(f"  MERGE in c{s['community_id']}: {doms}")
                            kws = s.get("keywords", [])
                            if kws:
                                typer.echo(f"         suggested name hint: {', '.join(kws)}")
                else:
                    typer.echo("\nNo alignment issues detected.")
        finally:
            await circuit.close()

    _run(_audit())

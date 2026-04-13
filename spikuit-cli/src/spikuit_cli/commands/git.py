"""Git wrappers for Brain version management.

Spikuit recommends using git for Brain versioning instead of
implementing in-engine snapshots/transactions. These commands are
thin wrappers around git that know the Spikuit commit message
conventions:

    ingest(<tag>): <summary>
    consolidate: <summary>
    review(<date>): <summary>
    manual: <summary>

Branch policy (enforced by agent runbooks, not core):

* Batch operations cut a short-lived branch from main, work on it,
  and merge fast-forward when the user confirms (or abandon if not).
* Single-neuron operations commit directly to main.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from ..helpers import (
    GITIGNORE_TEMPLATE,
    _brain_root,
    _current_branch,
    _get_circuit,
    _git,
    _is_git_repo,
    _out,
    _run,
)

branch_app = typer.Typer(help="Manage Brain version-control branches.")


# -- branch start/finish/abandon --------------------------------------------


def _ingest_branch(tag: str) -> str:
    return f"ingest/{tag}"


@branch_app.command(name="start")
def branch_start(
    tag: str = typer.Argument(..., help="Short tag for this batch (e.g. 'papers-2026-04')"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Cut a new ingest/<tag> branch from main for a batch operation."""
    if not _is_git_repo(brain):
        typer.echo("Brain has no git repository. Run 'spkt init --git' first.", err=True)
        raise typer.Exit(1)

    branch = _ingest_branch(tag)
    _git("checkout", "-b", branch, brain=brain, capture=True)
    _out({"branch": branch, "from": "main"}, use_json=as_json)


@branch_app.command(name="finish")
def branch_finish(
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Merge the current ingest/<tag> branch fast-forward into main and delete it."""
    if not _is_git_repo(brain):
        typer.echo("Brain has no git repository.", err=True)
        raise typer.Exit(1)

    current = _current_branch(brain)
    if not current.startswith("ingest/") and not current.startswith("consolidate/"):
        typer.echo(
            f"Refusing to finish: current branch '{current}' is not an ingest/consolidate branch.",
            err=True,
        )
        raise typer.Exit(1)

    _git("checkout", "main", brain=brain, capture=True)
    _git("merge", "--ff-only", current, brain=brain, capture=True)
    _git("branch", "-d", current, brain=brain, capture=True)
    _out({"merged": current, "into": "main"}, use_json=as_json)


@branch_app.command(name="abandon")
def branch_abandon(
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Discard the current ingest/<tag> branch without merging."""
    if not _is_git_repo(brain):
        typer.echo("Brain has no git repository.", err=True)
        raise typer.Exit(1)

    current = _current_branch(brain)
    if not current.startswith("ingest/") and not current.startswith("consolidate/"):
        typer.echo(
            f"Refusing to abandon: current branch '{current}' is not an ingest/consolidate branch.",
            err=True,
        )
        raise typer.Exit(1)

    _git("checkout", "main", brain=brain, capture=True)
    _git("branch", "-D", current, brain=brain, capture=True)
    _out({"abandoned": current}, use_json=as_json)


# -- history & undo (top-level commands) ------------------------------------


history_app = typer.Typer(
    help="Brain history: git log view + AMKB event-log prune.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@history_app.callback()
def _history_root(
    ctx: typer.Context,
    limit: int = typer.Option(20, "--limit", "-n", help="Max commits to show"),
    grep: Optional[str] = typer.Option(
        None, "--grep", "-g", help="Filter commits by message substring"
    ),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show Brain commit history when invoked without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    _history_show(limit=limit, grep=grep, brain=brain, as_json=as_json)


def _history_show(
    *,
    limit: int,
    grep: Optional[str],
    brain: Optional[Path],
    as_json: bool,
) -> None:
    if not _is_git_repo(brain):
        typer.echo("Brain has no git repository.", err=True)
        raise typer.Exit(1)

    args = ["log", f"-{limit}", "--pretty=format:%h%x09%ad%x09%s", "--date=iso-strict"]
    if grep:
        args.extend(["--grep", grep])
    result = _git(*args, brain=brain, capture=True)

    rows: list[dict] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            sha, date, msg = parts
            rows.append({"sha": sha, "date": date, "message": msg})

    if as_json:
        _out(rows, use_json=True)
    else:
        for r in rows:
            typer.echo(f"{r['sha']}  {r['date']}  {r['message']}")


@history_app.command(name="prune")
def history_prune_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Physically delete every soft-retired neuron and synapse.

    Escape hatch for AMKB soft-retire: once you are sure you will not need
    retired rows for audit or recovery, this reclaims their storage. The
    git-tracked event log is preserved.
    """
    async def _count(c):
        retired_total = await c._db.count_neurons(include_retired=True)
        live = await c._db.count_neurons()
        return retired_total - live

    circuit = _get_circuit(brain)
    pending = _run(_count(circuit))
    if pending == 0:
        _out({"neurons_pruned": 0, "synapses_pruned": 0}, use_json=as_json)
        if not as_json:
            typer.echo("Nothing to prune.")
        return

    if not yes:
        confirm = typer.confirm(
            f"Permanently delete {pending} retired neuron(s)? "
            "Event log is preserved."
        )
        if not confirm:
            raise typer.Exit(1)

    result = _run(circuit.prune_retired())
    _out(result, use_json=as_json)
    if not as_json:
        typer.echo(
            f"Pruned {result['neurons_pruned']} neurons, "
            f"{result['synapses_pruned']} synapses."
        )


def undo_cmd(
    to: Optional[str] = typer.Option(
        None, "--to", help="Revert all commits since <sha> (exclusive)"
    ),
    ingest_tag: Optional[str] = typer.Option(
        None, "--ingest-tag", help="Revert all commits matching ingest(<tag>)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    brain: Optional[Path] = typer.Option(None, "--brain", "-b", help="Brain root directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Revert Brain commits (last commit by default; use --to or --ingest-tag for batch).

    Wraps git revert with Spikuit-aware filters. Always preserves history —
    revert commits are added on top, never rewriting past commits.
    """
    if not _is_git_repo(brain):
        typer.echo("Brain has no git repository.", err=True)
        raise typer.Exit(1)

    # Resolve target commits
    if ingest_tag:
        result = _git(
            "log",
            "--grep",
            f"ingest({ingest_tag})",
            "--pretty=format:%H",
            brain=brain,
            capture=True,
        )
        targets = [s for s in result.stdout.strip().splitlines() if s]
    elif to:
        result = _git(
            "log", f"{to}..HEAD", "--pretty=format:%H", brain=brain, capture=True
        )
        targets = [s for s in result.stdout.strip().splitlines() if s]
    else:
        result = _git("rev-parse", "HEAD", brain=brain, capture=True)
        targets = [result.stdout.strip()]

    if not targets:
        typer.echo("No commits to revert.", err=True)
        raise typer.Exit(1)

    if not yes:
        typer.echo(f"About to revert {len(targets)} commit(s):")
        for sha in targets[:10]:
            msg = _git(
                "log", "-1", "--pretty=format:%s", sha, brain=brain, capture=True
            ).stdout.strip()
            typer.echo(f"  {sha[:8]} {msg}")
        if len(targets) > 10:
            typer.echo(f"  ... +{len(targets) - 10} more")
        if not typer.confirm("Proceed?", default=False):
            typer.echo("Aborted.")
            raise typer.Exit(1)

    # Revert in reverse chronological order so dependencies unwind cleanly
    _git("revert", "--no-edit", *targets, brain=brain, capture=True)
    _out({"reverted": targets, "count": len(targets)}, use_json=as_json)


# -- gitignore template helper (used by `spkt init`) ------------------------


def write_gitignore(brain_root: Path) -> Path:
    """Write the recommended .gitignore at the Brain root if absent."""
    path = brain_root / ".gitignore"
    if not path.exists():
        path.write_text(GITIGNORE_TEMPLATE)
    return path

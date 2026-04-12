"""``spkt skills extractor`` — pluggable ingestion extractors as SKILL.md bundles.

Subcommands:

* ``list``    — show resolved extractors (system + brain tier)
* ``status``  — availability check (required commands / packages present?)
* ``show``    — print manifest + SKILL.md for one extractor
* ``fork``    — copy a system extractor into the brain (shadcn-style)
* ``add``     — install an external extractor directory into the brain
* ``remove``  — delete a brain-local extractor
* ``refresh`` — regenerate ``_registry.toml`` for the brain tier
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer

from ..extractors import (
    AvailabilityReport,
    ResolvedExtractor,
    check_availability,
    list_extractors,
    resolve,
)
from ..extractors.registry import (
    brain_extractors_dir,
    system_extractors_dir,
)
from ..helpers import _brain_root, _out

extractor_app = typer.Typer(
    help="Manage Spikuit ingestion extractors (system + brain tier).",
    no_args_is_help=True,
)


def _to_dict(e: ResolvedExtractor) -> dict:
    m = e.manifest
    return {
        "name": e.name,
        "tier": e.tier,
        "path": str(e.path),
        "version": m.version,
        "description": m.description,
        "author": m.author,
        "match": {
            "file_patterns": m.match.file_patterns,
            "url_patterns": m.match.url_patterns,
            "content_keywords": m.match.content_keywords,
        },
        "requires": {
            "commands": m.requires.commands,
            "python_packages": m.requires.python_packages,
        },
    }


def _availability_dict(report: AvailabilityReport) -> dict:
    return {
        "name": report.name,
        "available": report.available,
        "missing_commands": report.missing_commands,
        "missing_python_packages": report.missing_python_packages,
    }


@extractor_app.command(name="list")
def extractor_list(
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List resolved extractors. Brain-tier shadows system-tier on name collision."""
    root = _brain_root(brain) if brain or _has_brain() else None
    extractors = list_extractors(root)

    if as_json:
        _out([_to_dict(e) for e in extractors], use_json=True)
        return

    if not extractors:
        typer.echo("No extractors found.")
        return

    typer.echo(f"{'NAME':20s} {'TIER':8s} {'VERSION':10s} DESCRIPTION")
    for e in extractors:
        desc = (e.manifest.description or "")[:60]
        typer.echo(f"{e.name:20s} {e.tier:8s} {e.manifest.version:10s} {desc}")


@extractor_app.command(name="status")
def extractor_status(
    name: str | None = typer.Argument(None, help="Single extractor to check; omit to check all."),
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check whether each extractor's required commands / packages are installed."""
    root = _brain_root(brain) if brain or _has_brain() else None
    extractors = resolve(root)

    targets: list[ResolvedExtractor]
    if name is not None:
        if name not in extractors:
            typer.echo(f"Extractor '{name}' not found.", err=True)
            raise typer.Exit(1)
        targets = [extractors[name]]
    else:
        targets = sorted(extractors.values(), key=lambda e: e.name)

    reports = [check_availability(e) for e in targets]

    if as_json:
        _out([_availability_dict(r) for r in reports], use_json=True)
        return

    typer.echo(f"{'NAME':20s} {'STATUS':12s} MISSING")
    for r in reports:
        status = "available" if r.available else "missing-deps"
        missing_parts: list[str] = []
        if r.missing_commands:
            missing_parts.append("commands=" + ",".join(r.missing_commands))
        if r.missing_python_packages:
            missing_parts.append("packages=" + ",".join(r.missing_python_packages))
        typer.echo(f"{r.name:20s} {status:12s} {' '.join(missing_parts)}")


@extractor_app.command(name="show")
def extractor_show(
    name: str = typer.Argument(..., help="Extractor name."),
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Print manifest + SKILL.md for one extractor."""
    root = _brain_root(brain) if brain or _has_brain() else None
    extractors = resolve(root)
    if name not in extractors:
        typer.echo(f"Extractor '{name}' not found.", err=True)
        raise typer.Exit(1)

    e = extractors[name]
    skill_text = e.skill_md.read_text(encoding="utf-8") if e.skill_md.is_file() else ""

    if as_json:
        payload = _to_dict(e)
        payload["skill_md"] = skill_text
        _out(payload, use_json=True)
        return

    typer.echo(f"# {e.name}  ({e.tier} tier, v{e.manifest.version})")
    typer.echo(f"path: {e.path}")
    typer.echo(f"description: {e.manifest.description}")
    typer.echo("")
    typer.echo("--- SKILL.md ---")
    typer.echo(skill_text)


@extractor_app.command(name="fork")
def extractor_fork(
    name: str = typer.Argument(..., help="System extractor to copy."),
    new_name: str | None = typer.Argument(
        None, help="Name for the brain-local copy. Defaults to the source name (override the system extractor)."
    ),
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
) -> None:
    """Copy a system extractor into ``<brain>/.spikuit/extractors/`` (shadcn-style)."""
    root = _brain_root(brain)
    src_root = system_extractors_dir()
    src = src_root / name
    if not src.is_dir():
        typer.echo(f"System extractor '{name}' not found at {src}.", err=True)
        raise typer.Exit(1)

    dest_name = new_name or name
    dest = brain_extractors_dir(root) / dest_name
    if dest.exists():
        typer.echo(f"Brain extractor '{dest_name}' already exists at {dest}.", err=True)
        raise typer.Exit(1)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)

    if dest_name != name:
        _rewrite_manifest_name(dest / "manifest.toml", dest_name)

    _write_registry(root)
    typer.echo(f"Forked '{name}' → {dest}")


@extractor_app.command(name="add")
def extractor_add(
    path: Path = typer.Argument(..., help="Local directory containing manifest.toml + SKILL.md."),
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
) -> None:
    """Install an external extractor directory into the brain."""
    root = _brain_root(brain)
    src = path.expanduser().resolve()
    if not src.is_dir():
        typer.echo(f"{src} is not a directory.", err=True)
        raise typer.Exit(1)
    manifest = src / "manifest.toml"
    if not manifest.is_file():
        typer.echo(f"{src} has no manifest.toml.", err=True)
        raise typer.Exit(1)

    from ..extractors.manifest import ManifestError, load_manifest
    try:
        m = load_manifest(manifest)
    except ManifestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    dest = brain_extractors_dir(root) / m.name
    if dest.exists():
        typer.echo(f"Brain extractor '{m.name}' already exists at {dest}.", err=True)
        raise typer.Exit(1)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    _write_registry(root)
    typer.echo(f"Installed '{m.name}' → {dest}")


@extractor_app.command(name="remove")
def extractor_remove(
    name: str = typer.Argument(..., help="Brain-local extractor to delete."),
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation."),
) -> None:
    """Delete a brain-local extractor (system extractors cannot be removed)."""
    root = _brain_root(brain)
    target = brain_extractors_dir(root) / name
    if not target.is_dir():
        typer.echo(f"Brain extractor '{name}' not found at {target}.", err=True)
        raise typer.Exit(1)

    if not yes and not typer.confirm(f"Delete {target}?", default=False):
        raise typer.Abort()

    shutil.rmtree(target)
    _write_registry(root)
    typer.echo(f"Removed {target}")


@extractor_app.command(name="refresh")
def extractor_refresh(
    brain: Path | None = typer.Option(None, "--brain", help="Brain root."),
) -> None:
    """Regenerate ``<brain>/.spikuit/extractors/_registry.toml``."""
    root = _brain_root(brain)
    written = _write_registry(root)
    if written is None:
        typer.echo("No brain extractors directory; nothing to refresh.")
        return
    typer.echo(f"Wrote {written}")


def _has_brain() -> bool:
    """Cheap check: are we inside a brain?"""
    from ..helpers import _load_brain_config
    try:
        _load_brain_config(None)
        return True
    except Exception:
        return False


def _rewrite_manifest_name(manifest_path: Path, new_name: str) -> None:
    """Patch the ``name = "..."`` line under ``[extractor]`` in a manifest.toml."""
    text = manifest_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_extractor = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_extractor = stripped == "[extractor]"
            continue
        if in_extractor and stripped.startswith("name") and "=" in stripped:
            lines[i] = f'name = "{new_name}"'
            break
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_registry(brain_root: Path) -> Path | None:
    """Write a brain-tier ``_registry.toml`` summarizing local extractors."""
    ext_dir = brain_extractors_dir(brain_root)
    if not ext_dir.is_dir():
        return None

    extractors = []
    for entry in sorted(ext_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        manifest_path = entry / "manifest.toml"
        if not manifest_path.is_file():
            continue
        from ..extractors.manifest import ManifestError, load_manifest
        try:
            m = load_manifest(manifest_path)
        except ManifestError:
            continue
        extractors.append((m, entry.name))

    lines = [f'generated_at = "{datetime.now(timezone.utc).isoformat()}"', ""]
    for m, dirname in extractors:
        lines.append("[[extractors]]")
        lines.append(f'name = "{m.name}"')
        lines.append(f'path = "{dirname}"')
        lines.append(f'description = {json.dumps(m.description)}')
        lines.append(f"file_patterns = {json.dumps(m.match.file_patterns)}")
        lines.append(f"url_patterns = {json.dumps(m.match.url_patterns)}")
        lines.append("")

    out = ext_dir / "_registry.toml"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out

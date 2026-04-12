"""Extractor registry — resolve system + brain tiers, brain wins."""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .manifest import Manifest, ManifestError, load_manifest

Tier = Literal["system", "brain"]


@dataclass
class ResolvedExtractor:
    """One extractor after tier resolution."""

    name: str
    tier: Tier
    path: Path
    manifest: Manifest

    @property
    def skill_md(self) -> Path:
        return self.path / "SKILL.md"


def system_extractors_dir() -> Path:
    """Path to the system-tier extractors bundled with spikuit-cli."""
    pkg = importlib.resources.files("spikuit_cli")
    return Path(str(pkg)) / "skills" / "spkt-ingest" / "extractors"


def brain_extractors_dir(brain_root: Path) -> Path:
    """Path to the brain-local extractors directory inside ``.spikuit/``."""
    return brain_root / ".spikuit" / "extractors"


def _scan(root: Path, tier: Tier) -> dict[str, ResolvedExtractor]:
    """Scan a directory for extractor subdirectories with valid manifests."""
    out: dict[str, ResolvedExtractor] = {}
    if not root.is_dir():
        return out
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        manifest_path = entry / "manifest.toml"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest(manifest_path)
        except ManifestError:
            continue
        out[manifest.name] = ResolvedExtractor(
            name=manifest.name,
            tier=tier,
            path=entry,
            manifest=manifest,
        )
    return out


def resolve(brain_root: Path | None = None) -> dict[str, ResolvedExtractor]:
    """Return the merged extractor map. Brain-tier shadows system-tier."""
    merged = _scan(system_extractors_dir(), "system")
    if brain_root is not None:
        merged.update(_scan(brain_extractors_dir(brain_root), "brain"))
    return merged


def list_extractors(brain_root: Path | None = None) -> list[ResolvedExtractor]:
    """Return resolved extractors as a list, sorted by name."""
    return sorted(resolve(brain_root).values(), key=lambda e: e.name)

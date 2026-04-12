"""Extractor manifest schema (parsed from manifest.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MatchSpec:
    """Routing rules — when should this extractor be picked?"""

    file_patterns: list[str] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)
    content_keywords: list[str] = field(default_factory=list)


@dataclass
class ExtractorRequires:
    """External dependencies the extractor needs to run."""

    commands: list[str] = field(default_factory=list)
    python_packages: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    """Parsed manifest.toml for one extractor."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    match: MatchSpec = field(default_factory=MatchSpec)
    requires: ExtractorRequires = field(default_factory=ExtractorRequires)


class ManifestError(ValueError):
    """Raised when a manifest.toml is malformed or missing required fields."""


def load_manifest(path: Path) -> Manifest:
    """Parse a ``manifest.toml`` file into a :class:`Manifest`."""
    if not path.is_file():
        raise ManifestError(f"manifest.toml not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    extractor = data.get("extractor", {})
    name = extractor.get("name")
    if not name:
        raise ManifestError(f"{path}: [extractor].name is required")

    match_data = data.get("match", {})
    requires_data = data.get("requires", {})

    return Manifest(
        name=name,
        version=str(extractor.get("version", "0.0.0")),
        description=str(extractor.get("description", "")),
        author=str(extractor.get("author", "")),
        match=MatchSpec(
            file_patterns=list(match_data.get("file_patterns", [])),
            url_patterns=list(match_data.get("url_patterns", [])),
            content_keywords=list(match_data.get("content_keywords", [])),
        ),
        requires=ExtractorRequires(
            commands=list(requires_data.get("commands", [])),
            python_packages=list(requires_data.get("python_packages", [])),
        ),
    )

"""Availability check — does the host environment have what an extractor needs?"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field

from .registry import ResolvedExtractor


@dataclass
class AvailabilityReport:
    """Result of probing one extractor's runtime requirements."""

    name: str
    available: bool
    missing_commands: list[str] = field(default_factory=list)
    missing_python_packages: list[str] = field(default_factory=list)


def check_availability(extractor: ResolvedExtractor) -> AvailabilityReport:
    """Check whether all of ``extractor.manifest.requires`` are present."""
    missing_cmds = [
        cmd for cmd in extractor.manifest.requires.commands
        if shutil.which(cmd) is None
    ]
    missing_pkgs = [
        pkg for pkg in extractor.manifest.requires.python_packages
        if importlib.util.find_spec(pkg.replace("-", "_")) is None
    ]
    return AvailabilityReport(
        name=extractor.name,
        available=not (missing_cmds or missing_pkgs),
        missing_commands=missing_cmds,
        missing_python_packages=missing_pkgs,
    )

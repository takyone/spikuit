"""Extractor framework — pluggable ingestion strategies as SKILL.md bundles.

Extractors live in two tiers:

    1. Brain-local:  <BRAIN>/.spikuit/extractors/<name>/   (highest priority)
    2. System:       <spkt-install>/skills/spkt-ingest/extractors/<name>/

A brain-local extractor with the same name shadows the system one
(shadcn-style "copy to own"). Each extractor is a directory containing at
minimum a ``manifest.toml`` and a ``SKILL.md`` that an Agent CLI invokes.
"""

from .manifest import ExtractorRequires, Manifest, MatchSpec
from .registry import ResolvedExtractor, list_extractors, resolve
from .availability import AvailabilityReport, check_availability

__all__ = [
    "AvailabilityReport",
    "ExtractorRequires",
    "Manifest",
    "MatchSpec",
    "ResolvedExtractor",
    "check_availability",
    "list_extractors",
    "resolve",
]

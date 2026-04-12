#!/usr/bin/env bash
# Build all three Spikuit distributions in lockstep.
#
# Usage:
#   scripts/release.sh           # build only
#   scripts/release.sh --publish # build + publish to PyPI (requires UV_PUBLISH_TOKEN)
#
# CI normally handles publishing via .github/workflows/publish.yml on tag push.
# This script exists for emergency / local releases and for verifying that all
# three wheels build cleanly before tagging.

set -euo pipefail

PUBLISH=0
if [[ "${1:-}" == "--publish" ]]; then
    PUBLISH=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CORE_VERSION=$(grep -m1 '^version' spikuit-core/pyproject.toml | cut -d'"' -f2)
CLI_VERSION=$(grep -m1 '^version'  spikuit-cli/pyproject.toml  | cut -d'"' -f2)
META_VERSION=$(grep -m1 '^version' pyproject.toml              | cut -d'"' -f2)

if [[ "$CORE_VERSION" != "$CLI_VERSION" || "$CORE_VERSION" != "$META_VERSION" ]]; then
    echo "ERROR: version mismatch" >&2
    echo "  spikuit-core: $CORE_VERSION" >&2
    echo "  spikuit-cli:  $CLI_VERSION" >&2
    echo "  spikuit:      $META_VERSION" >&2
    exit 1
fi
echo "Building Spikuit $CORE_VERSION (3 distributions)"

uv build --package spikuit-core --out-dir dist/spikuit-core
uv build --package spikuit-cli  --out-dir dist/spikuit-cli
uv build --package spikuit      --out-dir dist/spikuit

echo
echo "Built:"
ls dist/spikuit-core dist/spikuit-cli dist/spikuit

if [[ $PUBLISH -eq 1 ]]; then
    : "${UV_PUBLISH_TOKEN:?UV_PUBLISH_TOKEN must be set}"
    # Publish in dependency order so PyPI sees spikuit-core before spikuit-cli.
    uv publish dist/spikuit-core/*
    uv publish dist/spikuit-cli/*
    uv publish dist/spikuit/*
    echo "Published Spikuit $CORE_VERSION to PyPI."
else
    echo
    echo "Build only. Re-run with --publish to upload, or push a v* tag to trigger CI."
fi

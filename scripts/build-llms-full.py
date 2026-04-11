#!/usr/bin/env python3
"""Generate llms-full.txt by concatenating key documentation pages.

Usage:
    python scripts/build-llms-full.py          # writes docs/llms-full.txt
    python scripts/build-llms-full.py --check  # exits 1 if outdated
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
OUTPUT = DOCS / "llms-full.txt"

# Pages to include, in order. Relative to docs/.
PAGES = [
    "getting-started.md",
    "concepts.md",
    "cli.md",
    "how-to-use.md",
    "appendix/neuroscience.md",
    "appendix/psychology.md",
    "appendix/spaced-repetition.md",
    "appendix/graph.md",
    "appendix/retrieval.md",
    "appendix/implementation.md",
]

SEPARATOR = "\n\n---\n\n"


def build() -> str:
    header = (
        "# Spikuit — Full Documentation\n\n"
        "> Auto-generated from docs/. For the concise version, see llms.txt.\n"
        "> Source: https://github.com/takyone/spikuit\n"
        "> Docs: https://takyone.github.io/spikuit/\n"
    )
    sections: list[str] = [header]

    for page in PAGES:
        path = DOCS / page
        if not path.exists():
            print(f"WARNING: {page} not found, skipping", file=sys.stderr)
            continue
        content = path.read_text(encoding="utf-8").strip()
        sections.append(content)

    return SEPARATOR.join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check if output is up-to-date")
    args = parser.parse_args()

    generated = build()

    if args.check:
        if not OUTPUT.exists():
            print("llms-full.txt does not exist", file=sys.stderr)
            sys.exit(1)
        current = OUTPUT.read_text(encoding="utf-8")
        if current != generated:
            print("llms-full.txt is outdated — run: python scripts/build-llms-full.py", file=sys.stderr)
            sys.exit(1)
        print("llms-full.txt is up-to-date")
        return

    OUTPUT.write_text(generated, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(generated):,} chars)")


if __name__ == "__main__":
    main()

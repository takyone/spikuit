"""Migrate tataque knowledge to spikuit.

Usage:
    # Dry run (no writes)
    uv run python scripts/migrate_tataque.py --dry-run

    # Full migration into the current brain
    uv run python scripts/migrate_tataque.py

    # Specify brain location
    uv run python scripts/migrate_tataque.py --brain ~/math

Requires: tataque db at ~/.tataque/tataque.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fsrs import Card, State

from spikuit_core import Circuit, Neuron, SynapseType
from spikuit_core.config import load_config
from spikuit_core.embedder import create_embedder


TATAQUE_DB = Path.home() / ".tataque" / "tataque.db"


# ── Markdown conversion ──────────────────────────────────────────


def _knowledge_to_markdown(data: dict) -> str:
    """Convert tataque knowledge JSON to Markdown."""
    body = data.get("body", data)
    if not isinstance(body, dict):
        return str(body)

    lines: list[str] = []

    # Title
    term = body.get("term") or body.get("title", "")
    if term:
        lines.append(f"# {term}")
        lines.append("")

    # Definition
    defn = body.get("definition", "")
    if defn:
        lines.append(defn)
        lines.append("")

    # Pattern (language items)
    pattern = body.get("pattern", "")
    if pattern:
        lines.append(f"**Pattern:** {pattern}")
        lines.append("")

    # Gender / POS (language items)
    meta_parts = []
    if body.get("gender"):
        meta_parts.append(f"gender: {body['gender']}")
    if body.get("pos"):
        meta_parts.append(f"pos: {body['pos']}")
    if meta_parts:
        lines.append(f"*{', '.join(meta_parts)}*")
        lines.append("")

    # Rationale (design type)
    rationale = body.get("rationale")
    if rationale:
        if isinstance(rationale, list):
            lines.append("## Rationale")
            lines.append("")
            for r in rationale:
                lines.append(f"- {r}")
            lines.append("")
        else:
            lines.append(f"**Rationale:** {rationale}")
            lines.append("")

    # Examples
    examples = body.get("examples", [])
    if examples:
        lines.append("## Examples")
        lines.append("")
        for ex in examples:
            lines.append(f"- {ex}")
        lines.append("")

    # Contrasts
    contrasts = body.get("contrasts_with") or body.get("contrast")
    if contrasts:
        if isinstance(contrasts, str):
            contrasts = [contrasts]
        lines.append("## Contrasts")
        lines.append("")
        for c in contrasts:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines).strip()


# ── FSRS card construction ───────────────────────────────────────


def _build_card(fsrs_row: dict) -> Card:
    """Construct an FSRS Card from tataque fsrs_state row."""
    card = Card()
    card.stability = fsrs_row["stability"]
    card.difficulty = fsrs_row["difficulty"]

    if fsrs_row["review_count"] > 0:
        card.state = State.Review
    else:
        card.state = State.Learning

    if fsrs_row["next_review"]:
        card.due = datetime.fromisoformat(fsrs_row["next_review"])
    if fsrs_row["last_review"]:
        card.last_review = datetime.fromisoformat(fsrs_row["last_review"])

    return card


# ── Synapse discovery ────────────────────────────────────────────


def _extract_contrast_terms(data: dict) -> list[str]:
    """Extract contrast terms from knowledge data."""
    body = data.get("body", data)
    if not isinstance(body, dict):
        return []
    contrasts = body.get("contrasts_with") or body.get("contrast")
    if not contrasts:
        return []
    if isinstance(contrasts, str):
        return [contrasts]
    return contrasts


# ── Main migration ───────────────────────────────────────────────


async def migrate(brain_path: Path | None, dry_run: bool) -> None:
    if not TATAQUE_DB.exists():
        print(f"tataque DB not found at {TATAQUE_DB}")
        return

    # Load tataque data
    tdb = sqlite3.connect(str(TATAQUE_DB))
    tdb.row_factory = sqlite3.Row

    knowledges = tdb.execute(
        "SELECT id, type, domain, data, source, created_at FROM knowledge"
    ).fetchall()

    fsrs_rows = {}
    for row in tdb.execute("SELECT * FROM fsrs_state").fetchall():
        fsrs_rows[row["knowledge_id"]] = dict(row)

    tdb.close()
    print(f"Loaded {len(knowledges)} knowledge items from tataque")

    # Connect to spikuit
    config = load_config(brain_path)
    embedder = create_embedder(
        config.embedder.provider,
        base_url=config.embedder.base_url,
        model=config.embedder.model,
        dimension=config.embedder.dimension,
        api_key=config.embedder.api_key,
        timeout=config.embedder.timeout,
    )
    circuit = Circuit(db_path=config.db_path, embedder=embedder)
    await circuit.connect()

    try:
        # Phase 1: Create neurons + import FSRS state
        id_map: dict[str, str] = {}  # tataque_id -> neuron_id
        term_to_id: dict[str, str] = {}  # term -> neuron_id (for synapse matching)
        contrast_map: dict[str, list[str]] = {}  # neuron_id -> contrast terms

        added = 0
        skipped = 0

        for k in knowledges:
            data = json.loads(k["data"])
            content = _knowledge_to_markdown(data)
            if not content.strip():
                print(f"  SKIP (empty): {k['id']}")
                skipped += 1
                continue

            source = k["source"] or data.get("source")

            neuron = Neuron.create(
                content,
                type=k["type"],
                domain=k["domain"] if k["domain"] != "general" else None,
                source=source,
            )

            # Extract term for synapse matching
            body = data.get("body", data)
            if isinstance(body, dict):
                term = body.get("term") or body.get("title", "")
                if term:
                    term_to_id[term.lower()] = neuron.id

            # Extract contrasts for later synapse creation
            contrasts = _extract_contrast_terms(data)
            if contrasts:
                contrast_map[neuron.id] = contrasts

            id_map[k["id"]] = neuron.id

            if dry_run:
                title = content.split("\n")[0][:60]
                fsrs_info = ""
                if k["id"] in fsrs_rows:
                    fr = fsrs_rows[k["id"]]
                    fsrs_info = f" S={fr['stability']:.1f} D={fr['difficulty']:.1f} R={fr['review_count']}"
                print(f"  ADD {neuron.id} {title}{fsrs_info}")
            else:
                await circuit.add_neuron(neuron)

                # Import FSRS state if exists
                if k["id"] in fsrs_rows:
                    card = _build_card(fsrs_rows[k["id"]])
                    circuit._cards[neuron.id] = card
                    await circuit._db.upsert_fsrs_card(neuron.id, card.to_json())

            added += 1

        print(f"\nPhase 1: {added} neurons {'would be ' if dry_run else ''}added, {skipped} skipped")

        # Phase 2: Create synapses from contrast terms
        linked = 0
        for nid, contrasts in contrast_map.items():
            for term in contrasts:
                target_id = term_to_id.get(term.lower())
                if target_id and target_id != nid:
                    if dry_run:
                        print(f"  LINK {nid} --contrasts--> {target_id} ({term})")
                    else:
                        await circuit.add_synapse(
                            nid, target_id, SynapseType.CONTRASTS, weight=0.5
                        )
                    linked += 1

        # Phase 3: Semantic similarity-based synapses (if embedder available)
        auto_linked = 0
        if not dry_run and embedder is not None:
            print("\nPhase 3: Discovering semantic relations...")
            neuron_ids = list(id_map.values())
            for nid in neuron_ids:
                neuron = await circuit.get_neuron(nid)
                if not neuron:
                    continue
                # Use first 200 chars as query
                query = neuron.content[:200]
                results = await circuit.retrieve(query, limit=6)
                for r in results:
                    if r.id == nid:
                        continue
                    # Check if synapse already exists
                    if circuit.graph.has_edge(nid, r.id) or circuit.graph.has_edge(r.id, nid):
                        continue
                    await circuit.add_synapse(
                        nid, r.id, SynapseType.RELATES_TO, weight=0.3
                    )
                    auto_linked += 1

        print(f"Phase 2: {linked} contrast synapses {'would be ' if dry_run else ''}created")
        if auto_linked:
            print(f"Phase 3: {auto_linked} semantic synapses created")

        # Summary
        print(f"\n{'=== DRY RUN ===' if dry_run else '=== Migration complete ==='}")
        print(f"Neurons: {added}")
        print(f"Synapses: {linked + auto_linked}")
        fsrs_imported = sum(1 for kid in id_map if kid in fsrs_rows)
        print(f"FSRS states imported: {fsrs_imported}")

    finally:
        await circuit.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate tataque → spikuit")
    parser.add_argument("--brain", type=Path, default=None, help="Brain root directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    asyncio.run(migrate(args.brain, args.dry_run))


if __name__ == "__main__":
    main()

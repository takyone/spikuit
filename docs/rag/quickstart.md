# RAG Quickstart

Use Spikuit as a retrieval backend for your own application without
shipping the full Brain engine to production. The flow is:

1. **Author** a Brain locally with the full `spikuit` install.
2. **Export** it to a single SQLite bundle.
3. **Serve** it from a lightweight host that only needs `spikuit-core`.

The serving host stays small: `spikuit-core` (no extras) pulls only
`httpx` and `numpy`. The heavy engine deps (`fsrs`, `networkx`,
`aiosqlite`, `sqlite-vec`, `msgspec`) are confined to your authoring
machine.

## 1. Install

```bash
# Authoring machine — full engine + spkt CLI
pip install spikuit

# Serving host — read-only retrieval client
pip install spikuit-core
```

## 2. Build a brain (authoring machine)

```bash
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5

spkt source ingest https://en.wikipedia.org/wiki/Monad_(category_theory) -d math
spkt source ingest https://en.wikipedia.org/wiki/Functor -d math

spkt embed-all
spkt stats
```

## 3. Export a QABot bundle

```bash
spkt export qabot --output ./brain.db
```

The output is a single SQLite file containing neurons, sources, synapses,
embeddings, and the embedder spec (provider / model / dimension /
prefix style / hint base URL — **no API key**).

## 4. Retrieve from your application

```python
import asyncio
import os

from spikuit_core import QABot

# The serving host points the embedder at its own LM Studio / OpenAI endpoint
os.environ["SPIKUIT_EMBEDDER_BASE_URL"] = "http://localhost:1234/v1"

brain = QABot.load("brain.db")

async def main() -> None:
    hits = await brain.retrieve("What is a monad?", limit=5, domain="math")
    for h in hits:
        print(f"{h.score:.3f}  {h.content[:80]}")
        for s in h.sources:
            print(f"        ↳ {s['url']}")

asyncio.run(main())
```

## Embedder resolution order

`QABot.load` resolves the embedder endpoint in this order:

1. `SPIKUIT_EMBEDDER_BASE_URL` / `SPIKUIT_EMBEDDER_API_KEY` env vars
2. `base_url=` / `api_key=` keyword arguments
3. The hint stored in the bundle (warning: not guaranteed reachable)

If the bundle was exported with `provider = "none"` (no embedder), QABot
runs in keyword-only mode and never tries to call an embedding API.

## What QABot can and cannot do

QABot is intentionally read-only:

| Capability | Available |
|---|---|
| `retrieve()` — hybrid semantic + keyword search | ✅ |
| `system_prompt()` — concatenated `_meta` neurons | ✅ |
| `domains()`, `stats()`, `neuron(id)`, `sources(id)` | ✅ |
| Adding/updating neurons or synapses | ❌ — author offline, re-export |
| FSRS scheduling, propagation, STDP | ❌ — engine-only |

When you need to update the brain, edit it on the authoring machine and
publish a fresh bundle. The serving host swaps the SQLite file in place.

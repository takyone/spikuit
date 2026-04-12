# spikuit-core

[![PyPI](https://img.shields.io/pypi/v/spikuit-core.svg)](https://pypi.org/project/spikuit-core/)
[![Python versions](https://img.shields.io/pypi/pyversions/spikuit-core.svg)](https://pypi.org/project/spikuit-core/)
[![License](https://img.shields.io/github/license/takyone/spikuit.svg)](https://github.com/takyone/spikuit/blob/main/LICENSE)

**Core engine + lightweight RAG client for [Spikuit](https://github.com/takyone/spikuit) — a knowledge base that gets smarter the more you use it.**

> ⚠️ Pre-1.0 / under active development. Expect frequent breaking changes until v1.0.0.

`spikuit-core` ships in two profiles:

| Install | Pulls in | Use case |
|---|---|---|
| `pip install spikuit-core` | `httpx`, `numpy` | Read-only RAG client over an exported `brain.db` bundle |
| `pip install spikuit-core[engine]` | `+ fsrs`, `networkx`, `aiosqlite`, `sqlite-vec`, `msgspec` | Full Brain engine: FSRS scheduling, knowledge graph, spreading activation, STDP |

The minimal install is what you deploy to a server — the heavy engine deps stay on the authoring machine.

## Quick start (RAG client)

Author a brain locally with the full engine (or via the `spkt` CLI from
[`spikuit-cli`](https://pypi.org/project/spikuit-cli/)), export it once,
then retrieve from anywhere with just `spikuit-core`:

```python
import asyncio
import os

from spikuit_core import QABot

os.environ["SPIKUIT_EMBEDDER_BASE_URL"] = "http://localhost:1234/v1"

brain = QABot.load("brain.db")

async def main() -> None:
    hits = await brain.retrieve("What is a monad?", limit=5, domain="math")
    for h in hits:
        print(f"{h.score:.3f}  {h.content[:80]}")

asyncio.run(main())
```

`QABot.load` resolves the embedder endpoint in this order:

1. `SPIKUIT_EMBEDDER_BASE_URL` / `SPIKUIT_EMBEDDER_API_KEY` env vars
2. `base_url=` / `api_key=` keyword arguments
3. The hint stored in the bundle

If the bundle was exported with `provider="none"`, `QABot` runs in keyword-only mode and never calls an embedding API.

## Quick start (full engine)

```python
import asyncio
from spikuit_core import Circuit, Neuron

async def main() -> None:
    c = Circuit(db_path="brain.db")
    await c.connect()
    await c.add_neuron(
        Neuron.create("---\ntype: concept\ndomain: math\n---\n# Monad\n\n型の文脈化を表す抽象")
    )
    await c.close()

asyncio.run(main())
```

Engine symbols (`Circuit`, `Neuron`, `Session`, etc.) are loaded lazily via
PEP 562 `__getattr__` — importing them without the `[engine]` extras raises
a friendly `ImportError` pointing at the install command.

## Links

- **Documentation**: <https://takyone.github.io/spikuit/>
- **RAG quickstart**: <https://takyone.github.io/spikuit/rag/quickstart/>
- **Source**: <https://github.com/takyone/spikuit>
- **Issues**: <https://github.com/takyone/spikuit/issues>

## License

Apache-2.0

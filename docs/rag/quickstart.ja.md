# RAG クイックスタート

Spikuit は、本番環境にフル Brain エンジンを持ち込まなくても、自分のアプリ
ケーションの検索バックエンドとして使えます。流れはこうです。

1. **作成**：手元の開発機でフル `spikuit` を入れて Brain を作る
2. **エクスポート**：1 つの SQLite バンドルに書き出す
3. **配信**：軽量な `spikuit-core` だけ入れたホストから読み出す

配信側はとても軽くて済みます。`spikuit-core` を素で入れるとぶら下がる依存は
`httpx` と `numpy` だけ。重いエンジン依存（`fsrs` / `networkx` / `aiosqlite`
/ `sqlite-vec` / `msgspec`）は作成側のマシンに閉じ込められます。

## 1. インストール

```bash
# 作成側 — フルエンジン + spkt CLI
pip install spikuit

# 配信側 — 読み取り専用の検索クライアント
pip install spikuit-core
```

## 2. Brain を作る（作成側）

```bash
spkt init -p openai-compat \
  --base-url http://localhost:1234/v1 \
  --model text-embedding-nomic-embed-text-v1.5

spkt source learn https://ja.wikipedia.org/wiki/モナド_(圏論) -d math
spkt source learn https://ja.wikipedia.org/wiki/関手 -d math

spkt embed-all
spkt stats
```

## 3. QABot バンドルにエクスポート

```bash
spkt export qabot --output ./brain.db
```

出力は 1 つの SQLite ファイルで、Neuron / Source / Synapse / 埋め込みベクトル
に加えて embedder のスペック（provider / model / dimension / prefix style /
ヒント用 base URL）が入っています。**API キーは入りません**。

## 4. アプリから検索する

```python
import asyncio
import os

from spikuit_core import QABot

# 配信側ホストは自分の LM Studio / OpenAI エンドポイントを指す
os.environ["SPIKUIT_EMBEDDER_BASE_URL"] = "http://localhost:1234/v1"

brain = QABot.load("brain.db")

async def main() -> None:
    hits = await brain.retrieve("モナドとは？", limit=5, domain="math")
    for h in hits:
        print(f"{h.score:.3f}  {h.content[:80]}")
        for s in h.sources:
            print(f"        ↳ {s['url']}")

asyncio.run(main())
```

## Embedder の解決順

`QABot.load` は次の順番で embedder のエンドポイントを解決します。

1. 環境変数 `SPIKUIT_EMBEDDER_BASE_URL` / `SPIKUIT_EMBEDDER_API_KEY`
2. キーワード引数 `base_url=` / `api_key=`
3. バンドルに記録されているヒント（注意：到達できる保証なし）

バンドルが `provider = "none"` でエクスポートされている（embedder なし）場合、
QABot はキーワード検索のみのモードで動き、埋め込み API を呼びにいきません。

## QABot ができること・できないこと

QABot は意図的に読み取り専用です。

| 機能 | 可否 |
|---|---|
| `retrieve()` — セマンティック + キーワードのハイブリッド検索 | ✅ |
| `system_prompt()` — `_meta` Neuron の連結 | ✅ |
| `domains()` / `stats()` / `neuron(id)` / `sources(id)` | ✅ |
| Neuron や Synapse の追加・更新 | ❌ — オフラインで編集して再エクスポート |
| FSRS スケジューリング、伝播、STDP | ❌ — エンジン側専用 |

Brain を更新したくなったら、作成側のマシンで編集して、新しいバンドルを配信
側に置き換える運用になります。

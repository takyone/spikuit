# 情報検索とRAG

### ハイブリッド検索

Spikuitは複数のシグナルを1つのスコアに統合して検索します:

```
score = max(keyword_sim, semantic_sim) × (1 + retrievability + centrality + pressure + boost)
```

- **キーワード類似度**: BM25スタイルのテキストマッチング
- **セマンティック類似度**: エンベッダー設定時はsqlite-vecのKNN検索を利用
- **検索可能性**: FSRSベースの記憶の強さ — 定着している知識ほど上位に
- **中心性**: グラフ上の位置的な重要度
- **圧力**: 近傍の復習で蓄積するLIFベースの緊急度
- **フィードバックブースト**: QABotSessionの承認/不採用で蓄積される加点

### 検索拡張生成 (RAG)

従来のRAGパイプラインはドキュメントのチャンキング、メタデータ抽出、
エンベディングパイプラインの構築と、前処理の手間が大きいのが難点です。
Spikuitはこれを対話型キュレーションで置き換えます。エージェントが
`/spkt-ingest` の会話を通じて、チャンキング・タグ付け・接続まで面倒を見ます。

### 参考文献

- Robertson, S. & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval*, 3(4), 333–389.
- Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.

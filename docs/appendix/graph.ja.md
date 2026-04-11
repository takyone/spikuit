# ナレッジグラフとグラフベースML

### PageRankとAPPNP

- PageRank（Page et al., 1999）: リンク構造でノードの重要度を計算
- APPNP（Gasteiger et al., 2019）: テレポート確率で局所性を制御できるPersonalized PageRank
- Spikuitでは: 活性化の拡散と検索スコアリングに利用

### コミュニティ検出

- Louvainアルゴリズム（Blondel et al., 2008）: モジュラリティ最適化でコミュニティを検出
- Spikuitでは: 密につながったNeuronをクラスタにまとめ、検索のブーストや要約の自動生成に活用

### 参考文献

- Page, L., Brin, S., Motwani, R. & Winograd, T. (1999). The PageRank Citation Ranking: Bringing Order to the Web. *Stanford InfoLab Technical Report*.
- Gasteiger, J., Bojchevski, A. & Günnemann, S. (2019). Predict then Propagate: Graph Neural Networks meet Personalized PageRank. *ICLR 2019*.
- Blondel, V. D., Guillaume, J.-L., Lambiotte, R. & Lefebvre, E. (2008). Fast unfolding of communities in large networks. *Journal of Statistical Mechanics*, P10008.

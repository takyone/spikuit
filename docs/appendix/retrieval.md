# Information Retrieval & RAG

### Hybrid Retrieval

Spikuit combines multiple retrieval signals into a single score:

```
score = max(keyword_sim, semantic_sim) × (1 + retrievability + centrality + pressure + boost)
```

- **Keyword similarity**: BM25-style text matching
- **Semantic similarity**: sqlite-vec KNN search when an embedder is configured
- **Retrievability**: FSRS-based memory strength (concepts you know well rank higher)
- **Centrality**: graph-structural importance
- **Pressure**: LIF-based urgency from neighbor reviews
- **Feedback boost**: accumulated through QABotSession accept/reject signals

### Retrieval-Augmented Generation (RAG)

Traditional RAG pipelines require significant preprocessing: document chunking,
metadata extraction, embedding pipeline setup. Spikuit replaces this with
conversational curation — the agent handles chunking, tagging, and connecting
through dialogue via `/spkt-teach`.

### References

- Robertson, S. & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval*, 3(4), 333–389.
- Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.

# Knowledge Graphs & Graph-Based ML

### PageRank and APPNP

- PageRank (Page et al., 1999): score nodes by link structure
- APPNP (Gasteiger et al., 2019): Personalized PageRank with teleport probability for locality control
- In Spikuit: used for spreading activation and retrieve scoring

### Community Detection

- Louvain algorithm (Blondel et al., 2008): detects communities by modularity optimization
- In Spikuit: clusters densely connected neurons, enables community-boosted retrieval and summary generation

### References

- Page, L., Brin, S., Motwani, R. & Winograd, T. (1999). The PageRank Citation Ranking: Bringing Order to the Web. *Stanford InfoLab Technical Report*.
- Gasteiger, J., Bojchevski, A. & Günnemann, S. (2019). Predict then Propagate: Graph Neural Networks meet Personalized PageRank. *ICLR 2019*.
- Blondel, V. D., Guillaume, J.-L., Lambiotte, R. & Lefebvre, E. (2008). Fast unfolding of communities in large networks. *Journal of Statistical Mechanics*, P10008.

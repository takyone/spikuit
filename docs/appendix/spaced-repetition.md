# Spaced Repetition Systems

### FSRS (Free Spaced Repetition Scheduler)

Per-neuron spaced repetition (stability, difficulty, next review date).
FSRS v6 is a neural-network-based scheduler that outperforms SM-2 (Anki's default)
on recall prediction accuracy.

- Propagation never touches FSRS state — only affects pressure
- Each neuron maintains independent stability and difficulty parameters
- Grade mapping: `miss` → Again, `weak` → Hard, `fire` → Good, `strong` → Easy

### References

- Ye, J. (2024). FSRS: A modern spaced repetition algorithm. [github.com/open-spaced-repetition/fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki)
- Wozniak, P. A. & Gorzelanczyk, E. J. (1994). Optimization of repetition spacing in the practice of learning. *Acta Neurobiologiae Experimentalis*, 54, 59–62.
- Leitner, S. (1972). *So lernt man lernen*. Herder.

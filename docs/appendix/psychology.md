# Cognitive & Developmental Psychology

### Forgetting Curve and Spaced Repetition

<div class="chart-container">
  <canvas data-chart="forgetting-curve"></canvas>
</div>

- Memory decays exponentially over time (Ebbinghaus, 1885)
- Each successful retrieval strengthens the trace and slows future decay
- Optimal timing: review just before you'd forget
- In Spikuit: FSRS v6 models per-neuron stability and difficulty

### Testing Effect

- Actively retrieving > passively re-reading (Roediger & Karpicke, 2006)
- Even failed retrieval attempts improve later recall
- In Spikuit: the Learn protocol is "present → evaluate", not just "show content"

### ZPD and Scaffolding

<div class="zpd-diagram">
  <div class="zpd-outer">
    <span class="zpd-label">Can't do (yet)</span>
    <div class="zpd-mid">
      <span class="zpd-label">ZPD: can do with support</span>
      <div class="zpd-inner">
        <span class="zpd-label">Can do alone</span>
        <span class="zpd-sublabel">(mastered)</span>
      </div>
    </div>
  </div>
</div>

- ZPD (Vygotsky, 1978): the gap between what you can do alone vs. with guidance
- Scaffolding (Wood, Bruner & Ross, 1976): temporary support, gradually removed as competence grows
- In Spikuit: Scaffold level computed from FSRS state + graph neighbors

### Schema Theory

- Schemas = mental frameworks that organize knowledge (Bartlett, 1932; Piaget)
- New info is easier to learn when it connects to existing schemas
- In Spikuit: the knowledge graph *is* the schema; `IngestSession.ingest()` auto-discovers related concepts

### References

- Ebbinghaus, H. (1885). *Über das Gedächtnis*. Duncker & Humblot. (English translation: *Memory: A Contribution to Experimental Psychology*, 1913.)
- Bartlett, F. C. (1932). *Remembering: A Study in Experimental and Social Psychology*. Cambridge University Press.
- Vygotsky, L. S. (1978). *Mind in Society: The Development of Higher Psychological Processes*. Harvard University Press.
- Wood, D., Bruner, J. S. & Ross, G. (1976). The role of tutoring in problem solving. *Journal of Child Psychology and Psychiatry*, 17(2), 89–100.
- Roediger, H. L. & Karpicke, J. D. (2006). Test-enhanced learning: taking memory tests improves long-term retention. *Psychological Science*, 17(3), 249–255.
- Piaget, J. (1952). *The Origins of Intelligence in Children*. International Universities Press.

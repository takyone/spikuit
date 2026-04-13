# Coaching Theory Survey for Spikuit Tutor

**Status**: draft for review
**Target**: v0.6.3 #42 — Tutor coaching theory improvements
**Audience**: Spikuit contributors designing the Tutor session layer

## Why this survey exists

Issue #42 calls for "scientific teaching improvements" without specifying
which science. Spikuit already embeds one teaching-theory bet (FSRS + ZPD
scaffolding), so adding more without a map risks either reinventing the
same idea under a new name or layering techniques that cancel each other
out. This document enumerates the well-validated teaching/coaching theories,
maps each onto Spikuit's existing substrate, and recommends a concrete
subset for v0.6.3.

The scope is **pedagogical theory → Tutor session implementation**. Out of
scope: retrieval quality (RAG), knowledge curation (LearnSession),
per-neuron spacing policy (FSRS is already frozen).

## The existing substrate

Before adding anything, it helps to list what Spikuit already gives us for
free. Each theory below is evaluated in terms of *what's missing*, not
*what's ideal*.

| Mechanism | Spikuit component | Coverage |
|---|---|---|
| Spaced practice | FSRS per-neuron scheduling | ✓ Strong |
| Retrieval practice (testing effect) | `Flashcard` + `spkt quiz` | ✓ Partial — only self-grade recall, no cued/free-response |
| Scaffolding (Vygotsky ZPD) | `Scaffold` with FULL/GUIDED/MINIMAL/NONE levels | ✓ Partial — level is computed, but scaffolding content (hints) is static |
| Graph-aware prerequisites | Synapses + `scaffold.gaps` from APPNP | ✓ Strong |
| Interleaving | `spkt neuron due` mixes domains naturally | ✓ Incidental |
| Metacognitive calibration | `QuizResponse.confidence` field exists but unused | ✗ Wired but not used |
| Feedback timing | `Flashcard.back()` = immediate reveal | ✓ Immediate by default |
| Worked examples | ✗ None |
| Elaborative interrogation | ✗ None |
| Self-explanation | ✗ None |
| Deliberate practice / desirable difficulty modulation | ✗ FSRS drives schedule but not difficulty of the *question* |

The gaps below the line are where Tutor adds value beyond what core already
provides.

## Theories — one screen each

Each theory is presented with: *what it claims*, *evidence*, *what would
change in Spikuit*, *cost estimate*, *my recommendation for v0.6.3*.

### 1. Retrieval practice (testing effect)

**Claim**: Actively retrieving information from memory produces more
durable learning than re-studying. Effect transfers to novel contexts.

**Evidence**: Medium-to-large effect size across domains — Rowland (2014)
reports g = 0.50, Pan & Rickard (2018) reports d = 0.40 for transfer,
Yang et al. (2021) reports g = 0.50 in applied classroom settings. When
combined with spacing (Latimier et al. 2021), effect reaches g = 0.74.
The most robust finding in learning science.

**Spikuit gap**: Current `Flashcard` is self-graded recognition — the
learner reveals the back and rates themselves. This is *recognition*, not
*retrieval*. A cued-recall or free-response variant is missing.

**Implementation**: Add `FreeResponseQuiz` (already planned for v0.6.3
Phase 2). Front prompts the learner to produce the answer without
revealing; grading is either self-assessed against the revealed back
(`needs_tutor_grading=False`) or Tutor-graded via rubric
(`needs_tutor_grading=True`).

**Cost**: Low — one new Quiz class, ~80 LOC.

**Recommendation**: **Include in v0.6.3**. This is the highest-ROI change.

### 2. Spaced practice

**Claim**: Distributing study across time produces better retention than
massing.

**Evidence**: Robust across meta-analyses. Already validated.

**Spikuit gap**: None. FSRS handles this per-neuron.

**Recommendation**: **Skip** — already solved.

### 3. Interleaving

**Claim**: Mixing problem types during a session improves discrimination
and transfer vs blocking by type.

**Evidence**: Solid for motor skills and math problem categorization;
weaker for pure factual recall.

**Spikuit gap**: `spkt neuron due` naturally mixes domains because FSRS
schedules are independent. However, Tutor's queue ordering could
deliberately interleave by domain/community when slack exists in the
queue.

**Implementation**: `ExamPlan` adds an `interleave_by: str | None`
parameter; when set, the builder reorders the queue to avoid consecutive
same-domain items.

**Cost**: Very low — ~15 LOC in the queue builder.

**Recommendation**: **Include in v0.6.3** as a default-off knob. Low cost,
no downside.

### 4. Desirable difficulties (Bjork)

**Claim**: Making practice *harder* in specific ways (spacing, varying
conditions, interleaving, testing) improves long-term retention even
though it *feels* less effective in the moment.

**Evidence**: Strong meta-theory covering several of the above.

**Spikuit gap**: Partially covered by spacing + interleaving + retrieval.
The missing piece is **difficulty calibration at the question level** —
currently a neuron always presents the same Flashcard regardless of the
learner's FSRS state. A learner at `ScaffoldLevel.NONE` should get a
harder prompt (free response) than one at `FULL` (cued recall with
hints).

**Implementation**: `ExamPlan` selects Quiz *type* based on scaffold
level: `FULL → Flashcard(show_body=True)`, `GUIDED → Flashcard(title_only)`,
`MINIMAL/NONE → FreeResponseQuiz`. This ties together scaffold + quiz type
+ difficulty.

**Cost**: Low — selection logic lives in `ExamPlan.build_step()`.

**Recommendation**: **Include in v0.6.3**. This is the natural unification
of the scaffold level with the quiz type.

### 5. Elaborative interrogation

**Claim**: Asking "why is this true?" or "how does this work?" after a
correct answer deepens encoding by forcing learners to integrate new
knowledge with prior knowledge.

**Evidence**: Moderate utility in Dunlosky et al. (2013). Stronger for
fact-learning than for procedural skills. Dependent on learner having
prior knowledge to elaborate from.

**Spikuit gap**: Spikuit has prior knowledge baked in — the
`Scaffold.context` list (strong neighbor IDs) is exactly "what the
learner already knows about this neuron." A "why" follow-up referencing
those neighbors is straightforward.

**Implementation**: On `FIRE`/`STRONG` grade, Tutor optionally emits a
follow-up prompt: *"You said X. How does this relate to ${context[0]}?"*
The response is LLM-graded as a sanity check, not FSRS-fired (it's a
deepening step, not a review).

**Cost**: Medium — requires LLM prompt templates and a follow-up loop in
`ExamPlan.transitions`. Only runs on correct answers, so latency cost is
bounded.

**Recommendation**: **Include in v0.6.3** but gated behind a
`--elaborate` flag initially. The LLM cost is only justified when the
learner opts in.

### 6. Self-explanation

**Claim**: Prompting learners to explain a worked example or their own
reasoning improves comprehension and transfer.

**Evidence**: Moderate utility (Dunlosky 2013). Overlaps substantially
with elaborative interrogation.

**Spikuit gap**: Same niche as elaborative interrogation.

**Recommendation**: **Defer** — subsumed by elaborative interrogation in
v0.6.3. Revisit in v0.7.0 if the two need to be distinguished.

### 7. Metacognitive calibration

**Claim**: Having learners rate their confidence before revealing the
answer improves their self-awareness of what they do and don't know,
which correlates with better study allocation over time.

**Evidence**: Moderate. Strongest finding: learners are systematically
*over*-confident, and explicit calibration narrows the gap.

**Spikuit gap**: `QuizResponse.confidence` field is defined but not
wired. The TUI doesn't prompt for it, the agent doesn't consume it.

**Implementation**:
1. Add an optional confidence prompt *before* revealing the back: *"How
   confident are you? 1 (guess) — 4 (certain)"*.
2. Store alongside `spike.notes` in DB.
3. Downstream analytics: compare confidence to actual grade, surface
   calibration drift in `spkt progress`.

**Cost**: Low for the capture step (~30 LOC in TUI + DB column). The
analytics are a v0.7.0 concern.

**Recommendation**: **Include in v0.6.3** for the capture step only.
Analytics later.

### 8. Feedback timing — immediate vs delayed

**Claim**: Immediate feedback is best for procedural skills; delayed
feedback is best for complex conceptual learning.

**Evidence**: Mixed and context-dependent. Hattie's meta-analyses show
feedback is one of the largest levers but also one of the most variable.

**Spikuit gap**: `Flashcard.back()` is immediate. No delayed option.

**Recommendation**: **Defer**. The evidence is too context-sensitive to
design a good default, and the implementation adds asynchronous
complexity. Note it as a v0.7.0 experiment instead.

### 9. Cognitive load theory / worked examples

**Claim**: Novice learners benefit more from studying worked examples
than from problem-solving. As expertise grows, problem-solving becomes
more effective (expertise reversal).

**Evidence**: Strong for STEM/procedural domains; weaker for declarative
knowledge.

**Spikuit gap**: No worked-example Quiz type. `ScaffoldLevel.FULL`
already functions like a worked example (shows full body), but it's
displayed as a review card, not framed as "study this example, then try
the next one."

**Implementation**: A `WorkedExampleQuiz` type that shows a solved
example on the front, then on "next" shows a similar unsolved problem.
Requires structured content (examples with solutions), which most
Spikuit neurons don't have today.

**Cost**: High — requires content structure that doesn't exist.

**Recommendation**: **Defer** to v0.7.0 or later. Depends on a neuron
content schema change.

### 10. Mastery learning (Bloom)

**Claim**: Don't advance until the learner has mastered the current unit
(typically 80%+ correct).

**Evidence**: Strong original finding (Bloom's "2 sigma problem"), though
scale and feasibility are the practical challenges.

**Spikuit gap**: Tutor's `max_attempts` is a crude mastery check. FSRS
handles long-term mastery (stability grows with successful reviews). No
session-level mastery gate.

**Implementation**: `ExamPlan` adds an optional `require_mastery: bool`
— if true, MISSed neurons are re-queued later in the same session instead
of only scheduling via FSRS.

**Cost**: Low — re-queue logic in `ExamPlan.on_result()`.

**Recommendation**: **Include in v0.6.3** as an opt-in ExamPlan option.

### 11. Adaptive scaffolding with LLM tutors (2025 state of the art)

**Claim**: Recent research (Stanford SCALE, MathTutorBench) argues that
LLM-based pedagogical agents need explicit scaffolding frameworks —
LLMs alone don't reliably produce pedagogically sound responses. They
need evidence-centered design (structured assessment of what the learner
knows) + social cognitive theory (self-efficacy, goal orientation).

**Evidence**: Emerging 2025 literature. Consensus: LLMs are linguistically
fluent but pedagogically naive; they need harness.

**Spikuit positioning**: Spikuit's `Scaffold` + graph already provide the
evidence-centered piece (the graph *is* the knowledge model). What's
missing is the Tutor prompt harness — instead of letting the LLM freely
generate feedback, the prompt should be templated around scaffold state,
gaps, and recent grade history.

**Implementation**: `TutorSession` uses structured prompt templates
(`templates/tutor/*.j2` or Python format strings) that inject
`Scaffold.context`, `Scaffold.gaps`, recent grade streak, and confidence
calibration into every LLM call. No free-form LLM tutoring.

**Cost**: Medium — prompt template infrastructure.

**Recommendation**: **Include in v0.6.3** as the foundation for all
LLM-driven Tutor behavior. Without this, everything else falls back to
"ask GPT to tutor" which the research shows is unreliable.

## Recommended v0.6.3 subset

Synthesizing the above, here is the minimal coherent bundle for v0.6.3:

| # | Theory | ExamPlan / Tutor feature |
|---|---|---|
| 1 | Retrieval practice | `FreeResponseQuiz` type |
| 4 | Desirable difficulties | ExamPlan selects quiz type by scaffold level |
| 3 | Interleaving | ExamPlan `interleave_by` option (default off) |
| 5 | Elaborative interrogation | Follow-up on FIRE/STRONG (flag-gated) |
| 7 | Metacognitive calibration | Pre-reveal confidence prompt in TUI |
| 10 | Mastery learning | ExamPlan `require_mastery` option |
| 11 | Adaptive LLM scaffolding | Templated Tutor prompts |

This is larger than #42 implies but coherent — each piece reinforces the
others, and dropping any one leaves a gap. The total implementation cost
is dominated by (11) prompt harness and (5) elaborative follow-up loop,
both of which live in `spikuit-agents` and don't touch core.

Two items intentionally deferred:
- **Worked examples** (9) — needs content schema change
- **Feedback timing** (8) — too context-dependent to default

## How this shapes the ExamPlan abstraction

The survey motivates `ExamPlan` as more than "a list of Quizzes":

```python
@dataclass
class ExamPlan:
    steps: list[ExamStep]             # ordered quiz sequence
    interleave_by: str | None = None  # "domain" | "community" | None
    require_mastery: bool = False     # re-queue on MISS
    elaborate_on_correct: bool = False  # elaborative interrogation
    collect_confidence: bool = True   # metacognitive calibration
    prompt_template: str = "default"  # adaptive scaffolding harness

@dataclass
class ExamStep:
    neuron_id: str
    quiz: BaseQuiz              # selected by scaffold level → difficulty
    scaffold: Scaffold
    follow_ups: list[FollowUp]  # filled in by transitions
```

The ExamPlan is built by a `plan_exam(circuit, neuron_ids, **options)`
function that consults scaffold for each neuron and picks the right Quiz
type. The `TutorSession` just walks the plan.

## Decisions (resolved)

1. **Follow-up grading fires FSRS?** — **No.** Elaborative follow-ups
   are a deepening step, not a review. Firing them would double-count a
   neuron in one session and distort FSRS stability. Follow-up results
   are transcribed into `spike.notes` only (so a future review can see
   "last time X was hazy on composition"), never fired.

2. **Confidence prompt UX** — Prompt **on first flip**. When the learner
   presses Space for the first time on a card, intercept: show a Modal
   (*"Before revealing the answer, rate your confidence 1-4"*), then on
   dismiss proceed to flip and reveal back. Second Space press (flip
   back to front) does not re-prompt. This naturally avoids hindsight
   bias without the UI jank of forcing confidence on the front screen.

3. **Interleaving** — Soft fudge, **default off**. When
   `ExamPlan.interleave_by="domain"`, after loading due neurons, pull up
   to 20% additional near-due neurons (next review ≤ 2 days away) from
   other domains and interleave. FSRS optimality is preserved because
   near-due early review costs are negligible.

4. **Mastery loop bound** — Re-queue **max 2 times per neuron**, append
   to end of session queue (never immediate — preserves in-session
   spacing). After 3 total attempts fail, fire as MISS and let FSRS
   schedule the next review normally. Configurable via
   `ExamPlan.mastery_max_requeues: int = 2`.

## References

- Latimier, A., Peyre, H., & Ramus, F. (2021). [A Meta-Analytic Review of the Benefit of Spacing out Retrieval Practice Episodes on Retention](http://www.lscp.net/persons/ramus/docs/EPR20.pdf). *Educational Psychology Review*.
- Dunlosky, J. et al. (2013). [Improving Students' Learning With Effective Learning Techniques](https://journals.sagepub.com/doi/abs/10.1177/1529100612453266). *Psychological Science in the Public Interest*.
- Hou, X. et al. (2025). [A Meta-analytic Review of the Effectiveness of Spacing and Retrieval Practice for Mathematics Learning](https://link.springer.com/article/10.1007/s10648-025-10035-1). *Educational Psychology Review*.
- Stanford SCALE (2025). [A Theory of Adaptive Scaffolding for LLM-Based Pedagogical Agents](https://arxiv.org/html/2508.01503v1). arXiv:2508.01503.
- Macina, J. et al. (2025). [MathTutorBench: A Benchmark for Measuring Open-ended Pedagogical Capabilities of LLM Tutors](https://arxiv.org/html/2502.18940). arXiv:2502.18940.
- Mittelstädt, V. et al. (2025). [Large language models in education: a systematic review](https://www.sciencedirect.com/science/article/pii/S2666920X25001699). *Computers and Education: Artificial Intelligence*.
- Rowland, C. A. (2014). The effect of testing versus restudy on retention: A meta-analytic review of the testing effect. *Psychological Bulletin*, 140(6), 1432–1463.
- Pan, S. C., & Rickard, T. C. (2018). Transfer of test-enhanced learning: Meta-analytic review and synthesis. *Psychological Bulletin*, 144(7), 710–756.
- Yang, C., Luo, L., Vadillo, M. A., Yu, R., & Shanks, D. R. (2021). Testing (quizzing) boosts classroom learning: A systematic and meta-analytic review. *Psychological Bulletin*, 147(4), 399–435.
- Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning: Taking memory tests improves long-term retention. *Psychological Science*, 17(3), 249–255.
- Bjork, R. A., & Bjork, E. L. (2011). Making things hard on yourself, but in a good way: Creating desirable difficulties to enhance learning. *Psychology and the Real World*.
- Bloom, B. S. (1984). The 2 sigma problem: The search for methods of group instruction as effective as one-to-one tutoring. *Educational Researcher*, 13(6), 4–16.

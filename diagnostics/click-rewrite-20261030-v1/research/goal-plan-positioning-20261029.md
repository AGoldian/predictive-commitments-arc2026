# Positioning check: finite partial models and goal-conditioned disambiguation

Checked 29 October 2026 using primary paper pages/full texts. Read the close-prior
claims in `research/competition-and-novelty.md` and
`research/experiment-protocol.md`. This is a bounded three-paper check, including
exactly one additional close prior, Kepler. No experiments, repository execution,
account browsing, source changes, or score reproduction were performed.

The broad ingredients are established. A defensible research question is whether
our particular finite, partially specified committee improves **goal-directed
action selection at matched cost**, beyond the same goal planner without its
distinguishing-action term. A functioning goal/menu component is a prerequisite,
not evidence that this effect exists.

## Verified primary sources and concrete overlap

**Sergey Rodionov, _Executable World Models for ARC-AGI-3 in the Era of Coding
Agents_.** First submitted 6 May 2026; inspected arXiv **v2, 6 June 2026**. The
system maintains Python transition/state/planning code, checks recorded history,
refactors models, and plans through them. Its executor simulates a proposed
sequence and interrupts on an observed frame mismatch. These directly overlap
with executable modeling, retrospective fit, and checked execution; none is a
new contribution here. The described system centers on a maintained model,
rather than establishing our finite partial-committee compatibility rule. This
reading does not prove that rule absent from every related implementation.
[Versioned paper](https://arxiv.org/html/2605.05138v2),
[version/date record](https://arxiv.org/abs/2605.05138v2).

**Karl Friston et al., _Active inference and artificial reasoning_.** Nature
Communications **17, 10125**, published **8 September 2026**; the publisher's
indexed record gives version of record **23 September 2026**. It combines value
and expected information about alternative model structures in action/policy
selection, using Bayesian model reduction. This is direct conceptual prior for
goal-directed model disambiguation. Its ARC-AGI-3 connection is explicit, but its
experiments are three-ball simulations: it assumes an existing latent generative
structure and studies uncertainty about a rule-to-outcome mapping. It does not
demonstrate pixel-to-model induction or an ARC-AGI-3 agent. The earlier local
description is reasonable only with that scope stated. Its code statement names
`DEM_reasoning.m` and compatible SPM commit
`28d1f103b021f729266cb7ea07baaf4d0285b22a`; code was not downloaded or run.
[Publisher](https://www.nature.com/articles/s41467-026-77209-5),
[primary full text in PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13601584/).
The direct publisher fetch hit a cookie redirect; its indexed text and the PMC
article supplied the content, title and publication metadata.

**One additional close prior: Wensen Wu, _Kepler: Auditable World Models for
ARC-AGI-3_.** Inspected **arXiv v1, submitted 30 September 2026**. Sections 2.1–2.3
already combine executable hypotheses, history checks, planning, pre-action
predictions, and interruption on mismatches. Crucially, predictions may omit
cells using `None`; missing/empty predictions can permit execution and remain
unverified. Therefore partial predictions, UNKNOWN cells, coverage reporting and
conditional verification are already prior art. The paper also distinguishes
final replay success from first-exposure discovery and says its failed control
does not identify a causal harness effect. Those cautions apply to our proposed
study. Its described method does not establish our exact compatibility-clique
selector or an active/passive comparison with identical goal menus; that is a
limited reading, not an originality proof. No per-game traces were retrieved.
[Versioned methods/full text](https://arxiv.org/html/2610.00834v1),
[version/date record](https://arxiv.org/abs/2610.00834v1).

## What is concrete in our source, and what remains a hypothesis

The inspected `src/arc_paper/partial_committee.py` revision
`dc42ad901cfa92eab26d6dca9fb00a079959f53995ac17aa97f494169ca64dd6`
compares only overlapping known claims. Missing claims earn no prediction
credit. Because compatibility through UNKNOWN is not transitive, it enumerates
the largest pairwise-compatible subset for one to eight supplied models. Its
score `D = 1 - largest_compatible_size / K` is conditional on this supplied,
uniformly weighted committee; it is not calibrated Bayesian information gain.
It computes both goal-only and goal-filtered distinguishing recommendations
from one finite scored menu. A singleton yields D=0 and equal recommendations.

The motion prior is hand-written and bounded. The partial-motion successor
retains coordinate transitions as unknown, without learning their vectors or
forecasting their effects. It does not infer goals, public completion metadata,
or unmodeled dynamics. LLM-proposed goals/utilities must therefore remain
hypotheses, separate from native pixel forecasts. The integration/goal-menu
sources do not by themselves establish a competent complete solver, useful
semantics, an accurate committee member, or an efficacy result.

The possible contribution is this **specific operational contrast and its
failure analysis**, not executable worlds, model uncertainty, active learning,
partial forecasts, or goal planning in general. This search is too narrow to
claim that even the exact finite rule is unprecedented.

## Experiment that would distinguish the implemented mechanism

This is a proposal, not operation authority. Freeze a new action-selection study
after the goal component is usable; the older main protocol studies fleet
compute allocation/Brier features and cannot silently serve as this estimand.

1. Both passive and active arms perform identical native induction, goal/menu
   generation, utility scoring, all rollouts and **both shadow selections** on
   their own realized histories. Use the same model, prompts, sampling settings,
   action/CPU/model/wall ceilings and full actual cost accounting. Only the
   dispatched recommendation differs: goal-only versus the frozen goal-filtered
   D rule. Extra LLM reasoning in the active arm would confound the contrast.
2. Prospectively report real goal/level attainment and actions/resources to it,
   plus every failure/abstention, coverage, incorrect known claims and correctly
   predicted actually changed pixels. Commit before dispatch and assess only the
   next real return. Unexecuted alternatives have no observed correctness label;
   replay fit and D alone are not successful exploration. Record whether higher
   predicted distinction produces actual known-claim contradictions and later
   goal progress, including cases where the entire committee is wrong.
3. If resources permit a separately frozen diagnostic arm, remove the goal
   filter while retaining D and matched generation. This distinguishes useful
   goal-conditioned inquiry from disagreement seeking that spends actions on
   irrelevant mechanics. Keep all games and unsuccessful menus; do not select
   only decisions where a favorable candidate survives.

Use games held out from development of these changes for any transfer claim;
public-model/pretraining exposure remains possible. The current exposed DEV
prefixes and the same two development games can demonstrate prerequisites and
failure modes, not clean generalization. Even a positive matched result would
support a bounded component claim first; a complete entry and stronger baseline
comparison remain separate evidence requirements.

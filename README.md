# Testing Predictive Commitments in Interactive Reasoning

**Alexander Serov — Independent Researcher**  
Research release, 29 October 2026

Can recent action-prediction errors help an interactive agent allocate shared inference effort? This paper implements that question in ARC-AGI-3 and reports a failed development feasibility test. It does not demonstrate an allocation benefit.

Today's edition brings the implemented method, available results and limitations together, including all three instrumented baseline attempts and their original terminal refusals. The method and corrected baseline source were public before that outcome. The manuscript links below point to this edition; pinned source links preserve the source published before its outcome. This release is not a completed ARC Prize Paper Track submission.

## Read the paper and use the source

- [Short research writeup](paper-draft-20261029/kaggle-writeup.txt).
- [Standalone LaTeX manuscript](paper-draft-20261029/paper.tex), including methods, AI-use disclosure and limitations.
- [Complete selected method source and execution instructions](https://github.com/AGoldian/predictive-commitments-arc2026/tree/86d1690c9695e5d6a460c91cc71801be64c6ed4f/public-method-source-release-v1), including the notebook and readable payload.
- [Exact corrected full-baseline notebook and scoped notices](https://github.com/AGoldian/predictive-commitments-arc2026/tree/86d1690c9695e5d6a460c91cc71801be64c6ed4f/baselines/bpub-owned-preconnect-20261029), published before its outcome.
- [Frozen fitted parameter pair](https://github.com/AGoldian/predictive-commitments-arc2026/tree/86d1690c9695e5d6a460c91cc71801be64c6ed4f/public-method-source-release-v1/parameters).
- [Prospective scientific protocols, calibration methods, budgets and public-game split](https://github.com/AGoldian/predictive-commitments-arc2026/tree/86d1690c9695e5d6a460c91cc71801be64c6ed4f/study).
- [Sanitized corrected main-audit evidence](https://github.com/AGoldian/predictive-commitments-arc2026/blob/86d1690c9695e5d6a460c91cc71801be64c6ed4f/analysis/main-audit-corrected-seed101-20261029.md).

The manuscript and writeup are exact saved copies of this edition. The [second sanitized baseline outcome](analysis/bpub-owned-preconnect-result-20261029.md) retains the original refusal and evidence pins. [The preceding manuscript snapshot](https://github.com/AGoldian/predictive-commitments-arc2026/tree/6bcf404841fecc059fc36369ad926dbba463ca78/paper-draft-20261029) remains available through history. No separately exported PDF is included.

## What the results establish

The four-arm development pilot tested a shared prediction interface, baseline allocation and two learned allocators. The primary comparison is P versus A1: P adds event Brier-error features to matched probability/outcome features under fixed regularization. P supplied valid predictions for **89 of 417 eligible actions (21.3429%)**, below the prespecified **50%** requirement. B1 and A1 met that requirement, but this cannot replace P's failed condition. **No eligible P−A1 efficacy comparison is available.**

In the corrected main audit, B0 passed all 21 evidence checks. Its descriptive observed-public-prefix mean was **14.491341991341992** across all ten public games: one won and nine recorded crashed. The following B1 passed 19 of 21 checks but remained ineligible; no B1 score was calculated. Main-audit A1/P and the other eight fleets were not launched. The original pre-game main failure remains recorded. This technical correction used the same exposed roster, not a fresh sample.

The earlier held-out calibration and first full published-policy reproduction failed their strict readouts. The separate **25-game, four-pass instrumented Bpub run also ended ERROR**, and its original strict readout refused eligibility. All **100 planned slots** remain evidence_unavailable. Both full aggregates and upstream-score reproduction are unavailable; no subset score is reported.

Two sandbox deadlines triggered the shared fail-closed stop well before the 32,370-second work limit. Outer physical cleanup was recorded complete, and the affected children were reaped with closed pipes; these facts do not override the failed whole-run evidence gates. Why the snippets exceeded their deadlines is unestablished. A complete scan of 100 host journals returned a known target-token lower bound of zero and zero observed unknown/pending attempts, but the physical-cost gate failed and the accepted-target total remains unavailable. **This is not measured zero cost.** Those first two instrumented attempts do not establish the outcome of the unmodified upstream policy.

The third instrumented Bpub attempt, kernel141510931/version1, ended ERROR on29October at16:37:44UTC; original full retrieval finished16:48:06UTC. Its single strict readout refused, retaining all100planned rows and null full means. A full-history host-to-child reply required at least4,242,629bytes against a4,194,304-byte cap after eight public actions had settled. Outer physical cleanup completed before global work expiry. The cost scan is incomplete:6,966,479 is a lower bound, not a total; zero observed unknown/pending counters do not prove their absence. A separate initial automatic-RESET watermark parser mismatch remains a preserved refusal. [Sanitized O38 outcome and source hashes](analysis/bpub-timeout-compatible-result-20261029.md) and the [source published before the attempt](https://github.com/AGoldian/predictive-commitments-arc2026/tree/0784ab46ba023db92b6be605a02d863f1a268d88/baselines/bpub-timeout-compatible-20261029) distinguish this case from its predecessors. No successful full reproduction or allocator benefit is established.

The corresponding official P submission received **public score 0.00**. Actual rerun traces and resource use are unavailable, and the cause is unexplained. This official result is separate from the descriptive audit score and development feasibility test.

Public games are an exposed development sample. The incomplete audit, failed feasibility gate and unavailable whole-kernel/draft-model expenditure prevent claims of allocator benefit, generalization or compute efficiency. The paper retains unfavorable outcomes rather than averaging surviving subsets.

## Execution and licensing

The selected P entry notebook's ordinary Save branch writes a labelled offline placeholder. An actual competition rerun invokes the full P method; the placeholder is not a measured score. The separate Bpub notebook executes the full 25-game/four-pass reproduction under its 32,400-second ceiling. The corresponding Kaggle execution notebook remains private under the competition-source embargo, while its method source is public. Execution uses the pinned assets and depends on available free Kaggle resources.

The manuscript is CC BY 4.0. Original code and parameters are MIT-0; inherited code and models retain their separate terms. See the [scoped source notices](https://github.com/AGoldian/predictive-commitments-arc2026/blob/86d1690c9695e5d6a460c91cc71801be64c6ed4f/public-method-source-release-v1/NOTICE.txt). No claim of prize eligibility or organizer approval is made.

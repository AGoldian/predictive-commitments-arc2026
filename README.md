# Testing Predictive Commitments in Interactive Reasoning

Alexander Serov — Independent Researcher

**Preliminary research draft revised 29 October 2026 (Moscow); first public release 28 October.** This release does not demonstrate an allocation benefit. The corresponding official P public score is 0.00, with actual rerun traces and resource use unavailable. It is not a completed ARC Prize Paper Track submission.

- [Read the current short research draft](paper-draft-20261029/kaggle-writeup.txt).
- [Current standalone LaTeX manuscript](paper-draft-20261029/paper.tex), licensed CC BY 4.0, with AI disclosure and limitations. No separately exported PDF is included.
- [Current snapshot details and sanitized evidence](paper-draft-20261029/README.md); [unchanged 28 October snapshot](paper-draft-20261028/README.txt).
- [Complete selected method source and execution instructions](public-method-source-release-v1/README.md).
- [Corrected full published-policy baseline source](baselines/bpub-owned-preconnect-20261029/README.md), with the exact 25-game/four-pass notebook and scoped notices. Its newly accepted run has no result at this source-release cut.
- [Exact Kaggle notebook](public-method-source-release-v1/notebook/official-public-entry.ipynb) and [readable parent/worker payload](public-method-source-release-v1/readable-entry/).
- [Frozen fitted parameter pair and scoped terms](public-method-source-release-v1/parameters/).
- [Frozen prospective study protocol, calibration methods, budgets and public-game split](study/README.md).
- [Disclosed reader JSON-format correction and original A1 refusal](analysis/reader-json-format-erratum.md).
- [Original source archive](archives/public-method-source-release-v1.tar.xz) and [28 October preliminary paper package](archives/paper-draft-20261028-v1.zip).

## Evidence and current scope

The current paper snapshot is dated29October (Moscow), manuscript source commit `9764c8271d807d3fddfa91d8c30982f3ae594d65`, after one eligible corrected B0 result and the following B1 original refusal. It retains the original pre-game O34 failure, negative P DEV result, officialP0.00 and failed calibration/fullBpub. The [snapshot record](paper-draft-20261029/README.md) binds exact source hashes; [corrected-main evidence](analysis/main-audit-corrected-seed101-20261029.md) preserves all ten slots and uncertainty. Earlier snapshots remain available through Git history and the unchanged28October package.

In development, B1 completed: 331/422 valid prediction packets, 412,843 accepted target-output tokens over 287 known requests, with no observed unknown/pending requests in the accepted target scope. The original four-game B1 score also remains unavailable. A1 subsequently completed. Its original reader8 refusal exposed a JSON-list/Python-tuple comparison defect despite exact model identity. One separately pinned reader9 adjudication of unchanged original evidence passed all 21 folds: 390,586 accepted target-output tokens over 330 known attempts, zero observed unknown/pending attempts, and 276/374 valid prediction packets. All four raw states remain crashed and its original-rule fleet score remains unavailable. P subsequently completed but its original reader9 refused the packet-coverage gate: complete counts show 89/417 valid packets (21.3429%), below 50%; the other 20 of 21 folds passed. The 328 missing packets record `prediction_not_supplied`, with invalid/unknown transitions zero. Accepted target-output cost is 404,393 tokens over 303 known requests, with zero observed unknown/pending requests; no eligible P development score is reported; the separate official result is described below. [The sanitized feasibility result](analysis/p-v6-feasibility-result.md) preserves the original refusal and exact evidence pins. [The public technical erratum and exact patch](analysis/reader-json-format-erratum.md) preserve both analysis decisions; there was no A1 GPU replay, refit, model/runtime/budget or endpoint change. These development observations do not establish comparative policy effectiveness. The original audit B0 failed before gameplay. Its prospectively corrected B0 passed with a descriptive ten-game mean14.4913; corrected B1 then refused coverage/child evidence and the sequence stopped. Ten corrected cells remain unlaunched; no P-minus-A1 or complete three-seed/four-arm estimate exists. The five-game calibration has now failed its strict readout, as recorded below. The separate full instrumented Bpub attempt had failed with both complete-run aggregates unavailable; a successful published-policy reproduction remains outstanding. Whole-kernel and draft-model work are unavailable, not zero.

The included notebook is the exact source associated with the requested private P version whose official public score is 0.00; actual competition-rerun traces remain unavailable. Its ordinary Save branch deliberately writes a labelled offline placeholder; only an actual competition rerun invokes the full method. Do not interpret the placeholder as a measured score. Follow its pinned attachments and resource requirements. No paid API or GPU resource is required by this project's resource policy; execution depends on available free Kaggle resources.

Kaggle confirmed that notebooks using this competition as a source cannot be made public until the competition ends, so the corresponding Kaggle execution notebook is private and not anonymously accessible. The full method code was already public before the official request; the [execution metadata overlay](execution-metadata-20261029/README.md) supplies the exact private metadata while preserving the published notebook and payload bytes. Official submission **57749129** was accepted on 28 October at 21:28:14 UTC. Its original observer received API **COMPLETE** and public score **0.00** at **21:42:51.801722 UTC** that day, an API observation time rather than exact server completion. The request selected kernel **141404446/version 1**; final custody matched, without a server version echo. [The sanitized official result](analysis/official-p-result-20261029.md) retains these limits: no actual rerun logs, actions, runtime, tokens or cause of zero are available. The completed Save produced only a labelled placeholder; the official score came separately from the matched API result and does not reverse the P development refusal.


The separate **full instrumented Bpub reproduction failed**: API ERROR observed
at2026-10-28T22:10:23.061729UTC, full original retrieval at22:12:53.254375UTC,
531 API-listed files/532 final inventory entries/6,907,564 bytes. The strict readout
retains all100 planned episodes and returns both full aggregates and reproduced
upstream score as null. Four unknown-usage attempts leave complete target cost
unavailable; known lower bound0 is not actual cost0. The legacy720-second release
occurred while loading. Added accounting interrupted upstream retry handling and
preempted original exception recording; the underlying OS exception and outcome
of the **unmodified** upstream retry policy are not established. [The sanitized
failure note](analysis/bpub-full-reproduction-failure-20261029.md) preserves these
limits. It changes neither P's negative DEV feasibility nor its separate official
0.00 result. The first main B0 failed before gameplay; calibration is recorded below.

The **five-game calibration failed**: kernel141409675/version1 ended ERROR and one frozen readout returned ineligible, retaining all20 original slots as unverified. All five-game macro Brier/log-loss values remain unavailable; no refit or mask selection occurred. A227-frame public SDK return produced a1,952,774-byte host row, above the collection observer's1,048,576-byte limit. Later offline input/node-bound refusals are distinct. At least159,646 known target tokens are retained; the complete cost remains unknown. [Sanitized calibration evidence](analysis/validation-calibration-failure-20261029.md) explains the scope. No test suite, GPU replay or new advisor council was introduced for this manuscript release.

The **first main-audit B0 failed before gameplay**: after model readiness at1948s, an inherited four-session/four-game guard rejected its ten-game roster. One strict readout refused, and the controller stopped before later arms. [Original failure evidence](analysis/main-audit-first-failure-20261029.md) retains23files/537008bytes, eleven unlaunched fleets, unavailable audit score/full cost and the original refusal. Prospective source correction does not change that outcome.

## Provenance, licenses and release snapshots

The source archive SHA256 is `5b8659a11095743536ec8ed4d8ad1992eabc07712753dec434952ddf7e9bffc5`; the unchanged 28 October paper package SHA256 is `60e2ee9df8488ddb71d51314e6dbc029513eb7256d48854d6ca2ed68656f2765`. The byte-exact parameter pair SHA256 is `cccc2ffbaaf223ce1a284af1afd2405f58fca4cafeee4b12692678bd33f4b6ed`.

Original code/parameters are MIT-0; inherited code retains scoped Apache-2.0/MIT and other declared terms. Model licenses are separate. See [source notices](public-method-source-release-v1/NOTICE.txt), [complete dependency and license records](public-method-source-release-v1/notebook/release-notices/), and [current paper license](paper-draft-20261029/LICENSE-paper.txt). No blanket license overrides third-party material, and no organizer approval of model eligibility is asserted.

The archived READMEs and sanitized evidence record retain their prepublication assembly status, including historical `UNUPLOADED` wording and pending items at their stated cut. This repository publishes those exact snapshots; that wording does not attest to later execution or outcomes. No private notebook output, raw training rows, browser/account metadata, credentials, weights, wheels or full workspace history is published.

The corrected main cohort and [constant-control scope derivation](analysis/constant-probability-control-derivation-20261029.md) are included in the current manuscript. The control fits replace common forecast moments and compare derivative A1_q/P_q, rather than original A1. No fit, test suite, reader replay or new main job accompanied this publication.

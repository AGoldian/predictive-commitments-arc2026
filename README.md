# Testing Predictive Commitments in Interactive Reasoning

Alexander Serov — Independent Researcher

**Preliminary research draft revised 29 October 2026 (Moscow); first public release 28 October.** This release does not demonstrate an allocation benefit or report an official score for the proposed method. It is not a completed ARC Prize Paper Track submission.

- [Read the current short research draft](paper-draft-20261029/kaggle-writeup.txt).
- [Current standalone LaTeX manuscript](paper-draft-20261029/paper.tex), licensed CC BY 4.0, with AI disclosure and limitations. No separately exported PDF is included.
- [Current snapshot details and sanitized evidence](paper-draft-20261029/README.md); [unchanged 28 October snapshot](paper-draft-20261028/README.txt).
- [Complete selected method source and execution instructions](public-method-source-release-v1/README.md).
- [Exact Kaggle notebook](public-method-source-release-v1/notebook/official-public-entry.ipynb) and [readable parent/worker payload](public-method-source-release-v1/readable-entry/).
- [Frozen fitted parameter pair and scoped terms](public-method-source-release-v1/parameters/).
- [Frozen prospective study protocol, calibration methods, budgets and public-game split](study/README.md).
- [Disclosed reader JSON-format correction and original A1 refusal](analysis/reader-json-format-erratum.md).
- [Original source archive](archives/public-method-source-release-v1.tar.xz) and [28 October preliminary paper package](archives/paper-draft-20261028-v1.zip).

## Evidence and current scope

The current paper snapshot is dated 29 October (Moscow) and includes the completed P feasibility failure. Its [snapshot record](paper-draft-20261029/README.md) gives the actual UTC copy time. The unchanged earlier snapshot is dated 28 October, 18:30 UTC; it reports a genuine development fit on 16 complete windows (13 negative and 3 positive, all positives from one game/episode) and an evidence-eligible B0 development fleet. The four-game B0 score is unavailable because incomplete/crashed records remain in its original denominator. Its single completed game's score is not an aggregate result.

After that snapshot, B1 completed: 331/422 valid prediction packets, 412,843 accepted target-output tokens over 287 known requests, with no observed unknown/pending requests in the accepted target scope. The original four-game B1 score also remains unavailable. A1 subsequently completed. Its original reader8 refusal exposed a JSON-list/Python-tuple comparison defect despite exact model identity. One separately pinned reader9 adjudication of unchanged original evidence passed all 21 folds: 390,586 accepted target-output tokens over 330 known attempts, zero observed unknown/pending attempts, and 276/374 valid prediction packets. All four raw states remain crashed and its original-rule fleet score remains unavailable. P subsequently completed but its original reader9 refused the packet-coverage gate: complete counts show 89/417 valid packets (21.3429%), below 50%; the other 20 of 21 folds passed. The 328 missing packets record `prediction_not_supplied`, with invalid/unknown transitions zero. Accepted target-output cost is 404,393 tokens over 303 known requests, with zero observed unknown/pending requests; no P score or official result is reported. [The sanitized feasibility result](analysis/p-v6-feasibility-result.md) preserves the original refusal and exact evidence pins. [The public technical erratum and exact patch](analysis/reader-json-format-erratum.md) preserve both analysis decisions; there was no A1 GPU replay, refit, model/runtime/budget or endpoint change. These development observations do not establish comparative policy effectiveness. The five-game calibration, ten-game/three-request-seed/four-arm audit, separate full published-policy reproduction and corresponding official P result remain outstanding. Whole-kernel and draft-model work are unavailable, not zero.

The included notebook is source, not a claimed public Kaggle execution or scored entry. Its ordinary Save branch deliberately writes a labelled offline placeholder; only an actual competition rerun invokes the full method. Do not interpret the placeholder as a measured score. Follow its pinned attachments and resource requirements. No paid API or GPU resource is required by this project's resource policy; execution depends on available free Kaggle resources.

Kaggle confirmed that notebooks using this competition as a source cannot be made public until the competition ends, so the corresponding Kaggle execution notebook is private and not anonymously accessible. The full method code was already public before the official request; the [execution metadata overlay](execution-metadata-20261029/README.md) supplies the exact private metadata while preserving the published notebook and payload bytes. Official submission **57749129** was accepted on 28 October at 21:28:14 UTC and its result is pending at this snapshot; the completed Save verified source and produced a placeholder, and neither Save nor submission acceptance establishes a working or scored method result.

## Provenance, licenses and release snapshots

The source archive SHA256 is `5b8659a11095743536ec8ed4d8ad1992eabc07712753dec434952ddf7e9bffc5`; the unchanged 28 October paper package SHA256 is `60e2ee9df8488ddb71d51314e6dbc029513eb7256d48854d6ca2ed68656f2765`. The byte-exact parameter pair SHA256 is `cccc2ffbaaf223ce1a284af1afd2405f58fca4cafeee4b12692678bd33f4b6ed`.

Original code/parameters are MIT-0; inherited code retains scoped Apache-2.0/MIT and other declared terms. Model licenses are separate. See [source notices](public-method-source-release-v1/NOTICE.txt), [complete dependency and license records](public-method-source-release-v1/notebook/release-notices/), and [current paper license](paper-draft-20261029/LICENSE-paper.txt). No blanket license overrides third-party material, and no organizer approval of model eligibility is asserted.

The archived READMEs and sanitized evidence record retain their prepublication assembly status, including historical `UNUPLOADED` wording and pending items at their stated cut. This repository publishes those exact snapshots; that wording does not attest to later execution or outcomes. No private notebook output, raw training rows, browser/account metadata, credentials, weights, wheels or full workspace history is published.

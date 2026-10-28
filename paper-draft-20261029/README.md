# Preliminary paper snapshot — 29 October 2026 (Moscow)

Alexander Serov — Independent Researcher

Manuscript source commit: `84d851a98aad21eaf356a82f40442cedaffb0afe`, after the original calibration retrieval and single frozen readout. Public copy assembled at `2026-10-28T22:54:59.879502+00:00` UTC. [paper.tex](paper.tex) and [kaggle-writeup.txt](kaggle-writeup.txt) are exact workspace copies; the existing LaTeX compiled successfully in the desktop editor. The writeup has 1,499 whitespace-separated words. No separate PDF is included.

P's original development feasibility failure remains:89/417 valid packets (21.3429%) is below50%. The separate official P submission57749129 was observed COMPLETE/public0.00, with actual rerun traces, runtime and tokens unavailable. Full instrumented Bpub reproduction failed; both complete-run aggregates remain unavailable, and added accounting interrupted upstream retry handling.

Five-game calibration141409675/version1 ended ERROR. One strict readout retained all20 original slots as unverified and returned no eligible macro Brier/log-loss. A227-frame public response exceeded the collection observer's1MiB host-row bound. Later offline reader input/node-bound refusals are separate. Known target tokens are at least159,646; complete cost is unavailable. No refit, subset rescue, repeated experiment or measured mask tie was used. The main audit remains unlaunched.

[Sanitized snapshot evidence](evidence-summary.json) and [calibration note](../analysis/validation-calibration-failure-20261029.md) accompany the text. The [previous O32 snapshot](https://github.com/AGoldian/predictive-commitments-arc2026/tree/db8d4d21696f91996f258e51b2aaee7c08a18376/paper-draft-20261029) and [28 October release](../paper-draft-20261028/README.txt) remain available.

Reuse the [unchanged fitted parameters](../public-method-source-release-v1/parameters/), [conceptual cover](../paper-draft-20261028/cover.png) and [complete method source](../public-method-source-release-v1/README.md). The cover is an illustration. No private outputs, raw training rows, weights, binaries or account metadata are included. The Kaggle notebook remains private under the competition-source embargo.

Manuscript/writeup: [CC BY4.0](LICENSE-paper.txt). Code, upstream assets and models retain their separate terms. This is a preliminary research draft; no allocation benefit, contest-complete submission or organizer/model approval is claimed.

Exact source SHA256:

- paper.tex: `40104d85fae2e6c67624e3d3970488d026d96b457c2c0da1feedf75447f07a60`
- kaggle-writeup.txt: `0e6d3106fafaf02818b5bf14a739dcd340f21427cf0cad99cd70301a40172ae5`

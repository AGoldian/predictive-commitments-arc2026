# s101/B1 v2: retained runtime refusals, 29 October 2026

Read-only examination of the original report and source-owned lifecycle records for kernel **141464867/v1**. The API reported COMPLETE; the single completed core readout remains **ineligible, 19/21 folds passed**. No reader, coverage component, scorer, model, test, API or experiment was run for this note. No notebook, prompt/transcript, SDK environment/game implementation or generated child code was inspected.

**Native refusal has a concrete recorded cause: a 30-second child deadline, with successful subsequent physical cleanup.** In `artifacts/private/tier2-s101-b1-v2/capacity/host/child-invocations.jsonl`, lines 442–446 bind invocation **64** to `worker-4` (the original worker mapping identifies public game `r11l-495a7899`), lease 64 and PID 1633. The records show a 30-second sandbox, observed-live spawn and verified READY. Line **468** records `resource_failure={"stage":"deadline"}`, elapsed **30.033320401 s**, return code **-9**, `reaped=true`, `pipes_closed=true`, and both pre-cleanup EOF flags false; `error_type` and `cleanup_error_type` are null. Line 469 retains the terminal tool record. This is not evidence of an escaped/unreaped child or the earlier READY-identity race.

The selected reader's `child_witness_replay.py:156–162` requires no resource failure, return code zero and pre-cleanup EOFs; this exact record therefore triggers `child_return_or_cleanup_failure`. The selected sandbox source sets a per-invocation deadline at `python_tool_sandbox.py:1317–1318`, checks it at 1384–1387, records `BoundsFailure` at 1496–1499 and emits the final receipt at 1504–1535. `bounded_child_io.py:189–216` kills a still-running process and waits/closes pipes. The recorded `-9` is consistent with that cleanup path; the underlying reason the child did not finish within 30 seconds is **not established** by these infrastructure records. No generated code or transcript was examined to speculate about it.

The child finished at monotonic **1168.548481453 s**, well before the gameplay admission cutoff **2595.919701361 s**. The later governor record is separately explicit: `fleet-admission.jsonl:1771` reports `origin=admission_deadline`; lines 1825–1827 record physical closure, inner completion and `hard_stop_attempted=false`. Thus the earlier child deadline cannot be attributed to the planned end-of-budget stop. The outer `supervisor.json` reports worker return 0, reaped/cleanup/pipes closed, no remaining owned descendants or waitable children, no deadline/output-cap event and no errors. These later closure facts do not turn the failed child into a clean native invocation.

**Coverage's detailed cause and counts are not retained in the completed report.** Its `coverage` is null, with only `original_fleet_packet_coverage_refused`. `reader.py:789–795` checks the conjunction of `counts_complete` and, for B1, `packet_coverage_pass`; the dependency's `coverage.py:282–289` requires complete joins, nonzero denominator and V/D ≥ 0.5. `reader.py:490–495` saves context only after a component returns successfully, so the failed result is discarded before report construction at 810. The existing `readout-summary-v1.json` explicitly records D, V and rate as null. Consequently this evidence does **not** distinguish incomplete coverage counts from a genuine below-threshold rate (or zero denominator), and supplies no supported per-game counts. They remain unknown; no recomputation or new adjudication was performed.

The original report's complete target-cost component is retained: **441232** accepted target tokens (**429116** gameplay, **12116** late drain), **287** known attempts and zero recorded unknown/pending attempts. This component is not whole-kernel GPU/draft cost, an efficacy score, or whole-run eligibility. The original refusal and stopped controller remain unchanged.

Exact evidence/source SHA256 pins:

| Artifact | SHA256 |
|---|---|
| `artifacts/kaggle/tier2-s101-b1-v2/reader-inspection-v1.json` | `ee0f68e86189e13c454413e8f32cf030d77db6ac9290e1aadba52ce642d15ee2` |
| `artifacts/kaggle/tier2-s101-b1-v2/execution-record.json` | `50ab0e8ef3f65436e22c7c6825e9bd63889a9c1e98cd25d85002b996cd84750b` |
| `artifacts/kaggle/tier2-s101-b1-v2/readout-summary-v1.json` | `262e5d3921f3df075378fa810680b69c1be5f80b4719ad95de2a25b9e58bab90` |
| Private child journal (relative name above) | `96ece8383f2aa1d3e68d53862759b0a1ef448a702574c3d21e9190cc4e04c0c5` |
| Private admission journal (relative name above) | `2525b362f59073b7a8a5ece421db0e792b9304e388d47e292ab9b5169e9b3c21` |
| Private `capacity/worker-result.json` | `09a211a76f3a075ba9f8cfed9639585ef8ae5766cfae5a64af8f6b8494f0156b` |
| Private `capacity-supervisor/supervisor.json` | `6aa8efb3cccaa86de099ae6acae9f4f870d82db4844d2d633d48b2e49616180e` |
| Selected `reader.py` | `1a52cd98a1b5347832e63c8a8aa61d3e71f206063391677d99dbbb4815daaf5e` |
| Selected `child_witness_replay.py` | `6e2e3126874775b60930d9e0c8d9801aa08655078fc9767675f7fca0b279f7c7` |
| Selected `dependencies/coverage/coverage.py` | `e3068dbf8b01182db548d2481db19fc2812bbea8b8b48c56d65262c1c8e7e359` |
| Selected sandbox final source | `f75152a03fee9192492e7c9068567f2ac86af9b39169c065112400913936d3ec` |
| Selected `bounded_child_io.py` | `22dcf677a5eab3aca6a902919fa7bca2988d1cd4d4be2507c61213d6516419aa` |

Selected source root: `artifacts/reviews/tier2-audit-roster-methods-correction-v1-source/corrected/s101/reader/`; sandbox path below it is `dependencies/worker/runtime/final-source/ARC3-Inference/inference/agent/python_tool_sandbox.py`, and bounds path is `dependencies/worker/runtime/host-package/arc_paper/bounded_child_io.py`. No raw private records are copied into this note. This is a factual diagnosis, not another independent source acceptance or a proposed gate change.

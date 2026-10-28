# P development feasibility result — 28 October 2026 (UTC)

The original P run completed, but its once-only reader9 analysis refused the
prespecified prediction-packet feasibility gate. The other 20 of 21 evidence
folds passed. Overall scientific eligibility and complete-run acceptance remain
false; this is not an efficacy result or an official competition score.

One diagnostic invocation of the unchanged pure coverage component recovered
complete counts for all four original owners: **89 valid packets / 417 eligible
executed actions = 21.3429%**, below the unchanged 50% threshold.

| Exposed development game | Valid packets | Eligible actions | Coverage |
|---|---:|---:|---:|
| g50t-5849a774 | 0 | 22 | 0% |
| dc22-fdcac232 | 0 | 164 | 0% |
| ft09-0d8bbf25 | 89 | 90 | 98.8889% |
| ls20-9607627b | 0 | 141 | 0% |
| Total | 89 | 417 | 21.3429% |

The 328 missing packets all record `prediction_not_supplied`; invalid packets
and unknown transitions are both zero. Eligible actions were nonautomatic.
One RESET and three refused transitions were excluded by the existing rule.
The adapter records this reason for a missing/null prediction value. These
records do not distinguish an absent field from explicit null or establish why
the model omitted it. The failure is packet availability, rather than missing
labels, malformed probabilities or incomplete journal reconstruction.

Complete physical accepted target-output accounting retains **404,393 tokens**:
398,009 during gameplay and 6,384 late, over 303 known requests with zero
observed unknown or pending requests. These are component-level observations;
whole-kernel and draft-model expenditure remain unavailable, not zero. Matched
limits do not establish equal consumption.

The original refusal is preserved. The diagnostic is not a second full-reader
adjudication. No score was computed, no threshold was relaxed, and no subset,
refit or GPU replay was used. This note reports neither a policy benefit nor an
official P result. The exposed four-game development fleet is not a clean hidden
test set.

Evidence pins (SHA256; raw journals and account metadata are not distributed):

- Original reader refusal: `c6bdc1c957e21eb97da452afd6aae2ba4a26d33939ba8c4ec4d0dc693fec98b1`.
- Original execution record: `9a0afd05fc85fe63047c9b7a159e527b2df8540a52e0f4d7f8d7a6eb9efe5566`.
- Sole coverage component result: `3ae27f503c56612f348a894a74a88c8340d40ca974cc2b62eb7c6a5ef18a7597`.
- Closed diagnostic packet: `ddfa6198c2a2c829981dab45e5206de4a84886bcce098df7a49d832e1625d024`.
- Reader9 source: `87e786cbcde81fcaf413840955b049b6d145be90c7c3b4f43f48ddcf9d47569f`.

[Sanitized machine-readable summary](p-v6-feasibility-result.json). This prose is
licensed CC BY 4.0; the original result and its limitations are unchanged.

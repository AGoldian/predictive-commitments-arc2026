# Reader JSON-format erratum — 28 October 2026

The A1 development run completed at 19:59 UTC. Its first analysis with reader8
refused the allocator-model equality check: the expected in-memory model payload
contained Python tuples, while the durable JSON record contained lists. The
recorded `allocation.models`, in canonical JSON, exactly matches the unchanged
genuine parameter pair, SHA256
`cccc2ffbaaf223ce1a284af1afd2405f58fca4cafeee4b12692678bd33f4b6ed`.
The original refusal is retained, report SHA256
`c4a406c784fb53b38558f664e6130d77b9fa2a220d5b0e6933f645008314cb7e`.

Reader9 changes one operative line: it normalizes the expected payload through
JSON serialization and parsing before applying the same equality check. It does
not remove the identity check. One separate adjudication of the unchanged,
complete original evidence passed all 21 analysis folds, including checks that
the first refusal had not reached. The corrected report SHA256 is
`74b34887cc7ef310a6c20e0d73451118ec51f7db1d39858519cd4c09d07ecf50`.
There was no GPU replay, refit, model/runtime change, budget change or endpoint
change. This is a disclosed analysis-format correction, not a second experiment.

The retained A1 accounting contains 390586 accepted target-output tokens:
388225 during gameplay and 2361 late. It reports 330 known usage attempts,
zero unknown attempts and zero pending attempts. Valid prediction packets were
276 of 374 eligible actions. All four raw framework states were `crashed`, and
the original-rule fleet aggregate remains unavailable (`null`). Passing the
complete-evidence checks does not establish a successful allocator or an efficacy
improvement. Whole-kernel and draft-model expenditure remain unavailable.

These are development observations, not an official competition score. P was
accepted once at 20:10:56 UTC and was running at this update. The main audit,
calibration, full published-policy reproduction and official P result remain
pending. The same format correction was copied prospectively into the audit
analysis sources before any main-study outcomes; this does not rewrite the
original development refusal.

Reader9 source SHA256:
`87e786cbcde81fcaf413840955b049b6d145be90c7c3b4f43f48ddcf9d47569f`.
Its closed source-set SHA256:
`50354a6eabd7eee29893dda089f76b6b01e09f5b2554080519228cfcd74adb19`.
The accompanying [exact patch](reader-json-format.patch), SHA256
`6489c2e9ccc447f78081f7ba4a2e9db248384b09eab859e1fbb8033085313ce1`, is an MIT-0 analysis-code fragment. It is not a complete runnable
method; the selected notebook and readable method source are distributed
separately in [the method source release](../public-method-source-release-v1/README.md).
This prose is licensed CC BY 4.0. No private notebook references, account metadata
or raw training rows are included.

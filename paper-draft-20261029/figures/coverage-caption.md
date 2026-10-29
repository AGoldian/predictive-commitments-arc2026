# DEV prediction-packet coverage

Valid prospective prediction packets V divided by all eligible executed actions D in four exposed public DEV games (seed 101): B1 331/422 (78.4%), A1 276/374 (73.8%), and P 89/417 (21.3%). The dashed line marks the frozen per-arm feasibility gate, V/D >= 50%. B0 is excluded by design. These are packet-availability ratios, not prediction accuracy, a DEV score or efficacy. Actions are not IID; no confidence intervals, significance or causal advantage are asserted. A1 uses the documented JSON-format adjudication; P counts come from the sole pure coverage diagnostic and do not clear the original refusal.

Source aggregates (no reader replay or new scoring):

- `B1`: `artifacts/kaggle/tier1-v6-b1/reader-inspection-v1.json`
  SHA256 `aaaae60fa03635c4982d52a2adf96db0d04668b118e619cd3c536326f5e49122`
- `A1`: `artifacts/kaggle/tier1-v6-a1/reader-inspection-v2-json-format.json`
  SHA256 `74b34887cc7ef310a6c20e0d73451118ec51f7db1d39858519cd4c09d07ecf50`
- `P`: `artifacts/kaggle/tier1-v6-p/coverage-diagnostic-v1/coverage-component-output.json`
  SHA256 `3ae27f503c56612f348a894a74a88c8340d40ca974cc2b62eb7c6a5ef18a7597`

The complete source pins, frozen gate, scope and qualifications are in `coverage-data.json`. Rebuild with `coverage-build.py`.

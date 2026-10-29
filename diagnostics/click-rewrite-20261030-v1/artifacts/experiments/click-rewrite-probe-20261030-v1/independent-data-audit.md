# Independent first-round data-only audit

**Both frozen mechanistic criteria hold for this one exposed DEV probe.** `affine-d4-5` and `toggle` each made the same48 known cell claims, all correct and all actually changed. The idempotent candidate was contradicted on24 precommitted common cells. The two surviving mechanism names are observationally equivalent on this probe; this does not identify a unique mechanism or demonstrate goal-directed performance.

This audit independently parsed only the frozen protocol/config, retained input/provenance, fitted parameters, committed forecasts, returned public observations, slots and transport/resource receipts. It checked source bytes by SHA256 and read the runner's ordering; it did not execute/import the fitter, predictor, native motion code, SDK or models, inspect environment implementation, read root's subsequent analysis, or run tests/new experiments. Calculations below are direct JSON/cell comparisons using the standard library.

## Frozen identity and custody

The six current source-member hashes all match `precall-source.json`; recomputing its canonical member-map SHA256 gives closure `3b72230848f104da7345a738366925da5ccb2de588bedc7a64fa8d484b91e1c8`. Request and commitment bind exactly that identity. In particular, runner SHA256 is `36632fa5a49345734e7577f5990724d52ee9a60fdb36a9bed576090abeffa89d`, and `click_rewrite.py` is `98d20dc1a457e368da993474f87faaaa7c27c78d7aa0a381b6e8afc68dc2aa98`.

Verified byte hashes and joins:

| Artifact | SHA256 |
| --- | --- |
| frozen protocol | `c70dc2c429deaef968094ee0e907db6ffda2eb5e25078304b17f8cc2f055f99b` |
| frozen config | `daae3de58eee00f27e2e0ccdd1d4d94c6bc5a30aac6689713a001e6fab1c59cc` |
| six-record input prefix | `21c9e8190026427da1a7af9ae899379b80053915c2dfdcd90e97e517fa6f49fc` |
| fitted parameters | `d890bdb7ff20f701cc87b4dca14f6be5209830f5c4a57b99ad796bd0e61bfdb7` |
| commitment | `334df6b95d9ef34b39fc176199a8cd739808cd863459bc9fd42c499968ff5dd9` |
| comparison input | `7f92c54debe4936f43aad1c10f5a69b2d124ee09a85fc5c272ac59a83b643db1` |
| slots | `e1f14a61c2c9a0afe687103eb046cfb091424bd102e3b34cab9704cf76caa120` |
| worker receipt | `16ed06da3f8b8151bca801333b9df75704e73549faad6e8f9e39b629facba07a` |
| parent receipt | `49a8866b17661881f5e0857bcfe335ac4bfd86f9ef7e7f5062a5340f91a45995` |

The prefix's six original observation hashes and original24-slot ledger hash match its provenance receipt. All seven new observation hashes match their slots. Each of the six reconstructed public projections—state, level count, ordered advertised IDs and lossless last grid—equals its frozen input record, and all six actions match the original prefix. Comparison `before`/`after` exactly equal observations06/07, and its commitment hash equals the slot7 commitment hash. The retained runtime receipt matches the pinned inventory hash `5e6ad5e336002d0e4c1b116b3137c337b4dbf4c56fc0ee1007fca961ff8bccbe`, selected exact-game cache-file map and complete package maps (`arc-agi`0.9.9, `arcengine`0.9.3). This verifies receipt/inventory consistency, not a new SDK or cache execution audit.

Runner source saves fitted data, every forecast and witnesses before runtime verification and SDK setup. Retained file modification order agrees: commitment precedes runtime verification and observation01. These local artifacts support the prescribed ordering; hashes and modification times are not an independent trusted timestamp service.

## Selection and raw outcomes

The fitted relation is record index3→4 (slots4→5), click `(x48,y19)`. Three earlier transitions were retained as rejected for no qualifying equal-area remote change. The source pair grids/action exactly match those two input records. `training_scope` explicitly says one paired transition; later frames were not examined by the fitter. Do not describe this as a complete learned replay of all five transitions. Record6 supplies the actual final grid for forecasting. The fit openly records `source_prior_not_blind=true`.

All six fitted candidates appear once in the commitment: four affine parameterizations, idempotent and toggle. The selected probe `(x46,y18)` is the first row/column ordered four-neighbor interior control pixel not clicked in the prefix, independently checked against its47-cell mask and prior clicks. Action6 was currently advertised. No alternative point search is indicated.

The returned64×64 frame differs at49 cells:24 `8→4`,24 `4→8`, and one `0→3` at `(row63,col4)`. State remains `NOT_FINISHED`, levels remain0, and advertised IDs remain `[1,2,3,4,6]`.

| Candidate | Status | Known | Correct | Wrong | Predicted changed | Correctly predicted actual changed | Actual changed omitted |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| affine-d4-2 | unsupported | 0 | 0 | 0 | 0 | 0 | 49 |
| affine-d4-3 | supported | 48 | 24 | 24 | 48 | 24 | 25 |
| affine-d4-4 | supported | 48 | 24 | 24 | 48 | 24 | 25 |
| affine-d4-5 | supported | 48 | 48 | 0 | 48 | 48 | 1 |
| idempotent | supported | 24 | 0 | 24 | 0 | 0 | 25 |
| toggle | supported | 48 | 48 | 0 | 48 | 48 | 1 |

“Predicted changed” means a known predicted value differs from the pre-probe value. Correctly predicted actual changed cells must also match the returned value. There are no duplicate cell claims. For affine3/4, the24 wrong claims are spurious predicted destination changes on actually unchanged cells; their24 source-vacancy changes are correct, while the actual24 destination changes are outside their coverage. Idempotent makes24 incorrect stationary claims on actually changed cells. Affine2 refuses its entire forecast for24 third-color destination occupancies: its zero known leaves receive no consistency/accuracy credit, not a successful no-op.

The winner forecasts cover48/49 actual changed cells and leave4048/4096 grid cells UNKNOWN; the omitted changed cell is the `0→3` cell above. Idempotent leaves4072 cells UNKNOWN, and affine2 all4096. No candidate claims state, levels, advertised actions or goal; their unchanged metadata receives no prediction credit.

## Discrimination and frozen criteria

Six raw candidates yield **four distinct nonempty forecast classes**, plus one empty/unsupported class. Affine5 and toggle have byte-equivalent canonical cell forecasts and cannot be distinguished here. Affine3 and affine4 are separate incorrect destination classes; idempotent is a separate stationary class. Equal candidate counts are not calibrated probabilities.

All four saved incompatible pairs are correct and complete on their shared known cells: affine3/idempotent, affine4/idempotent, affine5/idempotent, and idempotent/toggle. Every pair has the same24 witness locations, rows24..29/columns18..21. Each supported moving candidate predicts4 there; idempotent predicts8; the return is4 on all24. The empty candidate has no witnesses and cannot create a partition. The moving classes agree on their overlaps: the common-cell witnesses alone do not distinguish their destinations. Full assessment of their precommitted exclusive claims refutes affine3/4. The result must not be presented as a unique mechanistic identification.

1. **Model-discrimination criterion: PASS.** Supported affine5/toggle each have all known claims correct, and supported idempotent is contradicted on precommitted common-cell witnesses shared with those survivors.
2. **Dynamic nonvacuity criterion: PASS.** Each survivor correctly predicts48 actually changed cells, exceeding the frozen requirement of at least one. This is not static-only consistency.

Both criteria therefore hold exactly as frozen. There is no all-models-wrong outcome, but three supported candidates fail and one candidate remains unsupported; all are retained.

## Failures, exposure and costs

All seven planned slots are observed: one factory RESET, five replayed setup clicks, one new probe. Worker reports six matched prefix slots, one fit, six native forecasts, zero LLM calls, no failure/cleanup-failure, and stop reason `one_novel_probe_returned`. Parent reports returncode0, no timeout and a present worker receipt; scientific success follows the cell checks above, not returncode0 alone.

Reported parent wall time is0.376045709s; worker wall0.248690750s, process CPU0.247870s, peak RSS113,164,288bytes. Timed one-fit wall is0.001494583s and six-forecast wall totals0.001396501s. Factory RESET costs0.016651500s, five replay steps total0.000981040s, and the new probe0.000164333s. The17 timed stages total0.024469748s; this is only a subset of whole-process wall/CPU, not a substitute for the full receipts. No inference, paid resource or extra action is hidden by reporting only the novel click. Prior acquisition/exposure also remains: this six-record prefix came from the already observed24-action D2 component episode in the96-action spatial study. The present7-action reconstruction is additional cost, not six free initial conditions.

This is one prospective return after selecting an already responsive public trace and declaring a hand-written conservative rewrite family. It establishes neither new-game transfer, goal utility, general causal identification, competitive efficacy nor novelty. An unobserved state variable, a repeat-cycle rule, or another unrepresented coordinate-conditioned process can agree with both surviving forecasts. One additional interior point provides limited support for spatial trigger invariance, not a general hit-region law. Visible checkpoint agreement does not reconstruct hidden state. No control intervention, second control, D1 nonconservation, new level, or goal event was tested here; goal truth/utility remains UNKNOWN. The stopped spatial2/2 and motion-transfer failures remain unchanged.

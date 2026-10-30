# CPU Kubyer B entry: exact submitted source

This directory preserves the closed `export-v3` used for Kaggle kernel
`141591475`, version1, and accepted competition submission `57787999`. It is an
attributed baseline integration, with no novelty or competitive-performance
claim. The submitted Kaggle notebook remains private; publishing this source
kit does not publish its notebook outputs, competition observations or journals.
Keep those materials private and respect any applicable competition embargo.

The solver is unchanged [Kubyer/arc-agi-3-solver](https://github.com/Kubyer/arc-agi-3-solver/tree/dade1e0efb7bc951b54297b4e4447b0d89fec6be),
revision `dade1e0efb7bc951b54297b4e4447b0d89fec6be`, under **CC BY4.0**.
Its16 retained files include agent B and its transitive A/world_model.py solver
dependency; original URLs, byte hashes, license and author documentation are in
`package/upstream-manifest.json` and `package/upstream/`. Upstream reported
scores remain external claims. Our runtime/bootstrap/configuration are MIT-0;
both licenses and the attribution notice are included. The notebook and archive
contain both license scopes. No official starter implementation is copied.

This entry enables B's native goals and MDL world model, sets `SUCCESS_OFF=1`
and requires the toy success prior to be absent: the success model starts at
zero prior. It is not the full upstream learned-success variant. No LLM calls,
model weights, training data, environment implementations or answers are
included. Neither the separate forecast gate nor the joint-goal experiment is
exported. Native CPU fitting/prediction remains active and its call count is
uninstrumented. The agent receives only public state, completed levels,
advertised actions and frames through a proxy.

## Exact artifact identity

`build-manifest.json` records the other26 exported members.
`package/package-manifest.json` lists22 payload members; its own pinned bytes
complete the23-file package. The complete export has27 files, including both
manifests. The publication allowlist additionally supplies this MIT-0 README.

| Artifact | SHA256 |
|---|---|
| `cpu-official.ipynb` | `813916a62506105c6fa4ffb0c4ec395fa9df61b9670ab79936c584e5854579b5` |
| `kernel-metadata.json` | `ee25b4ea9a26428f51d468346e5aa918c4a628a18ba3a3466ea54652aa1290d5` |
| `package.tar.xz` | `7b2b31000b6eea5216905482de34ebc82f6c48df6952bffe666d25fcd5079a76` |
| `package/package-manifest.json` | `13ca1d92e5022780b1eb51f4d330249e5e5941ac0741a4f8963f1566f57b65c2` |
| `build-manifest.json` | `38f86fc72d33773f868a96ba45bc07211edbf27a60ccc6a6f559f733f07482e7` |

The build's26-member canonical map closure is
`8acd93bda21026154b7887d79b4cd06cc074d9c92c4d37d14c4655f93922be8d`;
the outer build manifest is the27th file. Source assembly/import-free validation
is not runtime or gameplay validation.

## What has actually been observed

The ordinary private Save was COMPLETE. Its retained first-code/source-check
receipts report flag false, source verification,3.402837719seconds from first
code, and no SDK/solver import or gameplay. Base metadata reports Python3.13.15,
NumPy2.1.3, SciPy1.16.3, pandas2.3.3 and PyArrow23.0.1; arc-agi and arcengine were
not installed before the true branch. This proves only the false-branch source
check, placeholder creation and those metadata observations.

The retained exact-ref API observation at **2026-10-30 01:52:07.227865UTC** reports
submission57787999 **COMPLETE**, public score **0.00**. The original observer
finished at01:52:07.228618UTC and was reaped with exit0; no retry or requery was
performed for this reconciliation. These are observation/monitor timestamps,
not exact server completion or gameplay runtime. The score comes from the
submission API, not the false-Save placeholder. Actual rerun logs and server
version echo are unavailable: true flag, SDK dependency/ABI compatibility,
actual gameplay and gateway parquet readiness remain unobserved here. Terminal
COMPLETE does not establish a working pipeline, method execution or a cause
for zero score.
The supplied SDK wheels are universal, but other bundled binary dependencies
include cp312 wheels while the observed base is Python3.13. The runtime installs
only the two SDK wheels with `--no-deps`; success therefore depends on compatible
preinstalled dependencies, which the false branch did not establish.

## Explicit Kaggle execution

Create your own **new private CPU notebook with a distinct owner/slug** and
attach the official `arc-prize-2026-arc-agi-3` competition input. Upload
`cpu-official.ipynb`, keep GPU and Internet disabled, and review the exact source
and rules before choosing any Save or competition Submit. The bundled
`kernel-metadata.json` identifies the historical submitted notebook: do not push
it unchanged into the author's namespace. Editing metadata creates a distinct
reproduction artifact, not the exact submitted version.

An ordinary Save takes the source-check branch and writes an explicitly
unmeasured validator placeholder. An actual platform rerun uses the official
`bool(os.getenv('KAGGLE_IS_COMPETITION_RERUN'))` contract. It installs the pinned
arc-agi0.9.8 and arcengine0.9.3 wheels offline, checks active installed
requirements, opens one COMPETITION `Arcade` and shared scorecard, obtains the
actual gateway roster, and calls `make`/public `step` through that proxy. The
first factory return is reused. Every factory/later RESET, replay and policy
dispatch counts toward512 per game; one pass, seed606. Requested whole wall is
1800seconds from first code, with30seconds reserved for cleanup; per-game120s
is a soft signal bound. The gateway owns true `submission.parquet`; no manual
score rows are synthesized in that branch.

The [official starter interface](https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter/tree/eeb1535404f321d280a8f9194bbc1d7aca5f05fc)
is pinned at `eeb1535404f321d280a8f9194bbc1d7aca5f05fc`; see
`package/interface-provenance.json` for source hash and flag/output lines.
Its repository metadata advertised no license, so only interface semantics were
referenced. `test-key-123` is the explicit public gateway fixture, **not a user
credential**. No credentials, local home paths, operation/monitor scripts,
private downloads, `.venv`, weights or automatic Save/Submit/publication actions
are part of this kit. Notebook SDK actions occur only when explicitly executed.

# Full Bpub reproduction — prospective timeout compatibility correction

This source version preserves the full **25-game × four-pass, 100-planned-episode,
legacy C10** published-policy reproduction, with the same models, public roster,
SDK 0.9.8, release 720, analyzer 900 and first-code whole-job 32400/work 32370/cleanup 30
seconds. It is distinct from the learned P method. **The new result is unknown
at this source-release cut.** This source release does not establish successful
execution or a reproduced score.

The earlier [O37 reproduction failure](../../analysis/bpub-owned-preconnect-result-20261029.md)
and its original strict-reader refusal remain unchanged. This is a prospective
correction to our instrumentation: a trusted parent execution-window timeout
can return the upstream ordinary tool error only after source-bound setup and
ownership checks, durable receipts for all dispatched public SDK actions, no
pending or unknown actions/model usage, and actual child reaping and pipe
closure. The real deadline failure and return code remain recorded. Other
resource, source, ownership, accounting and cleanup failures remain fatal.

The original execution window is at most 30 seconds **after successful initial
input transmission**, with a separate finite 30-second setup/send envelope;
both remain bounded by the unchanged absolute whole-job work deadline. Built-in
`_socket` observations are represented by their actual built-in module/spec/
loader facts; they receive no invented file hash. File-backed dependencies
retain their observed paths and hashes. These are source corrections, not
claims of an independently certified runtime or successful baseline outcome.

The self-contained [bpub-public-reproduction.ipynb](bpub-public-reproduction.ipynb)
is copied exactly from the separately closed source packet, without rebuilding
it at publication time: SHA256
`f42dd4ff2b0c81b4eb2a90f03845a75aaf9a35e01ae97110844124882ca51e9e`,
957732 file bytes (957617 bytes in the SDK's normalized upload representation).
The actual source generator was
`c2345f7a51495b8abb2f1e951ba95626cbd99543940cb102d28d29776466cac7`;
its one source-only notebook build completed on 29 October 2026 at
13:15:33.934823 UTC. The embedded runtime closure is
`c2657f25acbd4a3e650b9b4e49e1220434c7364b5e1a696ed3d272aaec909479`
and its manifest SHA256 is
`9dea3470e29f442a05261aedc715a8325931aa6acbb5f2c2be6d346a41b8a2ef`.
These identities describe generated source, not an executed model or result.
Model weights, private outputs and account metadata are not redistributed.
Execution requires the pinned external model/dataset assets and compatible
Kaggle resources.

The ten files in [release-notices/](release-notices/) are exact copies of the
[previously published baseline notices](../bpub-owned-preconnect-20261029/release-notices/)
and the [P source component/license map](../../public-method-source-release-v1/notebook/release-notices/).
Use their [model/dataset and dependency references](release-notices/DEPENDENCY-REFERENCES.json),
[component attribution](release-notices/NOTICE.txt), [Qwen terms reference](release-notices/licenses/QWEN-COMMUNITY-1.0-reference.txt),
and [original-publisher Duck MIT declaration](release-notices/duck/DUCK-COMPONENT-NOTICE.txt).
The latter covers the five selected Duck package files and retains the original
pinned pyproject declaration. Our new code is MIT-0; inherited code and weights
retain their own terms. No model, dataset, upstream or vendor license selection
changed in this correction.

The 117-file transport vendor source has the same six readable license/notice
counterparts as the prior baseline, copied byte-exactly:

| Distribution | Readable copies |
|---|---|
| Requests 2.34.2 | [LICENSE](vendor-licenses/requests-2.34.2/LICENSE), [NOTICE](vendor-licenses/requests-2.34.2/NOTICE) |
| urllib3 2.8.0 | [LICENSE.txt](vendor-licenses/urllib3-2.8.0/LICENSE.txt) |
| charset_normalizer 3.5.1 | [LICENSE](vendor-licenses/charset_normalizer-3.5.1/LICENSE) |
| idna 3.20 | [LICENSE.md](vendor-licenses/idna-3.20/LICENSE.md) |
| certifi 2026.7.22 | [LICENSE](vendor-licenses/certifi-2026.7.22/LICENSE) |

Their original origins are the corresponding versioned `*.dist-info/licenses/`
paths in the embedded `runtime/vendor/worker-transport/` tree. Historical
`pending`/`UNUPLOADED` wording and hashes in the inherited notices remain a
dated source snapshot, not current execution or eligibility attestations.
No organizer approval or blanket legal certification is asserted. Kaggle's
notebook-visibility restriction is separate from this GitHub source release.

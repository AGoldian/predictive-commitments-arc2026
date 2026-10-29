# Corrected full Bpub reproduction — source release

This preserves the full **25-game × four-pass, 100-planned-episode, legacy C10** published-policy reproduction source. The corrected run has been accepted; **no outcome or reproduced score is included at this source-release cut**. This baseline is distinct from the learned P method and its official result, and from the earlier instrumented Bpub failure (O32). That failure remains recorded; the unmodified upstream retry-policy outcome was not established by it.

[`bpub-public-reproduction.ipynb`](bpub-public-reproduction.ipynb) is the exact existing self-contained source notebook, SHA256 `2b94d6235ddafef9483e6a69f59549483f0e26720bcb7e02563fc92d16b9439d`. Its embedded source payload, transport dependencies and original policy settings are preserved. Model weights and runtime outputs are not included; execution still requires the pinned external assets and compatible free Kaggle resources. This source release does not establish successful execution or a reproduced score.

The ten files in [`release-notices/`](release-notices/) are byte-identical to the [already published component/license map](../../public-method-source-release-v1/notebook/release-notices/). Refer to their [dependency and model/dataset references](release-notices/DEPENDENCY-REFERENCES.json), [component attribution](release-notices/NOTICE.txt), [Qwen terms reference](release-notices/licenses/QWEN-COMMUNITY-1.0-reference.txt), and [original-publisher Duck MIT declaration](release-notices/duck/DUCK-COMPONENT-NOTICE.txt). The latter explicitly covers the five selected Duck package files; the retained pinned pyproject supplies its original declaration. Original MIT-0 contributions do not relicense inherited components or weights.

These are retained source-snapshot notices. Historical `pending`/`UNUPLOADED` wording and the notice manifest are unchanged, not new execution or eligibility attestations. The added 117-file transport vendor tree has its own terms. Six readable copies below are byte-identical to the existing saved package's `runtime/vendor/worker-transport/` files, which also remain embedded in the notebook:

| Distribution | Readable copies | Original path below `worker-transport/` |
|---|---|---|
| Requests 2.34.2 | [LICENSE](vendor-licenses/requests-2.34.2/LICENSE), [NOTICE](vendor-licenses/requests-2.34.2/NOTICE) | `requests-2.34.2.dist-info/licenses/{LICENSE,NOTICE}` |
| urllib3 2.8.0 | [LICENSE.txt](vendor-licenses/urllib3-2.8.0/LICENSE.txt) | `urllib3-2.8.0.dist-info/licenses/LICENSE.txt` |
| charset_normalizer 3.5.1 | [LICENSE](vendor-licenses/charset_normalizer-3.5.1/LICENSE) | `charset_normalizer-3.5.1.dist-info/licenses/LICENSE` |
| idna 3.20 | [LICENSE.md](vendor-licenses/idna-3.20/LICENSE.md) | `idna-3.20.dist-info/licenses/LICENSE.md` |
| certifi 2026.7.22 | [LICENSE](vendor-licenses/certifi-2026.7.22/LICENSE) | `certifi-2026.7.22.dist-info/licenses/LICENSE` |

The older component notices are not a blanket license for that vendor tree. No organizer approval or blanket legal certification is asserted. The competition's Kaggle notebook-visibility restriction is separate from this existing GitHub method-source release.

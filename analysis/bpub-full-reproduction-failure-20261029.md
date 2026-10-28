# Full Bpub reproduction attempt — 29 October 2026 (Moscow)

The original instrumented full reproduction retained the published 25 public
games, four passes, 100 planned owners and legacy C10 scheduling. Its observer
recorded API **ERROR** at **2026-10-28T22:10:23.061729 UTC**. Complete original
retrieval finished at **22:12:53.254375 UTC**: 531 API-listed outputs and 532 final
inventory entries including the retained log, **6,907,564 bytes**.

The first completed strict readout was **ineligible**. Both complete-run
aggregates—the published-policy mean and SDK0.9.8 best-of-four per-game mean—are
**null**, as is the reproduced upstream score. All 100 planned episodes remain
in the denominator; no subset or zero score substitutes for the missing result.
The scan retained 100 host journals and four unknown-usage attempts, with zero
observed pending attempts. Complete accepted target tokens, draft work and
whole-kernel GPU expenditure are unavailable. The known-token lower bound of
zero is **not** a measurement of zero cost.

The retained log records the legacy 720-second benchmark release while the
model was still loading. Four generic `TransportError` attempts preceded
fail-closed accounting and `session_binding_failed` propagation. The underlying
OS exception was not preserved, so connection refusal is not proven. Crucially,
the added accounting wrapper raised before upstream retry handling and before
recording the original exception. **This attempt does not establish the outcome
of the unmodified upstream retry policy.** It is an instrumented reproduction
failure, distinct from official P's 0.00 and P's DEV packet-coverage failure.

This note accompanies manuscript source cut `38df78bfd2b6abc9369fdf372838e56179038ced`, committed before any
actual calibration request. Main audit and five-game calibration were unlaunched
at that cut. The public copy was assembled at `2026-10-28T22:23:50.636333+00:00`; that later
copy time is not a claim about subsequent operational status. Earlier source,
parameters, solver code, original outputs and failure decisions are unchanged.

[Sanitized summary](bpub-full-reproduction-failure-20261029.json) includes only
aggregate observations and evidence pins. Strict-report SHA256:
`0562b97f559c26db3c10a9ce83f5bab552e3bd02fb293de974504750deb9ef05`;
original-evidence cause-note SHA256:
`2620b36f100f30b3b31e9066e3ed800109bf8fc0f2a4e5d1d97b9ed4af2fc31a`.
No raw private file, account metadata or full claims registry is published here.
This prose is CC BY 4.0.

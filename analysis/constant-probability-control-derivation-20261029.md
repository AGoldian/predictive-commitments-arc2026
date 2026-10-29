# Constant-probability controls: exact basis and optimizer effects

Mathematical scope clarification,29October2026. No rows were read, no code from the selected fitter was imported or executed, and no fit, test or new measurement was performed. Only the existing aggregate control report was read for its field names and retained evidence pins. The statements below concern the raw fitted classifier control, not the deployed allocator or its missing-residual fallback.

## Selected implementation and convention

The selected reader closure is `b96fefa05b2eba74d761bd79aeb150a7215b9e165570db48cce2c7332b31b3c3` in `external/collection-real-reader-candidate-v5/candidate-checksums.json`. Relevant exact files, relative to that root:

| File | SHA256 | Relevant lines |
|---|---|---|
| `reused/dependencies/arc_paper/allocation.py` | `661f17f8b5636f63af8dcf4fc3bbbfc9aaf37bd4241c2f649d7640d8dc407bd7` |20–31 common/residual names;64–75 shared availability;173–185 optimizer defaults/vector;195–220 fit;237–242 label support/paired fit |
| `reused/dependencies/arc_paper/allocation_diagnostics.py` | `4ff970a5c75b7ef3a91314fb7e12893b40d996b35155960f4ed4bf92acd568fb` |23–24 constants/tolerance;36–50 transformation;54–67 scope;78–108 same fitter/training differences |
| `reused/dependencies/arc_paper/evidence_history.py` | `b22c63db8226790ebc9aef7ca56e08fbf9940d600231c97b186d1484a98d4aae` |125–135 event-specific matched pairs and moments |
| `reused/fitter_matrix_v2.py` | `ce6794c827763182135071970713694a3b3b7005c95df796b991221b1096fab0` |21–23 engine pins;82–94 preparation |

`reader.py:96–110` uses this engine and checks `l2=1`, `iterations=2000`, `learning_rate=.05`. Its objective convention, inferred directly from the implemented gradient, is

\[
J(\alpha,w)=L(\alpha,w)+\frac{\lambda}{2}\|w\|_2^2,
\quad L=\frac1n\sum_i[\log(1+e^{h_i})-z_i h_i],
\quad h_i=\alpha+w^T x_i.
\]

Here \(z_i\) is the binary progress-window completion label, distinct from an action's event outcome. The implementation evaluates a stable sigmoid for the gradients and does not evaluate \(L\) itself. The intercept is unpenalized. All weights and the intercept start at zero. Every iteration is a full-batch gradient step with \(\eta=.05\); the penalty gradient is \(\lambda w\), without division by \(n\). Although the intercept assignment precedes the weight assignment, both use the same already-computed errors, hence the same old iterate.

## The constant-control columns

Fix one event and a training row. Let \(r_i\) be its mean binary outcome over the retained scored pairs. Replacing each forecast by the same \(q\), without changing those pairs, gives

\[
B_i(q)=\overline{(q-y)^2}=q^2+(1-2q)r_i.
\]

Crucially, the actual control changes **common features as well as P features**: `allocation_diagnostics.py:44–49` sets the common paired probability mean to \(q\) and its squared mean to \(q^2\), leaves the common paired outcome mean \(r_i\) unchanged, and recomputes Brier as above. Scored counts and missingness are retained. Lines79–82 then pass these derivative rows to `fit_matched_models`, fitting both \(A1_q\) and \(P_q\). They do not compare a modified P against the original scientific A1 model. Below, a "fixed common matrix" means the shared derivative matrix **within this one control case**. It is generally different from the original matrix with varying forecast moments. Across the three constant-q controls, their common training matrices coincide in real arithmetic because the altered probability columns standardize to zero and the other common values/masks are unchanged.

Both \(B_i\) and \(r_i\) are missing exactly when that event has no scored pairs. Preprocessing computes each column's population mean/variance on its nonmissing training entries, uses scale1 for zero variance, and maps missing entries to standardized0. \(A1_q\) already contains the paired outcome column. Relative to this same derivative common matrix, \(P_q\) adds only the three Brier values; it adds no new residual-missingness indicator.

If the observed training variance of \(r\) is positive, write \(x_i=(r_i-\mu_r)/\sigma_r\), with0 on missing rows. Since \(\mu_B=q^2+(1-2q)\mu_r\) and \(\sigma_B=|1-2q|\sigma_r\), its standardized Brier column satisfies

\[
x_{B,i}=s x_i,\qquad s=\operatorname{sign}(1-2q).
\]

Thus \(q=.25\) gives an identical column and \(q=.75\) its negative. At \(q=.5\), every observed Brier value is.25 and the entire standardized Brier training column is0. The constant probability and squared-probability columns likewise standardize to0, while their existing missingness indicators are shared by A1/P.

If observed outcomes are constant, both outcome and Brier **training** columns are0. If no outcomes are observed, both are imputed0. Those coordinates receive no data gradient and stay at zero from initialization. The signed standardized-column identity should not be extended blindly to new observations after a zero-variance/all-missing training fit: the scale1 convention need not preserve it there. These edge cases do not create new training information. All identities here are exact in real arithmetic; floating-point centering/scaling can introduce roundoff, so bitwise identities are not asserted.

## Induced penalty and the finite trajectory

For a nonzero duplicate pair, let \(a\) multiply \(x\), \(b\) multiply \(s x\), and define \(\theta=a+s b\), \(\delta=a-s b\). Keeping all other coordinates \(u\) explicit,

\[
J=L(\alpha,\theta,u)+\frac\lambda4\theta^2
  +\frac\lambda4\delta^2+\frac\lambda2\|u\|^2.
\]

For a fixed effective coefficient \(\theta\), minimizing the duplicate-pair penalty gives \(a=\theta/2\), \(b=s\theta/2\). Its penalty is therefore \(\lambda\theta^2/4\), versus \(\lambda\theta^2/2\) for a single column. This halves shrinkage **in each duplicated coordinate**; it does not halve the whole model's ridge penalty or remove other collinearities.

Let \(g=\partial_\theta L\), evaluated at the current complete model. The actual two weight updates imply exactly

\[
\theta^+=\theta-\eta(2g+\lambda\theta)
          =\theta-2\eta(g+\lambda\theta/2),\qquad
\delta^+=(1-\eta\lambda)\delta.
\]

Zero initialization keeps \(\delta=0\) at every finite step. Other penalized coordinates obey \(u^+=u-\eta(\nabla_u L+\lambda u)\); the intercept obeys \(\alpha^+=\alpha-\eta\partial_\alpha L\). With the actual defaults, duplicate coordinates have effective step.10 and ridge-gradient coefficient.5 in that reparameterization; other coordinates retain step.05 and coefficient1. Their gradients are evaluated on the evolving common predictor and need not numerically match the single-column fit's gradients. Consequently the2000-step trajectory is not equivalent to running the entire A1 model with one globally altered learning rate or regularizer. The derivation neither assumes convergence nor explains a particular numerical difference by convergence alone.

Since the added columns are signed duplicates on these control training matrices, their fitted-probability differences cannot demonstrate new pairing information: basis-dependent shrinkage and finite optimization suffice to permit different fitted probabilities. The original scientific A1/P models are neither replaced nor validated by these derivative fits. No allocator efficacy, held-out calibration, ARC score, or novelty follows.

## Exact retained aggregate evidence

The original `artifacts/private/collection-real-v3-reader-fit-v5/constant-controls.json` is2317bytes, SHA256 `7fc50d819b24d393dab3f0f325ea43f0a25adccd8d052c7457396896c71080f3`. The original `inspection.json`, SHA256 `a57db9790fa4579b422d33f2af2e1c33c1096caff2cf1563adf3f4082a4e8a20`, binds exactly this length/hash in `output_files["constant-controls.json"]`. Its once-result is `artifacts/reviews/collection-real-v3-fit-once-v1/result.json`, SHA256 `52183a05b396ea7d27322e3ef15d63d3469561bb11564f98a02b6be4513c0fab`; no invocation was repeated here.

Actual report fields are `cases[i].constant_probability`, `cases[i].max_abs_training_probability_difference`, `cases[i].rms_training_probability_difference`, and `cases[i].equivalent_within_absolute_tolerance`. The retained cases are:

| i | `constant_probability` | `max_abs_training_probability_difference` | `equivalent_within_absolute_tolerance` |
|---|---|---|---|
|0|0.25|0.056532387482543744|false|
|1|0.5|0.0|true|
|2|0.75|0.056532387482543744|false|

The half case also records `rms_training_probability_difference=0.0`; `absolute_equivalence_tolerance=1e-12`. The common `source_rows_sha256` is `1d475d7e6de0a863f64268e7a1baab42cec62390a32d265333fe67ecfce04053`; the three `derived_rows_sha256` values are respectively `847ec3bc822e99685310d9bc5630de9fe66576800a71f3cab9b249908be72179`, `1965da3f361a42ead75f62d4b33344bdb41b6bb37743d407e5a48216e6e32964`, and `9a89c6d4ec13353af5be04a70ef5bc10157e0e6ca9f1371be2be91af53cb33b7`. The report explicitly says `prediction_evaluation="raw_fitted_probabilities_on_derivative_training_rows"`, `analysis_only=true`, `scientific_result=false`, `policy_performance_estimate=false`, `source_rows_modified=false` and `models_exported=false`. These are preserved observations, not new measurements. The0.0565 manuscript figure is the rounded maximum above, not a comparison with the original A1 predictions.

## Proposed appendix paragraph

The constant-probability controls replace the common forecast moments by \(q,q^2\), retain the common outcome mean, and refit both classifiers on the derivative rows. Within each such control, mean Brier is \(q^2+(1-2q)\bar y\) on exactly those scored pairs. After mean imputation and population standardization, P's added columns are zero at \(q=.5\), and signed duplicates of that control's A1 outcome columns at \(q=.25/.75\) when observed training variance is positive; zero-variance columns also contribute zero on training rows. With objective \(L+\lambda\|w\|^2/2\), a duplicate changes its effective coefficient's penalty from \(\lambda\theta^2/2\) to \(\lambda\theta^2/4\). Our zero-initialized full-gradient optimizer also doubles that coordinate's effective step, while other coordinates retain the original step. The observed0.0565 training-probability difference supplies no pairing information or policy evidence. These controls document, rather than remove, a regularization and optimization confound; their common matrix is not the original varying-forecast A1 matrix.

Owned note:MIT-0; proposed paper prose intended for CC BY4.0. No scientific protocol or selected source was changed.

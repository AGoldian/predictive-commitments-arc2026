"""Development-only progress fitting and matched allocation primitives.

These functions neither run a solver nor identify causal value per token. No
trained model or performance result is shipped. Callbacks must arrive in actual
execution order; token horizons cannot be reconstructed from action-only totals.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math

EVENTS = ('frame_changed', 'level_completed', 'attempt_failed')
PAIRED_MOMENT_FEATURES = tuple(f'{moment}_last8_{event}' for event in EVENTS
                              for moment in ('paired_probability_mean',
                                             'paired_probability_squared_mean',
                                             'paired_outcome_mean'))

COMMON_FEATURES = (
    'baseline_priority', 'generated_target_tokens', 'level_number', 'real_action_count',
    'consecutive_unproductive_actions', 'unique_observation_hash_count',
    'predictions_valid', 'predictions_abstained', 'missing_frame_changed',
    'missing_level_completed', 'missing_attempt_failed',
    'scored_last8_frame_changed', 'scored_last8_level_completed', 'scored_last8_attempt_failed',
    'residual_missing_last8_frame_changed', 'residual_missing_last8_level_completed',
    'residual_missing_last8_attempt_failed',
    'eligible_actions_last8', 'valid_predictions_last8',
) + tuple(f'outcomes_available_last8_{event}' for event in EVENTS) + PAIRED_MOMENT_FEATURES
RESIDUAL_FEATURES = ('brier_last8_frame_changed', 'brier_last8_level_completed',
                     'brier_last8_attempt_failed')
# Event-only is the initial option. Adding mask features requires the documented
# validation choice and a separately frozen schema before audit evaluation.


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')
    return value


def _finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('features must be finite real numbers or None')
    return float(value)


def validate_features(features, names):
    if not isinstance(features, dict) or set(features) != set(names):
        raise ValueError('feature names must match the frozen whitelist exactly')
    result = {name: None if features[name] is None else _finite(features[name]) for name in names}
    for name, value in result.items():
        if name.startswith(('scored_last8_', 'residual_missing_last8_', 'outcomes_available_last8_')) or name in {'valid_predictions_last8','eligible_actions_last8'}:
            maximum = 1 if name.startswith('residual_missing_') else 8
            if value is None or value != int(value) or not 0 <= value <= maximum:
                raise ValueError('last-eight coverage counts/flags must be observed and in range')
        elif value is not None and not 0 <= value <= (1 if name in RESIDUAL_FEATURES + PAIRED_MOMENT_FEATURES else 1e12):
            raise ValueError('feature outside the frozen nonnegative domain')
        elif value is not None and name in COMMON_FEATURES and name not in PAIRED_MOMENT_FEATURES and name != 'baseline_priority' and value != int(value):
            raise ValueError('observed token/action/level/availability counts must be integers')
    if 'eligible_actions_last8' in result and 'valid_predictions_last8' in result:
        if result['valid_predictions_last8'] > result['eligible_actions_last8']:
            raise ValueError('probability availability exceeds eligible history length')
    for event in EVENTS:
        count, flag, residual = (f'scored_last8_{event}', f'residual_missing_last8_{event}', f'brier_last8_{event}')
        if count in result and flag in result:
            unavailable = result[count] == 0
            if result[flag] != float(unavailable):
                raise ValueError('last-eight coverage and missingness flag disagree')
            if residual in result and (result[residual] is None) != unavailable:
                raise ValueError('residual availability must match common coverage features')
            for moment in ('paired_probability_mean', 'paired_probability_squared_mean', 'paired_outcome_mean'):
                name = f'{moment}_last8_{event}'
                if name in result and (result[name] is None) != unavailable:
                    raise ValueError('paired common moments must use the same scored-pair availability')
            for availability in ('valid_predictions_last8', f'outcomes_available_last8_{event}'):
                if availability in result and result[count] > result[availability]:
                    raise ValueError('paired count exceeds probability/outcome availability')
            if all(n in result for n in ('eligible_actions_last8','valid_predictions_last8',f'outcomes_available_last8_{event}')):
                length, valid, observed = (result[n] for n in ('eligible_actions_last8','valid_predictions_last8',f'outcomes_available_last8_{event}'))
                if observed > length or length-valid-observed+result[count] < 0:
                    raise ValueError('rolling availability categories are inconsistent')
    return result


class ProgressWindow:
    """One window; the caller enforces nonoverlap using the planned ledger.

    Completion on the horizon-th observed action is positive. A token horizon
    already reached before dispatch closes negative before a later action.
    """
    def __init__(self, window_id, episode, level, features, *, reserved_target_tokens,
                 token_horizon=8192, action_horizon=20):
        if not window_id or not episode:
            raise ValueError('window and episode identifiers required')
        self.level = _count(level, 'level')
        self.token_horizon = _count(token_horizon, 'token_horizon')
        self.action_horizon = _count(action_horizon, 'action_horizon')
        if not self.token_horizon or not self.action_horizon:
            raise ValueError('horizons must be positive')
        if _count(reserved_target_tokens, 'reserved_target_tokens') < self.token_horizon:
            raise ValueError('do not open a window without its reserved token capacity')
        self.window_id, self.episode = window_id, episode
        self.features = validate_features(features, COMMON_FEATURES + RESIDUAL_FEATURES)
        self.tokens = self.actions = 0
        self.action_ids = set()
        self.status, self.label, self.reason = 'open', None, None

    def _open(self):
        if self.status != 'open':
            raise ValueError('window is already closed')

    def _close(self, label, reason):
        self.status, self.label, self.reason = 'complete', label, reason

    def generated_tokens(self, accepted_target_tokens):
        self._open()
        self.tokens += _count(accepted_target_tokens, 'accepted_target_tokens')
        if self.tokens >= self.token_horizon:
            self._close(0, 'token_horizon')

    def action_observed(self, action_id, levels_completed, *, automatic=False):
        self._open()
        if not isinstance(action_id, str) or not action_id or action_id in self.action_ids:
            raise ValueError('each real action needs a unique identifier')
        if type(automatic) is not bool:
            raise ValueError('automatic must be explicit boolean')
        if levels_completed is None:
            # The label cannot be established from an unavailable observation.
            self.censor('missing_level_observation')
            return
        level = _count(levels_completed, 'levels_completed')
        if level < self.level:
            raise ValueError('completed-level counter regressed')
        self.action_ids.add(action_id)
        if not automatic:
            self.actions += 1
        if level > self.level:
            self._close(1, 'level_completed')
        elif self.actions >= self.action_horizon:
            self._close(0, 'action_horizon')

    def censor(self, reason):
        self._open()
        if not isinstance(reason, str) or not reason:
            raise ValueError('censor reason required')
        self.status, self.label, self.reason = 'censored', None, reason

    def record(self):
        return {'window_id': self.window_id, 'episode': self.episode, 'phase': 'development',
                'start_level': self.level, 'features': dict(self.features), 'status': self.status,
                'label': self.label, 'reason': self.reason, 'generated_target_tokens': self.tokens,
                'real_nonautomatic_actions': self.actions,
                'token_horizon': self.token_horizon, 'action_horizon': self.action_horizon}


def _sigmoid(x):
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    exp = math.exp(x)
    return exp / (1 + exp)


@dataclass(frozen=True)
class ProgressModel:
    names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training_sha256: str
    training_rows: int
    l2: float = 1.0
    iterations: int = 2000
    learning_rate: float = 0.05

    def vector(self, features):
        f = validate_features(features, self.names)
        # Development mean imputation + explicit missingness indicators. Means
        # and scales are never refit from a validation/audit stream.
        values = [(0.0 if f[name] is None else (f[name]-mean)/scale)
                  for name, mean, scale in zip(self.names, self.means, self.scales)]
        # Residual availability is already represented in COMMON_FEATURES for
        # both arms. Duplicating it in P would change its effective L2 penalty.
        return values + [float(f[name] is None) for name in self.names if name in COMMON_FEATURES]

    def probability(self, features):
        x = self.vector(features)
        return _sigmoid(self.intercept + sum(w*v for w,v in zip(self.coefficients,x)))

    def to_dict(self):
        return asdict(self)


def _fit(rows, names, training_sha):
    raw = [validate_features({n:r['features'][n] for n in names}, names) for r in rows]
    means, scales = [], []
    for name in names:
        values = [f[name] for f in raw if f[name] is not None]
        mean = sum(values)/len(values) if values else 0.0
        variance = sum((x-mean)**2 for x in values)/len(values) if values else 0.0
        means.append(mean)
        scales.append(math.sqrt(variance) if variance > 0 else 1.0)
    model = ProgressModel(tuple(names), tuple(means), tuple(scales),
                          (0.0,)*(len(names)+len(COMMON_FEATURES)), 0.0, training_sha, len(rows))
    xs = [model.vector(f) for f in raw]
    ys = [r['label'] for r in rows]
    weights = list(model.coefficients)
    intercept = 0.0
    for _ in range(model.iterations):
        errors = [_sigmoid(intercept + sum(w*v for w,v in zip(weights,x))) - y
                  for x,y in zip(xs,ys)]
        intercept -= model.learning_rate * sum(errors)/len(rows)
        gradients = [sum(e*x[j] for e,x in zip(errors,xs))/len(rows) + model.l2*weights[j]
                     for j in range(len(weights))]
        weights = [w-model.learning_rate*g for w,g in zip(weights,gradients)]
    if not all(math.isfinite(v) for v in (*means, *scales, *weights, intercept)):
        raise ValueError('non-finite fitted parameters; no model is available')
    return ProgressModel(model.names, model.means, model.scales, tuple(weights), intercept,
                         training_sha, len(rows))


def fit_matched_models(rows):
    """Fit A1/P on identical complete development windows; never drop censoring."""
    if not rows:
        raise ValueError('training windows required')
    ids = set()
    for row in rows:
        if row.get('phase') != 'development' or row.get('status') != 'complete':
            raise ValueError('all planned rows must be complete development windows')
        if type(row.get('label')) is not int or row['label'] not in (0,1):
            raise ValueError('complete binary progress labels required')
        if not isinstance(row.get('window_id'), str) or not row['window_id'] or row['window_id'] in ids:
            raise ValueError('duplicate or missing training window identifier')
        ids.add(row['window_id'])
        validate_features(row.get('features'), COMMON_FEATURES + RESIDUAL_FEATURES)
    if {r['label'] for r in rows} != {0,1}:
        raise ValueError('fitting infeasible without both positive and negative windows')
    training_sha = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'),
                                              allow_nan=False).encode()).hexdigest()
    return {'A1': _fit(rows, COMMON_FEATURES, training_sha),
            'P': _fit(rows, COMMON_FEATURES + RESIDUAL_FEATURES, training_sha)}


def adjusted_priority(baseline_priority, features, models, arm):
    """Only P sees residuals. Fully unavailable evidence falls back to A1."""
    base = _finite(baseline_priority)
    if base < 0 or arm not in {'B1', 'A1', 'P'}:
        raise ValueError('nonnegative baseline priority and a documented arm required')
    f = validate_features(features, COMMON_FEATURES + RESIDUAL_FEATURES)
    if arm == 'B1':
        return base
    use = 'A1' if arm == 'A1' or all(f[n] is None for n in RESIDUAL_FEATURES) else 'P'
    model = models[use]
    probability = model.probability({n:f[n] for n in model.names})
    return base * (0.5 + probability)

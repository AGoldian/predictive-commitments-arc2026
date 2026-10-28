"""Atomic, observable-only action prediction checks. No solver or scheduler yet.

Endpoint frame change includes HUD/animation changes and is not semantic progress.
RESET and unexecuted calls are excluded from residuals but must remain in traces.
An adapter must call commit BEFORE submitting the action, then observe exactly once.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time

EVENTS = ('frame_changed', 'level_completed', 'attempt_failed')


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    episode: str
    sequence: int
    frame_sha256: str
    levels_completed: int
    state: str


@dataclass(frozen=True)
class Commitment:
    id: str
    before: Observation
    action_sha256: str
    action_name: str
    probabilities: tuple[float, float, float] | None
    committed_monotonic_ns: int


def probabilities(value) -> tuple[float, float, float] | None:
    """Missing predictions abstain; malformed/extra/non-finite fields fail closed."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(EVENTS):
        raise ValueError('prediction must contain exactly the three documented events')
    result = []
    for event in EVENTS:
        p = value[event]
        if type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError('event probabilities must be finite real numbers in [0,1]')
        result.append(float(p))
    return tuple(result)


class PrequentialVerifier:
    def __init__(self):
        self.pending: Commitment | None = None
        self.counter = 0

    def commit(self, before: Observation, action: dict, prediction: dict | None) -> Commitment:
        if self.pending is not None:
            raise ValueError('previous action has no recorded outcome')
        if not isinstance(action, dict) or not isinstance(action.get('name'), str):
            raise ValueError('action name required')
        if before.state in {'WIN', 'GAME_OVER'} and action.get('name') != 'RESET':
            raise ValueError('terminal observations require an explicit reset')
        probs = probabilities(prediction)
        self.counter += 1
        pending = Commitment(f'C{self.counter:06d}', before, digest(action), action['name'], probs, time.monotonic_ns())
        self.pending = pending
        return pending

    def observe(self, commitment_id: str, action: dict, after: Observation | None, *, executed: bool = True) -> dict:
        pending = self.pending
        if pending is None or pending.id != commitment_id or digest(action) != pending.action_sha256:
            raise ValueError('outcome does not match pending action commitment')
        result = {'commitment_id': pending.id, 'action_sha256': pending.action_sha256,
                  'committed_monotonic_ns': pending.committed_monotonic_ns,
                  'observed_monotonic_ns': time.monotonic_ns(), 'outcomes': None, 'brier': None}
        if not executed:
            result['status'] = 'not_executed'
        elif pending.action_name == 'RESET':
            if after is None:
                raise ValueError('executed reset requires returned observation')
            result['status'] = 'reset_excluded'
        else:
            if after is None or after.episode != pending.before.episode or after.sequence != pending.before.sequence + 1:
                raise ValueError('must pair the immediately following observation in the same episode')
            if after.levels_completed < pending.before.levels_completed:
                raise ValueError('unrecorded reset or inconsistent level counter')
            outcomes = (int(after.frame_sha256 != pending.before.frame_sha256),
                        int(after.levels_completed > pending.before.levels_completed),
                        int(after.state == 'GAME_OVER'))
            result['outcomes'] = dict(zip(EVENTS, outcomes))
            if pending.probabilities is None:
                result['status'] = 'abstained'
            else:
                residuals = [(p - y) ** 2 for p, y in zip(pending.probabilities, outcomes)]
                result['brier'] = sum(residuals) / len(EVENTS)
                result['event_squared_errors'] = dict(zip(EVENTS, residuals))
                result['status'] = 'scored'
        self.pending = None
        return result

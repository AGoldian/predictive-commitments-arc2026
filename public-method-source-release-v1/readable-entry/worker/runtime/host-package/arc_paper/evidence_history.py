"""Common observable history for A1/P, from trusted host action receipts only.

Never consume a model/sandbox claim that an action executed. The integration
must bind these receipts to its actual SDK call ledger. This accumulator is a
component and does not establish that external receipts are truthful.
"""
from collections import deque
import math

from .allocation import COMMON_FEATURES, RESIDUAL_FEATURES, validate_features
from .predictions import EVENTS


class EvidenceHistory:
    def __init__(self, episode, initial):
        if initial.episode != episode:
            raise ValueError('initial public observation belongs to another episode')
        self.episode = episode
        self.level = initial.levels_completed
        self.unique_frames = set()
        if initial.final_frame_sha256 is not None:
            self.unique_frames.add(initial.final_frame_sha256)
        self.actions = self.valid = self.abstained = 0
        self.nochange_streak = 0
        self.missing = {e:0 for e in EVENTS}
        self.last8 = deque(maxlen=8)
        self.seen = set()
        self.watermark_ns = 0

    def update(self, receipt):
        if receipt.get('event') != 'receipt':
            raise ValueError('only trusted action-boundary host receipts are accepted')
        identifier = receipt.get('transition_id')
        if not isinstance(identifier,str) or not identifier or identifier in self.seen:
            raise ValueError('missing or duplicate transition receipt')
        at = receipt.get('observed_monotonic_ns')
        if type(at) is not int or at < self.watermark_ns:
            raise ValueError('receipt clock regressed')
        execution = receipt.get('execution')
        if execution not in {'executed','refused','unknown'}:
            raise ValueError('execution classification required')
        if execution == 'unknown':
            raise ValueError('unknown execution halts the episode; do not update features')
        after = receipt.get('after')
        if execution == 'executed' and (not isinstance(after,dict) or after.get('episode') != self.episode):
            raise ValueError('missing or foreign executed-action observation')
        name = receipt.get('action',{}).get('name')
        if name not in {'RESET',*[f'ACTION{i}' for i in range(1,8)]}:
            raise ValueError('documented action name required')
        outcomes = receipt.get('outcomes')
        errors = receipt.get('event_squared_errors')
        if not isinstance(outcomes,dict) or set(outcomes) != set(EVENTS) or not isinstance(errors,dict) or set(errors) != set(EVENTS):
            raise ValueError('complete event/missing-label schema required')
        for event in EVENTS:
            y,error = outcomes[event],errors[event]
            if y is not None and (type(y) is not int or y not in (0,1)):
                raise ValueError('observable event must be binary or missing')
            if error is not None and (type(error) not in (int,float) or not math.isfinite(error) or not 0<=error<=1 or y is None):
                raise ValueError('event error requires an available label and finite squared loss')
        prediction_status=receipt.get('prediction_status')
        if prediction_status not in {'valid','missing','invalid'}:
            raise ValueError('prediction validity must be explicit')
        if prediction_status != 'valid' and any(e is not None for e in errors.values()):
            raise ValueError('abstention cannot carry a predictive residual')
        probabilities=receipt.get('prediction_probabilities')
        if prediction_status == 'valid':
            if not isinstance(probabilities,dict) or set(probabilities) != set(EVENTS):
                raise ValueError('valid host receipt must retain committed event probabilities')
            for event,p in probabilities.items():
                if type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1:
                    raise ValueError('committed probabilities must be finite and in range')
                # Every valid prediction with an available label enters the
                # same paired sample; neither arm can select favorable pairs.
                eligible = execution == 'executed' and name not in {'RESET','ACTION7'} and outcomes[event] is not None
                expected = (p-outcomes[event])**2 if eligible else None
                if ((errors[event] is None) != (expected is None)
                    or expected is not None and not math.isclose(errors[event],expected,rel_tol=1e-12,abs_tol=1e-12)):
                    raise ValueError('host error must score every available committed prediction exactly once')
        elif probabilities is not None:
            raise ValueError('abstention cannot carry probabilities')
        if execution == 'executed':
            level = after.get('levels_completed')
            if level is not None and (type(level) is not int or level<0):
                raise ValueError('public level count must be nonnegative or missing')
            # Same canonical final-frame digest as the action adapter; no
            # sequence counters/timestamps in observation-novelty features.
            from .prediction_adapter import PublicObservation
            observation=PublicObservation(**after)
            frame_hash=observation.final_frame_sha256
        # All validation precedes mutation, so bad rows cannot partly advance it.
        self.seen.add(identifier)
        self.watermark_ns=at
        if execution == 'refused':
            return
        self.actions+=1 # captured calls include RESET/UNDO; pre-hook SDK startup is separate
        self.level=level
        if frame_hash is not None:self.unique_frames.add(frame_hash)
        if name in {'RESET','ACTION7'}:
            self.nochange_streak=0
            return
        changed=outcomes['frame_changed']
        self.nochange_streak=(self.nochange_streak+1 if self.nochange_streak is not None else None) if changed==0 else 0 if changed==1 else None
        if prediction_status=='valid':self.valid+=1
        else:self.abstained+=1
        for event in EVENTS:
            if outcomes[event] is None:self.missing[event]+=1
        self.last8.append({'errors':dict(errors),'probabilities':probabilities,
                           'outcomes':dict(outcomes),'valid':prediction_status=='valid'})

    def features(self, *, baseline_priority, generated_target_tokens):
        """level_number uses the public completed-level counter (0 at level 1).

        Token usage must come from the host request ledger, including generation
        without an action. Supply None if actual accepted usage is unavailable.
        The legacy field 'unproductive' means consecutive unchanged raw endpoint
        frames; it does not classify semantic progress or remove HUD pixels.
        """
        f={'baseline_priority':baseline_priority,'generated_target_tokens':generated_target_tokens,
           'level_number':self.level,'real_action_count':self.actions,
           'consecutive_unproductive_actions':self.nochange_streak,
           'unique_observation_hash_count':len(self.unique_frames),
           'predictions_valid':self.valid,'predictions_abstained':self.abstained,
           'eligible_actions_last8':len(self.last8),
           'valid_predictions_last8':sum(row['valid'] for row in self.last8)}
        for event in EVENTS:
            pairs=[row for row in self.last8 if row['errors'][event] is not None]
            errors=[row['errors'][event] for row in pairs]
            f[f'missing_{event}']=self.missing[event]
            f[f'scored_last8_{event}']=len(errors)
            f[f'residual_missing_last8_{event}']=int(not errors)
            f[f'brier_last8_{event}']=math.fsum(errors)/len(errors) if errors else None
            f[f'outcomes_available_last8_{event}']=sum(row['outcomes'][event] is not None for row in self.last8)
            f[f'paired_probability_mean_last8_{event}']=math.fsum(row['probabilities'][event] for row in pairs)/len(pairs) if pairs else None
            f[f'paired_probability_squared_mean_last8_{event}']=math.fsum(row['probabilities'][event]**2 for row in pairs)/len(pairs) if pairs else None
            f[f'paired_outcome_mean_last8_{event}']=math.fsum(row['outcomes'][event] for row in pairs)/len(pairs) if pairs else None
        return validate_features(f,COMMON_FEATURES+RESIDUAL_FEATURES)

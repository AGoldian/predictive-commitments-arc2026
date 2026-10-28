# SPDX-License-Identifier: MIT-0
"""Pure additive reconciliation of the frozen automatic RESET prefix journal.

This checks source-bound evidence consistency, not remote execution attestation.
It never projects out an action or supplies a logical exchange to another
validator. The original host/initial/queue and numerical gates remain required.
"""
from __future__ import annotations

import hashlib
import json
import math

from .prediction_adapter import PublicObservation

PREFIX_SOURCE_SHA256 = '63890808464c7df57e51cf0d97ce0a2a27ca65e10e1e71840626a8e309c79fb6'
POLICY_SHA256 = 'eef252ac22a0a6a7da696c5fbbac607e4085b1b9434d8b834f78b64ea71b6165'
TIME_TOLERANCE_NS = 1000  # Only cross-producer float conversion; never cutoff grace.
SOURCE_PAIRS = {'B0': ('3247cd61235c5b31d867bbb97b552349e9413a29574cef839d8b0986a8aa01e7', 'bc05dfb59cf0965f931faf8307993a27ae6b1fadf415e2649f52262b9585f746'), 'B1': ('13a9ec792526ab7a2cedc8857ff8331d9049df307d9a81ceb803287744b9642e', '4993d46cfae2f372699019bbeb2ce7070ea91a86e3b3e942c0bdb10c3744789e')}
SOURCE_PAIRS.update(A1=SOURCE_PAIRS['B1'], P=SOURCE_PAIRS['B1'])
BASE = {'schema_version', 'namespace', 'sequence', 'event', 'policy_sha256',
        'predecessor_solver_sha256', 'successor_solver_sha256', 'arm', 'run_id',
        'session_id', 'action_episode', 'monotonic', 'monotonic_ns'}
EXTRAS = {
    'admitted': {'cause', 'cause_ordinal', 'cause_monotonic', 'prefix', 'lease_id',
                 'features_sha256', 'allocation_sha256', 'before'},
    'body_finished': {'prefix', 'lease_id', 'transition_id', 'commitment_id', 'after'},
    'logical_reuse': {'lease_id', 'features_sha256', 'allocation_sha256', 'purpose', 'after'},
    'refused': {'reason', 'prefix'},
    'aborted': {'lease_id', 'reason', 'after', 'successful_service', 'capacity_feasible'},
}
WATERMARKS = {'binding_sha256', 'action_sequence', 'sdk_calls_executed',
              'taaf_history_commits', 'accepted_target_tokens', 'logical_sequence',
              'public_observation_sha256'}
GATE_EVENTS = {'fleet_registered', 'enqueue', 'refresh', 'admit', 'begin', 'first_service',
               'failed_exchange_settled', 'settle', 'abort', 'terminal', 'cancel', 'cancel_requested'}
HOST_EVENTS = {'ownership_bound', 'logical_request_started', 'logical_request_finished',
               'request_started', 'accepted_usage', 'action_dispatch', 'sdk_public_return',
               'action_receipt', 'sdk_action_refused', 'official_actions_observed', 'session_closed'}


class PrefixIntegrityError(ValueError):
    """Missing, contradictory or unsupported prefix evidence; caller retains costs."""


def _need(ok, reason):
    if not ok:
        raise PrefixIntegrityError(reason)


def _count(value):
    return type(value) is int and value >= 0


def _identifier(value):
    return type(value) is str and 0 < len(value) <= 512


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _observation(value, *, episode, sequence, initial=False):
    fields = {'episode', 'sequence', 'frames', 'levels_completed', 'state',
              'available_actions', 'frame_target_available'}
    _need(type(value) is dict and set(value) == fields, 'public_observation_schema')
    _need(value['sequence'] == sequence and type(value['sequence']) is int,
          'public_observation_sequence')
    # Exact frozen factory codec uses run_id; the adapter uses action_episode.
    # Only this source-defined episode substitution is allowed for initial data.
    _need(initial or value['episode'] == episode, 'public_observation_episode')
    rebound = dict(value, episode=episode)
    try:
        observation = PublicObservation(**rebound)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PrefixIntegrityError('invalid_public_observation') from exc
    return observation.sha256, value['state']


def _initial(initial_rows, owners):
    captures = {}
    for row in initial_rows:
        _need(type(row) is dict and row.get('schema_version') == 1
              and type(row.get('schema_version')) is int and _count(row.get('monotonic_ns'))
              and row.get('after_stop') is False
              and row.get('scope') == 'sdk_initialization' and _identifier(row.get('run_id'))
              and _identifier(row.get('capture_id')), 'initial_schema')
        captures.setdefault((row['run_id'], row['capture_id']), []).append(row)
    result = {}
    for pair, owner in owners.items():
        _need(_identifier(owner.get('initialization_capture_id')), 'initial_capture_identity')
        rows = captures.pop((pair[0], owner.get('initialization_capture_id')), None)
        _need(rows is not None and len(rows) == 3
              and [r.get('event') for r in rows] == ['initial_reset_dispatch',
                  'initial_reset_public_return', 'initial_reset_receipt']
              and [r.get('sequence') for r in rows] == [1, 2, 3]
              and all(type(r.get('sequence')) is int for r in rows)
              and all(a['monotonic_ns'] <= b['monotonic_ns'] for a, b in zip(rows, rows[1:])),
              'missing_or_unsettled_initial_capture')
        dispatch, public, receipt = rows
        _need(dispatch.get('action') == receipt.get('action') == 'RESET'
              and dispatch.get('before_available') is False
              and receipt.get('before_available') is False
              and dispatch.get('prediction_target_excluded') is True
              and receipt.get('prediction_target_excluded') is True
              and receipt.get('execution') == 'executed'
              and type(receipt.get('sdk_calls_executed')) is int
              and receipt['sdk_calls_executed'] == 1
              and type(receipt.get('taaf_history_commits')) is int
              and receipt['taaf_history_commits'] == 0
              and receipt.get('official_actions') is None
              and owner.get('initialization_sdk_calls_executed') == 1
              and type(owner.get('initialization_sdk_calls_executed')) is int
              and owner.get('initialization_receipt_sequence') == 3
              and receipt['monotonic_ns'] <= owner['monotonic_ns'] + TIME_TOLERANCE_NS,
              'initial_receipt_or_owner_mismatch')
        value = public.get('public_observation')
        _need(type(value) is dict and value.get('episode') == pair[0], 'initial_public_run_mismatch')
        result[pair] = _observation(value, episode=owner['action_episode'], sequence=0, initial=True)
    _need(not captures, 'foreign_initial_capture')
    return result


def _host(host_rows, bindings, initial_rows):
    groups = {}
    for row in host_rows:
        _need(type(row) is dict and row.get('schema_version') == 1
              and type(row.get('schema_version')) is int
              and _identifier(row.get('run_id')) and _identifier(row.get('session_id'))
              and _count(row.get('monotonic_ns')) and type(row.get('event')) is str
              and row['event'] in HOST_EVENTS,
              'unsupported_or_invalid_host_schema')
        groups.setdefault((row['run_id'], row['session_id']), []).append(row)
    _need(set(groups) == set(bindings.values()), 'full_host_owner_bijection')
    owners = {}
    for pair, rows in groups.items():
        _need(rows[0].get('event') == 'ownership_bound'
              and sum(r['event'] == 'ownership_bound' for r in rows) == 1,
              'host_ownership_missing_or_duplicate')
        owners[pair] = rows[0]
    initial = _initial(initial_rows, owners)
    parsed = {}
    for pair, rows in groups.items():
        owner = owners[pair]
        episode = owner.get('action_episode')
        _need(_identifier(episode), 'missing_action_episode')
        fixed = ('run_id', 'session_id', 'action_episode', 'history_episode', 'http_agent_id', 'http_episode_id')
        _need(all(_identifier(owner.get(k)) for k in fixed), 'host_owner_identity')
        _need(owner['history_episode'] == episode, 'host_history_episode_mismatch')
        state = dict(action_sequence=0, sdk_calls_executed=0, taaf_history_commits=0,
                     accepted_target_tokens=0, logical_sequence=0,
                     public_observation_sha256=initial[pair][0])
        public_state, last_action = initial[pair][1], None
        states, actions, logicals, pending_intervals = [], {}, {}, []
        request, action, logical_pending = None, None, False
        successes, closed, prior_ns = 0, False, -1
        seen_requests = set()
        for seq, row in enumerate(rows, 1):
            _need(type(row.get('sequence')) is int and row['sequence'] == seq
                  and row['monotonic_ns'] >= prior_ns and not closed
                  and all(row.get(k) == owner[k] for k in fixed)
                  and row.get('after_stop') is False, 'host_sequence_identity_or_integrity')
            at, event = row['monotonic_ns'], row['event']
            prior_ns = at
            if event == 'logical_request_started':
                _need(not logical_pending and request is None and action is None
                      and row.get('logical_sequence') == state['logical_sequence'] + 1
                      and type(row.get('logical_sequence')) is int
                      and row.get('purpose') in ('main', 'summary', 'tail'), 'logical_start_mismatch')
                state['logical_sequence'] += 1
                logical_pending = True
                logicals[state['logical_sequence']] = {'start': row}
            elif event == 'logical_request_finished':
                _need(logical_pending and request is None and action is None
                      and type(row.get('logical_sequence')) is int
                      and row['logical_sequence'] == state['logical_sequence']
                      and type(row.get('succeeded')) is bool, 'logical_finish_mismatch')
                successes += int(row['succeeded'])
                _need(type(row.get('successful_logical_requests')) is int
                      and row['successful_logical_requests'] == successes, 'logical_success_count')
                logical_pending = False
                logicals[state['logical_sequence']]['finish'] = row
                pending_intervals.append((logicals[state['logical_sequence']]['start']['monotonic_ns'], at))
            elif event in ('request_started', 'accepted_usage'):
                key = (row.get('call_id'), row.get('attempt_id'))
                _need(all(_identifier(v) for v in key) and logical_pending
                      and row.get('purpose') == logicals[state['logical_sequence']]['start']['purpose'],
                      'request_logical_join')
                if event == 'request_started':
                    _need(request is None and key not in seen_requests, 'request_duplicate_or_pending')
                    seen_requests.add(key)
                    request = key
                else:
                    _need(request == key and _count(row.get('accepted_target_tokens')), 'accepted_usage_join')
                    state['accepted_target_tokens'] += row['accepted_target_tokens']
                    _need(type(row.get('known_accepted_target_tokens_total')) is int
                          and row['known_accepted_target_tokens_total'] == state['accepted_target_tokens'],
                          'accepted_usage_total')
                    request = None
            elif event == 'action_dispatch':
                key = (row.get('transition_id'), row.get('commitment_id'))
                _need(action is None and request is None and not logical_pending
                      and all(_identifier(v) for v in key) and key not in actions
                      and type(row.get('automatic')) is bool and _identifier(row.get('action')),
                      'action_dispatch_join')
                action = key
                actions[key] = {'dispatch': row}
            elif event == 'sdk_public_return':
                key = (row.get('transition_id'), row.get('commitment_id'))
                _need(action == key and 'public' not in actions[key], 'sdk_public_return_join')
                digest, public_state = _observation(row.get('public_observation'), episode=episode,
                    sequence=state['action_sequence'] + 1)
                state['public_observation_sha256'] = digest
                actions[key]['public'] = row
            elif event == 'action_receipt':
                key = (row.get('transition_id'), row.get('commitment_id'))
                _need(action == key and 'public' in actions[key]
                      and row.get('execution') == 'executed' and row.get('history_committed') is True
                      and row.get('action') == actions[key]['dispatch']['action']
                      and row.get('automatic') is actions[key]['dispatch']['automatic'],
                      'unknown_or_unjoined_action_receipt')
                for name in ('action_sequence', 'sdk_calls_executed', 'taaf_history_commits'):
                    state[name] += 1
                actions[key]['receipt'] = row
                pending_intervals.append((actions[key]['dispatch']['monotonic_ns'], at))
                last_action = row['action']
                action = None
            elif event == 'sdk_action_refused':
                _need(action is None and row.get('reason') == 'host_stop'
                      and row.get('sdk_dispatches') == 0 and row.get('sdk_calls_executed') == 0
                      and row.get('history_committed') is False, 'unsettled_sdk_refusal')
            elif event == 'session_closed':
                _need(action is None and request is None and not logical_pending
                      and row.get('known_accepted_target_tokens_total') == state['accepted_target_tokens'],
                      'host_close_unsettled')
                closed = True
            if action is None and request is None and not logical_pending:
                states.append((at, dict(state), public_state, last_action, seq))
        _need(closed and action is None and request is None and not logical_pending, 'host_not_terminally_settled')
        parsed[pair] = dict(owner=owner, states=states, actions=actions, logicals=logicals,
                            pending_intervals=pending_intervals)
    return parsed


def _queue(rows, planned, allocation_sha):
    _need(rows, 'missing_queue_journal')
    bindings, freezes, tickets, ticket_freezes, leases = {}, {}, {}, {}, {}
    sequence, last_clock = 0, -1.
    registered = 0
    for row in rows:
        _need(type(row) is dict and row.get('schema_version') == 1
              and type(row.get('schema_version')) is int and _finite(row.get('monotonic')),
              'queue_schema')
        event = row.get('event')
        _need(type(event) is str, 'queue_event_schema')
        if event == 'planned_session_bound':
            sid, pair = row.get('planned_session_id'), (row.get('run_id'), row.get('accounting_session_id'))
            _need(sid in planned and sid not in bindings and all(_identifier(v) for v in pair)
                  and pair not in bindings.values(), 'queue_binding_mismatch')
            bindings[sid] = pair
        elif event == 'boundary_frozen':
            sid = row.get('planned_session_id')
            _need(sid in planned and row.get('allocation_sha256') == allocation_sha
                  and _sha(row.get('features_sha256')) and type(row.get('features')) is dict,
                  'frozen_features_schema')
            _need(all(_count(row.get(k)) for k in ('logical_sequence', 'action_watermark', 'accepted_target_tokens')),
                  'frozen_features_watermark_schema')
            try:
                feature_sha = _digest(row['features'])
            except (TypeError, ValueError, OverflowError) as exc:
                raise PrefixIntegrityError('invalid_frozen_features') from exc
            _need(feature_sha == row['features_sha256'], 'frozen_features_digest')
            freezes.setdefault(sid, []).append(row)
        if event not in GATE_EVENTS:
            _need('sequence' not in row, 'manual_queue_has_gate_sequence')
            continue  # Governor/manual events are checked by their own unchanged validators.
        sequence += 1
        _need(type(row.get('sequence')) is int and row['sequence'] == sequence
              and row['monotonic'] >= last_clock, 'gate_sequence_or_clock')
        last_clock = row['monotonic']
        sid = row.get('session_id')
        if event == 'fleet_registered':
            registered += 1
            _need(sequence == 1 and row.get('planned_sessions') == planned, 'planned_fleet_mismatch')
        elif event == 'enqueue':
            arrival = row.get('arrival')
            _need(sid in planned and _count(arrival) and arrival > 0 and arrival not in tickets
                  and row.get('model_sha256') == allocation_sha
                  and all(_sha(row.get(k)) for k in ('binding_sha256', 'features_sha256'))
                  and _identifier(row.get('episode_id'))
                  and all(_count(row.get(k)) for k in ('action_watermark', 'usage_watermark')),
                  'enqueue_ticket_schema')
            matching = [f for f in freezes.get(sid, [])
                        if f['features_sha256'] == row['features_sha256']
                        and f.get('action_watermark') == row['action_watermark']
                        and f.get('accepted_target_tokens') == row['usage_watermark']
                        and f['monotonic'] <= row['monotonic'] + TIME_TOLERANCE_NS / 1e9]
            _need(matching, 'enqueue_without_exact_frozen_features')
            tickets[arrival] = row
            ticket_freezes[arrival] = matching[-1]
        elif event in ('admit', 'begin', 'settle', 'abort', 'first_service', 'failed_exchange_settled'):
            lease_id, arrival = row.get('lease_id'), row.get('arrival')
            _need(type(lease_id) is int and lease_id > 0 and type(arrival) is int
                  and arrival in tickets, 'lease_without_ticket')
            ticket = tickets[arrival]
            fixed = ('session_id', 'arrival', 'binding_sha256', 'features_sha256', 'model_sha256',
                     'episode_id', 'action_watermark', 'usage_watermark', 'frozen_multiplier')
            _need(all(row.get(k) == ticket.get(k) for k in fixed), 'lease_ticket_changed')
            if event == 'admit':
                _need(lease_id not in leases, 'duplicate_lease')
                leases[lease_id] = dict(ticket=ticket, frozen=ticket_freezes[arrival], admit=row, services=[])
            else:
                _need(lease_id in leases and leases[lease_id]['ticket'] is ticket, 'lease_owner_changed')
                lease = leases[lease_id]
                if event == 'begin':
                    _need('begin' not in lease and 'end' not in lease, 'duplicate_or_late_begin')
                    lease['begin'] = row
                elif event in ('settle', 'abort'):
                    _need('begin' in lease and 'end' not in lease, 'unbegun_or_duplicate_settlement')
                    lease['end'] = row
                else:
                    lease['services'].append(row)
    _need(registered == 1 and set(bindings) == set(planned), 'full_planned_binding_missing')
    return bindings, leases


def reconcile_reset_prefix(prefix_rows, *, queue_rows, host_rows, planned,
                           allocation_sha256, predecessor_solver_sha256,
                           successor_solver_sha256, start_ns, cutoff_ns, initial_rows=()):
    """Return prefix-specific integrity/feasibility; never replace old gates.

    Inputs are decoded rows (duplicate-key/size checks belong to the caller).
    Full planned inventory and actual initial receipts are required. Valid
    no-chat/refusal evidence is retained with capacity_feasible=False. Partial,
    unknown or contradictory evidence raises PrefixIntegrityError.
    """
    _need(type(planned) is list and len(planned) >= 2
          and all(_identifier(s) for s in planned) and len(set(planned)) == len(planned), 'planned_inventory')
    _need(all(_sha(v) for v in (allocation_sha256, predecessor_solver_sha256, successor_solver_sha256))
          and (predecessor_solver_sha256, successor_solver_sha256) in SOURCE_PAIRS.values(), 'source_or_allocation_pin')
    _need(_count(start_ns) and _count(cutoff_ns) and start_ns < cutoff_ns, 'interval_schema')
    _need(type(prefix_rows) in (list, tuple) and type(host_rows) in (list, tuple)
          and type(queue_rows) in (list, tuple) and type(initial_rows) in (list, tuple), 'row_container_schema')
    bindings, leases = _queue(queue_rows, planned, allocation_sha256)
    hosts = _host(host_rows, bindings, initial_rows)
    reverse = {pair: sid for sid, pair in bindings.items()}
    automatic = {(pair, key): action for pair, host in hosts.items() for key, action in host['actions'].items()
                 if action['dispatch'].get('automatic') is True}
    _need(all(a['dispatch']['action'] == 'RESET' for a in automatic.values()), 'automatic_non_reset')
    seen, busy, first, ordinals, binding_hashes = set(), {}, {}, set(), {}
    counts = dict(admitted=0, body_finished=0, logical_reuse=0, refused=0, aborted=0)
    last_ns, arm, feasible = -1, None, True

    def watermark(pair, value, at):
        _need(type(value) is dict and set(value) == WATERMARKS
              and _sha(value.get('binding_sha256')) and _sha(value.get('public_observation_sha256'))
              and all(_count(value.get(k)) for k in WATERMARKS - {'binding_sha256', 'public_observation_sha256'}),
              'watermark_schema')
        digest = value['binding_sha256']
        _need(binding_hashes.setdefault(pair, digest) == digest, 'binding_digest_changed')
        matches = [s for s in hosts[pair]['states'] if s[0] <= at + TIME_TOLERANCE_NS
                   and all(s[1][k] == value[k] for k in s[1])]
        _need(matches, 'watermark_not_actual_settled_host_state')
        _need(not any(begin < at - TIME_TOLERANCE_NS and end > at + TIME_TOLERANCE_NS
                      for begin, end in hosts[pair]['pending_intervals']), 'watermark_inside_pending_exchange')
        # A matched earlier state cannot conceal a later completed host change.
        _need(not any(s[0] < at - TIME_TOLERANCE_NS and s[4] > matches[-1][4]
                      for s in hosts[pair]['states']), 'stale_host_watermark')
        return matches[-1]

    def lease_for(pair, lease_id, at, value=None):
        _need(type(lease_id) is int and lease_id > 0, 'prefix_lease_id_schema')
        lease = leases.get(lease_id)
        _need(lease is not None and 'begin' in lease and 'end' in lease
              and lease['ticket']['session_id'] == reverse[pair]
              and lease['ticket']['episode_id'] == hosts[pair]['owner']['action_episode']
              and round(lease['begin']['monotonic'] * 1e9) <= at + TIME_TOLERANCE_NS
              and at <= round(lease['end']['monotonic'] * 1e9) + TIME_TOLERANCE_NS,
              'prefix_outside_actual_begun_owned_lease')
        if value is not None:
            _need(value['binding_sha256'] == lease['ticket']['binding_sha256'], 'prefix_gate_binding_digest')
        return lease

    for sequence, row in enumerate(prefix_rows, 1):
        _need(type(row) is dict and type(row.get('event')) is str and row['event'] in EXTRAS
              and set(row) == BASE | EXTRAS[row['event']], 'prefix_exact_schema')
        event, at = row['event'], row['monotonic_ns']
        _need(type(row['schema_version']) is int and row['schema_version'] == 1
              and row['namespace'] == 'automatic-reset-prefix-v1'
              and type(row['sequence']) is int and row['sequence'] == sequence
              and _finite(row['monotonic']) and _count(at) and round(row['monotonic'] * 1e9) == at
              and at >= last_ns and at + TIME_TOLERANCE_NS >= start_ns
              and row['policy_sha256'] == POLICY_SHA256
              and row['predecessor_solver_sha256'] == predecessor_solver_sha256
              and row['successor_solver_sha256'] == successor_solver_sha256
              and type(row['arm']) is str and row['arm'] in SOURCE_PAIRS
              and SOURCE_PAIRS[row['arm']] == (predecessor_solver_sha256, successor_solver_sha256),
              'prefix_sequence_clock_policy_or_source')
        arm = arm or row['arm']
        _need(row['arm'] == arm, 'mixed_arm_journal')
        last_ns = at
        _need(_identifier(row['run_id']) and _identifier(row['session_id']), 'prefix_owner_identity')
        pair = (row['run_id'], row['session_id'])
        _need(pair in hosts and row['action_episode'] == hosts[pair]['owner']['action_episode'], 'prefix_owner_identity')
        counts[event] += 1
        if event in ('body_finished', 'logical_reuse', 'aborted'):
            _need(type(row['after']) is dict and set(row['after']) == WATERMARKS,
                  'watermark_schema')
        if event == 'admitted':
            _need(pair not in busy and type(row['prefix']) is bool and _count(row['cause_ordinal'])
                  and row['cause_ordinal'] > 0 and row['cause_ordinal'] not in ordinals
                  and _finite(row['cause_monotonic'])
                  and round(row['cause_monotonic'] * 1e9) <= at
                  and at < cutoff_ns, 'duplicate_cause_or_late_admitted')
            ordinals.add(row['cause_ordinal'])
            value = row['before']
            actual = watermark(pair, value, at)
            lease = lease_for(pair, row['lease_id'], at, value)
            _need(row['features_sha256'] == lease['ticket']['features_sha256']
                  and row['allocation_sha256'] == allocation_sha256, 'prefix_frozen_allocation_mismatch')
            if row['prefix']:
                _need(pair not in first and row['cause'] in ('warmup_claim', 'first_public_game_over')
                      and all(value[k] == 0 for k in WATERMARKS - {'binding_sha256', 'public_observation_sha256'})
                      and lease['ticket']['action_watermark'] == lease['ticket']['usage_watermark'] == 0
                      and lease['frozen']['logical_sequence'] == 0,
                      'not_first_zero_watermark_prefix')
                first[pair] = dict(admitted=row, phase='admitted')
            else:
                _need(row['cause'] in ('warmup_claim', 'public_game_over') and value['logical_sequence'] >= 1,
                      'tail_without_real_logical_sequence')
                logical = hosts[pair]['logicals'].get(value['logical_sequence'])
                _need(logical and 'finish' in logical
                      and lease['frozen']['logical_sequence'] == value['logical_sequence'] - 1
                      and logical['finish']['monotonic_ns'] <= at + TIME_TOLERANCE_NS
                      and round(lease['begin']['monotonic'] * 1e9) <= logical['start']['monotonic_ns'] + TIME_TOLERANCE_NS,
                      'tail_without_current_complete_logical_lease')
            if row['cause'] in ('first_public_game_over', 'public_game_over'):
                _need(actual[2] == 'GAME_OVER' and actual[3] != 'RESET', 'game_over_not_actual_public_state')
            busy[pair] = row
        elif event == 'body_finished':
            admitted = busy.pop(pair, None)
            _need(admitted is not None and row['prefix'] is admitted['prefix']
                  and row['lease_id'] == admitted['lease_id'], 'body_without_exact_admission')
            before, after = admitted['before'], row['after']
            watermark(pair, after, at)
            lease_for(pair, row['lease_id'], at, after)
            _need(after['binding_sha256'] == before['binding_sha256']
                  and all(after[k] == before[k] for k in ('accepted_target_tokens', 'logical_sequence'))
                  and all(after[k] == before[k] + 1 for k in ('action_sequence', 'sdk_calls_executed', 'taaf_history_commits')),
                  'body_not_exactly_one_reset')
            _need(_identifier(row['transition_id']) and _identifier(row['commitment_id']), 'body_action_identity')
            key = (row['transition_id'], row['commitment_id'])
            action = automatic.get((pair, key))
            _need(action is not None and (pair, key) not in seen
                  and admitted['monotonic_ns'] <= action['dispatch']['monotonic_ns'] + TIME_TOLERANCE_NS
                  and action['dispatch']['monotonic_ns'] < cutoff_ns
                  and action['receipt']['monotonic_ns'] <= at + TIME_TOLERANCE_NS,
                  'body_missing_actual_automatic_reset_or_late_dispatch')
            seen.add((pair, key))
            if admitted['prefix']:
                first[pair].update(body=row, phase='body_finished')
        elif event == 'logical_reuse':
            record = first.get(pair)
            _need(record is not None and record['phase'] == 'body_finished'
                  and row['purpose'] in ('main', 'summary')
                  and row['after'] == record['body']['after'] and row['after']['logical_sequence'] == 0
                  and row['lease_id'] == record['admitted']['lease_id']
                  and row['features_sha256'] == record['admitted']['features_sha256']
                  and row['allocation_sha256'] == allocation_sha256, 'invalid_sequence_zero_reuse')
            watermark(pair, row['after'], at)
            lease = lease_for(pair, row['lease_id'], at, row['after'])
            logical = hosts[pair]['logicals'].get(1)
            if logical is not None:
                _need(logical['start']['purpose'] == row['purpose']
                      and at <= logical['start']['monotonic_ns'] + TIME_TOLERANCE_NS
                      and logical['start']['monotonic_ns'] <= round(lease['end']['monotonic'] * 1e9) + TIME_TOLERANCE_NS
                      and lease['end']['event'] == 'settle'
                      and lease['end'].get('completed_successfully') is logical['finish']['succeeded'],
                      'reuse_without_actual_main_or_summary_start')
            # The real bridge rechecks stop after this callback. It can refuse
            # before logical_request_started; only a later source abort makes
            # that complete journal valid, and it remains capacity-infeasible.
            record['reuse_without_start'] = logical is None
            record['phase'] = 'reused'
        elif event == 'refused':
            _need(row['reason'] == 'host_stop' and type(row['prefix']) is bool, 'refusal_schema')
            admitted = busy.pop(pair, None)
            if admitted is not None:
                _need(row['prefix'] is admitted['prefix']
                      and not any(a['dispatch']['monotonic_ns'] >= admitted['monotonic_ns'] - TIME_TOLERANCE_NS
                                  and a['dispatch']['monotonic_ns'] <= at + TIME_TOLERANCE_NS
                                  for a in hosts[pair]['actions'].values()), 'refusal_after_actual_dispatch')
                if admitted['prefix']:
                    first[pair]['phase'] = 'refused'
            else:
                _need(row['prefix'] is False, 'refusal_prefix_without_admission')
            feasible = False
        elif event == 'aborted':
            record = first.get(pair)
            _need(record is not None and record['phase'] in ('body_finished', 'refused', 'reused')
                  and row['lease_id'] == record['admitted']['lease_id']
                  and row['reason'] == 'no_real_logical_request'
                  and row['successful_service'] is False and row['capacity_feasible'] is False
                  and row['after']['logical_sequence'] == 0 and not hosts[pair]['logicals'], 'invalid_no_chat_abort')
            watermark(pair, row['after'], at)
            lease = lease_for(pair, row['lease_id'], at, row['after'])
            _need(lease['end']['event'] == 'abort' and not lease['services'], 'no_chat_earned_service_or_settled')
            record['phase'] = 'aborted'
            feasible = False
    _need(not busy, 'incomplete_automatic_body')
    _need(seen == set(automatic), 'automatic_reset_missing_prefix_body_evidence')
    _need(all(r['phase'] in ('reused', 'aborted') for r in first.values()), 'prefix_missing_reuse_or_abort')
    _need(not any(r['phase'] == 'reused' and r.get('reuse_without_start') for r in first.values()),
          'reuse_without_actual_main_or_summary_start')
    return dict(schema_version=1, integrity_pass=True, capacity_feasible=feasible,
                prefix_source_sha256=PREFIX_SOURCE_SHA256, policy_sha256=POLICY_SHA256,
                planned_workers=len(planned), automatic_resets=len(automatic),
                first_prefixes=len(first), event_counts=counts,
                tolerance_ns=TIME_TOLERANCE_NS, original_initial_host_queue_gates_still_required=True)

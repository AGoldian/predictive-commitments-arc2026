# SPDX-License-Identifier: MIT-0
"""Validate the reviewed governor's additive journal before queue projection.

This is an evidence parser, not a governor or a capacity/usage/cleanup verifier.
It never edits input records. The unchanged queue replay must still validate
every projected row, and external supervisor evidence remains a separate gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import re


GOVERNOR_SOURCE_SHA256 = '3cb63ac4dae7c69ec62a38d3eb7de84710d292774d1dded3e44799213c3fd26d'
_BASE = {'schema_version', 'event', 'monotonic'}
_PREFIX = 'governor_v2_'
_FIELDS = {
    'started': set(),
    'stop_requested': {'origin', 'first_stop_monotonic', 'drain_end_monotonic'},
    'outer_cancel_observed': {'count'},
    'inner_cancel_requested': {'count'},
    'inner_task_done_observed': set(),
    'physical_closure_observed': set(),
    'join_finished': {'disposition', 'inner_done', 'physical_closure_observed', 'hard_stop_attempted'},
}
_MANUAL_FIELDS = {
    'common_fleet_started': {'config_sha256', 'allocation_sha256', 'workers'},
    'planned_session_bound': {'planned_session_id', 'accounting_session_id', 'run_id'},
    'physical_worker_started': {'planned_session_id'},
    'physical_worker_finished': {'planned_session_id'},
    'planned_session_closed': {'planned_session_id', 'censored', 'action_watermark', 'accepted_target_tokens'},
    'admission_deadline_reached': set(),
    'boundary_frozen': {'planned_session_id', 'features_sha256', 'allocation_sha256',
        'baseline_snapshot_sha256', 'features', 'priority_snapshot', 'logical_sequence',
        'action_watermark', 'accepted_target_tokens', 'frozen_multiplier'},
}
_CONFIG_FIELDS = {'planned_session_ids', 'capacity', 'arm', 'worker_ready_timeout_s',
    'admission_deadline_monotonic', 'drain_timeout_s', 'teardown_reserve_s', 'whole_deadline_monotonic'}
_REGISTRATION_FIELDS = {'sequence', 'capacity', 'planned_sessions', 'active_count',
    'active_sessions', 'queue_count', 'queue_sessions', 'bootstrap_complete', 'uncontended_control'}
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_STOP_ORIGINS = {'shared_stop', 'admission_deadline', 'outer_cancel', 'inner_done_physical_pending'}


class GovernorTraceError(ValueError):
    """Fixed, payload-free refusal code; original evidence stays with the caller."""


def _need(condition, code):
    if not condition:
        raise GovernorTraceError(code)


def _number(value, *, positive=False):
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and (value > 0 if positive else value >= 0))
    except (OverflowError, TypeError, ValueError):
        return False


def _integer(value, *, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0)


def _text(value):
    return type(value) is str and 0 < len(value) <= 128


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def _schema(row, fields):
    _need(set(row) == _BASE | fields and type(row['schema_version']) is int
          and row['schema_version'] == 1 and _number(row['monotonic']), 'unsupported_event_schema')


def validate_governor_trace(rows, *, config, governor_source_sha256):
    """Return original row references only after one successful governor join.

    ``config`` is the exact JSON allocation manifest's ``config`` object, not a
    reconstructed subset. Only this pinned producer is supported. Unknown
    non-governor labels remain in ``queue_rows`` for the unchanged queue parser
    to reject. A drained cutoff can pass this component while the numerical
    queue replay still refuses censorship, missing service or other failures.

    Manual journal insertion order is not a global clock order: clocks are
    captured before the journal lock. Governor events have their own single
    event-loop producer order; each physical owner's lifecycle is joined
    separately. Owner-close and finish journaling may follow closure observation
    because each source state mutation precedes its record. Both complete
    records must be present by the successful join; host-ledger lifetime joins
    remain the unchanged queue replay's responsibility.
    """
    _need(type(governor_source_sha256) is str and governor_source_sha256 == GOVERNOR_SOURCE_SHA256,
          'unsupported_governor_source')
    _need(type(config) is dict and set(config) == _CONFIG_FIELDS, 'unsupported_config_schema')
    planned = config['planned_session_ids']
    _need(type(planned) is list and len(planned) >= 2 and all(_text(s) for s in planned)
          and len(set(planned)) == len(planned), 'invalid_planned_roster')
    _need(_integer(config['capacity'], positive=True) and config['capacity'] < len(planned)
          and type(config['arm']) is str and config['arm'] in {'B0', 'B1', 'A1', 'P'}, 'invalid_common_config')
    _need(all(_number(config[k], positive=True) for k in _CONFIG_FIELDS
              - {'planned_session_ids', 'capacity', 'arm'}), 'invalid_common_clock_config')
    admission = float(config['admission_deadline_monotonic'])
    drain = float(config['drain_timeout_s'])
    whole = float(config['whole_deadline_monotonic'])
    teardown = float(config['teardown_reserve_s'])
    _need(admission + drain + teardown <= whole, 'missing_fixed_deadline_reserves')
    config_sha = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'),
                                           allow_nan=False).encode()).hexdigest()
    _need(type(rows) in (list, tuple) and bool(rows), 'missing_admission_rows')
    queue_rows, governor_rows, events, manual = [], [], {}, {}
    roster = {s: {} for s in planned}
    positions = {}
    registered = []
    for index, row in enumerate(rows):
        _need(type(row) is dict and type(row.get('event')) is str, 'unsupported_admission_row')
        name = row['event']
        if name.startswith(_PREFIX):
            event = name[len(_PREFIX):]
            _need(event in _FIELDS, 'unsupported_or_failed_governor_event')
            _schema(row, _FIELDS[event])
            governor_rows.append(row)
            events.setdefault(event, []).append(row)
            positions[id(row)] = index
            continue
        queue_rows.append(row)
        _need(name not in {'planned_session_censored', 'physical_drain_failed'}, 'failed_coordinator_trace')
        if name == 'fleet_registered':
            registered.append((index, row))
        if name not in _MANUAL_FIELDS:
            continue
        _schema(row, _MANUAL_FIELDS[name])
        manual.setdefault(name, []).append(row)
        positions[id(row)] = index
        if 'planned_session_id' in row:
            sid = row['planned_session_id']
            _need(type(sid) is str and sid in roster, 'foreign_planned_owner')
            if name != 'boundary_frozen':
                _need(name not in roster[sid], 'duplicate_owner_event')
                roster[sid][name] = row
        if name == 'planned_session_bound':
            _need(_text(row['run_id']) and _text(row['accounting_session_id']), 'invalid_host_binding')
        elif name == 'planned_session_closed':
            _need(row['censored'] is False and _integer(row['action_watermark'])
                  and _integer(row['accepted_target_tokens']), 'invalid_or_censored_host_close')
        elif name == 'boundary_frozen':
            _need(all(_hash(row[k]) for k in ('features_sha256', 'allocation_sha256',
                      'baseline_snapshot_sha256')) and type(row['features']) is dict
                  and type(row['priority_snapshot']) is dict
                  and all(_integer(row[k]) for k in ('logical_sequence', 'action_watermark',
                                                    'accepted_target_tokens'))
                  and _number(row['frozen_multiplier'], positive=True), 'invalid_boundary_schema')
    _need(all(len(events.get(name, [])) == 1 for name in
        ('started', 'inner_task_done_observed', 'physical_closure_observed', 'join_finished')),
        'missing_or_duplicate_governor_completion')
    _need(len(events.get('stop_requested', [])) <= 1 and len(events.get('inner_cancel_requested', [])) <= 1,
          'duplicate_stop_or_inner_cancel')
    _need(all(a['monotonic'] <= b['monotonic'] for a, b in zip(governor_rows, governor_rows[1:])),
          'governor_producer_clock_decreased')
    started, done, closure, joined = [events[name][0] for name in
        ('started', 'inner_task_done_observed', 'physical_closure_observed', 'join_finished')]
    at = lambda row: row['monotonic']
    pos = lambda row: positions[id(row)]
    _need(pos(started) < pos(done) < pos(joined) and pos(started) < pos(closure) < pos(joined),
          'invalid_governor_completion_order')
    _need(type(joined['disposition']) is str and joined['disposition'] == 'physically_closed'
          and joined['inner_done'] is True
          and joined['physical_closure_observed'] is True and joined['hard_stop_attempted'] is False,
          'unsuccessful_governor_join')
    _need(len(manual.get('common_fleet_started', [])) == 1 and len(registered) == 1,
          'missing_or_duplicate_common_start')
    common = manual['common_fleet_started'][0]
    registration_index, registration = registered[0]
    _schema(registration, _REGISTRATION_FIELDS)
    _need(type(registration['sequence']) is int and registration['sequence'] == 1
          and type(registration['planned_sessions']) is list and registration['planned_sessions'] == planned
          and type(registration['capacity']) is int and registration['capacity'] == config['capacity']
          and type(registration['active_count']) is int and registration['active_count'] == 0
          and type(registration['queue_count']) is int and registration['queue_count'] == 0
          and type(registration['active_sessions']) is list and registration['active_sessions'] == []
          and type(registration['queue_sessions']) is list and registration['queue_sessions'] == []
          and registration['bootstrap_complete'] is False and registration['uncontended_control'] is False,
          'fleet_registration_config_mismatch')
    _need(_hash(common['config_sha256']) and common['config_sha256'] == config_sha
          and _hash(common['allocation_sha256'])
          and type(common['workers']) is int and common['workers'] == len(planned), 'common_config_join_failed')
    _need(registration_index < pos(common) < pos(started)
          and registration['monotonic'] <= at(common) <= at(started) < admission,
          'common_start_clock_or_order_mismatch')
    binding_pairs = set()
    for owner in roster.values():
        _need(set(owner) == {'physical_worker_started', 'planned_session_bound',
              'planned_session_closed', 'physical_worker_finished'}, 'incomplete_planned_owner_lifecycle')
        begin, bound, close, finish = [owner[name] for name in ('physical_worker_started',
            'planned_session_bound', 'planned_session_closed', 'physical_worker_finished')]
        _need(pos(started) < pos(begin) < pos(bound) < pos(close) < pos(finish) < pos(joined)
              and at(started) <= at(begin) <= at(bound) <= at(close) <= at(finish) <= at(joined),
              'owner_lifecycle_outside_physical_join')
        pair = (bound['run_id'], bound['accounting_session_id'])
        _need(pair not in binding_pairs, 'duplicate_host_binding')
        binding_pairs.add(pair)
    _need(len({p[0] for p in binding_pairs}) == len(planned)
          and len({p[1] for p in binding_pairs}) == len(planned), 'nonbijective_host_bindings')
    deadline_rows = manual.get('admission_deadline_reached', [])
    _need(len(deadline_rows) <= 1 and all(at(row) >= admission for row in deadline_rows),
          'invalid_admission_deadline_observation')
    stop = events.get('stop_requested', [None])[0]
    outer = events.get('outer_cancel_observed', [])
    inner = events.get('inner_cancel_requested', [])
    _need(all(type(row['count']) is int and row['count'] == count
              for count, row in enumerate(outer, 1)), 'outer_cancel_count_mismatch')
    _need(not inner or type(inner[0]['count']) is int and inner[0]['count'] == 1,
          'inner_cancel_count_mismatch')
    origin, first_stop, end = None, None, admission + drain
    if stop is None:
        _need(not inner and not outer and at(done) < admission
              and at(closure) < admission, 'missing_governor_stop')
    else:
        origin, first_stop, end = stop['origin'], stop['first_stop_monotonic'], stop['drain_end_monotonic']
        _need(type(origin) is str and origin in _STOP_ORIGINS and _number(first_stop)
              and _number(end), 'invalid_governor_stop')
        _need(at(common) <= first_stop <= at(stop) and first_stop < end
              and end == min(first_stop + drain, admission + drain, whole - teardown),
              'fixed_drain_bound_mismatch')
        _need(all(pos(stop) < pos(row) for row in (*inner, *outer)), 'cancel_without_prior_stop')
        if origin == 'admission_deadline':
            _need(first_stop >= admission, 'premature_admission_stop')
        elif origin == 'outer_cancel':
            _need(bool(outer), 'missing_originating_outer_cancel')
        elif origin == 'inner_done_physical_pending':
            _need(pos(done) < pos(stop) < pos(closure) and not inner, 'invalid_inner_done_stop')
        if inner:
            _need(pos(started) < pos(inner[0]) < pos(done), 'inner_cancel_after_done')
    _need(at(joined) < end and all(at(row) < end for row in governor_rows)
          and at(joined) < whole - teardown, 'governor_completion_outside_fixed_bound')
    # Only deferred outer cancellation can add records after drive's final row.
    _need(all(row['event'] in {_PREFIX+'stop_requested', _PREFIX+'outer_cancel_observed'}
              for row in governor_rows if pos(row) > pos(joined)), 'governor_work_after_join')
    return {'queue_rows': queue_rows, 'governor_rows': governor_rows, 'summary': {
        'schema_version': 1, 'governor_source_sha256': GOVERNOR_SOURCE_SHA256,
        'config_sha256': config_sha, 'planned_session_ids': list(planned),
        'governor_started_monotonic': at(started), 'inner_done_monotonic': at(done),
        'physical_closure_monotonic': at(closure), 'join_finished_monotonic': at(joined),
        'first_stop_origin': origin, 'first_stop_monotonic': first_stop,
        'fixed_drain_end_monotonic': None if stop is None else end,
        'inner_cancel_count': len(inner), 'outer_cancel_count': len(outer),
        'disposition': 'physically_closed', 'planned_owner_lifecycles_joined': len(roster),
        'numerical_capacity_validated': False, 'external_cleanup_validated': False,
        'startup_clock_origin_exported': False,
    }}

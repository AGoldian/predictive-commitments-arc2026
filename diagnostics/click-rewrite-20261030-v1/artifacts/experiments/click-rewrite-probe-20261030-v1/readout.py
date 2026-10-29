# SPDX-License-Identifier: MIT-0
"""First root data-only assessment; no learner/interpreter/SDK imports."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
RUN = ROOT / 'run'


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


frozen = read(ROOT / 'precall-source.json')
request = read(RUN / 'request.json')
assert request['source'] == frozen['source']
assert request['config_sha256'] == frozen['config_sha256'] == sha(RUN / 'frozen-config.json')
assert request['protocol_sha256'] == frozen['protocol_sha256'] == sha(RUN / 'frozen-protocol.md')
config = read(RUN / 'frozen-config.json')
assert sha(ROOT / 'input-prefix.json') == config['prefix']['sha256']
slots, fitted, commitment, inputs, worker, parent = (read(RUN / p) for p in
    ('slots.json', 'fitted.json', 'commitment.json', 'comparison-input.json', 'worker-result.json', 'parent-result.json'))
assert len(slots) == 7 and [s['slot'] for s in slots] == list(range(1, 8))
assert [c['id'] for c in fitted['candidates']] == [p['candidate_id'] for p in commitment['forecasts']]
assert sha(RUN / 'commitment.json') == slots[6]['commitment_sha256'] == inputs['commitment_sha256']
assert slots[6]['action'] == commitment['action']
prefix = read(ROOT / 'input-prefix.json')['records']
for index, slot in enumerate(slots):
    assert slot['status'] == 'observed'
    path = RUN / ('observation-%02d.json' % (index + 1))
    assert sha(path) == slot['observation_sha256']
    obs = read(path)
    if index < 6:
        expected = prefix[index]['public']
        dense = [[v for v, n in row for _ in range(n)] for row in expected['last_grid_rle']]
        assert obs['frame'][-1] == dense
        assert all(obs[k] == expected[k] for k in ('state', 'levels_completed', 'available_actions'))
        assert slot['action'] == prefix[index]['action']
    if index:
        previous = read(RUN / ('observation-%02d.json' % index))
        assert slot['action']['action_id'] == 6 and 6 in previous['available_actions']
assert inputs['before'] == read(RUN / 'observation-06.json')
assert inputs['after'] == read(RUN / 'observation-07.json')
a, b = inputs['before']['frame'][-1], inputs['after']['frame'][-1]
assert inputs['before']['levels_completed'] == inputs['after']['levels_completed']
assert len(a) == len(b) and [len(r) for r in a] == [len(r) for r in b]
changed = {(r, c) for r, row in enumerate(b) for c, v in enumerate(row) if v != a[r][c]}
report = {'scope': 'one prospectively predicted exposed public DEV transition; no efficacy or generalization',
          'source': request['source'], 'action': commitment['action'], 'actual_changed_pixels': len(changed),
          'candidates': [], 'common_cell_witness_outcomes': [], 'unknown_metadata': commitment['all_unclaimed_cells_and_metadata']}
classes = {}
rows = {}
for item in commitment['forecasts']:
    pred = item['prediction']
    cells = pred['forecast']
    assert len({(v['row'], v['col']) for v in cells}) == len(cells)
    assert all(0 <= v['row'] < len(b) and 0 <= v['col'] < len(b[0]) for v in cells)
    wrong = [v for v in cells if b[v['row']][v['col']] != v['value']]
    correct_changed = [v for v in cells if (v['row'], v['col']) in changed and b[v['row']][v['col']] == v['value']]
    wrong_changed = [v for v in wrong if (v['row'], v['col']) in changed]
    key = json.dumps(cells, sort_keys=True, separators=(',', ':')) if cells else 'ABSTENTION'
    classes.setdefault(key, []).append(item['candidate_id'])
    row = {'candidate_id': item['candidate_id'], 'status': pred['status'], 'known_cells': len(cells),
           'correct_cells': len(cells) - len(wrong), 'wrong_cells': len(wrong),
           'correct_changed_cells': len(correct_changed), 'wrong_changed_cells': len(wrong_changed),
           'unclaimed_grid_cells': len(b) * len(b[0]) - len(cells),
           'fully_consistent_on_known_claims': pred['status'] == 'supported' and bool(cells) and not wrong,
           'reason': pred['reason'], 'unknown_reason_counts': pred['unknown_reason_counts']}
    rows[item['candidate_id']] = row
    report['candidates'].append(row)
for pair in commitment['disagreements']:
    left, right = rows[pair['left']], rows[pair['right']]
    outcomes = []
    for witness in pair['witnesses']:
        actual = b[witness['row']][witness['col']]
        assert witness['left'] != witness['right']
        outcomes.append(dict(witness, actual=actual,
            left_matches=actual == witness['left'], right_matches=actual == witness['right']))
    report['common_cell_witness_outcomes'].append({'left': pair['left'], 'right': pair['right'], 'witnesses': outcomes})
consistent = {name for name, row in rows.items() if row['fully_consistent_on_known_claims']}
discriminated = set()
for pair in report['common_cell_witness_outcomes']:
    if pair['left'] in consistent and any(v['left_matches'] and not v['right_matches'] for v in pair['witnesses']):
        discriminated.add(pair['left'])
    if pair['right'] in consistent and any(v['right_matches'] and not v['left_matches'] for v in pair['witnesses']):
        discriminated.add(pair['right'])
dynamic = {name for name in discriminated if rows[name]['correct_changed_cells'] > 0}
report.update(behavioral_classes=[{'candidate_ids': names, 'abstention': key == 'ABSTENTION'} for key, names in classes.items()],
    consistent_candidate_ids=sorted(consistent), primary_discrimination_passed=bool(discriminated),
    dynamic_nonvacuity_passed=bool(dynamic), both_frozen_criteria_passed=bool(dynamic),
    surviving_behavioral_forecast_classes=sum(any(name in consistent for name in names) for names in classes.values()),
    no_unique_mechanism_identified=len(consistent) != 1,
    prefix_projection_matches=worker['prefix_matched_slots'], observed_actions=worker['observed_actions'],
    native_fit_calls=worker['native_fit_calls'], native_forecast_calls=worker['native_forecast_calls'], LLM_calls=worker['LLM_calls'],
    parent_receipt=parent, worker_wall_seconds=worker['wall_seconds'], worker_cpu_seconds=worker['process_cpu_seconds'],
    maxrss_native_units=worker['maxrss_native_units'], maxrss_unit=worker['maxrss_unit'], final_public_state=worker['final_public_state'])
assert worker['status'] == 'completed' and worker['failure'] is None and worker['prefix_matched_slots'] == 6
assert worker['observed_actions'] == 7 and worker['native_fit_calls'] == 1 and worker['native_forecast_calls'] == 6
assert parent['returncode'] == 0 and not parent['timed_out']
(ROOT / 'readout.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('source', 'common_cell_witness_outcomes', 'candidates', 'parent_receipt')}))

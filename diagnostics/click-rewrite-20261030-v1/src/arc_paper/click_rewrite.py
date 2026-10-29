# SPDX-License-Identifier: MIT-0
"""Bounded, one-pair click-conditioned mask hypotheses from public pixels.

fit(records): 2..6 consecutive records; record[i].action caused record[i].public.
Public grids use ``grid`` or lossless ``last_grid_rle``. The first qualifying
transition supplies all mechanism parameters; no later frame is examined.
Return status fitted/no_qualifying_transition, all candidates, control,
selected_transition, source_pair (two dense grids/action/hash), and unknowns.
Invalid schemas/bounds raise ClickRewriteError; no target code is executed.

predict(candidate, grid, action): status supported/unsupported, forecast as
[{row,col,value}], next_mask, reason, and unknown_reason_counts. Any unresolved
destination rejects the WHOLE forecast, including vacated-background claims.
choose_probe(fitted, grid, used_actions): first row/column-sorted four-neighbor
interior control pixel absent from supplied prior clicks, or None. Prediction
alone knows the training click; the caller supplies complete prior click
history to choose_probe. Neither function mutates or remembers trials.

These are hand-written hypotheses, not recovered truth, goal inference or
evidence of click-position invariance. All unforecast pixels/metadata are unknown.
"""
from collections import deque
import hashlib
import json

MAX_SIDE, MAX_RECORDS, MAX_CANDIDATES = 128, 6, 10
D4 = tuple(sorted(((a, b), (c, d))
                  for a, b, c, d in ((1, 0, 0, 1), (1, 0, 0, -1),
                                     (-1, 0, 0, 1), (-1, 0, 0, -1),
                                     (0, 1, 1, 0), (0, 1, -1, 0),
                                     (0, -1, 1, 0), (0, -1, -1, 0))))
UNKNOWN = ["other_grid_pixels", "state", "levels_completed", "available_actions",
           "goal", "other_clicks", "click_position_invariance_is_a_hypothesis"]
BOUNDS = {"maximum_side": MAX_SIDE, "maximum_records": MAX_RECORDS,
          "maximum_candidates": MAX_CANDIDATES, "signed_permutation_matrices": 8}


class ClickRewriteError(ValueError):
    pass


def _need(condition, reason):
    if not condition:
        raise ClickRewriteError(reason)


def _grid(value):
    _need(type(value) is list and 1 <= len(value) <= MAX_SIDE and
          type(value[0]) is list and 1 <= len(value[0]) <= MAX_SIDE, "grid_bounds")
    width = len(value[0])
    _need(all(type(row) is list and len(row) == width and
              all(type(v) is int and 0 <= v <= 255 for v in row) for row in value), "grid_values")
    return [row[:] for row in value]


def _record_grid(record):
    _need(type(record) is dict and type(record.get("public")) is dict, "public_record")
    public, decoded = record["public"], None
    if "last_grid_rle" in public:
        rows = public["last_grid_rle"]
        _need(type(rows) is list and 1 <= len(rows) <= MAX_SIDE, "rle_height")
        decoded = []
        for runs in rows:
            _need(type(runs) is list and 1 <= len(runs) <= MAX_SIDE, "rle_row")
            row = []
            for run in runs:
                _need(type(run) is list and len(run) == 2 and
                      type(run[0]) is int and 0 <= run[0] <= 255 and
                      type(run[1]) is int and 1 <= run[1] <= MAX_SIDE and
                      len(row) + run[1] <= MAX_SIDE, "rle_run")
                row.extend([run[0]] * run[1])
            decoded.append(row)
        decoded = _grid(decoded)
    if "grid" in public:
        dense = _grid(public["grid"])
        _need(decoded is None or dense == decoded, "dense_rle_disagree")
        return dense
    _need(decoded is not None, "public_grid_required")
    return decoded


def _action(value, grid):
    _need(type(value) is dict and set(value) == {"action_id", "data"} and
          type(value["action_id"]) is int and 0 <= value["action_id"] <= 7 and
          type(value["data"]) is dict, "action_schema")
    data = value["data"]
    if value["action_id"] == 6:
        _need(set(data) == {"x", "y"} and all(type(v) is int for v in data.values()) and
              0 <= data["x"] < len(grid[0]) and 0 <= data["y"] < len(grid), "click_bounds")
    else:
        _need(data == {}, "ordinary_action_data")
    return {"action_id": value["action_id"], "data": dict(data)}


def _neighbors(point):
    r, c = point
    return ((r - 1, c), (r, c - 1), (r, c + 1), (r + 1, c))


def _component(grid, point):
    color, seen, queue = grid[point[0]][point[1]], {point}, deque([point])
    while queue:
        for r, c in _neighbors(queue.popleft()):
            if (0 <= r < len(grid) and 0 <= c < len(grid[0]) and (r, c) not in seen
                    and grid[r][c] == color):
                seen.add((r, c)); queue.append((r, c))
    return seen


def _mask(grid, color):
    return {(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v == color}


def _points(mask):
    return [list(p) for p in sorted(mask)]


def _transform(mask, matrix, translation=(0, 0)):
    return {(matrix[0][0] * r + matrix[0][1] * c + translation[0],
             matrix[1][0] * r + matrix[1][1] * c + translation[1]) for r, c in mask}


def fit(records):
    """Retain every supported D4 affine hypothesis plus idempotent and toggle."""
    _need(type(records) is list and 2 <= len(records) <= MAX_RECORDS, "record_cap")
    before, rejected = _record_grid(records[0]), {}
    for index in range(len(records) - 1):
        after = _record_grid(records[index + 1])
        action = _action(records[index + 1].get("action"), before)
        reason = None
        if action["action_id"] != 6:
            reason = "not_coordinate_transition"
        elif (len(before), len(before[0])) != (len(after), len(after[0])):
            reason = "shape_changed"
        else:
            click = (action["data"]["y"], action["data"]["x"])
            color, control = before[click[0]][click[1]], _component(before, click)
            if (any(after[r][c] != color for r, c in control) or
                    _component(after, click) != control):
                reason = "control_not_unchanged_component"
            else:
                a, b = _mask(before, color) - control, _mask(after, color) - control
                if not a or len(a) != len(b) or not a - b or not b - a:
                    reason = "remote_mask_not_nonempty_equal_area_change"
                else:
                    backgrounds = {after[r][c] for r, c in a - b} | {before[r][c] for r, c in b - a}
                    if len(backgrounds) != 1:
                        reason = "vacated_and_incoming_background_not_uniform"
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            before = after
            continue
        background = next(iter(backgrounds))
        pair = {"before_grid": before, "after_grid": after, "action": action}
        pair_hash = hashlib.sha256(json.dumps(pair, sort_keys=True, separators=(",", ":"),
                                            allow_nan=False).encode()).hexdigest()
        candidates = []

        def candidate(identifier, mechanism, matrix=None, translation=None):
            row = {"schema": "click-rewrite-candidate-v1", "id": identifier,
                   "mechanism": mechanism, "shape": [len(before), len(before[0])],
                   "color": color, "background": background,
                   "control": {"mask": _points(control), "training_click": list(click)},
                   "mask_a": _points(a), "mask_b": _points(b), "source_pair_sha256": pair_hash}
            if matrix is not None:
                row.update(matrix=[list(v) for v in matrix], translation=list(translation))
            candidates.append(row)

        for number, matrix in enumerate(D4):
            transformed = _transform(a, matrix)
            left, right = min(transformed), min(b)
            translation = (right[0] - left[0], right[1] - left[1])
            if _transform(a, matrix, translation) == b:
                candidate("affine-d4-" + str(number), "affine", matrix, translation)
        candidate("idempotent", "idempotent")
        candidate("toggle", "toggle")
        _need(len(candidates) <= MAX_CANDIDATES, "candidate_cap_no_trimming")
        return {"schema": "click-rewrite-fit-v1", "status": "fitted", "candidates": candidates,
                "selected_transition": {"from_record_index": index, "to_record_index": index + 1},
                "control": {"mask": _points(control), "training_click": list(click), "color": color},
                "source_pair": dict(pair, sha256=pair_hash), "rejected_transition_counts": rejected,
                "unknowns": UNKNOWN[:], "bounds": dict(BOUNDS), "source_prior_not_blind": True,
                "training_scope": "one paired transition; later frames not examined"}
    return {"schema": "click-rewrite-fit-v1", "status": "no_qualifying_transition", "candidates": [],
            "selected_transition": None, "control": None, "source_pair": None,
            "rejected_transition_counts": rejected, "unknowns": UNKNOWN[:],
            "bounds": dict(BOUNDS), "source_prior_not_blind": True}


def _context(candidate):
    _need(type(candidate) is dict and candidate.get("schema") == "click-rewrite-candidate-v1" and
          type(candidate.get("id")) is str and 0 < len(candidate["id"]) <= 128 and
          {"shape", "mask_a", "mask_b", "control", "color", "background", "mechanism"} <= set(candidate) and
          type(candidate["control"]) is dict and
          {"mask", "training_click"} <= set(candidate["control"]), "candidate_schema")
    shape = candidate["shape"]
    _need(type(shape) is list and len(shape) == 2 and
          all(type(n) is int and 1 <= n <= MAX_SIDE for n in shape), "candidate_shape")

    def points(value):
        _need(type(value) is list and 1 <= len(value) <= shape[0] * shape[1] and
              all(type(p) is list and len(p) == 2 and all(type(n) is int for n in p) and
                  0 <= p[0] < shape[0] and 0 <= p[1] < shape[1] for p in value), "candidate_mask")
        result = {tuple(p) for p in value}
        _need(len(result) == len(value), "candidate_duplicate_pixel")
        return result

    a, b, control = points(candidate["mask_a"]), points(candidate["mask_b"]), points(candidate["control"]["mask"])
    color, background = candidate["color"], candidate["background"]
    _need(all(type(v) is int and 0 <= v <= 255 for v in (color, background)) and color != background and
          len(a) == len(b) and a != b and not (a | b) & control, "candidate_context")
    click = candidate["control"]["training_click"]
    _need(type(click) is list and len(click) == 2 and all(type(v) is int for v in click) and
          tuple(click) in control, "candidate_training_click")
    mechanism = candidate["mechanism"]
    _need(mechanism in ("affine", "idempotent", "toggle"), "candidate_mechanism")
    if mechanism == "affine":
        _need({"matrix", "translation"} <= set(candidate), "candidate_affine_parameters")
        matrix, translation = candidate["matrix"], candidate["translation"]
        _need(type(matrix) is list and len(matrix) == 2 and
              all(type(row) is list and len(row) == 2 and all(type(v) is int for v in row) for row in matrix) and
              tuple(tuple(row) for row in matrix) in D4 and type(translation) is list and
              len(translation) == 2 and all(type(v) is int and abs(v) <= 2 * MAX_SIDE for v in translation),
              "candidate_affine_parameters")
        _need(_transform(a, matrix, translation) == b, "candidate_affine_training_join")
    return a, b, control, color, background


def _current_issue(candidate, grid, b, control, color):
    if [len(grid), len(grid[0])] != candidate["shape"]:
        return "current_shape_mismatch", 1
    if any(grid[r][c] != color for r, c in control) or _component(grid, min(control)) != control:
        return "current_control_not_unchanged", 1
    difference = (_mask(grid, color) - control) ^ b
    return ("current_remote_mask_not_b", len(difference)) if difference else (None, 0)


def _unsupported(reason, counts=None):
    return {"status": "unsupported", "forecast": [], "next_mask": None, "reason": reason,
            "unknown_reason_counts": counts or {reason: 1}, "unknowns": UNKNOWN[:]}


def predict(candidate, grid, action):
    """One conditional rewrite; unresolved collisions never imply a no-op."""
    a, b, control, color, background = _context(candidate)
    grid = _grid(grid)
    reason, count = _current_issue(candidate, grid, b, control, color)
    if reason:
        return _unsupported(reason, {reason: count})
    action = _action(action, grid)
    if action["action_id"] != 6:
        return _unsupported("action_not_click")
    click = (action["data"]["y"], action["data"]["x"])
    if list(click) == candidate["control"]["training_click"]:
        return _unsupported("training_click_already_tried")
    if click not in control or any(p not in control for p in _neighbors(click)):
        return _unsupported("click_not_control_interior")
    next_mask = (b if candidate["mechanism"] == "idempotent" else a if candidate["mechanism"] == "toggle"
                 else _transform(b, candidate["matrix"], candidate["translation"]))
    counts = {}
    for r, c in next_mask:
        reason = ("destination_out_of_bounds" if not (0 <= r < len(grid) and 0 <= c < len(grid[0]))
                  else "destination_hits_control" if (r, c) in control
                  # Same-color contact would also change the agreed fixed
                  # connected control component, even without overwriting it.
                  else "destination_joins_control" if any(p in control for p in _neighbors((r, c)))
                  else "destination_third_color" if grid[r][c] not in (color, background) else None)
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    if counts:
        return _unsupported("unresolved_destination", counts)
    return {"status": "supported", "forecast": [{"row": r, "col": c,
            "value": color if (r, c) in next_mask else background} for r, c in sorted(b | next_mask)],
            "next_mask": _points(next_mask), "reason": None, "unknown_reason_counts": {}, "unknowns": UNKNOWN[:]}


def choose_probe(fitted, currentgrid, used_actions):
    """Choose once from public control geometry; no candidate ranking or call."""
    _need(type(fitted) is dict and fitted.get("schema") == "click-rewrite-fit-v1", "fit_schema")
    if fitted.get("status") != "fitted":
        return None
    candidates = fitted["candidates"]
    _need(type(candidates) is list and 1 <= len(candidates) <= MAX_CANDIDATES, "fit_candidate_cap")
    candidate = candidates[0]
    _, b, control, color, _ = _context(candidate)
    grid = _grid(currentgrid)
    if _current_issue(candidate, grid, b, control, color)[0]:
        return None
    _need(type(used_actions) is list and len(used_actions) <= MAX_RECORDS, "used_action_cap")
    used = {tuple(candidate["control"]["training_click"])}
    for action in used_actions:
        _need(type(action) is dict and type(action.get("action_id")) is int, "used_action_schema")
        if action["action_id"] == 6:
            data = action.get("data")
            _need(type(data) is dict and set(data) == {"x", "y"} and
                  all(type(v) is int and 0 <= v < MAX_SIDE for v in data.values()), "used_click_schema")
            used.add((data["y"], data["x"]))
    for row, col in sorted(control):
        if (row, col) not in used and all(p in control for p in _neighbors((row, col))):
            return {"action_id": 6, "data": {"x": col, "y": row}}
    return None

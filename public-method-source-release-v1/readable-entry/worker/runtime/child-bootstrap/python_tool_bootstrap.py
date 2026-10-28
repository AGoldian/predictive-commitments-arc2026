
# Modified 2026-10-28 by ARC Prize research workspace: byte-derived JSON node ceiling; original JSON/history and native policy retained.
import ast
import builtins
import contextlib
import io
import json
import os
import sys
import traceback

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None

COLOR_CHARS = ""

"""Connected-component segmentation of a single frame layer.

This module is intentionally self-contained -- standard library only, no project
imports, no ``from __future__`` import -- so its source can be spliced verbatim into
the Python-tool sandbox bootstrap, where project packages are not importable.
"""

import hashlib

_ORTH = ((-1, 0), (1, 0), (0, -1), (0, 1))
# clockwise Moore-neighbour offsets, starting at NW
_CW = ((-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1))
_CW_INDEX = {off: i for i, off in enumerate(_CW)}


def _trace_outer_contour(cells, start):
    """Moore-neighbour trace of a 4-connected component's outer perimeter, clockwise."""
    if len(cells) == 1:
        return [start]

    contour = [start]
    b = start
    prev = (start[0], start[1] - 1)  # W neighbour: outside the component since start is reading-order-min
    second = None
    for _ in range(8 * len(cells) + 16):
        idx = _CW_INDEX[(prev[0] - b[0], prev[1] - b[1])]
        nxt = None
        for k in range(1, 9):
            off = _CW[(idx + k) % 8]
            cand = (b[0] + off[0], b[1] + off[1])
            if cand in cells:
                nxt = cand
                back = _CW[(idx + k - 1) % 8]
                new_prev = (b[0] + back[0], b[1] + back[1])
                break
        if nxt is None:
            break
        if second is None:
            second = nxt
        elif b == start and nxt == second:  # Jacob's stopping criterion
            break
        contour.append(nxt)
        prev, b = new_prev, nxt

    if len(contour) > 1 and contour[-1] == contour[0]:
        contour.pop()
    return contour


def _corner_points(contour):
    """Reduce a traced contour loop to only the points where its direction changes."""
    if len(contour) <= 2:
        return list(contour)
    m = len(contour)
    corners = []
    for i in range(m):
        prev, cur, nxt = contour[i - 1], contour[i], contour[(i + 1) % m]
        d_in = (cur[0] - prev[0], cur[1] - prev[1])
        d_out = (nxt[0] - cur[0], nxt[1] - cur[1])
        if d_in != d_out:
            corners.append(cur)
    return corners


def _normalize_cells(cells):
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return sorted((r - min_r, c - min_c) for r, c in cells)


def _rotate_cells_90(norm_cells):
    """Rotate a normalized cell set 90 degrees clockwise; returns normalized."""
    max_r = max(r for r, _ in norm_cells)
    return sorted((c, max_r - r) for r, c in norm_cells)


def _cells_hash(norm_cells, color):
    payload = repr((color, norm_cells)).encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def _object_signature(cells, color):
    """Rotation-canonical identity of an object.

    Hashes the shape in all four 90-degree rotations (extend the transform list
    with reflections for full D4 canonicalization later) and takes the lowest
    hash as the canonical id. Returns (canonical_hash, rotation, symmetry,
    pose_hash) where:
      - canonical_hash: identical for all rotated copies of the same shape+color.
      - rotation: degrees CLOCKWISE to rotate the canonical form to obtain the
        observed object. None for 4-fold symmetric shapes (all rotations equal);
        reduced mod 180 (i.e. 0 or 90) for 2-fold symmetric shapes.
      - symmetry: rotational symmetry order (1, 2, or 4).
      - pose_hash: the classic rotation-SENSITIVE hash of the observed pose.
    """
    norm = _normalize_cells(cells)
    variants = [norm]
    for _ in range(3):
        variants.append(_rotate_cells_90(variants[-1]))
    hashes = [_cells_hash(v, color) for v in variants]
    # The reference orientation is picked from the COLOUR-FREE hash. Choosing it
    # from the colour-bearing one made the argmin depend on the colour, so the
    # same shape in the same orientation reported a different rotation for a red
    # object than for a blue one - and a model comparing rotations across
    # objects was reading noise.
    shape_hashes = [_cells_hash(v, "__shape__") for v in variants]
    k = shape_hashes.index(min(shape_hashes))
    canonical = hashes[k]
    distinct = len(set(shape_hashes))
    symmetry = {1: 4, 2: 2, 4: 1}.get(distinct, 1)
    rotation = ((4 - k) % 4) * 90  # so observed = canonical rotated this much CW
    if symmetry == 4:
        rotation = None
    elif symmetry == 2:
        rotation = rotation % 180
    shape_hash = _cells_hash(norm, "__shape__")
    return canonical, rotation, symmetry, hashes[0], shape_hash


def segment_layer(layer, color_chars):
    """Segment one frame layer into connected-component nodes.

    Pass a single layer (if the frame has multiple) and ``color_chars``, the ARC
    color-symbol mapping (indexed by integer color value -> single-char label). The
    layer is partitioned into 4-connected components of equal integer value via flood
    fill, and each component becomes a node. Nodes are ordered by their
    top-most-left-most cell -- unique within a 64x64 layer -- and that order is the
    node ``id``.

    Each node is a dict with:
      - ``id``: index in the top-left ordering.
      - ``color``: the component's ARC color character (looked up in ``color_chars``).
      - ``hash``: a translation-invariant signature of the object -- its color plus its
        cell shape normalized to a top-left origin -- so the same shape gets the same
        hash regardless of position (lets objects be matched across frames, or when
        several similar objects appear in one frame).
      - ``pixels``: number of cells in the component.
      - ``boundary``: the component's outer perimeter as an ordered, clockwise list of
        ``[row, col]`` corner points -- a Moore-neighbour trace reduced to only the
        vertices where the contour changes direction (enclosed holes are not traced).
      - ``children``: ids of components directly enclosed by this node. A is a child of
        B only if B is the innermost component that fully surrounds A (every path from A
        to the grid edge crosses B), which yields a clean nesting tree.

    Returns a dict with:
      - ``nodes``: list of the node dicts above, in id order.
      - ``adjacency_list``: sorted list of ``[i, j]`` id pairs for components that share
        a 4-connected edge (includes parent/child pairs, since they physically touch).
    """
    height = len(layer)
    width = len(layer[0]) if height else 0

    # connected components, 4-connectivity. Reading-order scan => component ids are
    # already ordered by top-most-left-most cell (each layer is 64x64, so it is unique).
    comp_id = [[-1] * width for _ in range(height)]
    components = []  # each: {"value": int, "cells": set[(r, c)], "start": (r, c)}
    for sr in range(height):
        for sc in range(width):
            if comp_id[sr][sc] != -1:
                continue
            value = layer[sr][sc]
            cid = len(components)
            cells = set()
            stack = [(sr, sc)]
            comp_id[sr][sc] = cid
            while stack:
                r, c = stack.pop()
                cells.add((r, c))
                for dr, dc in _ORTH:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width and comp_id[nr][nc] == -1 and layer[nr][nc] == value:
                        comp_id[nr][nc] = cid
                        stack.append((nr, nc))
            components.append({"value": int(value), "cells": cells, "start": (sr, sc)})

    n = len(components)

    # adjacency between components: any two components with 4-adjacent cells
    adj_pairs = set()
    for r in range(height):
        for c in range(width):
            cid = comp_id[r][c]
            if r + 1 < height and comp_id[r + 1][c] != cid:
                other = comp_id[r + 1][c]
                adj_pairs.add((min(cid, other), max(cid, other)))
            if c + 1 < width and comp_id[r][c + 1] != cid:
                other = comp_id[r][c + 1]
                adj_pairs.add((min(cid, other), max(cid, other)))
    adjacency_list = sorted([a, b] for a, b in adj_pairs)

    # containment: for each component b, flood-fill its complement inward from the grid
    # border; any component whose cells are never reached is enclosed by b.
    enclosers = [set() for _ in range(n)]
    for b in range(n):
        reached = [[False] * width for _ in range(height)]
        stack = []
        for r in range(height):
            for c in (0, width - 1):
                if comp_id[r][c] != b and not reached[r][c]:
                    reached[r][c] = True
                    stack.append((r, c))
        for c in range(width):
            for r in (0, height - 1):
                if comp_id[r][c] != b and not reached[r][c]:
                    reached[r][c] = True
                    stack.append((r, c))
        while stack:
            r, c = stack.pop()
            for dr, dc in _ORTH:
                nr, nc = r + dr, c + dc
                if 0 <= nr < height and 0 <= nc < width and not reached[nr][nc] and comp_id[nr][nc] != b:
                    reached[nr][nc] = True
                    stack.append((nr, nc))
        for a in range(n):
            if a == b:
                continue
            ar, ac = components[a]["start"]
            if not reached[ar][ac]:
                enclosers[a].add(b)

    # parent = innermost encloser. enclosers are transitive, so along a nesting chain the
    # innermost component is the one that is itself most deeply enclosed.
    children = [[] for _ in range(n)]
    for a in range(n):
        if enclosers[a]:
            parent = max(enclosers[a], key=lambda e: (len(enclosers[e]), -e))
            children[parent].append(a)
    for child_list in children:
        child_list.sort()

    nodes = []
    for cid in range(n):
        comp = components[cid]
        color = color_chars[max(0, min(15, comp["value"]))]
        boundary = _corner_points(_trace_outer_contour(comp["cells"], comp["start"]))
        signature = _object_signature(comp["cells"], color)
        nodes.append(
            {
                "id": cid,
                "color": color,
                "hash": signature[0],
                "rotation": signature[1],
                "rotational_symmetry": signature[2],
                "pose_hash": signature[3],
                "shape_hash": signature[4],
                "pixels": len(comp["cells"]),
                "boundary": [[r, c] for r, c in boundary],
                "children": children[cid],
            }
        )

    return {"nodes": nodes, "adjacency_list": adjacency_list}

"""Object-level frame diff core, shared by the sandbox runtime and the host.

This module must stay dependency-free (stdlib only, no imports): its source is
injected verbatim into the sandbox bootstrap template (see
python_tool_sandbox.py), which runs under ``python -I -S`` and cannot import
project modules. The host imports it normally for the auto frame-diff feature.
"""


def _node_topleft(node):
    points = node.get("boundary") or []
    if not points:
        return (0, 0)
    return (min(p[0] for p in points), min(p[1] for p in points))

def _hungarian(cost):
    # Minimum-cost assignment (Jonker-Volgonant style with potentials).
    # cost: n x m matrix with n <= m. Returns list row -> column.
    n = len(cost)
    m = len(cost[0]) if n else 0
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)      # p[j] = row assigned to column j (1-based; 0 = none)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment

def _node_bbox(node):
    points = node.get("boundary") or []
    if not points:
        return (0, 0, 0, 0)
    rows = [p[0] for p in points]; cols = [p[1] for p in points]
    return (min(rows), min(cols), max(rows), max(cols))

def _node_center2(node):
    # bbox center in half-cell units (ints): (r0+r1, c0+c1)
    points = node.get("boundary") or []
    if not points:
        return (0, 0)
    rows = [p[0] for p in points]; cols = [p[1] for p in points]
    return (min(rows) + max(rows), min(cols) + max(cols))

def compute_frame_diff(grid_a, grid_b, nodes_a, nodes_b, max_group_match=None):
    # Object-level diff between two same-shaped grids with precomputed
    # segmentation nodes. Returns only what changed; unchanged objects are
    # omitted. When max_group_match is set, identical-hash groups larger than
    # it skip pairwise matching and report plain appeared/disappeared entries
    # (guards against O(n^3) assignment on e.g. hundreds of identical pixels).
    changed = set()
    for r, (row_a, row_b) in enumerate(zip(grid_a, grid_b)):
        if row_a == row_b:
            continue
        for c, (va, vb) in enumerate(zip(row_a, row_b)):
            if va != vb:
                changed.add((r, c))
    if not changed:
        return {"changed_cell_count": 0, "moved": [], "rotated": [],
                "appeared": [], "disappeared": [],
                "changed_color": [], "resized": []}

    def touched_nodes(nodes):
        touched = []
        for node in nodes:
            points = node.get("boundary") or []
            if not points:
                continue
            r0 = min(p[0] for p in points); r1 = max(p[0] for p in points)
            c0 = min(p[1] for p in points); c1 = max(p[1] for p in points)
            # dilate by 1 so objects that shrank/grew still register as
            # touched by the cells they vacated/claimed
            if any(r0 - 1 <= r <= r1 + 1 and c0 - 1 <= c <= c1 + 1 for (r, c) in changed):
                touched.append(node)
        return touched

    before_nodes = touched_nodes(nodes_a)
    after_nodes = touched_nodes(nodes_b)

    moved, appeared, disappeared = [], [], []
    rotated = []

    def _classify_match(node_a, node_b):
        rot_a = node_a.get("rotation")
        rot_b = node_b.get("rotation")
        symmetry = node_a.get("rotational_symmetry") or 1
        rotated_by = None
        if rot_a is not None and rot_b is not None:
            modulus = 180 if symmetry == 2 else 360
            delta = (rot_b - rot_a) % modulus
            if delta:
                rotated_by = delta
        pa, pb = _node_topleft(node_a), _node_topleft(node_b)
        base_entry = {"color": node_a.get("color"),
                      "pixels": node_a.get("pixels"),
                      "hash": node_a.get("hash")}
        if rotated_by is not None:
            ca, cb = _node_center2(node_a), _node_center2(node_b)
            in_place = (abs(ca[0] - cb[0]) <= 2 and abs(ca[1] - cb[1]) <= 2)
            base_entry["rotated_by"] = rotated_by
            if in_place:
                base_entry["at"] = list(pb)
                rotated.append(base_entry)
            else:
                base_entry["from"] = list(pa); base_entry["to"] = list(pb)
                moved.append(base_entry)
        elif pa != pb:
            base_entry["from"] = list(pa); base_entry["to"] = list(pb)
            moved.append(base_entry)
        # same hash, same position, same rotation: unchanged -> omit

    groups_before = {}
    for node in before_nodes:
        groups_before.setdefault(node.get("hash"), []).append(node)
    groups_after = {}
    for node in after_nodes:
        groups_after.setdefault(node.get("hash"), []).append(node)

    for key, group_a in groups_before.items():
        group_b = groups_after.pop(key, [])
        if (
            max_group_match is not None
            and max(len(group_a), len(group_b)) > max_group_match
        ):
            # too many identical objects to match affordably
            for node_a in group_a:
                disappeared.append({"color": node_a.get("color"),
                                    "pixels": node_a.get("pixels"),
                                    "hash": node_a.get("hash"),
                                    "shape_hash": node_a.get("shape_hash"),
                                    "at": list(_node_topleft(node_a)),
                                    "bbox": list(_node_bbox(node_a))})
            for node_b in group_b:
                appeared.append({"color": node_b.get("color"),
                                 "pixels": node_b.get("pixels"),
                                 "hash": node_b.get("hash"),
                                 "shape_hash": node_b.get("shape_hash"),
                                 "at": list(_node_topleft(node_b)),
                                 "bbox": list(_node_bbox(node_b))})
            continue
        if not group_b:
            for node_a in group_a:
                disappeared.append({"color": node_a.get("color"),
                                    "pixels": node_a.get("pixels"),
                                    "hash": node_a.get("hash"),
                                    "shape_hash": node_a.get("shape_hash"),
                                    "at": list(_node_topleft(node_a)),
                                    "bbox": list(_node_bbox(node_a))})
            continue
        # optimal assignment over bbox-center distances; rows = smaller side
        transposed = len(group_a) > len(group_b)
        rows, cols = (group_b, group_a) if transposed else (group_a, group_b)
        cost = []
        for row_node in rows:
            cr = _node_center2(row_node)
            cost.append([
                abs(cr[0] - _node_center2(col_node)[0])
                + abs(cr[1] - _node_center2(col_node)[1])
                for col_node in cols
            ])
        assignment = _hungarian(cost)
        matched_cols = set()
        for row_index, col_index in enumerate(assignment):
            if col_index < 0:
                continue
            matched_cols.add(col_index)
            if transposed:
                _classify_match(cols[col_index], rows[row_index])
            else:
                _classify_match(rows[row_index], cols[col_index])
        if transposed:
            for col_index, node_a in enumerate(cols):
                if col_index not in matched_cols:
                    disappeared.append({"color": node_a.get("color"),
                                        "pixels": node_a.get("pixels"),
                                        "hash": node_a.get("hash"),
                                    "shape_hash": node_a.get("shape_hash"),
                                        "at": list(_node_topleft(node_a)),
                                        "bbox": list(_node_bbox(node_a))})
        else:
            for col_index, node_b in enumerate(cols):
                if col_index not in matched_cols:
                    appeared.append({"color": node_b.get("color"),
                                     "pixels": node_b.get("pixels"),
                                     "hash": node_b.get("hash"),
                             "shape_hash": node_b.get("shape_hash"),
                                     "at": list(_node_topleft(node_b)),
                                     "bbox": list(_node_bbox(node_b))})
            continue
        # transposed: every after-node (a row) got matched; nothing appeared
    for group_b in groups_after.values():
        for node_b in group_b:
            appeared.append({"color": node_b.get("color"),
                             "pixels": node_b.get("pixels"),
                             "hash": node_b.get("hash"),
                             "shape_hash": node_b.get("shape_hash"),
                             "at": list(_node_topleft(node_b)),
                             "bbox": list(_node_bbox(node_b))})
    # Phase A - changed_color: EXACT pairs only. Same position, byte-
    # identical shape (color-independent pose signature), different
    # color. This asserts "these exact cells changed color" and nothing
    # more; fuzzy transformation claims are deliberately not made.
    changed_color = []
    used_gone, used_new = set(), set()
    for gi, gone in enumerate(disappeared):
        for ni, new in enumerate(appeared):
            if ni in used_new:
                continue
            if (gone["at"] == new["at"]
                    and gone.get("shape_hash")
                    and gone.get("shape_hash") == new.get("shape_hash")
                    and gone["color"] != new["color"]):
                changed_color.append({"at": gone["at"],
                                      "pixels": gone["pixels"],
                                      "before_color": gone["color"],
                                      "after_color": new["color"],
                                      "before_hash": gone.get("hash"),
                                      "after_hash": new.get("hash")})
                used_gone.add(gi); used_new.add(ni)
                break
    disappeared = [entry for index, entry in enumerate(disappeared) if index not in used_gone]
    appeared = [entry for index, entry in enumerate(appeared) if index not in used_new]

    # Phase B - resized: same-color pairs whose bboxes substantially
    # overlap (overlap area / smaller bbox area >= 0.5); greedy
    # one-to-one by descending overlap then size similarity.
    resized = []

    def _bbox_area(b):
        return max(0, b[2] - b[0] + 1) * max(0, b[3] - b[1] + 1)

    def _overlap_ratio(b1, b2):
        inter_r = min(b1[2], b2[2]) - max(b1[0], b2[0]) + 1
        inter_c = min(b1[3], b2[3]) - max(b1[1], b2[1]) + 1
        if inter_r <= 0 or inter_c <= 0:
            return 0.0
        smaller = min(_bbox_area(b1), _bbox_area(b2))
        return (inter_r * inter_c) / smaller if smaller else 0.0

    candidates = []
    for gi, gone in enumerate(disappeared):
        for ni, new in enumerate(appeared):
            if gone["color"] != new["color"]:
                continue
            bg = gone.get("bbox") or (0, 0, -1, -1)
            bn = new.get("bbox") or (0, 0, -1, -1)
            ratio = _overlap_ratio(bg, bn)
            if ratio >= 0.5:
                area_g, area_n = _bbox_area(bg), _bbox_area(bn)
                similarity = (min(area_g, area_n) / max(area_g, area_n)) if max(area_g, area_n) else 0.0
                candidates.append((ratio, similarity, gi, ni))
    candidates.sort(key=lambda item: (-item[0], -item[1]))
    used_gone, used_new = set(), set()
    for ratio, similarity, gi, ni in candidates:
        if gi in used_gone or ni in used_new:
            continue
        used_gone.add(gi); used_new.add(ni)
        gone, new = disappeared[gi], appeared[ni]
        resized.append({"at_before": gone["at"], "at_after": new["at"],
                        "color": gone["color"],
                        "before_pixels": gone["pixels"],
                        "after_pixels": new["pixels"],
                        "before_hash": gone.get("hash"),
                        "after_hash": new.get("hash")})
    disappeared = [entry for index, entry in enumerate(disappeared) if index not in used_gone]
    appeared = [entry for index, entry in enumerate(appeared) if index not in used_new]
    return {"changed_cell_count": len(changed), "moved": moved,
            "rotated": rotated,
            "appeared": appeared, "disappeared": disappeared,
            "changed_color": changed_color, "resized": resized}

"""Conservative source-only function retention; no snippet state is serialized.

Also embedded into the isolated Python runner. Keep this module stdlib-only.
"""
import ast
import dis
import sys
import types


def _import_statements(nodes):
    """One explicit absolute import per binding; never replay wildcard imports."""
    statements = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                binding = alias.asname or alias.name.split('.')[0]
                statements[binding] = ast.unparse(ast.Import(names=[alias]))
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for alias in node.names:
                if alias.name == '*':
                    raise ValueError('wildcard imports are not retained; use explicit imports inside the function')
                statements[alias.asname or alias.name] = ast.unparse(
                    ast.ImportFrom(module=node.module, names=[alias], level=0))
        else:
            raise ValueError('only explicit absolute imports can accompany retained functions')
    return statements


def _source_parts(source, retain_imports=True):
    tree = ast.parse(source, '<retained>', 'exec')
    if (not tree.body or not isinstance(tree.body[-1], ast.FunctionDef)
            or (not retain_imports and len(tree.body) != 1)):
        raise ValueError('only top-level function definitions can be retained')
    imports = _import_statements(tree.body[:-1])
    return tree.body[-1], imports


def function_signature(source):
    node, _ = _source_parts(source)
    return node.name + '(' + ast.unparse(node.args) + ')'


def _function_record(source, retain_imports=False):
    node, imports = _source_parts(source, retain_imports)
    if getattr(node, "type_params", []):
        raise ValueError("generic type parameters are not retained")
    if node.decorator_list:
        raise ValueError('decorated functions are not retained')
    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    args += [a for a in (node.args.vararg, node.args.kwarg) if a is not None]
    if node.returns is not None or any(a.annotation is not None for a in args):
        raise ValueError('use an unannotated definition for retention')
    # Restoration must never evaluate model calls or snapshot a frame via defaults.
    for default in [*node.args.defaults, *node.args.kw_defaults]:
        if default is not None:
            try:
                ast.literal_eval(default)
            except Exception:
                raise ValueError('defaults must be literals; pass changing data as arguments') from None
    tree = ast.Module(body=[node], type_ignores=[])
    code = next(c for c in compile(tree, '<retained>', 'exec').co_consts
                if isinstance(c, types.CodeType))
    reads = set()
    pending = [code]
    while pending:
        current = pending.pop()
        for instruction in dis.get_instructions(current):
            if instruction.opname in ('LOAD_GLOBAL', 'LOAD_NAME'):
                reads.add(instruction.argval)
            elif instruction.opname in ('STORE_GLOBAL', 'DELETE_GLOBAL'):
                raise ValueError('functions that assign global variables are not retained')
        pending.extend(c for c in current.co_consts if isinstance(c, types.CodeType))
    return node.name, source, reads - imports.keys()


def _rejection(name, reason, hint=None, **metadata):
    result = {'name': name, 'reason': reason, **metadata}
    if hint:
        result['hint'] = hint
    return result


def _validation_hint(reason):
    if 'decorat' in reason:
        return 'Use a plain top-level def without decorators if you want to reuse it.'
    if 'annotat' in reason:
        return 'Remove parameter and return annotations if you want to retain this function.'
    if 'default' in reason:
        return 'Use literal defaults and pass changing values explicitly as arguments.'
    if 'global variables' in reason:
        return 'Return updated values instead of assigning global variables.'
    if 'import' in reason:
        return 'Put explicit, sandbox-supported imports inside the function.'
    return 'Use a plain top-level def if you want to retain this function.'


def prepare_functions(sources, available, *, retain_imports=False):
    """Validate sources without executing them; drop invalid dependency chains."""
    records, rejected = {}, []
    for source in sources:
        name = '<unknown>'
        try:
            parsed = ast.parse(source)
            if (parsed.body and isinstance(parsed.body[-1], ast.FunctionDef)
                    and (retain_imports or len(parsed.body) == 1)):
                name = parsed.body[-1].name
                records.pop(name, None)
            name, source, reads = _function_record(source, retain_imports)
            _, imports = _source_parts(source)
            if imports.keys() & set(available):
                raise ValueError('import alias conflicts with a provided global or builtin')
            records[name] = (source, reads)
        except Exception as exc:
            reason = str(exc)[:180]
            rejected.append(_rejection(name, reason, _validation_hint(reason)))
    # Import bundles must not overwrite another retained function at restore.
    function_names = set(records)
    for name, (source, _) in list(records.items()):
        _, imports = _source_parts(source)
        if imports.keys() & function_names:
            del records[name]
            rejected.append(_rejection(name, 'import alias conflicts with a retained function',
                                       'Choose a different import alias or function name.'))
    # A wrapper must not survive its unavailable dependency. Re-run to a fixed point.
    while True:
        dropped = []
        for name, (source, reads) in records.items():
            missing = reads - set(available) - records.keys()
            if missing:
                dropped.append(name)
                names = ', '.join(sorted(missing))
                rejected.append(_rejection(
                    name, 'unavailable dependencies: ' + names,
                    'Pass ' + names + ' as arguments, or put their imports inside the function.',
                    missing_dependencies=sorted(missing)))
        if not dropped:
            break
        for name in dropped:
            del records[name]
    return {name: value[0] for name, value in records.items()}, rejected


def restore_functions(sources, namespace, available, *, retain_imports=False,
                      repair_hints=False):
    """Restore definitions and explicit imports through the sandbox importer.

    Never replay assignments, expressions, decorators, or previous actions.
    """
    kept, rejected = prepare_functions(sources, available, retain_imports=retain_imports)
    failed = set()
    for name, source in kept.items():
        before = dict(namespace)
        try:
            if name in available:
                raise ValueError('name conflicts with a provided global or builtin')
            exec(compile(source, '<retained>', 'exec'), namespace, namespace)
        except Exception:
            # A multi-import bundle can fail partway through. Restore bindings
            # so one failed helper does not replace another helper's globals.
            namespace.clear()
            namespace.update(before)
            failed.add(name)
            reason = ('could not restore this definition or its imports' if repair_hints else
                      'could not restore this definition; redefine it if needed')
            rejected.append(_rejection(name, reason,
                                       'Check its imports are supported by the sandbox, then redefine it if needed.'))
    survivors, dependencies = prepare_functions(
        [source for name, source in kept.items() if name not in failed], available,
        retain_imports=retain_imports)
    rejected.extend(dependencies)
    for name in kept.keys() - survivors.keys():
        if name not in available:
            namespace.pop(name, None)
    return survivors, rejected


def _matching_imports(nodes, namespace):
    """Recognize live import bindings without importing or evaluating anything.

    Only module bindings and callable/immutable exports are eligible. Ordinary
    snippet assignments and mutable imported data are never serialized. Looking
    in module dictionaries avoids invoking __getattr__ during bookkeeping.
    """
    matches, declared = {}, {}
    for node in nodes:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        try:
            statements = _import_statements([node])
        except ValueError:
            continue
        declared.update(statements)
        for binding, statement in statements.items():
            single = ast.parse(statement).body[0]
            alias = single.names[0]
            if isinstance(single, ast.Import):
                # Even unaliased dotted imports must already have executed.
                if alias.name not in sys.modules:
                    continue
                module_name = alias.name if alias.asname else alias.name.split('.')[0]
                expected = sys.modules.get(module_name)
            else:
                module = sys.modules.get(single.module)
                expected = vars(module).get(alias.name) if type(module) is types.ModuleType else None
            eligible = type(expected) in (
                types.ModuleType, types.FunctionType, types.BuiltinFunctionType, types.MethodType,
                type, str, bytes, int, float, complex, bool,
            )
            if eligible and binding in namespace and namespace[binding] is expected:
                matches[binding] = statement
    return matches, declared


def collect_functions(code_text, previous, namespace, available, *, retain_imports=False,
                      repair_hints=False):
    """Collect from the actual namespace, including after partial execution.

    A later def may never have run. Match the live function's source location
    rather than choosing the last definition in the submitted snippet.
    """
    candidates = {}
    rejected = []
    try:
        tree = ast.parse(code_text, '<python_tool>')
    except SyntaxError:
        # Parsing failed before execution; restored functions are still valid.
        tree = ast.Module(body=[], type_ignores=[])
    fresh = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fresh.setdefault(node.name, []).append(node)
    import_nodes = []
    for source in previous.values():
        # Old source-only records remain valid; no migration is necessary.
        import_nodes.extend(ast.parse(source).body[:-1])
    import_nodes.extend(tree.body)
    imports, declared_imports = (_matching_imports(import_nodes, namespace)
                                if retain_imports or repair_hints else ({}, {}))
    for name in dict.fromkeys([*previous, *fresh]):
        value = namespace.get(name)
        if not repair_hints and (name in available or type(value) is not types.FunctionType
                                 or value.__name__ != name):
            rejected.append(_rejection(name, 'definition did not execute, was removed/replaced, or conflicts with a provided name'))
            continue
        if name in available:
            rejected.append(_rejection(name, 'name conflicts with a provided global or builtin',
                                       'Choose a different function name.'))
            continue
        if name not in namespace:
            reason = 'function was removed' if name in previous else 'definition was not reached or was removed'
            rejected.append(_rejection(name, reason, 'Define it before calling it if it is still needed.'))
            continue
        if type(value) is not types.FunctionType or value.__name__ != name:
            rejected.append(_rejection(name, 'function name was replaced by another value',
                                       'Use a separate variable name; redefine the function only if needed.'))
            continue
        if name in previous and value.__code__.co_filename == '<retained>':
            # Preserve the restored definition when execution stopped before a
            # replacement (or while evaluating that replacement's defaults).
            candidates[name] = previous[name]
            continue
        node = next((node for node in fresh.get(name, [])
                     if isinstance(node, ast.FunctionDef) and not node.decorator_list
                     and value.__code__.co_filename == '<python_tool>'
                     and value.__code__.co_firstlineno == node.lineno), None)
        if node is None:
            rejected.append(_rejection(name, 'definition was decorated, replaced outside a top-level def, or is unsupported',
                                       'Use a plain top-level def without decorators if you want to reuse it.'))
            continue
        candidates[name] = ast.get_source_segment(code_text, node)
    # Rebuild every bundle from the LIVE namespace. An old helper must not
    # silently restore an obsolete import when that alias was rebound/deleted.
    for name, source in (list(candidates.items()) if retain_imports else []):
        try:
            node, _ = _source_parts(source)
            definition = ast.get_source_segment(source, node)
            _, _, reads = _function_record(definition)
            statements = [imports[n] for n in sorted(reads & imports.keys()) if n not in available]
            candidates[name] = '\n'.join([*statements, definition])
        except Exception:
            # Validation below produces the specific rejection and prunes callers.
            pass
    kept, invalid = prepare_functions(candidates.values(), available, retain_imports=retain_imports)
    for item in invalid:
        missing = item.get('missing_dependencies', [])
        if not missing:
            continue
        hints = []
        missing_imports = [n for n in missing if n in declared_imports]
        missing_helpers = [n for n in missing if n in candidates and n not in declared_imports]
        missing_data = sorted(set(missing) - set(missing_imports) - set(missing_helpers))
        if missing_imports:
            statements = '; '.join(declared_imports[n] for n in missing_imports)
            hints.append('Put `' + statements + '` inside this function if you want to reuse it.')
        if missing_helpers:
            hints.append('Make the helper dependencies retainable too: ' + ', '.join(missing_helpers) + '.')
        if missing_data:
            hints.append('Pass ' + ', '.join(missing_data) + ' as arguments; snippet variables are not retained.')
        item['hint'] = ' '.join(hints)
    return kept, rejected + invalid

HOST_STDOUT = sys.stdout

SAFE_MODULES = {
    "bisect",
    "collections",
    "copy",
    # pure-Python sequence comparison, no I/O. Measured across 32
    # transcripts it was imported 9 times and USED none of them - the model
    # reaches for it on "compare two things" and then writes the comparison
    # by hand. Allowing it therefore buys robustness, not capability: a
    # stray import line no longer costs the whole snippet.
    "difflib",
    "fractions",
    "functools",
    "heapq",
    "itertools",
    "json",
    "math",
    "operator",
    "random",
    "re",
    "statistics",
    "string",
}
# Original enforcement additions: MIT-0; exact CPU-probed source subset.
import ctypes

import errno

import mmap

import os

import platform

import stat

POLICY_VERSION = "synthetic-cpu-v1"

SCMP_ACT_ALLOW = 0x7FFF0000

SCMP_ACT_ERRNO_EPERM = 0x00050000 | errno.EPERM

SCMP_ACT_KILL_PROCESS = 0x80000000

SCMP_CMP_EQ = 4

SCMP_CMP_MASKED_EQ = 7

SCMP_FLTATR_ACT_BADARCH = 2

SCMP_FLTATR_CTL_NNP = 3

SCMP_FLTATR_CTL_TSYNC = 4

PR_SET_NO_NEW_PRIVS = 38

PR_GET_NO_NEW_PRIVS = 39

TRUSTED_SAFE_MODULES = (
    "bisect", "collections", "copy", "difflib", "fractions", "functools", "heapq",
    "itertools", "json", "math", "operator", "random", "re", "statistics", "string",
)

COMPUTATION_SYSCALLS = (
    "brk", "munmap", "mremap", "madvise", "futex", "rt_sigaction",
    "rt_sigprocmask", "rt_sigreturn", "sigaltstack", "clock_gettime",
    "clock_getres", "restart_syscall", "sched_yield", "close", "exit", "exit_group",
)

class PolicyFailure(RuntimeError):
    def __init__(self, stage: str, error: int | None = None):
        super().__init__(stage)
        self.stage, self.error = stage, error

    def record(self) -> dict:
        result = {"stage": self.stage}
        if self.error is not None:
            result.update(errno=int(self.error), errno_name=errno.errorcode.get(self.error, "UNKNOWN"))
        return result

class ArgCompare(ctypes.Structure):
    _fields_ = [("arg", ctypes.c_uint), ("op", ctypes.c_int),
                ("datum_a", ctypes.c_uint64), ("datum_b", ctypes.c_uint64)]

class LibVersion(ctypes.Structure):
    _fields_ = [("major", ctypes.c_uint), ("minor", ctypes.c_uint), ("micro", ctypes.c_uint)]

def policy_rules() -> list[tuple[str, list[tuple[int, int, int, int]]]]:
    '''Declarative rules; syscall numbers are resolved by the loaded library.'''
    rules = [("read", [(0, SCMP_CMP_EQ, 0, 0)]),
             ("write", [(0, SCMP_CMP_EQ, 1, 0)]),
             ("write", [(0, SCMP_CMP_EQ, 2, 0)])]
    rules.extend((name, []) for name in COMPUTATION_SYSCALLS)
    # Anonymous maps only, no executable mappings, and no file descriptor.
    rules.append(("mmap", [(2, SCMP_CMP_MASKED_EQ, mmap.PROT_EXEC, 0),
                           (3, SCMP_CMP_MASKED_EQ, mmap.MAP_ANONYMOUS, mmap.MAP_ANONYMOUS),
                           (4, SCMP_CMP_MASKED_EQ, 0xFFFFFFFF, 0xFFFFFFFF)]))
    rules.append(("mprotect", [(2, SCMP_CMP_MASKED_EQ, mmap.PROT_EXEC, 0)]))
    return rules

def _configure_library(lib):
    signatures = {
        "seccomp_init": ([ctypes.c_uint32], ctypes.c_void_p),
        "seccomp_release": ([ctypes.c_void_p], None),
        "seccomp_attr_set": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32], ctypes.c_int),
        "seccomp_syscall_resolve_name": ([ctypes.c_char_p], ctypes.c_int),
        "seccomp_rule_add_array": ([ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                    ctypes.c_uint, ctypes.POINTER(ArgCompare)], ctypes.c_int),
        "seccomp_load": ([ctypes.c_void_p], ctypes.c_int),
        "seccomp_arch_native": ([], ctypes.c_uint32),
        "seccomp_version": ([], ctypes.POINTER(LibVersion)),
    }
    try:
        for name, (args, returns) in signatures.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = args, returns
    except AttributeError:
        raise PolicyFailure("libseccomp_required_symbol_missing") from None

def load_libseccomp():
    if platform.system() != "Linux":
        raise PolicyFailure("unsupported_os")
    if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_long) != 8:
        raise PolicyFailure("unsupported_32_bit_abi")
    for name in ("libseccomp.so.2", "libseccomp.so"):
        try:
            lib = ctypes.CDLL(name, use_errno=True)
        except OSError:
            continue
        _configure_library(lib)
        return lib, name
    raise PolicyFailure("libseccomp_not_loadable")

def _checked_return(value: int, stage: str):
    if value != 0:
        raise PolicyFailure(stage, -int(value) if value < 0 else int(value))

def build_filter(lib) -> tuple[object, dict]:
    context = lib.seccomp_init(SCMP_ACT_ERRNO_EPERM)
    if not context:
        raise PolicyFailure("seccomp_init_failed", ctypes.get_errno() or None)
    details = {"default_action": "ERRNO(EPERM)", "native_arch_token": int(lib.seccomp_arch_native()),
               "resolved_rules": [], "unsupported_optional_syscalls": [],
               "tsync_requested": True, "no_new_privs_requested": True}
    try:
        for attribute, value in ((SCMP_FLTATR_ACT_BADARCH, SCMP_ACT_KILL_PROCESS),
                                 (SCMP_FLTATR_CTL_NNP, 1), (SCMP_FLTATR_CTL_TSYNC, 1)):
            _checked_return(lib.seccomp_attr_set(context, attribute, value), "seccomp_attribute_failed")
        for name, comparisons in policy_rules():
            number = int(lib.seccomp_syscall_resolve_name(name.encode("ascii")))
            if number < 0:
                if name in {"read", "write", "exit", "exit_group", "mmap", "mprotect"}:
                    raise PolicyFailure("required_syscall_unresolved")
                details["unsupported_optional_syscalls"].append(name)
                continue
            array = (ArgCompare * len(comparisons))(*(ArgCompare(*item) for item in comparisons))
            _checked_return(lib.seccomp_rule_add_array(
                context, SCMP_ACT_ALLOW, number, len(comparisons), array if comparisons else None),
                "seccomp_rule_add_failed")
            details["resolved_rules"].append({"syscall": name, "native_number": number,
                                               "comparisons": [list(item) for item in comparisons]})
    except BaseException:
        lib.seccomp_release(context)
        raise
    version = lib.seccomp_version()
    details["libseccomp_version"] = (f"{version.contents.major}.{version.contents.minor}."
                                    f"{version.contents.micro}" if version else None)
    return context, details

def close_inherited_descriptors() -> dict:
    '''Trusted single-thread setup: inspect fd numbers only, never fd targets.'''
    try:
        if len(os.listdir("/proc/self/task")) != 1:
            raise PolicyFailure("preload_created_threads")
        if not all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in (0, 1, 2)):
            raise PolicyFailure("stdio_must_be_parent_pipes")
        closed = 0
        for name in os.listdir("/proc/self/fd"):
            fd = int(name)
            if fd > 2:
                try:
                    os.close(fd)
                    closed += 1
                except OSError as exc:
                    if exc.errno != errno.EBADF:
                        raise
        # listdir's temporary directory fd is already closed before this loop.
        for name in os.listdir("/proc/self/fd"):
            fd = int(name)
            if fd > 2:
                try:
                    os.fstat(fd)
                except OSError as exc:
                    if exc.errno == errno.EBADF:
                        continue
                    raise
                raise PolicyFailure("descriptor_cleanup_incomplete")
    except OSError as exc:
        raise PolicyFailure("descriptor_setup_failed", exc.errno) from None
    return {"closed_fd_count": closed, "remaining_fd_above_2": 0,
            "stdio_verified_as_pipes": True, "single_thread_verified": True}

def install_filter_in_child(lib, context) -> dict:
    '''Private entry point called only after trusted preload in --_child.'''
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        prctl = libc.prctl
    except AttributeError:
        raise PolicyFailure("prctl_unavailable") from None
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise PolicyFailure("no_new_privs_set_failed", ctypes.get_errno())
    if prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1:
        raise PolicyFailure("no_new_privs_verification_failed", ctypes.get_errno() or None)
    _checked_return(lib.seccomp_load(context), "seccomp_load_failed")
    return {"policy_installed": True, "no_new_privs_verified_before_load": True}

_ARC_POLICY_SOURCE_SHA256 = 'a8412effd96184841e5db36f1eebc2498c897063537c6c2b1a05f51237eb4251'
_ARC_POLICY_FRAGMENT_SHA256 = '2128ea88d37b9d17e1cf0b25d8ff195c173e05b8faf83ff163bbee984c376b1e'

def _arc_preload_and_install_policy():
    context, library = None, None
    try:
        if tuple(sorted(SAFE_MODULES)) != TRUSTED_SAFE_MODULES:
            raise PolicyFailure("safe_module_inventory_differs")
        for name in TRUSTED_SAFE_MODULES:
            builtins.__import__(name)
        # Complete trusted codec/JSON/native setup before any retained code.
        json.loads(json.dumps({"public_setup_warmup": True}))
        library, library_name = load_libseccomp()
        context, details = build_filter(library)
        descriptor_setup = close_inherited_descriptors()
        installed = install_filter_in_child(library, context)
        library.seccomp_release(context)
        context = None
        return {"schema_version": 1, "status": "installed_before_untrusted_code",
                "phase": "before_restore_and_exec", "policy_version": POLICY_VERSION,
                "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
                "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256,
                "trusted_safe_modules_preloaded": list(TRUSTED_SAFE_MODULES),
                "library": library_name, "policy": details,
                "descriptor_setup": descriptor_setup, **installed,
                "isolation_certified": False}
    except BaseException as exc:
        failure = (exc.record() if isinstance(exc, PolicyFailure) else
                   {"stage": "unexpected_trusted_setup_failure", "exception_type": type(exc).__name__})
        if context is not None and library is not None:
            library.seccomp_release(context)
        _send({"type": "confinement_failed", "failure": failure,
               "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
               "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256})
        os._exit(72)

import math

DEVELOPMENT_PROFILE = {
    "max_tool_seconds": 30, "address_space_bytes": 512 * 1024 * 1024,
    "file_size_bytes": 1_000_000, "open_files": 32, "core_bytes": 0,
    "max_code_bytes": 256 * 1024, "max_retained_bytes": 256 * 1024,
    "max_retained_functions": 64, "max_input_bytes": 4 * 1024 * 1024,
    "max_frame_bytes": 1024 * 1024, "max_stdout_bytes": 4 * 1024 * 1024,
    "max_stderr_bytes": 64 * 1024, "max_display_stdout_bytes": 64 * 1024,
    "max_result_bytes": 256 * 1024, "max_json_depth": 32,
    "max_json_nodes": 2_097_152, "max_messages": 256,
}

ERROR_STAGES = frozenset({
    "invalid_timeout", "code_limit", "retained_limit", "json_type", "json_depth",
    "json_nodes", "json_bytes", "json_nonfinite", "invalid_json", "frame_limit",
    "stdout_limit", "stderr_limit", "message_limit", "incomplete_frame", "decode_error",
    "deadline", "pipe_io", "resource_setup", "unsupported_resource_platform",
    "display_stdout_limit", "result_limit", "resource_report", "child_exit",
    "unexpected_host_failure", "cleanup_failed",
})

class BoundsFailure(RuntimeError):
    def __init__(self, stage, error=None):
        self.stage = stage if stage in ERROR_STAGES else "unexpected_host_failure"
        self.error = error if type(error) is int else None
        super().__init__(self.stage)

    def record(self):
        record = {"stage": self.stage}
        if self.error is not None:
            record.update(errno=self.error, errno_name=errno.errorcode.get(self.error, "UNKNOWN"))
        return record

def _walk_json(value, profile, max_bytes):
    '''Count before serialization, visiting only exact builtin JSON types.'''
    pending, nodes, string_bytes = [(value, 0)], 0, 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > profile["max_json_nodes"]:
            raise BoundsFailure("json_nodes")
        if depth > profile["max_json_depth"]:
            raise BoundsFailure("json_depth")
        kind = type(item)
        if kind is str:
            if len(item) > max_bytes:
                raise BoundsFailure("json_bytes")
            string_bytes += len(item.encode("utf-8"))
            if string_bytes > max_bytes:
                raise BoundsFailure("json_bytes")
        elif kind is float:
            if not math.isfinite(item):
                raise BoundsFailure("json_nonfinite")
        elif kind is int:
            if item.bit_length() > 4096:
                raise BoundsFailure("json_bytes")
        elif item is None or kind is bool:
            pass
        elif kind in (list, tuple):
            if len(item) + nodes + len(pending) > profile["max_json_nodes"]:
                raise BoundsFailure("json_nodes")
            pending.extend((child, depth + 1) for child in item)
        elif kind is dict:
            if 2 * len(item) + nodes + len(pending) > profile["max_json_nodes"]:
                raise BoundsFailure("json_nodes")
            for key, child in item.items():
                if type(key) is not str:
                    raise BoundsFailure("json_type")
                pending.append((key, depth + 1))
                pending.append((child, depth + 1))
        else:
            raise BoundsFailure("json_type")

def encode_json(value, profile, max_bytes):
    _walk_json(value, profile, max_bytes)
    encoded = bytearray()
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
            raw = chunk.encode("utf-8")
            if len(encoded) + len(raw) + 1 > max_bytes:
                raise BoundsFailure("json_bytes")
            encoded.extend(raw)
    except (ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise BoundsFailure("invalid_json") from exc
    encoded.extend(b"\n")
    return bytes(encoded)

def _scan_json_structure(raw, profile):
    depth, nodes, quoted, escaped, atom = 0, 0, False, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
            continue
        if byte == 34:
            quoted, atom = True, False
            nodes += 1
        elif byte in (123, 91):
            depth += 1
            nodes += 1
            atom = False
            if depth > profile["max_json_depth"]:
                raise BoundsFailure("json_depth")
        elif byte in (125, 93):
            depth -= 1
            atom = False
        elif byte in (32, 9, 10, 13, 44, 58):
            atom = False
        elif not atom:
            atom = True
            nodes += 1
        if nodes > profile["max_json_nodes"]:
            raise BoundsFailure("json_nodes")

def decode_json_line(raw, profile, max_bytes):
    if len(raw) > max_bytes:
        raise BoundsFailure("frame_limit")
    _scan_json_structure(raw, profile)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise BoundsFailure("decode_error") from exc
    try:
        value = json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError) as exc:
        raise BoundsFailure("invalid_json") from exc
    _walk_json(value, profile, max_bytes)
    return value

def validate_inputs(code, retained, timeout, profile):
    if type(timeout) is not int or not 1 <= timeout <= profile["max_tool_seconds"]:
        raise BoundsFailure("invalid_timeout")
    if type(code) is not str or len(code) > profile["max_code_bytes"] or len(code.encode()) > profile["max_code_bytes"]:
        raise BoundsFailure("code_limit")
    if retained is not None:
        if type(retained) not in (list, tuple) or len(retained) > profile["max_retained_functions"]:
            raise BoundsFailure("retained_limit")
        size = 0
        for source in retained:
            if type(source) is not str or len(source) > profile["max_retained_bytes"]:
                raise BoundsFailure("retained_limit")
            size += len(source.encode())
            if size > profile["max_retained_bytes"]:
                raise BoundsFailure("retained_limit")

def _set_limits(timeout_seconds):
    if platform.system() != "Linux" or resource is None:
        raise BoundsFailure("unsupported_resource_platform")
    targets = {
        "RLIMIT_AS": DEVELOPMENT_PROFILE["address_space_bytes"],
        "RLIMIT_CPU": timeout_seconds + 1,
        "RLIMIT_FSIZE": DEVELOPMENT_PROFILE["file_size_bytes"],
        "RLIMIT_NOFILE": DEVELOPMENT_PROFILE["open_files"],
        "RLIMIT_CORE": DEVELOPMENT_PROFILE["core_bytes"],
    }
    report = {"verified": False, "limits": {}}
    for name, maximum in targets.items():
        identifier = getattr(resource, name, None)
        if identifier is None:
            raise BoundsFailure("resource_setup")
        try:
            inherited_soft, inherited_hard = resource.getrlimit(identifier)
            soft = maximum if inherited_soft == resource.RLIM_INFINITY else min(inherited_soft, maximum)
            hard = maximum if inherited_hard == resource.RLIM_INFINITY else min(inherited_hard, maximum)
            resource.setrlimit(identifier, (soft, hard))
            effective_soft, effective_hard = resource.getrlimit(identifier)
        except (OSError, ValueError) as exc:
            raise BoundsFailure("resource_setup", getattr(exc, "errno", None)) from exc
        if not 0 <= effective_soft <= effective_hard <= maximum:
            raise BoundsFailure("resource_setup")
        report["limits"][name] = {"requested_maximum": maximum,
            "soft": effective_soft, "hard": effective_hard}
    report["verified"] = True
    return report


def _arc_resource_failed(exc):
    _send({"type": "confinement_failed", "failure": exc.record(),
           "policy_source_sha256": _ARC_POLICY_SOURCE_SHA256,
           "policy_fragment_sha256": _ARC_POLICY_FRAGMENT_SHA256})
    os._exit(73)


class _ArcBoundedStdout(io.StringIO):
    def __init__(self):
        super().__init__()
        self._arc_bytes = 0

    def write(self, value):
        if len(value) > DEVELOPMENT_PROFILE["max_display_stdout_bytes"]:
            raise BoundsFailure("display_stdout_limit")
        self._arc_bytes += len(value.encode("utf-8"))
        if self._arc_bytes > DEVELOPMENT_PROFILE["max_display_stdout_bytes"]:
            raise BoundsFailure("display_stdout_limit")
        return super().write(value)


def _arc_bounded_result(value):
    encode_json(value, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_result_bytes"])
    return value

SAFE_BUILTINS = {
    # Exception types. Only four were present, so anything narrower than
    # `except Exception` failed at the except clause and took the snippet
    # with it. These are inert classes and expose nothing; SystemExit and
    # KeyboardInterrupt stay out because the sandbox uses them for its own
    # timeout and shutdown handling.
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "EOFError",
    "IndexError",
    "KeyError",
    "LookupError",
    "NameError",
    "NotImplementedError",
    "OverflowError",
    "RecursionError",
    "StopIteration",
    "UnboundLocalError",
    "ZeroDivisionError",
    "abs",
    "all",
    "any",
    "ascii",
    "bin",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "complex",
    "dict",
    "dir",
    "divmod",
    "enumerate",
    "Exception",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "hasattr",
    "hash",
    "hex",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "oct",
    "ord",
    "pow",
    "print",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "tuple",
    "TypeError",
    "type",
    "ValueError",
    "RuntimeError",
    "zip",
}


def _send(payload):
    HOST_STDOUT.write(encode_json(payload, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_frame_bytes"]).decode("utf-8"))
    HOST_STDOUT.flush()


def _recv():
    raw = sys.stdin.buffer.readline(DEVELOPMENT_PROFILE["max_input_bytes"] + 1)
    if not raw or not raw.endswith(b"\n"):
        raise BoundsFailure("incomplete_frame")
    value = decode_json_line(raw, DEVELOPMENT_PROFILE, DEVELOPMENT_PROFILE["max_input_bytes"])
    if type(value) is not dict:
        raise BoundsFailure("json_type")
    return value


class FrameView:
    def __init__(self, *, ascii, step, level, shape, grid):
        self.ascii = ascii
        self.step = step
        self.level = level
        self.shape = tuple(shape)
        self._grid = grid
        self._segmentation = None

    @property
    def segmentation(self):
        if self._segmentation is None:
            self._segmentation = segment_layer(self._grid, COLOR_CHARS)
        return self._segmentation

    def __str__(self):
        rows, cols = self.shape
        return f"AsciiFrameView(level={self.level}, step={self.step}, shape={rows}x{cols})"

    __repr__ = __str__


class HistoryEntryView:
    def __init__(self, *, action, frame, result=None):
        self.action = action
        self.frame = frame
        self.result = dict(result) if isinstance(result, dict) else {}

    def __str__(self):
        return f"AsciiHistoryEntryView(action={self.action!r}, frame={self.frame})"

    __repr__ = __str__


class TransitionView:
    def __init__(self, *, action, before_frame, after_frame, result):
        self.action = action
        self.before_frame = before_frame
        self.after_frame = after_frame
        self.frame = after_frame
        self.result = dict(result) if isinstance(result, dict) else {}

    def __str__(self):
        return (
            "ActionTransitionView("
            f"action={self.action!r}, "
            f"before_frame={self.before_frame}, "
            f"after_frame={self.after_frame})"
        )

    __repr__ = __str__


def _frame_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    return FrameView(
        ascii=str(payload.get("ascii", "")),
        step=int(payload.get("step", 0)),
        level=int(payload.get("level", 0)),
        shape=payload.get("shape", [0, 0]),
        grid=payload.get("grid", []),
    )


def _history_from_payload(payload):
    items = []
    for entry in payload or []:
        if not isinstance(entry, dict):
            continue
        items.append(
            HistoryEntryView(
                action=str(entry.get("action", "")),
                frame=_frame_from_payload(entry.get("frame")),
                result=entry.get("result"),
            )
        )
    return items


def _transitions_from_history(history):
    transitions = []
    for index, entry in enumerate(history):
        action = str(getattr(entry, "action", "") or "").strip()
        if not action:
            continue
        before_frame = history[index - 1].frame if index > 0 else None
        transitions.append(
            TransitionView(
                action=action,
                before_frame=before_frame,
                after_frame=entry.frame,
                result=entry.result,
            )
        )
    return transitions


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _sanitize_exception(exc):
    extracted = traceback.extract_tb(exc.__traceback__)
    user_frames = [frame for frame in extracted if frame.filename == "<python_tool>"]
    lines = ["Traceback (most recent call last):"]
    for frame in user_frames or extracted[-1:]:
        lines.append(f'  File "<python_tool>", line {frame.lineno}, in {frame.name}')
    lines.append(f"{exc.__class__.__name__}: {exc}")
    return "\n".join(lines)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = str(name or "").split(".", 1)[0]
    if root not in SAFE_MODULES:
        raise ImportError(f"Module '{name}' is not allowed in the sandbox.")
    return builtins.__import__(name, globals, locals, fromlist, level)





def _normalize_actions(actions):
    if isinstance(actions, str):
        items = [actions]
    elif isinstance(actions, dict):
        items = [actions]
    elif isinstance(actions, (list, tuple)):
        items = list(actions)
    else:
        raise TypeError(
            "action(actions) expects a string, an action object, or a list of action strings/objects."
        )
    if not items:
        raise ValueError("action(actions) requires at least one action.")

    normalized = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            action_name = item.strip()
            if not action_name:
                raise ValueError(f"Action {index} is empty.")
            normalized.append({"action": action_name})
            continue
        if isinstance(item, dict):
            action_name = str(item.get("action", "")).strip()
            if not action_name:
                raise ValueError(f"Action {index} is missing an `action` field.")
            entry = {"action": action_name}
            if action_name.upper() == "MOUSE" and ("x" in item or "y" in item):
                raise ValueError(
                    f"Action {index} uses legacy MOUSE x/y fields; use row and col."
                )
            if "row" in item:
                entry["row"] = item.get("row")
            if "col" in item:
                entry["col"] = item.get("col")
            normalized.append(entry)
            continue
        raise TypeError(f"Action {index} must be a string or a dict.")
    return normalized


def main():
    try:
        _set_limits(DEVELOPMENT_PROFILE["max_tool_seconds"])
        initial = _recv()
        validate_inputs(initial.get("code"), initial.get("kept_functions"),
                        initial.get("timeout_seconds"), DEVELOPMENT_PROFILE)
    except BoundsFailure as exc:
        _arc_resource_failed(exc)
    global COLOR_CHARS
    COLOR_CHARS = str(initial.get("color_chars") or "")
    timeout_seconds = max(1, int(initial.get("timeout_seconds", 30)))
    sandbox_cwd = str(initial.get("sandbox_cwd", "")).strip()
    if sandbox_cwd:
        os.chdir(sandbox_cwd)
    try:
        _arc_resource_report = _set_limits(timeout_seconds)
    except BoundsFailure as exc:
        _arc_resource_failed(exc)
    _arc_confinement = _arc_preload_and_install_policy()
    _arc_confinement["resource_limits"] = _arc_resource_report
    _send({"type": "confinement_ready", "confinement": _arc_confinement})

    action_results = []
    stdout = _ArcBoundedStdout()
    runtime_globals = {
        "__builtins__": {
            name: getattr(builtins, name)
            for name in SAFE_BUILTINS
        },
        "result": None,
    }
    runtime_globals["__builtins__"]["__import__"] = _safe_import
    _animation_views = []

    def frame_diff(before=None, after=None):
        # Object-level diff between two frames. Defaults: previous_frame -> current_frame.
        # Returns only what changed; unchanged objects are omitted.
        if before is None:
            before = runtime_globals.get("previous_frame")
        if after is None:
            after = runtime_globals.get("current_frame")
        if before is None or after is None:
            return {"error": "need two frames (no previous_frame available?)"}
        if before.shape != after.shape:
            return {"changed_cell_count": -1, "note": "frame shapes differ; full redraw",
                    "before_shape": before.shape, "after_shape": after.shape}
        return compute_frame_diff(
            before._grid,
            after._grid,
            before.segmentation.get("nodes", []),
            after.segmentation.get("nodes", []),
        )

    def _refresh_state(state_payload):
        current_frame = _frame_from_payload(state_payload.get("current_frame"))
        history = _history_from_payload(state_payload.get("history"))
        last_action_call_result = state_payload.get("last_action_call_result")
        action_result = (
            dict(last_action_call_result) if isinstance(last_action_call_result, dict) else {}
        )
        # action_echo is printed by action(), then removed from its return value.
        # Keep the exposed call result identical across subsequent inspections.
        action_result.pop("action_echo", None)
        transitions = _transitions_from_history(history)
        last_transition = transitions[-1] if transitions else None

        runtime_globals["current_frame"] = current_frame
        runtime_globals["latest_frame"] = current_frame
        runtime_globals["history"] = history
        runtime_globals["transitions"] = transitions
        runtime_globals["last_transition"] = last_transition
        runtime_globals["previous_frame"] = (
            last_transition.before_frame if last_transition is not None else None
        )
        runtime_globals["last_action_frame"] = (
            last_transition.after_frame if last_transition is not None else None
        )
        runtime_globals["last_action"] = last_transition.action if last_transition is not None else None
        runtime_globals["frame_diff"] = frame_diff
        runtime_globals["valid_actions"] = [str(item) for item in state_payload.get("valid_actions", [])]
        runtime_globals["death_ledger"] = state_payload.get("death_ledger") or {"attempts": []}
        runtime_globals["last_action_call_result"] = action_result

    # Both refusals derive from BaseException, not Exception, so a
    # defensive `except Exception:` around action(...) - which models write
    # routinely - cannot swallow them. A refusal means the action did not
    # run at all, so the snippet's assumed state is already wrong and every
    # line after it rests on a false premise. One run treated 1500
    # consecutive refusals as proof that every cell on the board was inert.
    # StaleStateActionError below is deliberately catchable: it reports a
    # belief that MAY be stale rather than a verdict on the action.
    class KnownNoOpActionError(BaseException):
        pass  # raised INSTEAD of executing an action already proven inert here

    class KnownDeathActionError(BaseException):
        pass  # raised INSTEAD of executing an action that ended a prior attempt

    # Raised INSTEAD of executing an action this snippet has already run
    # from this exact board. Buggy loop code can spend a whole life bar
    # getting nowhere - a cursor that wraps turns RIGHT into a short cycle,
    # a mistaken `while pos < j: LEFT` walks away from its target forever -
    # and the terminal latch only stops that once the game actually ends,
    # measured at 20 to 30 wasted actions. BaseException like the two above:
    # the shape that produces these loops is `try: action(...) except
    # Exception:` inside a while, which would otherwise swallow the verdict
    # and keep going. No override slot: the snippet is not reading the
    # refusal, its code is running, and writing a new snippet IS the
    # response - the map is rebuilt per execution.
    class RepeatedActionInStateError(BaseException):
        pass

    # Raised when a PREVIOUS action in this snippet changed nothing, and the
    # snippet then tries to act again. Deliberately a plain Exception, not
    # BaseException: unlike the two refusals above this is a warning about
    # the snippet's beliefs rather than a verdict on the action, and a model
    # that has re-read current_frame may legitimately want to proceed.
    class StaleStateActionError(Exception):
        pass

    runtime_globals["KnownNoOpActionError"] = KnownNoOpActionError
    runtime_globals["KnownDeathActionError"] = KnownDeathActionError
    runtime_globals["StaleStateActionError"] = StaleStateActionError
    runtime_globals["RepeatedActionInStateError"] = RepeatedActionInStateError
    # armed when an action changes nothing; scoped to THIS snippet because
    # the closure is rebuilt per execution, so no reset path can be missed
    _stale_state: list[str] = []

    # Raised when a snippet tries to act after the attempt or level ended.
    # Derives from BaseException, not Exception, so a defensive
    # `try: action(...) except Exception:` around the call - which models
    # write routinely - cannot swallow it. Continuing to execute a path
    # computed against a board that no longer exists is never correct.
    class TerminalStateActionError(BaseException):
        pass

    runtime_globals["TerminalStateActionError"] = TerminalStateActionError
    # latched when an action reports a terminal result; scoped to THIS
    # snippet because these closures are rebuilt for every execution, so
    # no reset path can be missed and the next snippet always starts clear
    _terminal_state = []

    _TERMINAL_DETAIL = {
        "game_over": (
            "the previous action reported game_over. The level has been reset to its "
            "start, so the board you planned against is gone and this action was not "
            "executed. The next turn begins from the new state."
        ),
        "level_completed": (
            "the previous action reported level_completed. A new level has been loaded, "
            "so the board you planned against is gone and this action was not executed. "
            "The next turn begins from the new state."
        ),
        "run_complete": (
            "the previous action reported run_complete. The run is finished and this "
            "action was not executed."
        ),
    }

    def action(actions, *, prediction=None):
        if _terminal_state:
            raise TerminalStateActionError(_TERMINAL_DETAIL[_terminal_state[0]])
        normalized_actions = _normalize_actions(actions)
        if len(normalized_actions) != 1:
            raise ValueError('Prediction pilot accepts exactly one action per call.')
        _send({
            "type": "action",
            "actions": normalized_actions,
            "prediction": prediction,
            # the solver decides precedence: a known death or a known no-op
            # is a sharper message than "your state may be stale", and it
            # carries a concrete override
            "stale_after": _stale_state[0] if _stale_state else None,
        })
        reply = _recv()
        if reply.get("type") == "action_error":
            raise RuntimeError(str(reply.get("error", "action failed")))
        if reply.get("type") != "action_result":
            raise RuntimeError("Invalid action response from sandbox host.")
        action_result = reply.get("action_result") or {}
        action_results.append(action_result)
        # Cached animations describe the previous action. Invalidate the
        # existing views so aliases also refresh, even if a guard raises.
        for view in _animation_views:
            view.invalidate()
        _refresh_state(reply.get("state") or {})
        if action_result.get("stop_reason") == "reset_not_first":
            raise RuntimeError(str(action_result.get("stop_detail")))
        if action_result.get("stop_reason") == "stale_state":
            raise StaleStateActionError(
                str(action_result.get("stop_detail") or "stale state")
            )
        if action_result.get("stop_reason") == "known_death":
            raise KnownDeathActionError(
                str(action_result.get("stop_detail") or "known fatal action was not executed.")
            )
        if action_result.get("stop_reason") == "repeated_action_in_state":
            raise RepeatedActionInStateError(
                str(action_result.get("stop_detail") or "")
                or "this action was already run from this board in this snippet"
            )
        if action_result.get("stop_reason") == "known_noop":
            # nothing executed and no action was spent; halt the snippet so
            # the model re-plans instead of continuing on a false premise
            raise KnownNoOpActionError(
                str(action_result.get("stop_detail") or "known no-op action was not executed.")
            )
        for _flag in ("run_complete", "done", "level_completed", "game_over"):
            if action_result.get(_flag):
                # `done` means the run was won; report it as run_complete
                _terminal_state.append(
                    "run_complete" if _flag == "done" else _flag
                )
                break
        _echo = action_result.pop("action_echo", None)
        if _echo:
            # into the snippet's own stdout, so a loop can see what its
            # call did without waiting for the next turn's opener
            print(_echo)
        gameplay_changed = action_result.get("gameplay_changed")
        if gameplay_changed is True:
            # a real change means the snippet's beliefs are current again
            del _stale_state[:]
        if gameplay_changed is False and action_result.get("executed"):
            _executed = action_result.get("executed_actions")
            _name = (
                _executed[-1]
                if isinstance(_executed, list) and _executed
                else action_result.get("action_display")
                or action_result.get("action_name")
                or "?"
            )
            # Arm rather than raise. The action executed and changed
            # nothing, which is often exactly what the snippet went looking
            # for - it printed the board before, and wants to print it
            # after. Killing it here throws away the second half of the
            # measurement AND the batch stop's own trace, which is computed
            # and then discarded. So let the snippet finish observing, and
            # stop it only if it tries to ACT on the stale belief.
            if not _stale_state:
                _stale_state.append(str(_name))
        return action_result

    def _animation_fetch(kind):
        _send({"type": "animation", "request": {"kind": kind}})
        reply = _recv()
        if reply.get("type") == "animation_error":
            raise RuntimeError(str(reply.get("error", "animation failed")))
        if reply.get("type") != "animation_result":
            raise RuntimeError("Invalid animation response from sandbox host.")
        payload = reply.get("animation")
        if kind != "frames":
            return payload or {}
        return [
            FrameView(
                ascii=item.get("ascii", ""),
                step=item.get("step", 0),
                level=item.get("level", 0),
                shape=item.get("shape", (0, 0)),
                grid=item.get("grid", ()),
            )
            for item in (payload or [])
        ]

    runtime_globals["action"] = action
    if initial.get("animation_enabled"):
        # Globals rather than attributes on last_transition: after a death
        # the harness appends a RESET entry, so last_transition is the
        # reset and not the action that animated. The record is simply
        # "the last executed action that animated", and naming it that way
        # removes the mismatch. Empty when the last executed action
        # returned a single frame.
        class _LazyAnimation:
            def __init__(self, kind, empty):
                self._kind = kind
                self._empty = empty
                self._value = None

            def _get(self):
                if self._value is None:
                    self._value = _animation_fetch(self._kind) or self._empty
                return self._value

            def invalidate(self):
                self._value = None

            def __len__(self):
                return len(self._get())

            def __iter__(self):
                return iter(self._get())

            def __getitem__(self, key):
                return self._get()[key]

            def __bool__(self):
                return bool(self._get())

            def __contains__(self, key):
                return key in self._get()

            def keys(self):
                return self._get().keys()

            def get(self, key, default=None):
                return self._get().get(key, default)

            def __repr__(self):
                return repr(self._get())

        runtime_globals["last_animation_frames"] = _LazyAnimation("frames", [])
        runtime_globals["last_animation_timeline"] = _LazyAnimation("timeline", {})
        _animation_views.extend((runtime_globals["last_animation_frames"],
                                 runtime_globals["last_animation_timeline"]))

    _refresh_state(initial.get("state") or {})

    _persistence_enabled = bool(initial.get("persistence_enabled"))
    _retention_options = {
        "retain_imports": bool(initial.get("retain_imports")),
        "repair_hints": bool(initial.get("repair_hints")),
    }
    _kept_pool = {}
    _retention_rejected = []
    _available_names = set(runtime_globals) | set(runtime_globals["__builtins__"])
    if _persistence_enabled:
        _before_restore = dict(runtime_globals)
        try:
            _kept_pool, _retention_rejected = restore_functions(
                initial.get("kept_functions") or [], runtime_globals, _available_names,
                **_retention_options)
        except Exception:
            # Optional cache maintenance must never prevent this snippet running.
            runtime_globals.clear()
            runtime_globals.update(_before_restore)
            _kept_pool = {}
            _retention_rejected = [{"name": "all", "reason": "restoration failed; redefine needed functions"}]

    def _collect_retention_payload():
        if not _persistence_enabled:
            return {}
        try:
            kept, rejected = collect_functions(
                _code_text, _kept_pool, runtime_globals, _available_names,
                **_retention_options)
            return {
                "keepable_functions": [{"name": n, "source": src} for n, src in kept.items()],
                "retention_rejected": _retention_rejected + rejected,
            }
        except Exception:
            # Bookkeeping failures may drop helpers, but must never replace
            # the snippet's original error/output or replay its actions.
            return {"keepable_functions": [], "retention_rejected": [
                {"name": "all", "reason": "retention failed; redefine needed functions"}]}

    try:
        _code_text = str(initial.get("code", ""))
        _tree = ast.parse(_code_text, "<python_tool>")
        _last_expr = None
        if _tree.body and isinstance(_tree.body[-1], ast.Expr):
            _last_expr = ast.Expression(_tree.body[-1].value)
            ast.copy_location(_last_expr, _tree.body[-1])
            _tree.body = _tree.body[:-1]
        with contextlib.redirect_stdout(stdout):
            if _tree.body:
                exec(compile(_tree, "<python_tool>", "exec"), runtime_globals, runtime_globals)
            if _last_expr is not None:
                _value = eval(compile(_last_expr, "<python_tool>", "eval"), runtime_globals, runtime_globals)
                if _value is not None:
                    print(repr(_value))
                    if runtime_globals.get("result") is None:
                        runtime_globals["result"] = _value
        _send(
            {
                "type": "final",
                **_collect_retention_payload(),
                "stdout": stdout.getvalue(),
                "result": _arc_bounded_result(runtime_globals.get("result")),
                "action_results": _json_safe(action_results),
            }
        )
    except (
        KnownNoOpActionError,
        RepeatedActionInStateError,
        KnownDeathActionError,
        TerminalStateActionError,
        Exception,
    ) as exc:
        # The three refusals derive from BaseException so a model's own
        # `except Exception:` cannot swallow them - but THIS handler is the
        # same construct, so without naming them explicitly they escaped it
        # too, killed the child process, and the host reported a bare
        # "Sandbox process exited unexpectedly". The refusal messages - the
        # action name, that nothing was spent, how to override - were built
        # and then never delivered. They stop the snippet either way; the
        # point is that the model is told why.
        _send(
            {
                "type": "error",
                **_collect_retention_payload(),
                "error": _sanitize_exception(exc),
                "stdout": stdout.getvalue(),
                "action_results": _json_safe(action_results),
            }
        )


if __name__ == "__main__":
    main()

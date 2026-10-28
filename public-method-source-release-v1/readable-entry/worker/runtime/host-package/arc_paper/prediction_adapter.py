"""Observable-only, single-action prediction boundary (original code, MIT-0).

This module is an evaluation-host component, not a sandbox. It never loads an
environment or gives an SDK object to solver code. SDK objects are projected to
explicit public fields by ``observation_from_sdk``. The adapter must surround
the real action dispatch, before a harness performs any automatic reset.

Partial labels stay missing. A dispatch exception is *unknown execution*, not
a refusal: an action may already have executed. Callers must stop that session.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import json
import threading
import time
from typing import Any, Callable, Literal

from .predictions import EVENTS, digest, probabilities

SCHEMA_VERSION = "arc-event-prediction-v1"
Grid = tuple[tuple[int, ...], ...]
Mask = tuple[tuple[int, ...], ...]
Execution = Literal["executed", "refused", "unknown"]
ACTION_NAMES = ("RESET", *(f"ACTION{i}" for i in range(1, 8)))
MODEL_ACTIONS = {
    "UP": "ACTION1", "DOWN": "ACTION2", "LEFT": "ACTION3",
    "RIGHT": "ACTION4", "SPACE": "ACTION5", "MOUSE": "ACTION6",
    "UNDO": "ACTION7",
}


def canonical_action(action: Any) -> dict[str, Any]:
    """Strict engine action; exact click x/y payload is included in its hash."""
    if not isinstance(action, dict) or set(action) - {"name", "data"}:
        raise ValueError("action must have only name and data")
    name = action.get("name")
    data = action.get("data", {})
    if name not in ACTION_NAMES or not isinstance(data, dict):
        raise ValueError("unknown engine action or non-object data")
    if name == "ACTION6":
        if set(data) != {"x", "y"} or any(type(data[k]) is not int or not 0 <= data[k] < 64 for k in data):
            raise ValueError("ACTION6 requires exactly integer x/y in [0,63]")
    elif data:
        raise ValueError("simple actions must have empty data")
    return {"name": name, "data": dict(data)}


def duck_action(action: Any) -> dict[str, Any]:
    """Convert the documented Duck model label/row/col API, never guess x/y."""
    if not isinstance(action, dict) or set(action) - {"action", "row", "col"}:
        raise ValueError("Duck action requires action, and row/col only for MOUSE")
    label = action.get("action")
    if not isinstance(label, str):
        raise ValueError("Duck action label required")
    label = label.strip().upper()
    name = MODEL_ACTIONS.get(label, label)
    if name == "ACTION6":
        if set(action) != {"action", "row", "col"}:
            raise ValueError("MOUSE requires exactly row and col")
        data = {"x": action["col"], "y": action["row"]}
    else:
        if set(action) != {"action"}:
            raise ValueError("simple Duck action cannot carry coordinates")
        data = {}
    return canonical_action({"name": name, "data": data})


def _grid(value: Any) -> Grid:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("a frame must be a nonempty rectangular grid")
    rows = []
    width = None
    for row in value:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError("a frame must have nonempty rows")
        if width is None:
            width = len(row)
        if len(row) != width or any(type(x) is not int or not 0 <= x <= 15 for x in row):
            raise ValueError("frame cells must be rectangular ARC palette integers")
        rows.append(tuple(row))
    return tuple(rows)


def _mask(value: Any) -> Mask | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 8:
        raise ValueError("change_mask must have exactly eight rows")
    if any(not isinstance(row, (list, tuple)) or len(row) != 8
           or any(type(x) is not int or x not in (0, 1) for x in row) for row in value):
        raise ValueError("change_mask must contain 8 by 8 integer zero/one cells")
    return tuple(tuple(row) for row in value)


@dataclass(frozen=True)
class ParsedPrediction:
    status: Literal["valid", "missing", "invalid"]
    probabilities: tuple[float, float, float] | None = None
    change_mask: Mask | None = None
    reason: str | None = None


def parse_prediction(value: Any) -> ParsedPrediction:
    """Malformed predictions abstain, with an explicit reason in the trace."""
    if value is None:
        return ParsedPrediction("missing", reason="prediction_not_supplied")
    try:
        if not isinstance(value, dict) or set(value) not in (
            {"schema_version", "probabilities"},
            {"schema_version", "probabilities", "change_mask"},
        ):
            raise ValueError("prediction has missing or extra fields")
        if value["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported prediction schema version")
        probs = probabilities(value["probabilities"])
        if probs is None:
            raise ValueError("a supplied prediction requires all event probabilities")
        return ParsedPrediction("valid", probs, _mask(value.get("change_mask")))
    except (TypeError, ValueError) as exc:
        return ParsedPrediction("invalid", reason=str(exc))


def decode_request(value: str | dict[str, Any], *, duck: bool = False) -> tuple[dict[str, Any], ParsedPrediction]:
    """Decode one atomic tool request. Batches and duplicate JSON keys fail closed."""
    if isinstance(value, str):
        def unique_keys(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = item
            return result
        value = json.loads(value, object_pairs_hook=unique_keys,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON constant")))
    if not isinstance(value, dict) or set(value) - {"action", "prediction"} or "action" not in value:
        raise ValueError("one action/prediction object is required; batches are disabled")
    action = duck_action(value["action"]) if duck else canonical_action(value["action"])
    return action, parse_prediction(value.get("prediction"))


def prediction_schema() -> dict[str, Any]:
    """Schema for the prediction field; the host, not the model, assigns IDs."""
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": ["schema_version", "probabilities"],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "probabilities": {
                "type": "object", "additionalProperties": False,
                "required": list(EVENTS),
                "properties": {e: {"type": "number", "minimum": 0, "maximum": 1} for e in EVENTS},
            },
            "change_mask": {"anyOf": [
                {"type": "null"},
                {"type": "array", "minItems": 8, "maxItems": 8, "items": {
                    "type": "array", "minItems": 8, "maxItems": 8,
                    "items": {"type": "integer", "enum": [0, 1]},
                }},
            ]},
        },
    }


PREDICTION_PROMPT = """For the single next real action, optionally supply prediction with
schema_version \"arc-event-prediction-v1\" and probabilities for frame_changed,
level_completed, and attempt_failed. Each probability must be a finite number
from 0 to 1. frame_changed compares the last returned visible frame of this
action with the current final frame, including HUD pixels; level_completed
means the public completed-level count increases, including a final win;
attempt_failed means the returned public state is GAME_OVER. Predict this
executed action only, before it runs. Missing prediction means abstention.
Optional change_mask is an 8 by 8 array of integer zero/one tiles, using floor
boundaries across the entire frame. No game-specific cropping. RESET and
UNDO/ACTION7 are logged but excluded from prediction scoring. Submit one action
per call; do not embed a batch or issue further actions without a new observation.
"""


@dataclass(frozen=True)
class PublicObservation:
    episode: str
    sequence: int
    frames: tuple[Grid, ...]
    levels_completed: int | None
    state: str | None
    available_actions: tuple[str, ...] | None = None
    # For an API that explicitly combines action failure and reset, the returned
    # board is diagnostic only. The host must mark target availability; it must
    # not reconstruct a missing failure frame or derive failure from that board.
    frame_target_available: bool = True

    def __post_init__(self):
        if not isinstance(self.episode, str) or not self.episode or type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("explicit episode and nonnegative transition sequence required")
        if self.levels_completed is not None and (type(self.levels_completed) is not int or self.levels_completed < 0):
            raise ValueError("completed-level count must be nonnegative or missing")
        if self.state is not None and self.state not in {"NOT_PLAYED", "NOT_FINISHED", "GAME_OVER", "WIN"}:
            raise ValueError("unknown public state")
        if type(self.frame_target_available) is not bool:
            raise ValueError("target availability must be explicit boolean")
        # Convert nested mutable inputs to immutable validated values.
        object.__setattr__(self, "frames", tuple(_grid(frame) for frame in self.frames))
        if self.available_actions is not None:
            actions = tuple(self.available_actions)
            if any(name not in ACTION_NAMES for name in actions) or len(actions) != len(set(actions)):
                raise ValueError("invalid public legal actions")
            object.__setattr__(self, "available_actions", actions)

    @property
    def final_frame(self) -> Grid | None:
        return self.frames[-1] if self.frames and self.frame_target_available else None

    @property
    def final_frame_sha256(self) -> str | None:
        return digest(self.final_frame) if self.final_frame is not None else None

    @property
    def sha256(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode, "sequence": self.sequence,
            "frames": self.frames, "levels_completed": self.levels_completed,
            "state": self.state, "available_actions": self.available_actions,
            "frame_target_available": self.frame_target_available,
        }


def observation_from_sdk(raw: Any, *, episode: str, sequence: int,
                         frame_target_available: bool = True) -> PublicObservation:
    """Host projection of FrameDataRaw. No game ID, paths, engine, score or baseline.

    Only named documented public fields are accessed. For combined failure/reset
    APIs construct a PublicObservation with unavailable labels explicitly;
    this function does not pretend a post-reset state labels the failing action.
    """
    frames = raw.frame
    state = raw.state
    if state is not None and hasattr(state, "name"):
        state = state.name
    levels = raw.levels_completed
    available = raw.available_actions
    action_names = None
    if available is not None:
        names = []
        for action in available:
            index = action.value if hasattr(action, "value") else action
            if type(index) is not int or not 0 <= index <= 7:
                raise ValueError("invalid SDK legal action ID")
            names.append(ACTION_NAMES[index])
        action_names = tuple(names)
    return PublicObservation(episode, sequence, tuple(frames or ()), levels, state,
                             action_names, frame_target_available)


def action_from_sdk(action: Any) -> dict[str, Any]:
    """Project only the public ActionInput id/data fields."""
    return canonical_action({"name": action.id.name, "data": dict(action.data)})


def tile_changes(before: Grid, after: Grid) -> Mask | None:
    """Full-frame floor bands. Shape change has no aligned mask target."""
    if len(before) != len(after) or len(before[0]) != len(after[0]):
        return None
    h, w = len(before), len(before[0])
    return tuple(tuple(int(any(
        before[r][c] != after[r][c]
        for r in range(i * h // 8, (i + 1) * h // 8)
        for c in range(j * w // 8, (j + 1) * w // 8)
    )) for j in range(8)) for i in range(8))


@dataclass(frozen=True)
class ActionCommitment:
    id: str
    transition_id: str
    before: PublicObservation
    action_json: str
    action_sha256: str
    prediction: ParsedPrediction
    committed_monotonic_ns: int
    automatic: bool

    @property
    def action(self) -> dict[str, Any]:
        return json.loads(self.action_json)


def _synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class ActionBoundaryAdapter:
    """One in-flight transition per environment; immutable pre-action record.

    ``emit`` runs synchronously, before dispatch can be marked. A write failure
    therefore prevents dispatch. Integrators should use an append-only host log.
    IDs and exact payload must be carried through the actual dispatch callback;
    association by nearest timestamp or whichever frame arrives next is invalid.
    """
    def __init__(self, initial: PublicObservation, *, emit: Callable[[dict], None] | None = None,
                 clock: Callable[[], int] = time.monotonic_ns):
        self.current: PublicObservation | None = initial
        self.pending: ActionCommitment | None = None
        self._dispatch_ns: int | None = None
        self._counter = 0
        self._emit = emit or (lambda record: None)
        self._clock = clock
        self._lock = threading.RLock()

    def _record(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        record = {"schema_version": SCHEMA_VERSION, "event": event, **data}
        # Independent JSON-safe copy prevents a log sink mutating live state.
        self._emit(json.loads(json.dumps(record, allow_nan=False)))
        return record

    @_synchronized
    def commit(self, action: dict[str, Any], prediction: ParsedPrediction | dict | None,
               *, automatic: bool = False) -> ActionCommitment:
        if self.pending is not None:
            raise ValueError("previous committed action has no resolved receipt")
        if self.current is None:
            raise ValueError("execution or observation is unknown; stop this session")
        action = canonical_action(action)
        if type(automatic) is not bool:
            raise ValueError("automatic flag must be boolean")
        parsed = prediction if isinstance(prediction, ParsedPrediction) else parse_prediction(prediction)
        # ParsedPrediction is public; validate even manually constructed objects.
        if parsed.status == "valid":
            if not isinstance(parsed.probabilities, (tuple, list)) or len(parsed.probabilities) != 3:
                raise ValueError("valid prediction requires exactly three probabilities")
            checked = probabilities(dict(zip(EVENTS, parsed.probabilities or ())))
            if checked is None:
                raise ValueError("valid prediction requires probabilities")
            parsed = ParsedPrediction("valid", checked, _mask(parsed.change_mask), parsed.reason)
        elif parsed.status not in {"missing", "invalid"} or parsed.probabilities is not None or parsed.change_mask is not None:
            raise ValueError("invalid prediction status or abstention carrying values")
        self._counter += 1
        cid = f"C{self._counter:08d}"
        commitment = ActionCommitment(
            cid, f"{self.current.episode}:{cid}", self.current,
            json.dumps(action, sort_keys=True, separators=(",", ":")), digest(action),
            parsed, self._clock(), automatic,
        )
        data = {
            "commitment_id": cid, "transition_id": commitment.transition_id,
            "before": self.current.to_dict(), "before_sha256": self.current.sha256,
            "before_final_frame_sha256": self.current.final_frame_sha256,
            "level_identifier": self.current.levels_completed,
            "action": action, "action_sha256": commitment.action_sha256,
            "prediction_status": parsed.status, "prediction_reason": parsed.reason,
            "probabilities": dict(zip(EVENTS, parsed.probabilities)) if parsed.probabilities else None,
            "change_mask": parsed.change_mask,
            "committed_monotonic_ns": commitment.committed_monotonic_ns,
            "automatic": automatic,
        }
        self.pending = commitment
        try:
            self._record("commit", data)
        except BaseException:
            self.pending = None
            raise
        return commitment

    def _matching(self, commitment_id: str, transition_id: str, action: dict[str, Any]) -> ActionCommitment:
        pending = self.pending
        if pending is None or pending.id != commitment_id or pending.transition_id != transition_id:
            raise ValueError("unknown or already resolved action/transition ID")
        if digest(canonical_action(action)) != pending.action_sha256:
            raise ValueError("action payload differs from immutable commitment")
        return pending

    @_synchronized
    def mark_dispatched(self, commitment_id: str, transition_id: str, action: dict[str, Any]) -> int:
        pending = self._matching(commitment_id, transition_id, action)
        if self._dispatch_ns is not None:
            raise ValueError("action has already been dispatched")
        now = self._clock()
        if now <= pending.committed_monotonic_ns:
            raise ValueError("dispatch must be strictly after completed commitment")
        self._record("dispatch", {"commitment_id": pending.id, "transition_id": transition_id,
                                  "action_sha256": pending.action_sha256, "dispatched_monotonic_ns": now})
        self._dispatch_ns = now
        return now

    @_synchronized
    def resolve(self, commitment_id: str, transition_id: str, action: dict[str, Any],
                after: PublicObservation | None, *, execution: Execution,
                reason: str | None = None, echoed_action: dict[str, Any] | None = None) -> dict[str, Any]:
        pending = self._matching(commitment_id, transition_id, action)
        if execution not in {"executed", "refused", "unknown"}:
            raise ValueError("execution must be explicit executed/refused/unknown")
        if execution != "executed" and not reason:
            raise ValueError("a refused or unknown execution requires a reason")
        if execution == "executed" and self._dispatch_ns is None:
            raise ValueError("an executed action requires a dispatch record")
        if execution != "executed" and after is not None:
            raise ValueError("a nonexecuted/unknown receipt cannot label an observation")
        if echoed_action is not None and digest(canonical_action(echoed_action)) != pending.action_sha256:
            raise ValueError("returned action echo does not match committed payload")
        before = pending.before
        name = pending.action["name"]
        if after is not None:
            if name == "RESET" and after.episode != before.episode:
                if after.sequence != 0:
                    raise ValueError("new reset episode must begin at sequence zero")
            elif after.episode != before.episode or after.sequence != before.sequence + 1:
                raise ValueError("receipt must identify this immediate transition in the same episode")
            if (name not in {"RESET", "ACTION7"} and before.levels_completed is not None
                    and after.levels_completed is not None and after.levels_completed < before.levels_completed):
                raise ValueError("level count regressed without an explicit reset/undo")
        now = self._clock()
        if now < (self._dispatch_ns or pending.committed_monotonic_ns):
            raise ValueError("observation time precedes action commitment/dispatch")
        result = {
            "commitment_id": pending.id, "transition_id": transition_id,
            "action": pending.action, "action_sha256": pending.action_sha256,
            "committed_monotonic_ns": pending.committed_monotonic_ns,
            "dispatched_monotonic_ns": self._dispatch_ns,
            "observed_monotonic_ns": now, "execution": execution, "reason": reason,
            "automatic": pending.automatic, "prediction_status": pending.prediction.status,
            "prediction_reason": pending.prediction.reason,
            "prediction_probabilities": dict(zip(EVENTS, pending.prediction.probabilities))
                if pending.prediction.probabilities is not None else None,
            "after": after.to_dict() if after is not None else None,
            "after_sha256": after.sha256 if after is not None else None,
            "outcomes": {event: None for event in EVENTS},
            "event_squared_errors": {event: None for event in EVENTS},
            "available_event_count": 0, "brier_available_events_mean": None,
            "mask_target": None, "mask_residual": None, "mask_unavailable_reason": None,
        }
        if execution == "refused":
            result["status"] = "not_executed"
        elif execution == "unknown":
            result["status"] = "execution_unknown"
        elif name in {"RESET", "ACTION7"}:
            result["status"] = "reset_excluded" if name == "RESET" else "undo_excluded"
        else:
            outcomes = result["outcomes"]
            if after is not None:
                if before.final_frame is not None and after.final_frame is not None:
                    outcomes["frame_changed"] = int(before.final_frame != after.final_frame)
                if before.levels_completed is not None and after.levels_completed is not None:
                    outcomes["level_completed"] = int(after.levels_completed > before.levels_completed)
                if after.state is not None:
                    outcomes["attempt_failed"] = int(after.state == "GAME_OVER")
            result["available_event_count"] = sum(v is not None for v in outcomes.values())
            parsed = pending.prediction
            if parsed.status != "valid":
                result["status"] = "abstained"
            else:
                for event, p in zip(EVENTS, parsed.probabilities):
                    if outcomes[event] is not None:
                        result["event_squared_errors"][event] = (p - outcomes[event]) ** 2
                errors = [v for v in result["event_squared_errors"].values() if v is not None]
                result["brier_available_events_mean"] = sum(errors) / len(errors) if errors else None
                result["status"] = "scored" if len(errors) == 3 else "scored_partial" if errors else "labels_missing"
                if parsed.change_mask is None:
                    result["mask_unavailable_reason"] = "prediction_not_supplied"
                elif after is None or before.final_frame is None or after.final_frame is None:
                    result["mask_unavailable_reason"] = "target_frame_missing"
                else:
                    target = tile_changes(before.final_frame, after.final_frame)
                    result["mask_target"] = target
                    if target is None:
                        result["mask_unavailable_reason"] = "frame_shape_changed"
                    else:
                        union = sum(bool(p or y) for ps, ys in zip(parsed.change_mask, target) for p, y in zip(ps, ys))
                        difference = sum(p != y for ps, ys in zip(parsed.change_mask, target) for p, y in zip(ps, ys))
                        result["mask_residual"] = difference / union if union else 0.0
        self._record("receipt", result)
        # Refusals preserve the pre-action state; executed missing receipts and
        # uncertain execution invalidate it and deliberately halt future calls.
        if execution == "executed":
            self.current = after
        elif execution == "unknown":
            self.current = None
        self.pending = None
        self._dispatch_ns = None
        return result

    def execute(self, action: dict[str, Any], prediction: ParsedPrediction | dict | None,
                dispatch: Callable[[dict[str, Any]], Any],
                project: Callable[[Any, str, int], PublicObservation], *, automatic: bool = False,
                echo: Callable[[Any], dict[str, Any]] | None = None) -> tuple[Any, dict[str, Any]]:
        """Synchronous host hook surrounding exactly one real SDK action.

        Run legality/guard checks before this helper, logging refusals through
        commit/resolve if needed. Do not wrap a batch or an auto-resetting tool.
        A missing SDK return is uncertain, not a known unexecuted action.
        """
        c = self.commit(action, prediction, automatic=automatic)
        self.mark_dispatched(c.id, c.transition_id, c.action)
        try:
            raw = dispatch(c.action)
        except BaseException as exc:
            self.resolve(c.id, c.transition_id, c.action, None, execution="unknown",
                         reason=f"dispatch_exception:{type(exc).__name__}")
            raise
        if raw is None:
            result = self.resolve(c.id, c.transition_id, c.action, None, execution="unknown", reason="missing_dispatch_return")
            return raw, result
        try:
            after = project(raw, c.before.episode, c.before.sequence + 1)
            returned_action = echo(raw) if echo is not None else None
            result = self.resolve(c.id, c.transition_id, c.action, after, execution="executed",
                                  echoed_action=returned_action)
        except (TypeError, ValueError, AttributeError):
            # No prospective label is accepted after a malformed host projection.
            self.resolve(c.id, c.transition_id, c.action, None, execution="unknown", reason="invalid_return_projection")
            raise
        return raw, result

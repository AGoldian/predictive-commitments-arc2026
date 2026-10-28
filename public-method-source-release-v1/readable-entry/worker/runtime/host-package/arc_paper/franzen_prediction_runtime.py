"""Host hooks for the checksum-pinned Franzen instrumented control pilot.

No new scheduler is implemented here. All hooks use public SDK observations,
and never hand the game/session/adapter to the solver's Python subprocess.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable

from .evidence_history import EvidenceHistory
from .prediction_adapter import (
    ActionBoundaryAdapter, PublicObservation, action_from_sdk, duck_action,
    observation_from_sdk,
)


def _adapter(session) -> ActionBoundaryAdapter:
    existing = getattr(session, "_arc_paper_prediction_adapter", None)
    if existing is not None:
        return existing
    initial = observation_from_sdk(session.game.current_state.raw,
                                   episode=f"episode-{uuid.uuid4().hex}", sequence=0)
    path = session.state_path.with_suffix(".predictions.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never append a fresh run to an old session's evidence or truncate it.
    with path.open("x", encoding="utf-8"):
        pass
    history = EvidenceHistory(initial.episode, initial)
    session._arc_paper_evidence_history = history
    session._arc_paper_evidence_history_stopped = False

    def emit(record):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Consume only this synchronous host emitter's real-action receipts,
        # after durable logging. Never inspect child final action_results/stdout.
        if record.get("event") == "receipt":
            if record.get("execution") == "unknown":
                session._arc_paper_evidence_history_stopped = True
            else:
                history.update(record)

    adapter = ActionBoundaryAdapter(initial, emit=emit)
    session._arc_paper_prediction_adapter = adapter
    return adapter


def _request_refused(session, reason: str, arguments: dict[str, Any]) -> None:
    """Keep malformed/batched attempts without assigning fictional transitions."""
    raw_actions = arguments.get("actions")
    count = len(raw_actions) if isinstance(raw_actions, list) else 1 if "action" in arguments else None
    _adapter(session)._record("request_refused", {"reason": reason, "requested_count": count,
                                                "executed_count": 0, "outcomes": None})


def prediction_step_env(session, arguments: dict[str, Any], original: Callable[[dict], dict]) -> dict:
    """Wrap a single prospective tool action, preserving the published guards."""
    if str(arguments.get("query") or "").strip() == "prediction_integrity_error":
        session.stop_event.set()
        _adapter(session)._record("integrity_failure", {"reason": "child_action_receipt_mismatch",
                                                       "executed_count": 0})
        return {"executed": False, "stop_reason": "receipt_integrity_error"}
    if str(arguments.get("query") or "").strip() == "animation":
        return original(arguments)
    # Use the existing host normalizer for availability/exposure semantics, but
    # additionally require valid exact coordinates instead of its clamp/coercion.
    actions, error = session._normalize_actions(arguments)
    if error is not None or actions is None:
        _request_refused(session, str(error or "invalid_action_request"), arguments)
        return original(arguments)  # original error path; no engine action
    if len(actions) != 1:
        _request_refused(session, "single_action_required", arguments)
        return session._error_payload("Prediction pilot accepts exactly one real action per call.")
    if arguments.get("actions") is not None:
        requested = arguments["actions"][0]
    else:
        requested = {"action": arguments.get("action")}
        for key in ("row", "col"):
            if key in arguments:
                requested[key] = arguments[key]
    try:
        strict_action = duck_action(requested)
    except (ValueError, TypeError):
        _request_refused(session, "invalid_exact_action_syntax", arguments)
        return session._error_payload("Prediction pilot requires exact legal action/coordinate syntax.")
    if strict_action != action_from_sdk(actions[0]):
        _request_refused(session, "normalized_action_mismatch", arguments)
        return session._error_payload("Requested action differs from the actual normalized engine action.")
    adapter = _adapter(session)
    c = adapter.commit(strict_action, arguments.get("prediction"))
    result = None
    try:
        result = original(arguments)
        return result
    finally:
        # A guard/terminal refusal returns without reaching the actual engine
        # hook. There is no target observation or correctness credit for it.
        if adapter.pending is not None:
            if adapter.pending.id != c.id:
                session.stop_event.set()
                raise ValueError("prediction action association changed inside one tool call")
            reason = "pre_dispatch_exception"
            if isinstance(result, dict):
                reason = str(result.get("stop_reason") or result.get("error") or "not_dispatched")
            adapter.resolve(c.id, c.transition_id, c.action, None, execution="refused", reason=reason)


def prediction_game_action(session, action: Any, *, generated_tokens: int, automatic: bool):
    """Replace only session._execute_action's call to game.execute_action.

    The returned observation is captured synchronously before the next play-loop
    iteration can perform automatic RESET. TAAF can insert a synthetic green
    diagnostic animation frame for single-frame level changes; its final frame
    remains the SDK endpoint. This is not an isolation or competition certificate.
    """
    adapter = _adapter(session)
    canonical = action_from_sdk(action)
    if adapter.pending is None:
        # The existing warmup/death-reset path bypasses step_env; retain it as a
        # separately identified, unpredicted and excluded real transition.
        if not automatic or canonical["name"] != "RESET":
            session.stop_event.set()
            raise ValueError("real action reached dispatch without its tool-call commitment")
        c = adapter.commit(canonical, None, automatic=True)
    else:
        c = adapter.pending
        if automatic:
            session.stop_event.set()
            raise ValueError("automatic reset cannot consume a pending predicted action")
    adapter.mark_dispatched(c.id, c.transition_id, canonical)
    try:
        new_state = session.game.execute_action(action, generated_tokens=generated_tokens, uncached_input_tokens=0)
        raw = new_state.raw
        after = observation_from_sdk(raw, episode=c.before.episode, sequence=c.before.sequence + 1)
        if canonical["name"] != "RESET" and getattr(raw, "full_reset", False):
            # A post-reset board cannot label the preceding attempt. The SDK
            # field does not say why reset happened; leave all event labels
            # missing, with returned pixels retained only as diagnostics.
            after = PublicObservation(after.episode, after.sequence, after.frames,
                                      None, None, after.available_actions, False)
        adapter.resolve(c.id, c.transition_id, canonical, after, execution="executed",
                        echoed_action=action_from_sdk(raw.action_input))
    except BaseException as exc:
        session.stop_event.set()
        if adapter.pending is not None:
            adapter.resolve(c.id, c.transition_id, c.action, None, execution="unknown",
                            reason=f"game_action_exception:{type(exc).__name__}")
        raise
    return new_state

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT-0
"""One frozen fit, exact public-prefix reconstruction and one novel click.

No LLM inference, generated code, cache acquisition or game-source inspection.
--help uses only the standard library. Existing output must never be rerun.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("scripts/run_click_rewrite_probe.py", "src/arc_paper/click_rewrite.py",
           "src/arc_paper/__init__.py", "scripts/run_partial_motion_development.py",
           "scripts/local_public_game_session.py", "scripts/smoke_arc3.py")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity():
    members = {p: sha((ROOT / p).read_bytes()) for p in SOURCES}
    return {"members": members, "closure_sha256": sha(canonical(members).encode())}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode(rle):
    return [[v for v, n in row for _ in range(n)] for row in rle]


class Deadline(BaseException):
    pass


class ProbeFailure(Exception):
    """Only own fixed public reason strings; never include SDK exception text."""


def worker(request_path):
    request = json.loads(request_path.read_text())
    out = Path(request["output"])
    helper = load("click_receipts", ROOT / "scripts/run_partial_motion_development.py")
    save = helper.save
    config = json.loads(helper.read_pinned(Path(request["config"]), request["config_sha256"]))
    helper.read_pinned(Path(request["protocol"]), request["protocol_sha256"])
    prefix = json.loads(helper.read_pinned(ROOT / config["prefix"]["path"], config["prefix"]["sha256"]))
    if identity() != request["source"]:
        raise ValueError("source_changed")
    records = prefix["records"]
    slots = json.loads((out / "slots.json").read_text())
    result = {"status": "failed", "failure": None, "official_score": None,
              "LLM_calls": 0, "native_fit_calls": 0, "native_forecast_calls": 0,
              "costs": [], "prefix_matched_slots": 0, "probe_dispatched": False}
    start, cpu = time.monotonic(), time.process_time()
    arcade, observation = None, None

    def expired(signum, frame):
        raise Deadline()

    def ledger():
        save(out / "slots.json", slots, replace=True)

    def timed(stage, callback):
        began, process_cpu = time.monotonic(), time.process_time()
        try:
            return callback()
        finally:
            result["costs"].append({"stage": stage, "wall_seconds": time.monotonic() - began,
                                    "process_cpu_seconds": time.process_time() - process_cpu})

    def retain(obs, slot):
        slot["observation_sha256"] = save(out / ("observation-%02d.json" % slot["slot"]), obs)
        slot["status"] = "observed"
        ledger()

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(.001, request["deadline"] - time.monotonic() - 5))
    try:
        if len(records) != 6 or records[0]["action"] != {"action_id": 0, "data": {}}:
            raise ProbeFailure("six_record_exact_prefix_required")
        sys.path.insert(0, str(ROOT / "src"))
        from arc_paper.click_rewrite import fit, predict, choose_probe
        result["native_fit_calls"] += 1
        fitted = timed("one_fit", lambda: fit(records))
        save(out / "fitted.json", fitted)
        if fitted["status"] != "fitted" or not fitted["candidates"]:
            raise ProbeFailure("no_qualifying_rule")
        grid = decode(records[-1]["public"]["last_grid_rle"])
        action = choose_probe(fitted, grid, [r["action"] for r in records])
        if action is None:
            raise ProbeFailure("no_new_interior_probe")
        forecasts = []
        for candidate in fitted["candidates"]:
            result["native_forecast_calls"] += 1
            prediction = timed("precommit_native_forecast", lambda: predict(candidate, grid, action))
            forecasts.append({"candidate_id": candidate["id"], "prediction": prediction})
        # The single chosen geometry point must yield an actual disagreement;
        # do not search alternative points after looking at its forecasts.
        disagreements = []
        for i, left in enumerate(forecasts):
            a = {(c["row"], c["col"]): c["value"] for c in left["prediction"]["forecast"]}
            for right in forecasts[i + 1:]:
                b = {(c["row"], c["col"]): c["value"] for c in right["prediction"]["forecast"]}
                witnesses = [{"row": r, "col": c, "left": a[(r, c)], "right": b[(r, c)]}
                             for r, c in sorted(a.keys() & b.keys()) if a[(r, c)] != b[(r, c)]]
                if witnesses:
                    disagreements.append({"left": left["candidate_id"], "right": right["candidate_id"], "witnesses": witnesses})
        packet = {"action": action, "forecasts": forecasts, "disagreements": disagreements,
                  "source": request["source"], "prefix_sha256": config["prefix"]["sha256"],
                  "goal_utility": "UNKNOWN", "all_unclaimed_cells_and_metadata": "UNKNOWN"}
        slots[6].update(action=action, status="selected_not_dispatched",
                        commitment_sha256=save(out / "commitment.json", packet))
        ledger()
        if not disagreements:
            raise ProbeFailure("chosen_probe_has_no_known_cell_disagreement")
        verification = timed("verify_runtime", lambda: helper.verify_runtime_inventory(config, config["game_id"]))
        save(out / "runtime-verification.json", verification)
        loading = load("click_public_loading", ROOT / "scripts/smoke_arc3.py")
        driver = load("click_public_rle", ROOT / "scripts/local_public_game_session.py")
        from arc_agi import OperationMode
        from arcengine import GameAction

        def projection(obs):
            value = {k: obs[k] for k in ("state", "levels_completed", "available_actions")}
            value["last_grid_rle"] = driver.rle(obs["frame"][-1])
            return value

        with loading.no_network():
            arcade = timed("SDK_setup", lambda: loading.make_arcade(OperationMode.OFFLINE,
                    ROOT / "external/arc3-public-envs", out / "evaluation/scorecards"))
            if sum(e.game_id == config["game_id"] for e in arcade.get_environments()) != 1:
                raise ProbeFailure("exact_game_id_not_unique")
            slots[0].update(action=records[0]["action"], status="dispatched_result_unknown")
            ledger()
            env = timed("factory_reset", lambda: arcade.make(config["game_id"], seed=config["seed"], save_recording=False))
            if env is None:
                raise ProbeFailure("environment_missing")
            observation = loading.public_observation(env.observation_space)
            retain(observation, slots[0])
            if projection(observation) != records[0]["public"]:
                raise ProbeFailure("initial_prefix_projection_mismatch")
            result["prefix_matched_slots"] = 1
            for index, record in enumerate(records[1:], 1):
                replay = record["action"]
                if replay["action_id"] != 6 or 6 not in observation["available_actions"] or observation["state"] in ("WIN", "GAME_OVER"):
                    raise ProbeFailure("prefix_replay_not_currently_permitted")
                slots[index].update(action=replay, status="dispatched_result_unknown")
                ledger()
                observation = loading.public_observation(timed("prefix_replay_step", lambda: env.step(GameAction.from_id(6), data=replay["data"])))
                retain(observation, slots[index])
                if projection(observation) != record["public"]:
                    raise ProbeFailure("prefix_projection_mismatch")
                result["prefix_matched_slots"] += 1
            if 6 not in observation["available_actions"] or observation["state"] in ("WIN", "GAME_OVER"):
                raise ProbeFailure("probe_not_currently_permitted")
            before = observation
            slots[6]["status"] = "dispatched_result_unknown"
            result["probe_dispatched"] = True
            ledger()
            observation = loading.public_observation(timed("single_novel_probe", lambda: env.step(GameAction.from_id(6), data=action["data"])))
            retain(observation, slots[6])
            save(out / "comparison-input.json", {"before": before, "after": observation,
                "commitment_sha256": slots[6]["commitment_sha256"], "comparison_scope": "assess all known claims data-only after return"})
            result.update(status="completed", stop_reason="one_novel_probe_returned")
    except Deadline:
        result.update(status="stopped", stop_reason="work_deadline")
    except Exception as error:
        result.update(status="failed", stop_reason="unrepaired_exception", failure={"type": type(error).__name__,
                      "reason": str(error)[:160] if type(error) is ProbeFailure else None})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if arcade is not None:
            try:
                with loading.no_network():
                    timed("SDK_cleanup", arcade.close_scorecard)
            except Exception as error:
                result["cleanup_failure"] = {"type": type(error).__name__}
        ledger()
        result.update(wall_seconds=time.monotonic() - start, process_cpu_seconds=time.process_time() - cpu,
            maxrss_native_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            maxrss_unit="bytes" if sys.platform == "darwin" else "KiB",
            observed_actions=sum(s["status"] == "observed" for s in slots),
            dispatched_actions=sum(s["status"] in ("observed", "dispatched_result_unknown") for s in slots),
            final_public_state={k: observation[k] for k in ("state", "levels_completed", "available_actions")} if observation else None)
        save(out / "worker-result.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--source-closure-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--_request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._request:
        worker(args._request)
        return
    if any(getattr(args, p) is None for p in ("config", "config_sha256", "protocol", "protocol_sha256", "source_closure_sha256", "output")):
        parser.error("pinned config/protocol/source and fresh output required")
    helper = load("click_parent_receipts", ROOT / "scripts/run_partial_motion_development.py")
    save = helper.save
    config_raw = helper.read_pinned(args.config, args.config_sha256)
    protocol_raw = helper.read_pinned(args.protocol, args.protocol_sha256)
    config = json.loads(config_raw)
    source = identity()
    if config["schema"] != "click-rewrite-probe-v1" or source["closure_sha256"] != args.source_closure_sha256:
        raise ValueError("configuration_or_source_mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "evaluation").mkdir()
    save(args.output / "slots.json", [{"slot": i, "action": None, "status": "not_attempted"} for i in range(1, 8)], replace=True)
    (args.output / "frozen-config.json").write_bytes(config_raw)
    (args.output / "frozen-protocol.md").write_bytes(protocol_raw)
    request = {"config": str(args.config.resolve()), "config_sha256": args.config_sha256,
        "protocol": str(args.protocol.resolve()), "protocol_sha256": args.protocol_sha256,
        "source": source, "output": str(args.output.resolve()), "deadline": time.monotonic() + 120}
    save(args.output / "request.json", request)
    began = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    if identity() != source:
        raise ValueError("source_changed_before_spawn")
    child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--_request",
        str((args.output / "request.json").resolve())], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    timed_out = False
    try:
        child.wait(timeout=max(0, request["deadline"] - time.monotonic()))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
    receipt = {"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_wall_seconds": time.monotonic() - began, "returncode": child.returncode,
        "timed_out": timed_out, "result_present": (args.output / "worker-result.json").is_file(),
        "python": platform.python_version(), "platform": platform.platform(),
        "python_executable_sha256": sha(Path(sys.executable).resolve().read_bytes())}
    save(args.output / "parent-result.json", receipt)
    print(canonical(receipt))


if __name__ == "__main__":
    main()

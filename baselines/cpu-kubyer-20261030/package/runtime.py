#!/usr/bin/env python3
# SPDX-License-Identifier: MIT-0
"""Trusted CPU gateway owner. No SDK/solver imports until verified true rerun."""
import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
import gzip
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import logging
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen
import zipfile

sys.dont_write_bytecode = True


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def save(path, value):
    with path.open("w") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def verify_package(root, expected):
    raw = (root / "package-manifest.json").read_bytes()
    if digest(raw) != expected:
        raise ValueError("package_manifest_pin")
    manifest = json.loads(raw)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if (any(p.is_symlink() for p in root.rglob("*")) or
            {p.relative_to(root).as_posix() for p in files} != set(manifest["files_sha256"]) | {"package-manifest.json"}):
        raise ValueError("closed_package_members")
    for name, pin in manifest["files_sha256"].items():
        if digest((root / name).read_bytes()) != pin:
            raise ValueError("package_member_pin")
    if (root / "upstream/agents/b/success_prior.json").exists():
        raise ValueError("toy_prior_present")
    return json.loads((root / "config.json").read_bytes())


def dependency_report():
    """Metadata only; validate recursive active requirements without SDK imports."""
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    roots = ["arc-agi", "arcengine", "numpy", "scipy", "pandas", "pyarrow"]
    pending, seen, problems, versions = list(roots), set(), [], {}
    while pending:
        name = pending.pop().lower().replace("_", "-")
        if name in seen:
            continue
        seen.add(name)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            problems.append({"distribution": name, "reason": "missing"})
            continue
        versions[name] = {"version": dist.version,
            "METADATA_sha256": digest((dist.read_text("METADATA") or "").encode()),
            "RECORD_sha256": digest((dist.read_text("RECORD") or "").encode())}
        python_requirement = dist.metadata.get("Requires-Python")
        if python_requirement and not SpecifierSet(python_requirement).contains(sys.version.split()[0]):
            problems.append({"distribution": name, "Requires-Python": python_requirement, "actual_python": sys.version.split()[0]})
        for line in dist.requires or []:
            req = Requirement(line)
            if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                continue
            try:
                installed = metadata.version(req.name)
                if req.specifier and not req.specifier.contains(installed, prereleases=True):
                    problems.append({"distribution": name, "requirement": str(req), "installed": installed})
            except metadata.PackageNotFoundError:
                problems.append({"distribution": name, "requirement": str(req), "reason": "missing"})
            pending.append(req.name)
    return {"python": sys.version.split()[0], "distributions": versions, "problems": problems,
            "requirements_satisfied": not problems, "SDK_imported": False}


def bundled_wheel_report(wheelhouse):
    """Read only wheel bytes and distribution metadata in the supplied directory."""
    root = Path(wheelhouse)
    report = {"directory": str(root), "present": root.is_dir(), "wheels": [], "problems": [],
              "SDK_imported": False, "wheel_code_imported": False, "installed": False}
    if not report["present"]:
        return report
    resolved = root.resolve()
    for path in sorted(root.rglob("*.whl")):
        item = {"filename": path.relative_to(root).as_posix()}
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(resolved) or not path.is_file():
                raise ValueError("wheel_not_regular_within_supplied_directory")
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1048576), b""):
                    h.update(block)
            item.update(bytes=path.stat().st_size, sha256=h.hexdigest())
            with zipfile.ZipFile(path) as wheel:
                fields = [m for m in wheel.infolist() if m.filename.endswith(".dist-info/METADATA")]
                if len(fields) != 1 or fields[0].file_size > 2097152:
                    raise ValueError("wheel_metadata_count_or_size")
                raw = wheel.read(fields[0])
            meta = BytesParser().parsebytes(raw)
            item.update({"Name": meta.get("Name"), "Version": meta.get("Version"),
                "Requires-Dist": meta.get_all("Requires-Dist", []), "Requires-Python": meta.get("Requires-Python"),
                "METADATA_sha256": digest(raw)})
        except Exception as error:
            item["metadata_failure_type"] = type(error).__name__
            report["problems"].append({"filename": item["filename"], "type": type(error).__name__})
        report["wheels"].append(item)
    report["wheel_count"] = len(report["wheels"])
    return report


class Journal:
    """Same canonical newline/hash-chain/independent gzip-member format as DEV."""
    def __init__(self, path):
        self.stream = path.open("xb")
        self.n, self.previous = 0, None

    def append(self, event):
        raw = (canonical(dict(event, sequence=self.n, previous_event_sha256=self.previous)) + "\n").encode()
        self.stream.write(gzip.compress(raw, compresslevel=1, mtime=0))
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.previous, self.n = digest(raw), self.n + 1
        return self.previous

    def close(self):
        self.stream.close()


class Boundary(BaseException):
    pass


def public(raw):
    if raw is None:
        raise ValueError("SDK_return_unknown")
    return {"state": raw.state.name, "levels_completed": int(raw.levels_completed),
            "available_actions": sorted(int(a) for a in raw.available_actions),
            "frame": [g.tolist() if hasattr(g, "tolist") else g for g in raw.frame]}


def play(arcade, card, game, package, output, config, whole_deadline, solver):
    # Game identity stays in the trusted SDK owner, never in solver/proxy input.
    journal = Journal(output / "events.jsonl.gz")
    began, cpu = time.monotonic(), time.process_time()
    deadline = min(began + config["per_game_soft_seconds"], whole_deadline)
    current, agent, slots, returns = None, None, 0, 0
    result = {"status": "failed", "stop_reason": None, "failure": None, "first_WIN_slot": None,
              "maximum_levels_completed": None, "initial_levels_completed": None, "language_model_calls": 0}
    def alarm(signum, frame):
        raise Boundary("whole_work_deadline" if time.monotonic() >= whole_deadline else "per_game_soft_deadline")
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max(.001, deadline-time.monotonic()))
    def charge(a, phase):
        nonlocal slots
        if slots >= config["max_dispatches_per_game"]:
            raise Boundary("host_action_cap")
        if time.monotonic() >= deadline:
            alarm(None, None)
        journal.append({"event": "goal_snapshot", "before_slot": slots+1,
            "snapshot": dict(agent._goal_snapshot) if agent else None,
            "snapshot_scope": "last upstream decision; RESET can retain preceding snapshot"})
        slots += 1
        return journal.append({"event": "dispatch", "slot": slots, "phase": phase, "action": a,
            "before_public_sha256": digest(canonical(current).encode()) if current is not None else None})
    def retain(raw, phase, dispatched):
        nonlocal current, returns
        new = public(raw)
        journal.append({"event": "observation", "slot": slots, "phase": phase,
                        "dispatch_sha256": dispatched, "observation": new})
        current, returns = new, returns + 1
        if result["initial_levels_completed"] is None:
            result["initial_levels_completed"] = new["levels_completed"]
        result["maximum_levels_completed"] = max(new["levels_completed"], result["maximum_levels_completed"] or 0)
        if new["state"] == "WIN" and result["first_WIN_slot"] is None:
            result["first_WIN_slot"] = slots
    try:
        from arcengine import GameAction, GameState
        dispatched = charge({"action_id": 0, "data": {}}, "factory_reset")
        env = arcade.make(game, scorecard_id=card, save_recording=False)
        if env is None:
            raise ValueError("factory_return_unknown")
        retain(env.observation_space, "factory_reset", dispatched)
        primed = True
        def view():
            p = json.loads(canonical(current))
            return SimpleNamespace(state=GameState[p["state"]], levels_completed=p["levels_completed"],
                                   available_actions=p["available_actions"], frame=p["frame"])
        def step(action, data=None):
            aid, payload = action.value, {} if data is None else data
            if type(aid) is not int or aid not in range(8) or type(payload) is not dict:
                raise ValueError("invalid_public_action")
            if aid != 0 and aid not in current["available_actions"]:
                raise ValueError("action_not_advertised")
            if aid == 6:
                if (set(payload) != {"x", "y"} or any(type(v) is not int for v in payload.values()) or
                        not current["frame"] or not 0 <= payload["y"] < len(current["frame"][-1]) or
                        not 0 <= payload["x"] < len(current["frame"][-1][0])):
                    raise ValueError("invalid_public_coordinates")
            elif payload:
                raise ValueError("unexpected_action_data")
            phase = "reset" if aid == 0 else "policy"
            h = charge({"action_id": aid, "data": payload}, phase)
            retain(env.step(action, data=data), phase, h)
            return view()
        class PublicProxy:
            __slots__ = ()
            def reset(self):
                nonlocal primed
                if primed:
                    primed = False
                    return view()
                return step(GameAction.RESET)
            def step(self, action, data=None):
                return step(action, data)
        agent = solver.ObjCuriosityAgent(PublicProxy(), seed=config["agent_seed"], max_actions=512,
            max_wall_s=110, baselines=None, verbose=False, enable_goals=True)
        if not agent.success_off or agent.success.prior_info != "none (zero prior)":
            raise ValueError("success_prior_policy")
        result["upstream_report_secondary"] = agent.run()
        result.update(status="completed", stop_reason="upstream_returned")
    except Boundary as error:
        result.update(status="stopped", stop_reason=error.args[0])
    except BaseException as error:
        result.update(status="failed", stop_reason="unrepaired_exception", failure={"type": type(error).__name__})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if agent is not None:
            result["upstream_counters_secondary"] = dict(agent.stats)
            result["first_goal_action_secondary"] = agent.first_goal_action
        result.update(dispatches=slots, full_returns=returns, unresolved_dispatches=slots-returns,
            final_levels_completed=current["levels_completed"] if current else None,
            final_public_state=current["state"] if current else None,
            wall_seconds=time.monotonic()-began, CPU_seconds=time.process_time()-cpu,
            peak_RSS_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            peak_RSS_unit="KiB" if sys.platform.startswith("linux") else "bytes")
        journal.append({"event": "run_end", "status": result["status"], "stop_reason": result["stop_reason"]})
        journal.close()
        save(output / "result.json", result)
    return result


def run(package, expected_manifest, first_code):
    config = verify_package(package, expected_manifest)
    if not bool(os.getenv("KAGGLE_IS_COMPETITION_RERUN")):
        raise ValueError("true_gateway_branch_required")
    output = Path("/kaggle/working/cpu-official-receipts")
    output.mkdir(exist_ok=False)
    start, cpu = time.monotonic(), time.process_time()
    work_deadline = first_code + config["whole_wall_seconds"] - config["cleanup_reserve_seconds"]
    def whole_alarm(signum, frame):
        raise Boundary("whole_work_deadline")
    signal.signal(signal.SIGALRM, whole_alarm)
    signal.setitimer(signal.ITIMER_REAL, max(.001, work_deadline-time.monotonic()))
    arcade = card = None
    result = {"status": "failed", "flag_present": bool(os.getenv("KAGGLE_IS_COMPETITION_RERUN")),
              "branch": "competition_gateway", "language_model_calls": 0, "rows": [], "official_score": None}
    try:
        # Only two official bundled game-SDK wheels; no network or dependency upgrades.
        target = Path("/tmp/cpu-official-sdk-v1")
        if target.exists():
            raise ValueError("SDK_target_not_fresh")
        wheelhouse = Path(config["competition_wheelhouse"])
        wheels = []
        for name, version in (("arc_agi", "0.9.8"), ("arcengine", "0.9.3")):
            found = list(wheelhouse.rglob(name + "-" + version + "-*.whl"))
            if len(found) != 1:
                raise ValueError("exact_bundled_SDK_wheel_missing_or_ambiguous")
            wheels.append(found[0])
        wheel_pins = {p.name: digest(p.read_bytes()) for p in wheels}
        if wheel_pins[wheels[0].name] != config["arc_agi_wheel_sha256"]:
            raise ValueError("bundled_arc_agi_wheel_pin")
        save(output / "SDK-install-intent.json", {"wheels_sha256": wheel_pins, "offline": True, "no_deps": True})
        subprocess.run([sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
            "--no-index", "--no-deps", "--no-cache-dir", "--target", str(target), *map(str, wheels)],
            check=True, timeout=max(.001, min(120, work_deadline-time.monotonic())),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sys.path.insert(0, str(target))
        dep = dependency_report()
        save(output / "dependency-metadata.json", dep)
        if not dep["requirements_satisfied"]:
            raise ValueError("distribution_requirements_unsatisfied")
        os.chdir(package)  # Closed package has no .env/.env.example; SDK cannot read personal dotenv files.
        gateway_deadline = min(time.monotonic()+600, work_deadline)
        while True:
            try:
                with urlopen(config["gateway_base_url"].rstrip("/")+"/api/games",
                             timeout=max(.001, min(10, gateway_deadline-time.monotonic()))) as ready:
                    if ready.status == 200:
                        break
            except Exception:
                pass
            if time.monotonic() >= gateway_deadline:
                raise TimeoutError("gateway_startup_deadline")
            time.sleep(min(5, max(0, gateway_deadline-time.monotonic())))
        from arc_agi import Arcade, OperationMode
        logger = logging.getLogger("cpu.official.sdk")
        logger.disabled = True
        logging.getLogger("arc_agi.scorecard").disabled = True
        arcade = Arcade(operation_mode=OperationMode.COMPETITION, arc_base_url=config["gateway_base_url"],
            arc_api_key=config["public_gateway_fixture"], environments_dir="", recordings_dir=str(output / "private-recordings"), logger=logger)
        games = [e.game_id for e in arcade.get_environments()]
        if not games or len(set(games)) != len(games):
            raise ValueError("empty_or_duplicate_gateway_roster")
        result["rows"] = [{"ordinal": i, "game_id": game, "status": "not_started"} for i, game in enumerate(games)]
        save(output / "entry-result.json", result)
        card = arcade.create_scorecard()
        if not card:
            raise ValueError("shared_scorecard_missing")
        result["shared_scorecard_id_sha256"] = digest(card.encode())
        spec = importlib.util.spec_from_file_location("cpu_kubyer_b", package / "upstream/agents/b/__init__.py",
            submodule_search_locations=[str(package / "upstream/agents/b")])
        solver = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = solver
        spec.loader.exec_module(solver)
        for row in result["rows"]:
            if time.monotonic() >= work_deadline:
                row.update(status="not_played", stop_reason="whole_work_deadline")
                continue
            case = output / ("game-%04d" % row["ordinal"])
            case.mkdir()
            row.update(play(arcade, card, row["game_id"], package, case, config, work_deadline, solver))
            signal.signal(signal.SIGALRM, whole_alarm)
            signal.setitimer(signal.ITIMER_REAL, max(.001, work_deadline-time.monotonic()))
            save(output / "entry-result.json", result)
        result["status"] = "completed_with_actual_per_game_outcomes"
    except BaseException as error:
        result.update(status="failed", failure={"type": type(error).__name__})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if arcade is not None and card is not None:
            try:
                closed = arcade.close_scorecard(card)
                result["same_scorecard_close_called"] = True
                result["scorecard_close_returned"] = closed is not None
            except BaseException as error:
                result.update(status="failed", cleanup_failure={"type": type(error).__name__})
        result.update(runtime_wall_seconds=time.monotonic()-start, CPU_seconds=time.process_time()-cpu,
                      first_code_elapsed_seconds=time.monotonic()-first_code)
        save(output / "entry-result.json", result)
    submission = Path("/kaggle/working/submission.parquet")
    if (result["status"] == "failed" or not result.get("same_scorecard_close_called") or
            not submission.is_file() or submission.is_symlink() or submission.stat().st_size == 0):
        raise RuntimeError("actual_gateway_lifecycle_or_parquet_missing")
    save(output / "gateway-output.json", {"gateway_owned": True, "bytes": submission.stat().st_size,
        "sha256": digest(submission.read_bytes()), "same_scorecard_lifecycle": True, "official_score": None,
        "synthetic_rows_written": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--first-code-monotonic", type=float, required=True)
    args = parser.parse_args()
    try:
        run(args.package, args.manifest_sha256, args.first_code_monotonic)
    except BaseException as error:
        print(json.dumps({"status": "failed", "type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)

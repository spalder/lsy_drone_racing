#!/usr/bin/env python3
"""Bounded, detached one-candidate robustness tuning effort for expanded-soft drag_030."""

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".pixi/envs/default/bin/python"
RUNNER = ROOT / "scripts/mpcc_robustness_tuning_expanded_soft_drag030_20261104_v1.py"
ANALYZER = ROOT / "scripts/analyze_robustness_tuning_expanded_soft_drag030_20261104_v1.py"
FROZEN = ROOT / "logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1"
FROZEN_PLAN = FROZEN / "screen/plan.json"
ROUNDTRIP = ROOT / "scripts/mpcc_bound_roundtrip_20261104_v1.py"
INSTRUMENT = ROOT / "scripts/mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v2.py"
OUT = ROOT / "logs/mpcc-prediction-v1/robustness-tuning-expanded-soft-drag030-20261104-v2"
CASES = ["drag_030_parent", "drag030_slew_003"]
DIAG_SEEDS = [1603822, 1603805]
CONSTRUCTION_SEEDS = [1605100, 1605101, 1605102]
SCREEN_SEEDS = list(range(1605000, 1605030))
ENV = dict(os.environ)
ENV.update(
    ACADOS_SOURCE_DIR=str(ROOT / "acados"),
    LD_LIBRARY_PATH=str(ROOT / "acados/lib"),
    SCIPY_ARRAY_API="1",
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
)
ENV.pop("XLA_FLAGS", None)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def remaining(deadline):
    return max(0.0, deadline - time.time())


def command(args, deadline):
    args = [str(x) for x in args]
    with (OUT / "orchestrator.log").open("a") as log:
        log.write("$ " + " ".join(args) + "\n")
        log.flush()
        child = subprocess.Popen(
            args, cwd=ROOT, env=ENV, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        write(OUT / "active-command.json", {"pid": child.pid, "args": args, "started_epoch": time.time()})
        try:
            rc = child.wait(timeout=max(1.0, remaining(deadline)))
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise RuntimeError("45-minute deadline reached; child stopped")
    if rc:
        raise RuntimeError("command failed rc=" + str(rc) + ": " + " ".join(args))


def seed_plan_paths():
    paths = []
    used = set()
    for path in (ROOT / "logs").rglob("plan.json"):
        if OUT in path.parents:
            continue
        try:
            value = read(path)
        except (OSError, ValueError):
            continue
        if isinstance(value, dict):
            for key in ("seeds", "prediction_seeds"):
                if isinstance(value.get(key), list):
                    used.update(x for x in value[key] if type(x) is int)
            paths.append({"path": str(path), "sha256": sha(path)})
    return used, paths


def prepare(name, stage, seeds, prediction_seeds):
    path = OUT / name
    command([
        PYTHON, RUNNER, "prepare", "--output", path, "--parent", FROZEN_PLAN,
        "--stage", stage, "--seed-list", ",".join(map(str, seeds)),
        "--cases", ",".join(CASES), "--prediction-seeds", ",".join(map(str, prediction_seeds)),
    ], DEADLINE)
    plan = read(path / "plan.json")
    if plan["seeds"] != seeds or plan["case_order"] != CASES:
        raise RuntimeError("prepared plan differs from frozen seed/order choice")
    return path


def construction_audit(path):
    plan = read(path / "plan.json")
    libraries = []
    rows = {}
    for case in CASES:
        records = read(path / "run-v1" / case / "constructions.json")
        if [x["seed"] for x in records] != CONSTRUCTION_SEEDS:
            raise RuntimeError("construction seed order mismatch")
        rows[case] = []
        for record in records:
            if record["requested_settings"] != record["effective_settings"] or record["effective_settings"] != plan["cases"][case]:
                raise RuntimeError("construction settings mismatch")
            runtime = record["runtime"]
            if not (runtime["loaded_mapping_verified"] and runtime["getter_observable_state_preserved"]):
                raise RuntimeError("construction runtime identity/getter audit failed")
            if not runtime["initial_equality_hard"] or runtime["effective_numerics"] != plan["cases"][case]["numerics"]:
                raise RuntimeError("construction hard equality/numerics audit failed")
            if any(stage["ubx"][-1] != runtime["path_length"] for stage in runtime["stages"][1:]):
                raise RuntimeError("construction progress bound does not match live path length")
            libraries.append(runtime["library"])
            rows[case].append({"seed": record["seed"], "library": runtime["library"], "handle": runtime["handle"], "construction_s": record["construction_s"]})
    if len(libraries) != len(set(libraries)):
        raise RuntimeError("construction libraries are not unique")
    write(OUT / "construction-audit.json", {
        "status": "passed", "construction_episodes": len(libraries), "racing_episodes": 0,
        "seeds": CONSTRUCTION_SEEDS, "cases": CASES, "unique_loaded_paths": True,
        "distinct_handles_and_getter_preservation": True, "live_progress_matches_current_path": True,
        "complete_effective_settings": True, "rows": rows,
    })


def timing_budget(diag_path):
    old = FROZEN / "frozen-continuation-v1/run-v1"
    simulations = []
    constructions = []
    for case in ("drag_030", "soft_reference"):
        for record in read(old / case / "episodes.json"):
            rr = record["research_runtime"]
            simulations.append(rr["episode_s"] - rr["construction_s"])
            constructions.append(rr["construction_s"])
    for case in CASES:
        for record in read(diag_path / "run-v1" / case / "episodes.json"):
            rr = record["research_runtime"]
            simulations.append(rr["episode_s"] - rr["construction_s"])
            constructions.append(rr["construction_s"])
    max_sim = max(simulations)
    max_construction = max(constructions)
    estimate = 1.30 * len(SCREEN_SEEDS) * (max_sim + max_construction) + 600.0
    receipt = {
        "historical_and_diagnostic_max_simulation_s": max_sim,
        "unique_library_construction_cost_s": max_construction,
        "episodes": len(SCREEN_SEEDS) * len(CASES), "headroom": 1.30,
        "audit_reserve_s": 600.0, "estimate_s": estimate,
        "remaining_before_screen_s": remaining(DEADLINE),
        "selection_basis": "bounded timing evidence only; no outcome-based stopping",
    }
    write(OUT / "budget-receipt.json", receipt)
    if estimate > remaining(DEADLINE):
        raise RuntimeError("diagnostic gate passed but full 60-episode cohort is unlikely to fit the remaining deadline")


def write_report(status, reason, screen_path=None):
    summary = read(OUT / "execution-summary.json")
    lines = ["# Expanded-soft drag_030 robustness tuning", "", status, "", reason, ""]
    lines += ["Candidate: one parameter, `mpcc.attitude_slew_weight` 0.02 → 0.03. Parent and candidate retain `reference_speed=3.0`, `max_speed=3.2`, the exact expanded-soft drag_030 formulation, attitude envelope, slack penalties, hard commands/progress/dynamics, model compensation, numerical options and 1e-5 audit tolerance.", ""]
    lines += ["Mechanism selected before racing: failures were concentrated at crossing 4 (12/18); the two evidence-selected failures showed attitude saturation on 57/48 ticks and large command-slew excursions. The modest slew penalty targets abrupt attitude-command changes without reducing speed demand.", ""]
    if (OUT / "diagnostic/independent-analysis-v1/statistics.json").exists():
        stats = read(OUT / "diagnostic/independent-analysis-v1/statistics.json")
        lines += ["## Four-episode diagnostic gate", "", "```json", json.dumps(stats, indent=2), "```", ""]
    if screen_path and (screen_path / "independent-analysis-v1/statistics.json").exists():
        stats = read(screen_path / "independent-analysis-v1/statistics.json")
        pairs = read(screen_path / "independent-analysis-v1/paired.json")
        lines += ["## Fresh matched screen", "", "| Case | Finish | Exact 95% interval | Status/fallback | Constraint RTIs |", "|---|---:|---|---:|---:|"]
        for case, value in stats.items():
            lines.append(f"| {case} | {value['finishes']}/{value['n']} | {value['completion_exact95']} | {value['numerical_ticks']}/{value['fallback_ticks']} | {value['constraint_violating_RTI_solves']} |")
        lines += ["", "Paired candidate-minus-parent results; negative lap differences favor the candidate:", ""]
        for key, value in pairs.items():
            lines.append(f"- {key}: shared={value['shared_n']}, mean={value['delta_s']} s, bootstrap95={value['bootstrap95_s']}, rescues={value['rescues']}, regressions={value['regressions']}.")
        lines += ["", "Failure crossings, slack/attitude maxima and percentiles, advisory latency, instrumentation overhead, and all event lists are in `screen/independent-analysis-v1/statistics.json`; segment crossing distributions are in `screen/independent-analysis-v1/segments.json`.", ""]
        candidate = stats[CASES[1]]
        parent = stats[CASES[0]]
        qualifies = candidate["completion"] >= .4 and candidate["health_pass"]
        lines += [f"Inclusive internal observed floor: candidate {candidate['finishes']}/{candidate['n']} ({candidate['completion']:.3f}), parent {parent['finishes']}/{parent['n']} ({parent['completion']:.3f}). The separate public 50% threshold is reported in the JSON and is not a reliability proof.", "", "Conclusion: " + ("candidate has provisional evidence for separately authorized larger confirmation; parent remains frozen and no next step is automatic." if qualifies else "candidate does not show enough robustness evidence for confirmation; parent remains frozen and further diagnosis is required."), ""]
    lines += ["No promotion, confirmation, deployment, calibration racing, extra batch, parameter sweep, or real-flight execution was performed.", ""]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    (OUT / "HANDOFF.md").write_text(status + "\n\n" + reason + "\n\nNo next step was executed automatically. Read REPORT.md, execution-summary.json, frozen plans, audit receipts and compact-evidence.zip.\n")


def compact_zip():
    target = OUT / "compact-evidence.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob("*")):
            if not path.is_file() or path == target:
                continue
            if "generated" in path.parts or "failed-QPs" in path.parts or path.suffix in {".gz", ".log", ".zip", ".npz", ".so", ".o"}:
                continue
            archive.write(path, path.relative_to(OUT))


def main():
    global DEADLINE
    started = time.time()
    DEADLINE = started + 45 * 60
    OUT.mkdir(parents=True, exist_ok=False)
    screen_path = None
    status = "FAILED_INTEGRITY"
    reason = "initialization incomplete"
    try:
        used, plan_receipts = seed_plan_paths()
        if used.intersection(CONSTRUCTION_SEEDS + SCREEN_SEEDS):
            raise RuntimeError("selected seed overlaps an existing plan")
        if any(SCREEN_SEEDS[i + 1] != SCREEN_SEEDS[i] + 1 for i in range(len(SCREEN_SEEDS) - 1)):
            raise RuntimeError("screen seed order is not frozen contiguous order")
        frozen = {
            "started_epoch": started, "deadline_epoch": DEADLINE, "cases": CASES,
            "parent": str(FROZEN_PLAN), "candidate": {"parameter": "mpcc.attitude_slew_weight", "parent": 0.02, "candidate": 0.03},
            "diagnostic_seeds": DIAG_SEEDS, "construction_seeds": CONSTRUCTION_SEEDS, "screen_seeds": SCREEN_SEEDS,
            "diagnostic_episodes": 4, "screen_episodes": 60, "headroom": 1.30, "audit_reserve_s": 600,
            "seed_plan_receipts": plan_receipts, "source_hashes": {str(p): sha(p) for p in [Path(__file__), RUNNER, ANALYZER, ROUNDTRIP, INSTRUMENT, FROZEN_PLAN]},
            "environment": {k: ENV.get(k) for k in ["ACADOS_SOURCE_DIR", "LD_LIBRARY_PATH", "SCIPY_ARRAY_API", "PYTHONDONTWRITEBYTECODE", "OMP_NUM_THREADS", "XLA_FLAGS"]},
            "authorization": "Exactly four diagnostics and, if the integrity gate and timing budget pass, exactly one fresh matched 60-episode screen.",
        }
        write(OUT / "frozen-orchestration.json", frozen)
        construction = prepare("construction", "construction", CONSTRUCTION_SEEDS, [])
        command([PYTHON, RUNNER, "run", construction], DEADLINE)
        construction_audit(construction)
        diagnostic = prepare("diagnostic", "diagnostic", DIAG_SEEDS, DIAG_SEEDS)
        command([PYTHON, RUNNER, "run", diagnostic], DEADLINE)
        command([PYTHON, ANALYZER, "analyze", diagnostic], DEADLINE)
        command([PYTHON, ANALYZER, "gate", diagnostic], DEADLINE)
        gate = read(diagnostic / "gate-decision.json")
        if not gate["proceed"]:
            status = "BLOCKED"
            reason = "Four diagnostic episodes retained, but the runtime integrity/health gate failed. No screen seeds were allocated and no retuning or substitute batch was run."
        else:
            timing_budget(diagnostic)
            screen_path = prepare("screen", "screen", SCREEN_SEEDS, SCREEN_SEEDS[:2])
            command([PYTHON, RUNNER, "run", screen_path], DEADLINE)
            command([PYTHON, ANALYZER, "analyze", screen_path], DEADLINE)
            expected = len(CASES) * len(SCREEN_SEEDS)
            completed = sum(len(read(p / "episodes.json")) for p in (screen_path / "run-v1").glob("*/episodes.json"))
            if completed != expected:
                status = "PARTIAL"
                reason = f"Screen execution stopped with {completed}/{expected} episodes; incomplete screen is not completed."
            elif read(screen_path / "independent-analysis-v1/audit.json")["status"] != "passed":
                status = "FAILED_INTEGRITY"
                reason = "Independent screen audit failed after all episodes; results are not promotion evidence."
            else:
                status = "COMPLETED"
                reason = "Construction-only validation, four diagnostic episodes, and the exactly 60-episode fresh matched screen completed with independent audits passing."
    except Exception as exc:
        if status != "BLOCKED":
            status = "PARTIAL" if screen_path and (screen_path / "run-v1").exists() else "FAILED_INTEGRITY"
        reason = type(exc).__name__ + ": " + str(exc)
    finally:
        count = 0
        if screen_path and (screen_path / "run-v1").exists():
            count = sum(len(read(p)) for p in (screen_path / "run-v1").glob("*/episodes.json"))
        diagnostic_count = 0
        if (OUT / "diagnostic/run-v1").exists():
            diagnostic_count = sum(len(read(p)) for p in (OUT / "diagnostic/run-v1").glob("*/episodes.json"))
        write(OUT / "execution-summary.json", {"status": status, "reason": reason, "elapsed_s": time.time() - started, "screen_episodes_retained": count, "screen_episodes_planned": 60, "diagnostic_episodes_retained": diagnostic_count, "no_confirmation": True, "no_promotion": True, "screen": str(screen_path) if screen_path else None})
        write_report(status, reason, screen_path)
        compact_zip()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Detached, deadline-bounded MPCC prediction/adaptation campaign."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/mpcc_prediction_research.py"
PYTHON = ROOT / ".pixi/envs/default/bin/python"
OUT = ROOT / "logs/mpcc-prediction-v1/autonomous-20261104-v1"
SMOKE_SEED = 1603000
SCREEN_SEED = 1603100
SCREEN_COUNT = 30
DEADLINE_S = 7500


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def used_seeds() -> set[int]:
    used: set[int] = set()
    for path in (ROOT / "logs").rglob("plan.json"):
        try:
            value = json.loads(path.read_text())
            seeds = value.get("seeds", []) if isinstance(value, dict) else []
            used.update(s for s in seeds if type(s) is int)
        except Exception:
            continue
    return used


def run(cmd: list[str], log: Path, timeout: float | None = None) -> tuple[int, float]:
    started = time.monotonic()
    with log.open("a") as stream:
        stream.write("$ " + " ".join(cmd) + "\n")
        stream.flush()
        try:
            result = subprocess.run(cmd, cwd=ROOT, env=ENV, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
            return result.returncode, time.monotonic() - started
        except subprocess.TimeoutExpired:
            stream.write("TIMEOUT\n")
            return 124, time.monotonic() - started


def wait_for_lock(deadline: float, log: Path) -> bool:
    lock_path = ROOT / "logs/mpcc-tuning/.combination.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() < deadline:
        with lock_path.open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(5)
                continue
            fcntl.flock(lock, fcntl.LOCK_UN)
            return True
    log.write_text(log.read_text() + "lock wait exceeded deadline\n" if log.exists() else "lock wait exceeded deadline\n")
    return False


def main() -> int:
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=False)
    log = OUT / "orchestrator.log"
    occupied = used_seeds()
    proposed = {SMOKE_SEED, *range(SCREEN_SEED, SCREEN_SEED + SCREEN_COUNT)}
    if occupied.intersection(proposed):
        raise RuntimeError("fresh seed check failed: " + repr(sorted(occupied.intersection(proposed))))
    source = {
        "runner": str(RUNNER),
        "runner_sha256": sha(RUNNER),
        "parent": str(ROOT / "config/research/mpcc_prediction_v1/parent-fast.json"),
        "cases": str(ROOT / "config/research/mpcc_prediction_v1/cases.json"),
        "numerics": str(ROOT / "config/research/mpcc_prediction_v1/numerics-classical-lm.json"),
        "smoke_seed": SMOKE_SEED,
        "screen_seed_start": SCREEN_SEED,
        "seed_count": SCREEN_COUNT,
        "contact_diagnostic": {
            "status": "blocked_and_skipped",
            "reason": "The compiled JAX environment step exposes no small harness-only pre-warp contact hook; implementing one would require architecture changes beyond the preparation budget.",
            "seeds": [1606112014, 1606112004, 1606112003],
        },
        "created_utc_epoch": time.time(),
    }
    write(OUT / "frozen-orchestration.json", source)
    write(OUT / "initial-state.json", {
        "cwd": str(ROOT),
        "git_status": subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True,
                                      capture_output=True, check=False).stdout,
    })
    smoke = OUT / "smoke"
    screen = OUT / "screen"
    base = [str(PYTHON), str(RUNNER)]
    common = ["--parent", "config/research/mpcc_prediction_v1/parent-fast.json",
              "--numerics", "config/research/mpcc_prediction_v1/numerics-classical-lm.json"]
    remaining = lambda: max(1.0, DEADLINE_S - (time.monotonic() - started))
    # Separate calibration workload; production cohort is selected only from elapsed cost.
    rc, elapsed = run(base + ["prepare", "--output", str(smoke), "--stage", "smoke",
                              "--seed-start", str(SMOKE_SEED), "--seed-count", "1",
                              "--cases", "baseline,combined_example",
                              "--prediction-seeds", str(SMOKE_SEED)] + common,
                     log, min(600.0, remaining()))
    if rc == 0:
        rc, run_elapsed = run(base + ["run", str(smoke)], log, min(1200.0, remaining()))
        elapsed += run_elapsed
    if rc == 0:
        rc, _ = run(base + ["analyze", str(smoke)], log, min(600.0, remaining()))
    write(OUT / "calibration-receipt.json", {"status": "passed" if rc == 0 else "failed",
                                               "elapsed_s": elapsed,
                                               "episodes": 2,
                                               "selection_rule": "full ten-case 30-seed screen if conservative estimate fits deadline; no outcome inspection"})
    if rc != 0 or not wait_for_lock(started + remaining(), log):
        write(OUT / "execution-summary.json", {"status": "FAILED", "reason": "calibration or lock wait failed", "elapsed_s": time.monotonic()-started})
        return 1
    # Smoke runtime is used only as a cost estimate. No episode outcome is read.
    per_episode = max(10.0, elapsed / 2.0)
    estimated = per_episode * 300.0 + 900.0
    selection = "full_10x30" if estimated < remaining() - 300.0 else "reduced_10x20"
    count = 30 if selection == "full_10x30" else 20
    write(OUT / "cohort-selection.json", {"selection": selection, "seed_start": SCREEN_SEED,
                                           "seed_count": count, "cases": 10,
                                           "smoke_elapsed_s": elapsed, "per_episode_estimate_s": per_episode,
                                           "estimated_screen_s": per_episode * 10 * count + 900,
                                           "outcome_inspection": False})
    rc, _ = run(base + ["prepare", "--output", str(screen), "--stage", "screen",
                        "--seed-start", str(SCREEN_SEED), "--seed-count", str(count),
                        "--prediction-seeds", ",".join(str(SCREEN_SEED+i) for i in range(min(3, count)))] + common,
               log, min(600.0, remaining()))
    if rc == 0:
        # The runner's screen minimum is 30; never launch an invalid reduced cohort.
        if count < 30:
            rc = 125
            log.write_text(log.read_text() + "reduced cohort rejected by runner contract; no racing launched\n")
        else:
            rc, _ = run(base + ["run", str(screen)], log, max(1.0, remaining() - 300.0))
    if rc == 0 and (screen / "execution-completed.json").exists():
        rc, _ = run(base + ["analyze", str(screen)], log, max(1.0, remaining() - 30.0))
    complete = (screen / "execution-completed.json").exists() and (screen / "analysis-v1/audit.json").exists() and rc == 0
    write(OUT / "execution-summary.json", {"status": "COMPLETED" if complete else "PARTIAL",
                                           "elapsed_s": time.monotonic()-started,
                                           "screen": str(screen), "smoke": str(smoke),
                                           "episodes": 300 if complete else None,
                                           "audit": str(screen / "analysis-v1/audit.json") if complete else None,
                                           "contact_diagnostic": "skipped_blocked"})
    write(OUT / "HANDOFF.md", "# Autonomous MPCC campaign\n\n" +
          ("COMPLETED\n" if complete else "PARTIAL\n") +
          f"Smoke: {smoke}\nScreen: {screen}\nDeterministic orchestration log: {log}\n")
    return 0 if complete else 2


ENV = dict(os.environ,
           ACADOS_SOURCE_DIR=str(ROOT / "acados"),
           LD_LIBRARY_PATH=str(ROOT / "acados/lib") + (":" + os.environ["LD_LIBRARY_PATH"] if os.environ.get("LD_LIBRARY_PATH") else ""),
           SCIPY_ARRAY_API="1", PYTHONDONTWRITEBYTECODE="1",
           PATH=str(ROOT / ".pixi/envs/default/bin") + ":" + os.environ.get("PATH", ""),
           OMP_NUM_THREADS="1")

if __name__ == "__main__":
    raise SystemExit(main())

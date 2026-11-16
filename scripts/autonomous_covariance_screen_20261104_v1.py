#!/usr/bin/env python3
"""Detached bounded orchestration for the covariance and small-drag screen."""
from __future__ import annotations
import fcntl, hashlib, json, os, subprocess, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".pixi/envs/default/bin/python"
RUNNER = ROOT / "scripts/mpcc_prediction_research_covariance_20261104_v1.py"
OUT = ROOT / "logs/mpcc-prediction-v1/covariance-screen-20261104-v1"
SMOKE_SEED, SCREEN_SEED, MAX_COUNT, DEADLINE = 1603200, 1603300, 60, 7500.0
CASES = ["baseline", "scalar_kf", "kf_p0_0001", "kf_p0_0005", "kf_p0_0100",
         "kf_q_00008", "kf_q_008", "kf_r_0025", "kf_r_0400", "drag_005",
         "drag_015", "drag_030"]

ENV = dict(os.environ, ACADOS_SOURCE_DIR=str(ROOT / "acados"),
           LD_LIBRARY_PATH=str(ROOT / "acados/lib") + (":" + os.environ["LD_LIBRARY_PATH"] if os.environ.get("LD_LIBRARY_PATH") else ""),
           SCIPY_ARRAY_API="1", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
           PATH=str(ROOT / ".pixi/envs/default/bin") + ":" + os.environ.get("PATH", ""))

def write(p: Path, v: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(v, indent=2, allow_nan=False) + "\n")

def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def used_seeds() -> set[int]:
    used: set[int] = set()
    for p in (ROOT / "logs").rglob("plan.json"):
        try:
            d = json.loads(p.read_text())
            used.update(x for x in d.get("seeds", []) if type(x) is int)
        except Exception:
            pass
    return used

def command(args: list[str], log: Path, timeout: float) -> tuple[int, float]:
    t = time.monotonic()
    with log.open("a") as f:
        f.write("$ " + " ".join(args) + "\n"); f.flush()
        try:
            r = subprocess.run(args, cwd=ROOT, env=ENV, stdout=f, stderr=subprocess.STDOUT,
                               timeout=max(1.0, timeout), check=False)
            return r.returncode, time.monotonic() - t
        except subprocess.TimeoutExpired:
            f.write("TIMEOUT\n"); return 124, time.monotonic() - t

def wait_lock(until: float) -> bool:
    p = ROOT / "logs/mpcc-tuning/.combination.lock"; p.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() < until:
        with p.open("a+") as f:
            try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: time.sleep(5); continue
            fcntl.flock(f, fcntl.LOCK_UN); return True
    return False

def compact_zip(screen: Path, path: Path) -> None:
    names = ["plan.json", "run-v1/execution-manifest.json", "analysis-v1/statistics.json",
             "analysis-v1/pairwise-vs-baseline.json", "analysis-v1/prediction-summaries.json",
             "analysis-v1/audit.json", "execution-completed.json"]
    names += ["calibration-receipt.json", "cohort-selection.json", "execution-summary.json",
              "frozen-orchestration.json", "initial-state.json"]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel in names:
            p = (screen / rel) if rel in {"plan.json", "run-v1/execution-manifest.json", "analysis-v1/statistics.json",
                "analysis-v1/pairwise-vs-baseline.json", "analysis-v1/prediction-summaries.json", "analysis-v1/audit.json",
                "execution-completed.json"} else (OUT / rel)
            if p.exists(): z.write(p, rel)
        for case in CASES:
            p = screen / "run-v1" / case / "episodes.json"
            if p.exists(): z.write(p, f"run-v1/{case}/episodes.json")

def main() -> int:
    started = time.monotonic(); OUT.mkdir(parents=True, exist_ok=False); log = OUT / "orchestrator.log"
    if SMOKE_SEED in used_seeds() or used_seeds().intersection(range(SCREEN_SEED, SCREEN_SEED + MAX_COUNT)):
        raise RuntimeError("fresh seed check failed")
    write(OUT / "frozen-orchestration.json", {
        "runner": str(RUNNER), "runner_sha256": digest(RUNNER),
        "cases": str(ROOT / "config/research/mpcc_prediction_v1/covariance-screen-20261104-v1/cases.json"),
        "parent": str(ROOT / "config/research/mpcc_prediction_v1/parent-fast.json"),
        "numerics": str(ROOT / "config/research/mpcc_prediction_v1/numerics-classical-lm.json"),
        "cases_order": CASES, "smoke_seed": SMOKE_SEED, "screen_seed_start": SCREEN_SEED,
        "max_seed_count": MAX_COUNT, "contact_instrumentation": "not attempted per instruction",
        "created_epoch": time.time()})
    write(OUT / "initial-state.json", {"git_status": subprocess.run(["git", "status", "--short"], cwd=ROOT,
        text=True, capture_output=True, check=False).stdout})
    base = [str(PYTHON), str(RUNNER), "--parent", "config/research/mpcc_prediction_v1/parent-fast.json",
            "--numerics", "config/research/mpcc_prediction_v1/numerics-classical-lm.json"]
    left = lambda: max(1.0, DEADLINE - (time.monotonic() - started))
    smoke = OUT / "smoke"; screen = OUT / "screen"
    rc, smoke_prepare = command(base[:2] + ["prepare", "--output", str(smoke), "--stage", "smoke",
        "--seed-start", str(SMOKE_SEED), "--seed-count", "1", "--cases", "baseline,scalar_kf,drag_005",
        "--prediction-seeds", str(SMOKE_SEED)] + base[2:], log, min(600, left()))
    elapsed = smoke_prepare
    if rc == 0:
        rc, e = command(base[:2] + ["run", str(smoke)], log, min(1200, left())); elapsed += e
    if rc == 0: rc, _ = command(base[:2] + ["analyze", str(smoke)], log, min(600, left()))
    write(OUT / "calibration-receipt.json", {"status": "passed" if rc == 0 else "failed",
        "elapsed_s": elapsed, "episodes": 3, "outcome_inspection": False})
    if rc != 0 or not wait_lock(started + DEADLINE):
        write(OUT / "execution-summary.json", {"status": "FAILED", "reason": "calibration or lock wait failed"}); return 1
    per_episode = max(8.0, elapsed / 3.0)
    remaining = left(); chosen = next((n for n in (60, 50, 40, 30)
        if per_episode * 12 * n + 900 < remaining - 300), 30)
    write(OUT / "cohort-selection.json", {"selection": f"12x{chosen}", "seed_start": SCREEN_SEED,
        "seed_count": chosen, "per_episode_estimate_s": per_episode,
        "estimated_screen_s": per_episode * 12 * chosen + 900, "timing_only": True})
    rc, _ = command(base[:2] + ["prepare", "--output", str(screen), "--stage", "screen",
        "--seed-start", str(SCREEN_SEED), "--seed-count", str(chosen), "--cases", ",".join(CASES),
        "--prediction-seeds", ",".join(str(SCREEN_SEED+i) for i in range(min(3, chosen)))] + base[2:], log, min(600, left()))
    if rc == 0: rc, _ = command(base[:2] + ["run", str(screen)], log, max(1, left() - 300))
    if rc == 0 and (screen / "execution-completed.json").exists():
        rc, _ = command(base[:2] + ["analyze", str(screen)], log, max(1, left() - 30))
    complete = rc == 0 and (screen / "analysis-v1/audit.json").exists()
    summary = {"status": "COMPLETED" if complete else "PARTIAL", "elapsed_s": time.monotonic()-started,
               "episodes": chosen * 12 if complete else None, "screen": str(screen), "smoke": str(smoke),
               "audit": str(screen / "analysis-v1/audit.json") if complete else None}
    write(OUT / "execution-summary.json", summary)
    if complete: compact_zip(screen, OUT / "compact-results.zip")
    write(OUT / "HANDOFF.md", ("# Covariance and small-drag screen\n\n" + summary["status"] +
        f"\nScreen: {screen}\nAudit: {summary['audit']}\n"))
    return 0 if complete else 2

if __name__ == "__main__": raise SystemExit(main())

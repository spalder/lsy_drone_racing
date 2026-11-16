#!/usr/bin/env python3
"""Finalize the already-computed four-episode diagnostic gate without rerunning episodes."""
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs/mpcc-prediction-v1/robustness-tuning-expanded-soft-drag030-20261104-v2"
DIAG = OUT / "diagnostic"
FROZEN = ROOT / "logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1/frozen-continuation-v1/run-v1"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    plan = read(DIAG / "plan.json")
    stats = read(DIAG / "independent-analysis-v1/statistics.json")
    audit = read(DIAG / "independent-analysis-v1/audit.json")
    assert plan["case_order"] == ["drag_030_parent", "drag030_slew_003"]
    assert plan["seeds"] == [1603822, 1603805]
    assert audit["status"] == "passed" and audit["episodes"] == 4
    assert all(stats[c]["n"] == 2 for c in plan["case_order"])
    assert all(stats[c]["health_pass"] for c in plan["case_order"])
    gate = {
        "proceed": True,
        "all_four_required": True,
        "tolerance": 1e-5,
        "criterion": "Runtime identity/settings, zero nonzero solver-status and fallback ticks, finite valid commands, and predicted constraint compliance; ordinary racing failure is data.",
        "statistics": stats,
        "independent_audit": audit,
        "receipt_repair": "The first gate invocation attempted to rerun a completed idempotent analysis and hit an existing-output error; this receipt consumes the already-passed independent audit and does not rerun any episode.",
        "source_sha256": sha(Path(__file__)),
    }
    write(DIAG / "gate-decision.json", gate)
    sim = []
    construction = []
    for case in ("drag_030", "soft_reference"):
        for record in read(FROZEN / case / "episodes.json"):
            rr = record["research_runtime"]
            sim.append(rr["episode_s"] - rr["construction_s"])
            construction.append(rr["construction_s"])
    for case in plan["case_order"]:
        for record in read(DIAG / "run-v1" / case / "episodes.json"):
            rr = record["research_runtime"]
            sim.append(rr["episode_s"] - rr["construction_s"])
            construction.append(rr["construction_s"])
    estimate = 1.30 * 60 * (max(sim) + max(construction)) + 600.0
    write(OUT / "budget-receipt.json", {
        "historical_and_diagnostic_max_simulation_s": max(sim),
        "unique_library_construction_cost_s": max(construction),
        "episodes": 60, "headroom": 1.30, "audit_reserve_s": 600.0,
        "estimate_s": estimate, "remaining_after_diagnostics_s": 45 * 60 - (time.time() - read(OUT / "frozen-orchestration.json")["started_epoch"]),
        "selection_basis": "bounded timing evidence only; no outcome-based stopping",
    })


if __name__ == "__main__":
    main()

"""Re-read frozen v2 screen records and recalculate outcome, timing and selection."""

# ruff: noqa: ANN001, ANN201, D103, E501
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np


def audit(directory):
    root = Path(directory)
    plan = json.loads((root / "plan.json").read_text())
    episodes = json.loads((root / "episodes.json").read_text())
    assert json.loads((root / "status.json").read_text())["status"] == "completed"
    assert len(episodes) == len(plan["cases"]) * len(plan["seeds"])
    for path, expected in plan["hashes"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    groups, summary = {}, {}
    for name, case in plan["cases"].items():
        rows = [e for e in episodes if e["case"] == name]
        assert [e["seed"] for e in rows] == plan["seeds"]
        groups[name] = {e["seed"]: e for e in rows}
        for e in rows:
            assert e["effective_settings"] == case["settings"]
            assert e["environment_kind"] == plan["environment_kind"]
            assert (e["outcome"] == "success") == (e["gates_passed"] == 5)
            assert 1 <= e["steps"] <= 1500
            assert e["official_time_s"] == (e["steps"] - 1) / 50
            assert e["completed_step_time_s"] == e["steps"] / 50
            assert e["penalized_time_s"] == (e["steps"] / 50 if e["outcome"] == "success" else 30)
            d = e["compute_durations_ms"]
            assert len(d) == e["steps"] == len(e["solver_statuses"])
            assert np.isfinite(d).all() and min(d) >= 0
            assert e["control_p99_ms"] == float(np.percentile(d, 99))
            assert e["control_max_ms"] == max(d)
            assert e["control_overruns"] == sum(t > 20 for t in d)
            assert e["failed_solve_ticks"] == len(e["failed_solve_indices"])
            assert all(
                s == 0 or i in e["failed_solve_indices"] for i, s in enumerate(e["solver_statuses"])
            )
        successes = [e for e in rows if e["outcome"] == "success"]
        failures = sum(e["failed_solve_ticks"] for e in rows)
        fraction = sum(e["control_overruns"] for e in rows) / sum(e["steps"] for e in rows)
        summary[name] = dict(
            finishes=len(successes),
            total=len(rows),
            successful_mean_s=float(np.mean([e["completed_step_time_s"] for e in successes]))
            if successes
            else None,
            penalized_mean_s=float(np.mean([e["penalized_time_s"] for e in rows])),
            failed_solve_ticks=failures,
            max_episode_p99_ms=max(e["control_p99_ms"] for e in rows),
            compute_max_ms=max(e["control_max_ms"] for e in rows),
            overrun_fraction=fraction,
            eligible=failures == 0
            and all(e["control_p99_ms"] <= 20 for e in rows)
            and fraction <= 0.01,
        )
    comparisons = {}
    for a, b in itertools.combinations(groups, 2):
        sa = {s for s, e in groups[a].items() if e["outcome"] == "success"}
        sb = {s for s, e in groups[b].items() if e["outcome"] == "success"}
        shared = sorted(sa & sb)
        delta = (
            float(
                np.mean(
                    [
                        groups[b][s]["completed_step_time_s"]
                        - groups[a][s]["completed_step_time_s"]
                        for s in shared
                    ]
                )
            )
            if shared
            else None
        )
        base = (
            float(np.mean([groups[a][s]["completed_step_time_s"] for s in shared]))
            if shared
            else None
        )
        comparisons[b + " vs " + a] = dict(
            rescues=sorted(sb - sa),
            regressions=sorted(sa - sb),
            shared_seeds=shared,
            shared_n=len(shared),
            paired_delta_s=delta,
            paired_cost_percent=100 * delta / base if shared else None,
            penalized_delta_s=summary[b]["penalized_mean_s"] - summary[a]["penalized_mean_s"],
        )
    recommended = "A"
    if "A" in groups:
        eligible = [
            n
            for n in groups
            if n != "A"
            and summary[n]["eligible"]
            and summary[n]["finishes"] > max(10, summary["A"]["finishes"])
            and comparisons[n + " vs A"]["shared_n"] >= 5
            and comparisons[n + " vs A"]["paired_cost_percent"] <= 2
        ]
        if eligible:
            recommended = sorted(
                eligible,
                key=lambda n: (
                    -summary[n]["finishes"],
                    comparisons[n + " vs A"]["paired_cost_percent"],
                    n,
                ),
            )[0]
    pareto = [
        a
        for a in summary
        if summary[a]["eligible"]
        and not any(
            summary[b]["eligible"]
            and summary[b]["finishes"] >= summary[a]["finishes"]
            and summary[b]["penalized_mean_s"] <= summary[a]["penalized_mean_s"]
            and (
                summary[b]["finishes"] > summary[a]["finishes"]
                or summary[b]["penalized_mean_s"] < summary[a]["penalized_mean_s"]
            )
            for b in summary
            if b != a
        )
    ]
    result = dict(
        status="passed",
        environment_kind=plan["environment_kind"],
        summary=summary,
        comparisons=comparisons,
        recommendation=recommended,
        pareto=pareto,
        completion_contrast_D_minus_B_minus_C_plus_A=(
            summary["D"]["finishes"]
            - summary["B"]["finishes"]
            - summary["C"]["finishes"]
            + summary["A"]["finishes"]
        )
        if "D" in summary
        else None,
        episodes_sha256=hashlib.sha256((root / "episodes.json").read_bytes()).hexdigest(),
        infrastructure_exceptions=0,
        timing_exclusions="Controller initialization, environment stepping and callbacks excluded; parent compute calls only. No population reliability claim; no pooling.",
    )
    (root / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    with (root / "summary.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=["case"] + list(next(iter(summary.values()))))
        writer.writeheader()
        writer.writerows(dict(case=n, **s) for n, s in summary.items())
    with (root / "episodes.csv").open("w") as f:
        keys = [
            "case",
            "seed",
            "outcome",
            "steps",
            "official_time_s",
            "completed_step_time_s",
            "penalized_time_s",
            "failed_solve_ticks",
            "control_p99_ms",
            "control_max_ms",
            "control_overruns",
        ]
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(episodes)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    audit(parser.parse_args().directory)

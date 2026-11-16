"""One-factor MPCC robustness study with isolated solver workers and fresh seeds."""

# Long report-table strings are intentionally kept intact.
# ruff: noqa: E501

import argparse
import csv
import fcntl
import time
from copy import deepcopy
from pathlib import Path

from scripts import overnight_mpcc as h
from scripts.overnight_mpcc_analysis import paired

GRIDS = dict(
    contour_weight=[400, 600, 800],
    horizon_steps=[40, 50, 60],
    over_gate_lift=[0.10, 0.15, 0.20],
    attitude_slew_weight=[0.01, 0.02, 0.04],
    max_angle=[0.60, 0.65, 0.70],
)
PARENT = h.ROOT / "logs/mpcc-tuning/speed-safety-revised-20261103/fresh_validation/report.json"
PREP = h.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"


def matrix(base: dict) -> dict:
    """Create exactly eleven full configs, deduplicating the shared baseline."""
    cases = {"baseline": deepcopy(base)}
    for parameter, values in GRIDS.items():
        section = "mpcc_experiment" if parameter == "over_gate_lift" else "mpcc"
        for value in values:
            if value == base["controller"][section][parameter]:
                continue
            config = deepcopy(base)
            config["controller"][section][parameter] = value
            cases[f"{parameter}_{value}"] = config
    assert len(cases) == 11
    return cases


def export(path: Path, rows: list[dict]) -> None:
    """Save complete structured rows to CSV."""
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(output: Path) -> None:
    """Recalculate race, fixed-config and latency evidence and write per-field tables."""
    plan = h.read(output / "plan.json")
    report = h.read(output / "report.json")
    assert report["status"] == "completed"
    assert len(report["evaluations"]) == 11
    for file, expected in plan["manifest"]["source_sha256"].items():
        assert h.sha(h.ROOT / file) == expected
    assert h.sha(Path(__file__)) == plan["driver_sha256"]
    assert h.sha(PARENT) == plan["parent_sha256"]
    seeds = plan["seeds"]
    assert len(seeds) == len(set(seeds)) == 20
    assert plan["cases"] == matrix(plan["cases"]["baseline"])
    for e in report["evaluations"]:
        assert e["config"] == plan["cases"][e["configuration"]]
        xs = e["episodes"]
        assert [x["seed"] for x in xs] == seeds
        s = e["summary"]
        success = [x["elapsed_s"] for x in xs if x["outcome"] == "success"]
        assert s["completed"] == len(success)
        assert s["completion_rate"] == len(success) / 20
        if success:
            assert abs(sum(success) / len(success) - s["average_success_time_s"]) < 1e-10
        else:
            assert s["average_success_time_s"] is None
        penalty = sum(x["elapsed_s"] if x["outcome"] == "success" else 30 for x in xs) / 20
        assert abs(penalty - s["penalized_mean_s"]) < 1e-10
        assert sum(x["failed_solve_ticks"] for x in xs) == s["failed_solve_ticks"]
        p99 = max(x["whole_call_p99_ms"] for x in xs)
        over = sum(x["whole_call_overruns"] for x in xs) / sum(x["steps"] for x in xs)
        assert p99 == s["max_episode_p99_ms"] and over == s["overrun_fraction"]
        assert s["latency_eligible"] == (p99 <= 20 and over <= 0.01)
        for x in xs:
            assert x["outcome"] in ("success", "terminated", "timeout")
            assert (x["gates_passed"] == 5) == (x["outcome"] == "success")
            assert x["elapsed_s"] == x["steps"] / 50 and 0 < x["steps"] <= 1500
            assert x["effective_settings"] == dict(
                mpcc=e["config"]["controller"]["mpcc"],
                mpcc_experiment=e["config"]["controller"]["mpcc_experiment"],
            )
    ref = report["evaluations"][0]
    assert ref["configuration"] == "baseline"
    comparisons = {
        e["configuration"]: paired(ref, e, bootstrap=True) for e in report["evaluations"]
    }
    h.write_report(output / "comparisons.json", comparisons)
    export(
        output / "summary.csv",
        [dict(configuration=e["configuration"], **e["summary"]) for e in report["evaluations"]],
    )
    export(
        output / "episodes.csv",
        [
            dict(configuration=e["configuration"], **x)
            for e in report["evaluations"]
            for x in e["episodes"]
        ],
    )
    export(output / "comparisons.csv", [dict(configuration=k, **v) for k, v in comparisons.items()])
    lines = [
        "# MPCC one-factor robustness study",
        "",
        "**Exploratory: 20 fresh matched seeds per configuration; no combinations.**",
        f"220 episodes completed in {report['elapsed_wall_s'] / 60:.2f} minutes including preparation before launch; seeds {seeds[0]}–{seeds[-1]}.",
        "Fixed speed 2.2/2.5, recentering 0.25, obstacle clearance 0.26, observed override None. Baseline lift 0.15; every variant changes exactly one requested parameter.",
        "Successful means use each configuration's own successful subset; paired differences condition on shared finishes. Negative differences mean faster. Do not pool these means.",
        "Every unsuccessful race receives a fixed 30 s score. Numerical failures and latency are separate from completion; infrastructure errors are never converted into races.",
        "",
    ]
    nominations = {}
    for parameter, values in GRIDS.items():
        section = "mpcc_experiment" if parameter == "over_gate_lift" else "mpcc"
        rows = []
        for value in values:
            e = next(
                e
                for e in report["evaluations"]
                if e["configuration"]
                == (
                    "baseline"
                    if value == ref["config"]["controller"][section][parameter]
                    else f"{parameter}_{value}"
                )
            )
            rows.append((value, e, comparisons[e["configuration"]]))
        lines += [
            f"## {parameter}",
            "",
            "| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for value, e, c in rows:
            s = e["summary"]
            d = c["paired_mean_s"]
            avg = s["average_success_time_s"]
            lines.append(
                f"| {value} | {s['completed']}/20 ({s['completion_rate']:.0%}) | {avg if avg is None else f'{avg:.4f}'} | {d if d is None else f'{d:+.4f}'} ({len(c['shared_success_seeds'])}) | {c['rescued_seeds']} | {c['regressed_seeds']} | {s['failed_solve_ticks']} | {s['max_episode_p99_ms']:.3f} | {s['latency_eligible']} | {s['penalized_mean_s']:.4f} |"
            )
        eligible = [
            row
            for row in rows
            if row[1]["summary"]["failed_solve_ticks"] == 0
            and row[1]["summary"]["latency_eligible"]
        ]
        ranked = sorted(
            eligible,
            key=lambda row: (
                -row[1]["summary"]["completed"],
                row[2]["paired_mean_s"] if row[2]["paired_mean_s"] is not None else float("inf"),
                abs(row[0] - ref["config"]["controller"][section][parameter]),
            ),
        )
        if not ranked:
            lines += [
                "",
                "No numerically/latency-eligible value in this cohort. Do not nominate a winner.",
                "",
            ]
            continue
        value, e, c = ranked[0]
        gain = e["summary"]["completed"] - ref["summary"]["completed"]
        d = c["paired_mean_s"]
        speed = d is not None and d < 0
        category = (
            "both"
            if gain > 0 and speed
            else "completion"
            if gain > 0
            else "speed"
            if speed
            else "neither"
        )
        nominations[parameter] = dict(
            value=value, completion_gain=gain, paired_delta_s=d, category=category
        )
        lines += [
            "",
            f"Most promising eligible value: **{value}**. Improved **{category}** relative to baseline; finish-count change {gain:+d}/20. Selection prioritizes more finishes then smaller paired time cost.",
            f"Tradeoff/uncertainty: paired-speed bootstrap 95% interval {c.get('paired_mean_bootstrap_95ci_s')}; only {len(c['shared_success_seeds'])} shared finishes. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.",
            "",
        ]
    lines += [
        "## Recommendation for later work",
        "",
        "The nominated values above are candidates for a later combination study only. Interactions are untested; no combinations were executed, no defaults changed, and nothing deployed.",
        "Bootstrap intervals use 10,000 paired-seed resamples with RNG seed 20261102. Completion tests in comparisons.json are exploratory and unadjusted. Whole-call controller timing excludes initialization, environment stepping and callbacks.",
        "Data: plan.json contains frozen exact configs, cohort and provenance; report.json contains committed episodes; summary.csv, episodes.csv and comparisons.json/csv contain the comparison evidence. simulation.log retains native diagnostics. audit.json records validation.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    h.write_report(output / "recommendations.json", nominations)
    h.write_report(
        output / "audit.json",
        dict(
            status="passed",
            episodes=220,
            report_sha256=h.sha(output / "report.json"),
            driver_sha256=h.sha(Path(__file__)),
        ),
    )
    print("AUDIT PASSED", output, flush=True)


def main() -> None:
    """Freeze and execute or independently audit a completed run."""
    started = time.time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "audit"])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if args.action == "audit":
        audit(output)
        return
    _, _, manifest = h.load_prepared(PREP)
    prior = h.read(PARENT)["evaluations"][1]
    base = prior["config"]
    assert base["controller"]["mpcc"]["reference_speed"] == 2.2
    assert base["controller"]["mpcc"]["max_speed"] == 2.5
    assert base["controller"]["mpcc_experiment"] == dict(
        gate_center_snap=0.25, over_gate_lift=0.15, observed_obstacle_clearance=None
    )
    with (h.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        used, evidence = h.fresh_inventory()
        seeds = list(range(max(used) + 100, max(used) + 120))
        assert not set(seeds) & used
        base = deepcopy(base)
        base["env"]["seed"] = seeds[0]
        cases = matrix(base)
        output.mkdir(parents=True, exist_ok=False)
        plan = dict(
            seeds=seeds,
            cases=cases,
            manifest=manifest,
            driver_sha256=h.sha(Path(__file__)),
            parent_sha256=h.sha(PARENT),
            freshness=evidence,
            started_epoch=started,
            deadline_epoch=started + 27 * 60,
            reporting_reserve_minutes=3,
        )
        h.write_report(output / "plan.json", plan)
        report = dict(status="running", evaluations=[], infrastructure_errors=[])
        print("OUTPUT", output, flush=True)
        try:
            for label, config in cases.items():
                e = dict(configuration=label, config=config, episodes=[])
                report["evaluations"].append(e)
                h.write_report(output / "report.json", report)
                with (output / "simulation.log").open("a", buffering=1) as log:
                    for x in h.configuration_episodes(
                        h.ConfigDict(config), seeds, plan["deadline_epoch"], log
                    ):
                        e["episodes"].append(x)
                        h.write_report(output / "report.json", report)
                if len(e["episodes"]) != 20:
                    report["status"] = "incomplete_budget"
                    break
                e["summary"] = h.summary(e["episodes"])
                print(label, e["summary"], flush=True)
            else:
                report["status"] = "completed"
        except BaseException as error:
            report["status"] = "infrastructure_error"
            report["infrastructure_errors"].append(repr(error))
            raise
        finally:
            report["elapsed_wall_s"] = time.time() - started
            h.write_report(output / "report.json", report)
        if report["status"] == "completed":
            audit(output)


if __name__ == "__main__":
    main()

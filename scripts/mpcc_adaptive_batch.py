"""Checkpointed adaptive MPCC batches; orchestration decisions stay explicit in requests."""

# Long report strings preserve readable tables.
# ruff: noqa: E501

import argparse
import csv
import fcntl
import signal
import time
from copy import deepcopy
from pathlib import Path

from scripts import overnight_mpcc as h
from scripts.overnight_mpcc_analysis import paired

PREP = h.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"
PARENT = h.ROOT / "logs/mpcc-tuning/speed-safety-revised-20261103/fresh_validation/report.json"
STOP = False
BOUNDS = dict(
    reference_speed=(1.2, 3.0),
    max_speed=(1.5, 3.5),
    horizon_steps=(20, 70),
    contour_weight=(100, 1200),
    lag_weight=(100, 1200),
    progress_weight=(3, 36),
    max_angle=(0.5, 0.8),
    attitude_rate_weight=(0.025, 0.3),
    attitude_slew_weight=(0.005, 0.06),
    thrust_slew_weight=(0.025, 0.3),
    terminal_weight=(0.05, 0.6),
)


def stop_requested(_signal: int, _frame: object) -> None:
    """Finish the active episode, checkpoint it, then stop before acknowledging another."""
    global STOP
    STOP = True


def config_for(base: dict, changes: dict) -> dict:
    """Permit existing optimizer/geometry settings only, with explicit bounded values."""
    c = deepcopy(base)
    geometry = {
        "gate_center_snap": (0.0, 1.0),
        "over_gate_lift": (0.0, 0.3),
        "observed_obstacle_clearance": (0.20, 0.45),
    }
    for k, v in changes.items():
        if k in geometry:
            assert (
                v is None
                and k == "observed_obstacle_clearance"
                or isinstance(v, (float, int))
                and geometry[k][0] <= v <= geometry[k][1]
            )
            c["controller"]["mpcc_experiment"][k] = v
        else:
            limits = (0.20, 0.45) if k == "obstacle_clearance" else BOUNDS.get(k)
            assert limits is not None and limits[0] <= v <= limits[1], (k, v)
            c["controller"]["mpcc"][k] = v
    n = c["controller"]["mpcc"]["horizon_steps"]
    assert int(n) == n
    return c


def export(path: Path, rows: list[dict]) -> None:
    """Write tabular raw or summary evidence."""
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(output: Path) -> dict:
    """Re-read committed records and independently recompute eligibility and scores."""
    plan = h.read(output / "plan.json")
    r = h.read(output / "report.json")
    assert r["status"] == "completed"
    assert len(r["evaluations"]) == len(plan["cases"])
    for file, expected in plan["manifest"]["source_sha256"].items():
        assert h.sha(h.ROOT / file) == expected
    assert h.sha(Path(__file__)) == plan["driver_sha256"]
    _, _, runtime = h.load_prepared(PREP)
    assert runtime == plan["manifest"]
    from scipy.stats import beta

    intervals = {}
    for e in r["evaluations"]:
        assert e["config"] == plan["cases"][e["configuration"]]
        xs = e["episodes"]
        assert [x["seed"] for x in xs] == plan["seeds"]
        s = e["summary"]
        n = len(xs)
        success = [x["elapsed_s"] for x in xs if x["outcome"] == "success"]
        assert (
            s["runs"] == n
            and s["completed"] == len(success)
            and s["completion_rate"] == len(success) / n
        )
        assert (
            s["average_success_time_s"] is None
            if not success
            else abs(s["average_success_time_s"] - sum(success) / len(success)) < 1e-10
        )
        penalty = sum(x["elapsed_s"] if x["outcome"] == "success" else 30 for x in xs) / n
        assert abs(s["penalized_mean_s"] - penalty) < 1e-10
        assert s["failed_solve_ticks"] == sum(x["failed_solve_ticks"] for x in xs)
        p99 = max(x["whole_call_p99_ms"] for x in xs)
        over = sum(x["whole_call_overruns"] for x in xs) / sum(x["steps"] for x in xs)
        assert s["max_episode_p99_ms"] == p99 and s["overrun_fraction"] == over
        assert s["latency_eligible"] == (p99 <= 20 and over <= 0.01)
        for x in xs:
            assert x["outcome"] in ["success", "terminated", "timeout"]
            assert (x["gates_passed"] == 5) == (x["outcome"] == "success")
            assert (
                0 < x["steps"] <= 1500 and x["elapsed_s"] == x["steps"] / e["config"]["env"]["freq"]
            )
            assert x["effective_settings"] == dict(
                mpcc=e["config"]["controller"]["mpcc"],
                mpcc_experiment=e["config"]["controller"]["mpcc_experiment"],
            )
        k = len(success)
        intervals[e["configuration"]] = [
            float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0,
            float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0,
        ]
    ref = next(e for e in r["evaluations"] if e["configuration"] == plan["reference"])
    comparisons = {e["configuration"]: paired(ref, e, bootstrap=True) for e in r["evaluations"]}
    # Also save every constituent comparison for later interaction assessment.
    from itertools import combinations

    all_pairs = [paired(a, b) for a, b in combinations(r["evaluations"], 2)]
    result = dict(
        status="passed",
        report_sha256=h.sha(output / "report.json"),
        comparisons=comparisons,
        all_pairs=all_pairs,
        completion_exact_95ci=intervals,
    )
    h.write_report(output / "audit.json", result)
    export(
        output / "summary.csv",
        [dict(configuration=e["configuration"], **e["summary"]) for e in r["evaluations"]],
    )
    export(
        output / "episodes.csv",
        [
            dict(configuration=e["configuration"], **x)
            for e in r["evaluations"]
            for x in e["episodes"]
        ],
    )
    export(output / "comparisons.csv", [dict(configuration=k, **v) for k, v in comparisons.items()])
    lines = [
        "# Adaptive MPCC batch: " + plan["request"]["question"],
        "",
        "Evidence class: "
        + plan["request"]["kind"]
        + ". Successful lap averages are conditional on each configuration finishing; paired comparisons use shared finishes. Do not pool cohorts.",
        f"Seeds {plan['seeds'][0]}–{plan['seeds'][-1]}; {len(plan['seeds'])} per case. No population reliability guarantee.",
        "",
        "| Case | Finishes | Successful mean, s | Paired Δ s (shared) | Rescues | Regressions | Penalized mean / Δ s | Numerical ticks | Max p99 ms | Overruns fraction | Latency eligible |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in r["evaluations"]:
        k = e["configuration"]
        s = e["summary"]
        c = comparisons[k]
        lines.append(
            f"| {k} | {s['completed']}/{s['runs']} ({s['completion_rate']:.1%}) | {s['average_success_time_s']} | {c['paired_mean_s']} ({len(c['shared_success_seeds'])}) | {c['rescued_seeds']} | {c['regressed_seeds']} | {s['penalized_mean_s']} / {c['penalized_mean_delta_s']} | {s['failed_solve_ticks']} | {s['max_episode_p99_ms']:.3f} | {s['overrun_fraction']:.6f} | {s['latency_eligible']} |"
        )
    lines += [
        "",
        "All failed races score 30 s. audit.json includes exact completion intervals/tests, conservative paired completion intervals, 10,000 paired bootstrap intervals and constituent comparisons. These exploratory tests are unadjusted. Initialization, simulation stepping and callbacks are excluded from controller-call latency. Infrastructure failures are separate.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return result


def execute(request_path: Path, output: Path, resume: bool) -> None:
    """Reserve fresh matched seeds and run serially with immutable provenance."""
    request = h.read(request_path)
    _, _, manifest = h.load_prepared(PREP)
    with (h.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if resume:
            plan = h.read(output / "plan.json")
            assert plan["request"] == request and plan["manifest"] == manifest
            assert plan["driver_sha256"] == h.sha(Path(__file__))
            report = h.read(output / "report.json")
        else:
            used, evidence = h.fresh_inventory()
            n = request["seed_count"]
            seeds = list(range(max(used) + 100, max(used) + 100 + n))
            assert not set(seeds) & used
            cases = {}
            for label, config in request["cases"].items():
                config = deepcopy(config)
                config["env"]["seed"] = seeds[0]
                # Prove immutable environment/settings except supported knobs.
                base = h.read(PARENT)["evaluations"][1]["config"]
                changes = {
                    **config["controller"]["mpcc"],
                    **config["controller"]["mpcc_experiment"],
                }
                changes = {k: v for k, v in changes.items() if k not in ["adaptation_rate"]}
                expected = config_for(base, changes)
                expected["env"]["seed"] = seeds[0]
                assert config == expected
                cases[label] = config
            assert len({h.digest(c) for c in cases.values()}) == len(cases)
            assert request["reference"] in cases
            forecast = sum(
                n * 6.5 * (c["controller"]["mpcc"]["horizon_steps"] / 40) ** 0.5 + 10
                for c in cases.values()
            )
            assert forecast <= request["budget_minutes"] * 60 - 120, "batch too large for budget"
            output.mkdir(parents=True, exist_ok=False)
            started = time.time()
            plan = dict(
                request=request,
                reference=request["reference"],
                cases=cases,
                seeds=seeds,
                manifest=manifest,
                driver_sha256=h.sha(Path(__file__)),
                freshness=evidence,
                started_epoch=started,
                deadline_epoch=started + request["budget_minutes"] * 60 - 120,
                forecast_s=forecast,
            )
            h.write_report(output / "plan.json", plan)
            report = dict(status="running", evaluations=[], infrastructure_errors=[])
        print("BATCH", output, flush=True)
        try:
            for index, (label, config) in enumerate(plan["cases"].items()):
                if STOP:
                    break
                if index == len(report["evaluations"]):
                    report["evaluations"].append(
                        dict(configuration=label, config=config, episodes=[])
                    )
                e = report["evaluations"][index]
                assert e["config"] == config
                h.write_report(output / "report.json", report)
                remaining = plan["seeds"][len(e["episodes"]) :]
                with (output / "simulation.log").open("a", buffering=1) as log:
                    stream = h.configuration_episodes(
                        h.ConfigDict(config), remaining, plan["deadline_epoch"], log
                    )
                    try:
                        for x in stream:
                            e["episodes"].append(x)
                            h.write_report(output / "report.json", report)
                            if STOP:
                                break
                    finally:
                        stream.close()
                if len(e["episodes"]) != len(plan["seeds"]):
                    break
                e["summary"] = h.summary(e["episodes"])
                print(label, e["summary"], flush=True)
            complete = len(report["evaluations"]) == len(plan["cases"]) and all(
                len(e["episodes"]) == len(plan["seeds"]) for e in report["evaluations"]
            )
            report["status"] = (
                "completed" if complete else "stopped" if STOP else "incomplete_budget"
            )
        except BaseException as error:
            report["status"] = "infrastructure_error"
            report["infrastructure_errors"].append(repr(error))
            raise
        finally:
            report["elapsed_wall_s"] = time.time() - plan["started_epoch"]
            h.write_report(output / "report.json", report)
        if report["status"] == "completed":
            audit(output)
        print("FINISHED", report["status"], flush=True)


def main() -> None:
    """Explicit execution/audit interface; USR1 safely stops scheduling."""
    signal.signal(signal.SIGUSR1, stop_requested)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "audit"])
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.action == "audit":
        audit(args.output_dir.resolve())
    else:
        if args.request is None:
            parser.error("--request is required")
        execute(args.request.resolve(), args.output_dir.resolve(), args.resume)


if __name__ == "__main__":
    main()

"""Adaptive, budgeted reference-speed/geometry study. Only `run` launches simulations."""

import argparse
import csv
import fcntl
import itertools
import time
from copy import deepcopy
from pathlib import Path

from scripts import overnight_mpcc as harness
from scripts.overnight_mpcc_analysis import paired

PLAN = harness.ROOT / "docs/control/mpcc_speed_safety_revised_plan.json"
PREPARED = harness.ROOT / "logs/mpcc-tuning/overnight-prep-20261102T212955383826Z"
FIELDS = (
    "max_speed",
    "gate_center_snap",
    "over_gate_lift",
    "obstacle_clearance",
    "observed_obstacle_clearance",
    "reference_speed",
)
GRIDS = (
    [2.1, 2.3, 2.5, 2.7, 2.9],
    [0.0, 0.25, 0.5, 0.75],
    [0.05, 0.1, 0.15, 0.2],
    [0.26, 0.30, 0.34],
    [None, 0.30, 0.34],
    [1.8, 2.0, 2.2, 2.4, 2.6],
)


def baseline(plan: dict) -> dict:
    """Extract the five explicitly mutable fields."""
    c = plan["baseline_config"]["controller"]
    return dict(
        max_speed=c["mpcc"]["max_speed"],
        reference_speed=c["mpcc"]["reference_speed"],
        obstacle_clearance=c["mpcc"]["obstacle_clearance"],
        **c["mpcc_experiment"],
    )


def unique(cases: list[dict]) -> list[dict]:
    """Deduplicate in proposal order."""
    return list({harness.digest(c): c for c in cases}.values())


def config_for(plan: dict, settings: dict, seed: int) -> dict:
    """Reject all undeclared changes and build the full frozen simulation config."""
    assert set(settings) == set(FIELDS)
    assert all(settings[k] in grid for k, grid in zip(FIELDS, GRIDS))
    c = deepcopy(plan["baseline_config"])
    c["env"]["seed"] = seed
    for key in ("max_speed", "obstacle_clearance", "reference_speed"):
        c["controller"]["mpcc"][key] = settings[key]
    c["controller"]["mpcc_experiment"] = {
        k: settings[k]
        for k in FIELDS
        if k not in ("max_speed", "obstacle_clearance", "reference_speed")
    }
    assert settings["max_speed"] == round(settings["reference_speed"] + 0.3, 1)
    return c


def eligible(e: dict) -> bool:
    """Require numerical and whole-call latency eligibility."""
    s = e["summary"]
    return s["failed_solve_ticks"] == 0 and s["latency_eligible"]


def delta(a: dict, b: dict) -> float | None:
    """Fractional paired time change, with at least five shared finishes."""
    aa = {x["seed"]: x for x in a["episodes"] if x["outcome"] == "success"}
    bb = {x["seed"]: x for x in b["episodes"] if x["outcome"] == "success"}
    shared = set(aa) & set(bb)
    if len(shared) < 5:
        return None
    return sum(bb[s]["elapsed_s"] - aa[s]["elapsed_s"] for s in shared) / sum(
        aa[s]["elapsed_s"] for s in shared
    )


def distance(c: dict, parent: dict) -> float:
    """Fixed normalized L1 departure for deterministic ranking."""
    score = sum(
        abs(c[k] - parent[k]) / scale for k, scale in zip(FIELDS[:4], [0.3, 0.25, 0.05, 0.04])
    )
    a, b = c[FIELDS[4]], parent[FIELDS[4]]
    return (
        abs(c["reference_speed"] - parent["reference_speed"]) / 0.2
        + score
        + (float(a != b) if None in (a, b) else abs(a - b) / 0.04)
    )


def recovery_rows(report: dict) -> list[dict]:
    """Rank repairs using only their matched parent cohort."""
    parent = report["evaluations"][0]
    rows = []
    for e in report["evaluations"][1:]:
        s = e["summary"]
        d = delta(parent, e)
        if (
            eligible(e)
            and s["completion_rate"] > 0.5
            and d is not None
            and d <= 0.05
            and (
                s["completion_rate"] >= 0.65 or s["completed"] >= parent["summary"]["completed"] + 2
            )
        ):
            rows.append(e)
    return sorted(
        rows,
        key=lambda e: (
            -e["summary"]["completed"],
            delta(parent, e),
            distance(e["settings"], parent["settings"]),
            e["configuration"],
        ),
    )


def frontier(report: dict) -> tuple[dict, bool]:
    """Pick a useful eligible cap, or a nearby recoverable completion drop."""
    parent = report["evaluations"][0]
    useful = [
        e
        for e in report["evaluations"][1:]
        if eligible(e) and delta(parent, e) is not None and delta(parent, e) <= -0.01
    ]
    above = [e for e in useful if e["summary"]["completion_rate"] > 0.5]
    current = max(above, key=lambda e: e["settings"]["reference_speed"], default=parent)
    next_rows = sorted(
        [
            e
            for e in useful
            if e["settings"]["reference_speed"] > current["settings"]["reference_speed"]
        ],
        key=lambda e: e["settings"]["reference_speed"],
    )
    if next_rows:
        nxt = next_rows[0]
        rate = nxt["summary"]["completion_rate"]
        if rate >= 0.25 and (rate < 0.65 or parent["summary"]["completion_rate"] - rate >= 0.1):
            current = nxt
    return current["settings"], bool(useful)


def stronger(c: dict, field: str) -> dict | None:
    """Next bounded neighbor in one safety field."""
    grid = GRIDS[FIELDS.index(field)]
    index = grid.index(c[field])
    return dict(c, **{field: grid[index + 1]}) if index + 1 < len(grid) else None


def proposals(stage: str, reports: dict, plan: dict) -> tuple[list[dict], str]:
    """Pure adaptive transitions; never inspect future cohorts."""
    base = baseline(plan)
    if stage == "cap_probe":
        return [
            dict(base, reference_speed=v, max_speed=round(v + 0.3, 1)) for v in GRIDS[5][:-1]
        ], "revised reference-speed ladder; matched cap=reference+0.3"
    parent, useful = frontier(reports["cap_probe"])
    if stage == "safety_singles":
        return unique(
            [
                parent,
                dict(parent, gate_center_snap=0.5),
                dict(parent, over_gate_lift=0.15),
                dict(parent, obstacle_clearance=0.30),
                dict(parent, observed_obstacle_clearance=0.30),
                dict(parent, obstacle_clearance=0.30, observed_obstacle_clearance=0.30),
            ]
        ), "isolated recovery"
    singles = recovery_rows(reports["safety_singles"]) if "safety_singles" in reports else []
    if stage == "safety_combinations":
        if not singles:
            return [], "no improving safety family"
        best = singles[0]["settings"]
        combined = dict(best)

        def changed(c: dict) -> set:
            return {
                ("obstacle" if "clearance" in k else k) for k in FIELDS[1:] if c[k] != parent[k]
            }

        alternative = next(
            (e["settings"] for e in singles[1:] if changed(e["settings"]) - changed(best)), None
        )
        if alternative:
            combined.update({k: v for k, v in alternative.items() if v != parent[k]})
        else:
            key = next(k for k in FIELDS[1:] if best[k] != parent[k])
            combined = stronger(best, key) or best
        return unique(
            [parent, best, combined]
        ), "combine measured improving families or bounded neighbor"
    for name in ("safety_singles", "safety_combinations"):
        if name in reports:
            ranked = recovery_rows(reports[name])
            if ranked:
                parent = ranked[0]["settings"]
    if stage == "cap_reescalation":
        recovered = next(
            (
                e
                for r in reversed(list(reports.values()))
                for e in r["evaluations"]
                if e["settings"] == parent
            ),
            None,
        )
        if recovered and recovered["summary"]["completion_rate"] <= 0.5:
            return [], "failed recovery; no escalation"
        ineffective = [
            e["settings"]
            for r in reports.values()
            for e in r["evaluations"][1:]
            if delta(r["evaluations"][0], e) is not None and delta(r["evaluations"][0], e) > -0.01
        ]
        higher = [
            v
            for v in GRIDS[5]
            if v > parent["reference_speed"]
            and dict(parent, reference_speed=v, max_speed=round(v + 0.3, 1)) not in ineffective
        ][:2]
        return [parent] + [
            dict(parent, reference_speed=v, max_speed=round(v + 0.3, 1)) for v in higher
        ] if higher else [], "recheck cap after recovery"
    if stage == "second_recovery":
        if "cap_reescalation" not in reports:
            return [], "no second cap round"
        target, gain = frontier(reports["cap_reescalation"])
        current = next(
            e for e in reports["cap_reescalation"]["evaluations"] if e["settings"] == target
        )
        if not gain or target == parent or current["summary"]["completion_rate"] >= 0.65:
            return [], "no useful speed/completion frontier"
        order = ["gate_center_snap", "over_gate_lift", "obstacle_clearance"]
        reference = reports["cap_reescalation"]["evaluations"][0]
        lost = [
            x
            for x in current["episodes"]
            if x["outcome"] != "success"
            and any(
                y["seed"] == x["seed"] and y["outcome"] == "success" for y in reference["episodes"]
            )
        ]
        if lost and sum(x["gates_passed"] == 3 for x in lost) > len(lost) / 2:
            order[:2] = reversed(order[:2])
        return unique(
            [target] + [v for k in order if (v := stronger(target, k))]
        ), "second bounded recovery; no inferred pole collisions"
    # Cross-cohort summaries nominate finalists only, never pool evidence.
    candidates = [
        e
        for r in reports.values()
        for e in r["evaluations"]
        if eligible(e) and e["summary"]["completion_rate"] > 0.5 and e["settings"] != base
    ]
    fastest = sorted(
        candidates, key=lambda e: (e["summary"]["average_success_time_s"], e["configuration"])
    )
    if not fastest:
        fallback = sorted(
            [e for r in reports.values() for e in r["evaluations"] if e["settings"] != base],
            key=lambda e: (not eligible(e), -e["summary"]["completed"], e["configuration"]),
        )
        return unique(
            [base] + [e["settings"] for e in fallback[:1]]
        ), "fallback comparison, no endorsement"
    first = fastest[0]
    near = [
        e
        for e in fastest
        if e["settings"] != first["settings"]
        and e["summary"]["average_success_time_s"]
        <= 1.05 * first["summary"]["average_success_time_s"]
    ]
    second = sorted(
        near,
        key=lambda e: (-e["summary"]["completion_rate"], e["summary"]["average_success_time_s"]),
    )
    other = second[:1] or [e for e in fastest if e["settings"] != first["settings"]][:1]
    return unique(
        [base, first["settings"]] + [e["settings"] for e in other]
    ), "frozen fresh validation finalists"


def fit(
    cases: list[dict], n: int, remaining: float, seconds: float, validation: bool
) -> list[dict]:
    """Keep complete matched cohorts and reserve three-case final validation."""
    reserve = 0 if validation else 150 * seconds + 30
    for count in range(len(cases), 1, -1):
        if count * (n * seconds + 10) + reserve <= remaining:
            return cases[:count]
    return []


def evaluate(output: Path, choice: dict, plan: dict, deadline: float) -> dict:
    """Checkpoint each worker episode; freeze full configs before measurement."""
    path = output / "report.json"
    report = (
        harness.read(path)
        if path.exists()
        else dict(status="running", seeds=choice["seeds"], evaluations=[])
    )
    assert report["seeds"] == choice["seeds"]
    try:
        for index, settings in enumerate(choice["cases"]):
            config = config_for(plan, settings, choice["seeds"][0])
            if index == len(report["evaluations"]):
                report["evaluations"].append(
                    dict(
                        configuration=harness.digest(settings)[:12],
                        settings=settings,
                        config=config,
                        episodes=[],
                    )
                )
            e = report["evaluations"][index]
            assert e["config"] == config
            harness.write_report(path, report)
            with (output / "simulation.log").open("a", buffering=1) as log:
                for x in harness.configuration_episodes(
                    harness.ConfigDict(config), choice["seeds"][len(e["episodes"]) :], deadline, log
                ):
                    assert x["effective_settings"] == dict(
                        mpcc=config["controller"]["mpcc"],
                        mpcc_experiment=config["controller"]["mpcc_experiment"],
                    )
                    e["episodes"].append(x)
                    harness.write_report(path, report)
            if len(e["episodes"]) != len(choice["seeds"]):
                report["status"] = "incomplete_budget"
                return report
            e["summary"] = harness.summary(e["episodes"])
            print(output.name, e["settings"], e["summary"], flush=True)
        report["status"] = "completed"
        return report
    finally:
        harness.write_report(path, report)


def audit(output: Path, plan: dict) -> dict:
    """Independently verify settings, seeds and primary arithmetic; export evidence."""
    r = harness.read(output / "report.json")
    choice = harness.read(output / "decision.json")
    assert r["status"] == "completed"
    for e, c in zip(r["evaluations"], choice["cases"], strict=True):
        assert e["config"] == config_for(plan, c, choice["seeds"][0])
        assert [x["seed"] for x in e["episodes"]] == choice["seeds"]
        success = [x["elapsed_s"] for x in e["episodes"] if x["outcome"] == "success"]
        assert len(success) == e["summary"]["completed"]
        assert all(
            (x["gates_passed"] == 5) == (x["outcome"] == "success")
            and x["elapsed_s"] == x["steps"] / 50
            for x in e["episodes"]
        )
        ticks = sum(x["failed_solve_ticks"] for x in e["episodes"])
        steps = sum(x["steps"] for x in e["episodes"])
        over = sum(x["whole_call_overruns"] for x in e["episodes"])
        p99 = max(x["whole_call_p99_ms"] for x in e["episodes"])
        assert ticks == e["summary"]["failed_solve_ticks"]
        assert (p99 <= 20 and over / steps <= 0.01) == e["summary"]["latency_eligible"]
        penalty = sum(
            x["elapsed_s"] if x["outcome"] == "success" else 30 for x in e["episodes"]
        ) / len(e["episodes"])
        assert abs(penalty - e["summary"]["penalized_mean_s"]) < 1e-9
        for x in e["episodes"]:
            assert x["effective_settings"] == dict(
                mpcc=e["config"]["controller"]["mpcc"],
                mpcc_experiment=e["config"]["controller"]["mpcc_experiment"],
            )
    comparisons = [
        paired(a, b, bootstrap=True) for a, b in itertools.combinations(r["evaluations"], 2)
    ]
    result = dict(
        status="passed", comparisons=comparisons, report_sha256=harness.sha(output / "report.json")
    )
    harness.write_report(output / "audit.json", result)
    for filename, rows in [
        (
            "summary.csv",
            [dict(configuration=e["configuration"], **e["summary"]) for e in r["evaluations"]],
        ),
        (
            "episodes.csv",
            [
                dict(configuration=e["configuration"], **x)
                for e in r["evaluations"]
                for x in e["episodes"]
            ],
        ),
    ]:
        with (output / filename).open("w", newline="") as stream:
            w = csv.DictWriter(stream, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return result


def execute(output: Path, started: float, resume: bool = False) -> None:
    """Run only via explicit command, preserving absolute budget and provenance."""
    plan = harness.read(PLAN)
    _, _, manifest = harness.load_prepared(PREPARED)
    manifest = deepcopy(manifest)
    manifest["driver_sha256"] = harness.sha(Path(__file__))
    manifest["study_plan_sha256"] = harness.sha(PLAN)
    with (harness.ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if resume:
            state = harness.read(output / "study.json")
            assert state["manifest"] == manifest
            assert state["plan"] == plan
        else:
            used, evidence = harness.fresh_inventory()
            seed = max(used) + 100
            output.mkdir(parents=True, exist_ok=False)
            stages = []
            for spec in plan["stages"]:
                stages.append(
                    dict(stage=spec["stage"], seeds=list(range(seed, seed + spec["seeds"])))
                )
                seed += spec["seeds"]
            state = dict(
                status="running",
                started_epoch=started,
                deadline_epoch=started + 55 * 60,
                manifest=manifest,
                plan=plan,
                stages=stages,
                decisions={},
                skipped={},
                freshness=evidence,
            )
            harness.write_report(
                output / "plan.json", dict(plan=plan, stages=stages, manifest=manifest)
            )
        reports = {}
        try:
            for spec in state["stages"]:
                stage = spec["stage"]
                directory = output / stage
                if stage in state["skipped"]:
                    continue
                if stage not in state["decisions"]:
                    if stage != "cap_probe" and "cap_probe" not in reports:
                        break
                    cases, reason = proposals(stage, reports, plan)
                    walls = [
                        x["wall_s"]
                        for r in reports.values()
                        for e in r["evaluations"]
                        for x in e["episodes"]
                    ]
                    seconds = max(6.5, 1.2 * sum(walls) / len(walls)) if walls else 6.5
                    cases = fit(
                        cases,
                        len(spec["seeds"]),
                        state["deadline_epoch"] - time.time(),
                        seconds,
                        stage == "fresh_validation",
                    )
                    if not cases:
                        state["skipped"][stage] = (
                            "no useful proposals or insufficient budget with protected validation"
                        )
                        harness.write_report(output / "study.json", state)
                        continue
                    directory.mkdir(exist_ok=True)
                    choice = dict(
                        cases=cases,
                        seeds=spec["seeds"],
                        reason=reason,
                        parents={k: harness.sha(output / k / "report.json") for k in reports},
                        seconds_forecast=seconds,
                    )
                    state["decisions"][stage] = choice
                    harness.write_report(directory / "decision.json", choice)
                    harness.write_report(output / "study.json", state)
                choice = state["decisions"][stage]
                for k, v in choice["parents"].items():
                    assert harness.sha(output / k / "report.json") == v
                report = evaluate(directory, choice, plan, state["deadline_epoch"])
                if report["status"] != "completed":
                    break
                audit(directory, plan)
                reports[stage] = report
            final = reports.get("fresh_validation")
            recommendation = None
            if final:
                ref = final["evaluations"][0]
                valid = [
                    e
                    for e in final["evaluations"][1:]
                    if eligible(e)
                    and e["summary"]["completion_rate"] > 0.5
                    and delta(ref, e) is not None
                    and delta(ref, e) <= -0.01
                ]
                valid.sort(
                    key=lambda e: (
                        delta(ref, e),
                        -e["summary"]["completed"],
                        distance(e["settings"], ref["settings"]),
                        e["configuration"],
                    )
                )
                recommendation = (
                    valid[0]
                    if valid
                    else ref
                    if eligible(ref) and ref["summary"]["completion_rate"] > 0.5
                    else None
                )
            state["status"] = "completed" if final else "incomplete_budget"
            harness.write_report(
                output / "recommendation.json",
                dict(
                    status=state["status"],
                    recommendation=recommendation,
                    caveat=(
                        "Observed >50% is not a population guarantee; "
                        "paired speed is conditional on shared finishes."
                    ),
                ),
            )
        except BaseException as error:
            state["status"] = "infrastructure_error"
            state["error"] = repr(error)
            raise
        finally:
            state["elapsed_wall_s"] = time.time() - state["started_epoch"]
            harness.write_report(output / "study.json", state)


def main() -> None:
    """Expose a non-simulation check and an explicitly selected execution command."""
    started = time.time()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "run", "audit"])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--started-epoch", type=float, default=started)
    args = parser.parse_args()
    if args.action == "check":
        plan = harness.read(PLAN)
        harness.load_prepared(PREPARED)
        for c in proposals("cap_probe", {}, plan)[0]:
            config_for(plan, c, 1)
        print("Plan and preparation match; no simulations started.")
        return
    if args.output_dir is None:
        parser.error("--output-dir is required")
    if args.action == "run":
        assert args.started_epoch <= started
        execute(args.output_dir.resolve(), args.started_epoch, args.resume)
    else:
        state = harness.read(args.output_dir / "study.json")
        for file, expected in state["manifest"]["source_sha256"].items():
            assert harness.sha(harness.ROOT / file) == expected
        for stage in state["decisions"]:
            directory = args.output_dir / stage
            if harness.read(directory / "report.json")["status"] == "completed":
                audit(directory, state["plan"])


if __name__ == "__main__":
    main()

"""Screen local height/recentering changes and independently validate one challenger."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import itertools
import json
import math
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from lsy_drone_racing.utils import load_config
from scripts import compare_mpcc as common
from scripts.probe_mpcc import create_environment, run_episode
from scripts.tune_mpcc import ROOT, simulation_output, write_report

CASES = {
    f"snap_{snap:.3f}_height_{height:.2f}": (snap, height, None)
    for snap in (0.0, 0.025)
    for height in (0.03, 0.05, 0.07)
}
INCUMBENT = "snap_0.000_height_0.05"
SCREEN_SEEDS = list(range(301, 401))
VALIDATION_SEEDS = list(range(401, 601))


def candidate_config(config: dict, values: tuple, initial_seed: int) -> dict:
    """Apply one local geometry combination with all other settings fixed."""
    candidate = common.candidate_config(config, values)
    candidate.env.seed = initial_seed
    return candidate


def fingerprint(config: dict, seeds: list[int], cases: dict) -> dict:
    """Fingerprint episode code, runtime, full settings, candidates and ordered seeds."""
    manifest = common.fingerprint(config, {"fresh": seeds})
    manifest["cases"] = {
        name: candidate_config(config, values, seeds[0]).to_dict() for name, values in cases.items()
    }
    manifest["source_sha256"][str(Path(__file__).resolve().relative_to(ROOT))] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    return manifest


def freshness_evidence(seeds: list[int], directory: Path) -> dict:
    """Reject previously evaluated seeds and retain hashes of the checked reports."""
    reports = {}
    for path in sorted((ROOT / "logs/mpcc-tuning").rglob("report.json")):
        if path.resolve() == (directory / "report.json").resolve():
            continue
        prior = json.loads(path.read_text())
        used = {e["seed"] for v in prior.get("evaluations", []) for e in v.get("episodes", [])}
        if used.intersection(seeds):
            raise ValueError(f"Fresh seed overlap with {path}")
        reports[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(checked_at=common.now(), prior_report_sha256=reports, overlap=[])


def validate(report: dict, complete: bool = False) -> dict:
    """Validate prefixes for resume and complete episode/settings invariants at finish."""
    manifest = report["manifest"]
    seeds = manifest["cohorts"]["fresh"]
    assert all(name in CASES for name in manifest["cases"])
    assert [e["configuration"] for e in report["evaluations"]] == list(manifest["cases"])
    total = 0
    for evaluation in report["evaluations"]:
        name = evaluation["configuration"]
        assert evaluation["cohort"] == "fresh"
        assert evaluation["config"] == manifest["cases"][name]
        options = evaluation["config"]["controller"]["mpcc_experiment"]
        assert options == dict(
            gate_center_snap=CASES[name][0],
            over_gate_lift=CASES[name][1],
            observed_obstacle_clearance=None,
        )
        assert evaluation["config"]["controller"]["mpcc"]["obstacle_clearance"] == 0.26
        episodes = evaluation["episodes"]
        assert [e["seed"] for e in episodes] == seeds[: len(episodes)]
        for episode in episodes:
            assert episode["outcome"] in ("success", "terminated", "timeout")
            assert episode["elapsed_s"] == episode["steps"] / evaluation["config"]["env"]["freq"]
            assert episode["steps"] > 0
            assert 0 <= episode["failed_solve_ticks"] <= episode["steps"]
            assert (episode["gates_passed"] == 5) == (episode["outcome"] == "success")
        if episodes:
            assert evaluation["effective_settings"]["mpcc_experiment"] == options
            assert (
                evaluation["effective_settings"]["mpcc"]
                == report["evaluations"][0]["effective_settings"]["mpcc"]
            )
        if evaluation["status"] == "completed":
            assert len(episodes) == len(seeds)
            assert evaluation["summary"] == common.summarize(episodes)
        if complete:
            assert evaluation["status"] == "completed"
        total += len(episodes)
    assert report["planned_episodes"] == len(seeds) * len(manifest["cases"])
    if complete:
        assert total == report["planned_episodes"]
    return dict(
        validated_episodes=total,
        expected_episodes=report["planned_episodes"],
        complete=complete,
        checked_at=common.now(),
    )


def comparisons(report: dict) -> list[dict]:
    """Save every within-cohort paired comparison and exact completion statistics."""
    result = []
    for a, b in itertools.combinations(report["evaluations"], 2):
        comparison = common.compare(a, b)
        differences = list(comparison["paired_time_differences_s"].values())
        gained, lost = len(comparison["newly_completed_seeds"]), len(comparison["regressed_seeds"])
        discordant = gained + lost
        p_value = (
            min(
                1.0,
                2
                * sum(math.comb(discordant, k) for k in range(min(gained, lost) + 1))
                / 2**discordant,
            )
            if discordant
            else 1.0
        )
        comparison.update(
            net_completion_change=gained - lost,
            median_paired_time_difference_s=median(differences) if differences else None,
            faster_shared_seeds=sum(d < 0 for d in differences),
            slower_shared_seeds=sum(d > 0 for d in differences),
            unchanged_time_shared_seeds=sum(d == 0 for d in differences),
            exact_paired_completion_p_value_unadjusted=p_value,
        )
        result.append(comparison)
    return result


def study(
    config: dict,
    directory: Path,
    resume: bool = False,
    seeds: list[int] | None = None,
    cases: dict | None = None,
) -> dict:
    """Execute fixed cases serially and checkpoint every measured episode."""
    seeds = SCREEN_SEEDS if seeds is None else seeds
    cases = CASES if cases is None else cases
    manifest = fingerprint(config, seeds, cases)
    path = directory / "report.json"
    print(f"Report: {path.resolve()}", flush=True)
    if resume:
        report = json.loads(path.read_text())
        if report["manifest"] != manifest:
            raise ValueError("Resume rejected: source, runtime, seeds or settings differ.")
        validate(report)
    else:
        if path.exists():
            raise FileExistsError(path)
        evidence = freshness_evidence(seeds, directory)
        report = dict(
            schema_version=1,
            status="running",
            started_at=common.now(),
            manifest=manifest,
            design="local geometry screening or independent validation; paired fresh seeds",
            freshness=evidence,
            planned_episodes=len(seeds) * len(manifest["cases"]),
            infrastructure_errors=[],
            time_definition="completed environment steps / env.freq; stop at completion callback",
            average_time_definition="mean successful race time; seed subsets can differ",
            paired_time_definition="candidate minus reference on shared successful seeds",
            control_time_definition="p50/p95 perf_counter compute_control durations in ms; "
            "excludes construction, environment stepping and callbacks",
            failure_tick_definition="controller._prediction is None after compute_control; "
            "measured outcome",
            seed_definition="env.reset(seed=episode.seed); new controller per episode; "
            "serial shared environment",
            statistical_definition="exact two-sided paired binomial/McNemar p values are "
            "unadjusted; screening exploratory; validation single prespecified comparison",
            evaluations=[
                dict(
                    cohort="fresh",
                    configuration=name,
                    status="pending",
                    config=manifest["cases"][name],
                    episodes=[],
                )
                for name in cases
            ],
        )
    report["status"] = "running"
    write_report(path, report)
    env, current_seed, evaluation = None, None, None
    with (directory / "simulation.log").open("a", buffering=1) as log:
        try:
            for evaluation in report["evaluations"]:
                if evaluation["status"] == "completed":
                    continue
                candidate = candidate_config(config, CASES[evaluation["configuration"]], seeds[0])
                for current_seed in seeds[len(evaluation["episodes"]) :]:
                    with simulation_output(log):
                        print(
                            f"{common.now()} {evaluation['configuration']} seed={current_seed}",
                            flush=True,
                        )
                        if env is None:
                            env = create_environment(candidate)
                        episode = run_episode(env, common.MeasuredMPCC, candidate, current_seed)
                    effective = deepcopy(common.MeasuredMPCC.effective)
                    if "effective_settings" in evaluation:
                        assert evaluation["effective_settings"] == effective
                    evaluation["effective_settings"] = effective
                    evaluation["episodes"].append(episode)
                    write_report(path, report)
                evaluation["summary"] = common.summarize(evaluation["episodes"])
                evaluation["status"] = "completed"
                write_report(path, report)
                common.csv_exports(directory, report)
                s = evaluation["summary"]
                average = s["average_success_time_s"]
                average_text = f"{average:.3f} s" if average is not None else "n/a"
                print(
                    f"{evaluation['configuration']}: {s['completed']}/{s['runs']} "
                    f"({s['completion_rate']:.1%}); average successful race time {average_text}",
                    flush=True,
                )
            report["validation"] = validate(report, complete=True)
            report["comparisons"] = comparisons(report)
            report["status"] = "completed"
            report["completed_at"] = report.get("completed_at", common.now())
        except BaseException as error:
            report["status"] = (
                "interrupted" if isinstance(error, KeyboardInterrupt) else "infrastructure_error"
            )
            report["infrastructure_errors"].append(
                dict(
                    at=common.now(),
                    configuration=evaluation["configuration"] if evaluation else None,
                    seed=current_seed,
                    error=f"{type(error).__name__}: {error}",
                    traceback=traceback.format_exc(),
                )
            )
            raise
        finally:
            report["updated_at"] = common.now()
            write_report(path, report)
            common.csv_exports(directory, report)
            if env is not None:
                with simulation_output(log):
                    env.close()
    print(f"Report ({report['status']}): {path.resolve()}", flush=True)
    return report


def audit(directory: Path) -> dict:
    """Independently recompute episode summaries, settings, exports and paired comparisons."""
    # Crazyflow must initialize SCIPY_ARRAY_API before scipy is imported.
    from scipy.stats import binomtest

    report = json.loads((directory / "report.json").read_text())
    assert report["status"] == "completed"
    validation = validate(report, complete=True)
    for relative, expected in report["manifest"]["source_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    baseline = deepcopy(report["evaluations"][0]["config"])
    baseline["controller"].pop("mpcc_experiment")
    for evaluation in report["evaluations"]:
        normalized = deepcopy(evaluation["config"])
        normalized["controller"].pop("mpcc_experiment")
        assert normalized == baseline
        episodes = evaluation["episodes"]
        successes = [e for e in episodes if e["outcome"] == "success"]
        s = evaluation["summary"]
        assert s["completed"] == len(successes)
        assert s["completion_rate"] == len(successes) / len(episodes)
        expected_mean = (
            sum(e["elapsed_s"] for e in successes) / len(successes) if successes else None
        )
        if expected_mean is None:
            assert s["average_success_time_s"] is None
        else:
            assert math.isclose(s["average_success_time_s"], expected_mean, abs_tol=1e-12)
        assert s["failed_solve_ticks"] == sum(e["failed_solve_ticks"] for e in episodes)
    for filename, expected in (
        (
            "episodes.csv",
            [
                dict(cohort=e["cohort"], configuration=e["configuration"], **r)
                for e in report["evaluations"]
                for r in e["episodes"]
            ],
        ),
        (
            "summary.csv",
            [
                dict(cohort=e["cohort"], configuration=e["configuration"], **e["summary"])
                for e in report["evaluations"]
            ],
        ),
    ):
        with (directory / filename).open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == len(expected)
        for row, expected_row in zip(rows, expected):
            assert row == {k: "" if v is None else str(v) for k, v in expected_row.items()}
    pairs = list(itertools.combinations(report["evaluations"], 2))
    assert len(report["comparisons"]) == len(pairs)
    regression_details = []
    for c, (a, b) in zip(report["comparisons"], pairs):
        assert (c["reference"], c["candidate"]) == (a["configuration"], b["configuration"])
        ea, eb = {e["seed"]: e for e in a["episodes"]}, {e["seed"]: e for e in b["episodes"]}
        sa = {s for s in ea if ea[s]["outcome"] == "success"}
        sb = {s for s in eb if eb[s]["outcome"] == "success"}
        assert c["newly_completed_seeds"] == sorted(sb - sa)
        assert c["regressed_seeds"] == sorted(sa - sb)
        assert c["shared_success_seeds"] == sorted(sa & sb)
        delta = {str(s): eb[s]["elapsed_s"] - ea[s]["elapsed_s"] for s in sorted(sa & sb)}
        assert c["paired_time_differences_s"] == delta
        if delta:
            assert math.isclose(
                c["mean_paired_time_difference_s"], sum(delta.values()) / len(delta), abs_tol=1e-12
            )
        else:
            assert c["mean_paired_time_difference_s"] is None
        assert c["median_paired_time_difference_s"] == (median(delta.values()) if delta else None)
        assert c["faster_shared_seeds"] == sum(d < 0 for d in delta.values())
        assert c["slower_shared_seeds"] == sum(d > 0 for d in delta.values())
        assert c["unchanged_time_shared_seeds"] == sum(d == 0 for d in delta.values())
        gained, lost = len(sb - sa), len(sa - sb)
        expected_p = binomtest(gained, gained + lost).pvalue if gained + lost else 1.0
        assert math.isclose(c["exact_paired_completion_p_value_unadjusted"], expected_p)
        assert c["net_completion_change"] == len(sb) - len(sa)
        assert (
            c["numerical_failure_tick_difference"]
            == b["summary"]["failed_solve_ticks"] - a["summary"]["failed_solve_ticks"]
        )
        regression_details.append(
            dict(
                reference=c["reference"],
                candidate=c["candidate"],
                regressions=[
                    dict(seed=s, reference=ea[s], candidate=eb[s]) for s in sorted(sa - sb)
                ],
            )
        )
    rows = [
        dict(
            reference=c["reference"],
            candidate=c["candidate"],
            newly_completed=len(c["newly_completed_seeds"]),
            regressed=len(c["regressed_seeds"]),
            net_completion_change=c["net_completion_change"],
            shared_finishes=len(c["shared_success_seeds"]),
            mean_paired_time_difference_s=c["mean_paired_time_difference_s"],
            median_paired_time_difference_s=c["median_paired_time_difference_s"],
            exact_paired_completion_p_value_unadjusted=c[
                "exact_paired_completion_p_value_unadjusted"
            ],
        )
        for c in report["comparisons"]
    ]
    with (directory / "comparisons.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = dict(
        status="validated",
        **validation,
        regression_details=regression_details,
        input_sha256={
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("report.json", "episodes.csv", "summary.csv", "comparisons.csv")
        },
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    write_report(directory / "analysis.json", result)
    lines = [
        "# Local MPCC geometry study",
        "",
        "Same ordered fresh seeds within cohort; no observed-pole override; pole clearance 0.26 m.",
        "",
        "| Configuration | Completion | Mean successful race time (s) | Numerical failure ticks |",
        "| --- | ---: | ---: | ---: |",
    ]
    for e in report["evaluations"]:
        s = e["summary"]
        average = s["average_success_time_s"]
        time_text = f"{average:.6f}" if average is not None else "n/a"
        lines.append(
            f"| {e['configuration']} | {s['completed']}/{s['runs']} "
            f"({s['completion_rate']:.0%}) | {time_text} | {s['failed_solve_ticks']} |"
        )
    lines += [
        "",
        "Successful-run means use different seed subsets; "
        "speed comparisons below use shared finishes only.",
        "",
        "| Reference → candidate | Newly completed seeds | Regressed seeds | Shared finishes | "
        "Mean paired Δ (ms) | Exact paired completion p (unadjusted) |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for c in report["comparisons"]:
        delta = c["mean_paired_time_difference_s"]
        text = f"{1000 * delta:.3f}" if delta is not None else "n/a"
        lines.append(
            f"| {c['reference']} → {c['candidate']} | {c['newly_completed_seeds']} | "
            f"{c['regressed_seeds']} | {len(c['shared_success_seeds'])} | {text} | "
            f"{c['exact_paired_completion_p_value_unadjusted']:.6g} |"
        )
    lines += [
        "",
        "All pairwise comparisons are exploratory; "
        "screening p values are unadjusted. "
        "Race time has 20 ms episode resolution at 50 Hz. "
        "Screening and independent validation cohorts must remain separate. "
        "Do not compare completion rates directly with earlier studies on different seeds.",
        "",
    ]
    (directory / "analysis.md").write_text("\n".join(lines))
    print(
        f"Validated {validation['validated_episodes']} episodes: "
        f"{(directory / 'analysis.json').resolve()}"
    )
    return result


def select_challenger(report: dict) -> dict:
    """Freeze the prespecified completion-first challenger using screening only."""
    incumbent = next(e for e in report["evaluations"] if e["configuration"] == INCUMBENT)
    rankings = []
    for evaluation in report["evaluations"]:
        name = evaluation["configuration"]
        if name == INCUMBENT:
            continue
        c = common.compare(incumbent, evaluation)
        delta = c["mean_paired_time_difference_s"]
        snap, height, _ = CASES[name]
        distance = round(snap / 0.025 + abs(height - 0.05) / 0.02, 8)
        rankings.append(
            dict(
                configuration=name,
                completed=evaluation["summary"]["completed"],
                paired_delta_s=delta,
                grid_distance=distance,
            )
        )
    rankings.sort(
        key=lambda r: (
            -r["completed"],
            r["paired_delta_s"] if r["paired_delta_s"] is not None else math.inf,
            r["grid_distance"],
            r["configuration"],
        )
    )
    return dict(
        selected=rankings[0]["configuration"],
        rankings=rankings,
        selection_definition="completion count, paired time, grid distance, name",
    )


def finish(directory: Path) -> dict:
    """Create the independent holdout recommendation and regression inspection."""
    screening = json.loads((directory / "screening/report.json").read_text())
    selection = json.loads((directory / "selection.json").read_text())
    assert selection["selection"] == select_challenger(screening)
    assert (
        selection["screening_report_sha256"]
        == hashlib.sha256((directory / "screening/report.json").read_bytes()).hexdigest()
    )
    validation = json.loads((directory / "validation/report.json").read_text())
    assert validation["started_at"] >= selection["frozen_at"]
    assert set(screening["manifest"]["cohorts"]["fresh"]).isdisjoint(
        validation["manifest"]["cohorts"]["fresh"]
    )
    assert screening["manifest"]["cohorts"]["fresh"] == SCREEN_SEEDS
    assert validation["manifest"]["cohorts"]["fresh"] == VALIDATION_SEEDS
    assert list(screening["manifest"]["cases"]) == list(CASES)
    assert len(validation["evaluations"]) == 2
    a, b = validation["evaluations"]
    assert a["configuration"] == INCUMBENT
    assert b["configuration"] == selection["selection"]["selected"]
    c = comparisons(validation)[0]
    gained, lost = len(c["newly_completed_seeds"]), len(c["regressed_seeds"])
    n = len(a["episodes"])
    difference = (gained - lost) / n
    variance = ((gained + lost) / n - difference**2) / (n - 1)
    radius = 1.96 * math.sqrt(variance)
    paired_time = c["mean_paired_time_difference_s"]
    choose = gained > lost or (gained == lost == 0 and paired_time is not None and paired_time < 0)
    recommended = b if choose else a
    episodes_a = {e["seed"]: e for e in a["episodes"]}
    episodes_b = {e["seed"]: e for e in b["episodes"]}
    result = dict(
        status="validated",
        planned_episodes=1000,
        completed_episodes=sum(
            len(e["episodes"]) for r in (screening, validation) for e in r["evaluations"]
        ),
        selected_challenger=b["configuration"],
        recommended=recommended["configuration"],
        recommended_config=recommended["config"],
        recommended_effective_settings=recommended["effective_settings"],
        validation_comparison=c,
        paired_completion_difference=difference,
        approximate_paired_completion_difference_95ci=[
            max(-1, difference - radius),
            min(1, difference + radius),
        ],
        regressions=[
            dict(seed=s, incumbent=episodes_a[s], challenger=episodes_b[s])
            for s in c["regressed_seeds"]
        ],
        rescues=[
            dict(seed=s, incumbent=episodes_a[s], challenger=episodes_b[s])
            for s in c["newly_completed_seeds"]
        ],
        numerical_failure_ticks=sum(
            e["summary"]["failed_solve_ticks"]
            for r in (screening, validation)
            for e in r["evaluations"]
        ),
        infrastructure_errors=[
            error for r in (screening, validation) for error in r["infrastructure_errors"]
        ],
        limitations=[
            "One nominal course, geometry parameters only.",
            "Screening selects; only the separate 200-seed holdout validates.",
            "Successful-time averages use different seed subsets; use paired times.",
            "20 ms episode race-time resolution; gate stage does not establish collision cause.",
            "Completion difference confidence interval is approximate paired normal.",
        ],
        input_sha256={
            str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [directory / "selection.json"]
            + [
                directory / cohort / filename
                for cohort in ("screening", "validation")
                for filename in (
                    "report.json",
                    "analysis.json",
                    "summary.csv",
                    "episodes.csv",
                    "comparisons.csv",
                )
            ]
        },
    )
    assert result["completed_episodes"] == 1000
    write_report(directory / "recommendation.json", result)
    return result


def main() -> None:
    """Run 600 screening episodes and 400 independent validation episodes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/level2.toml")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if (args.resume or args.audit_only) and args.output_dir is None:
        parser.error("--resume/--audit-only require --output-dir")
    directory = args.output_dir or ROOT / "logs/mpcc-tuning" / datetime.now(timezone.utc).strftime(
        "local-%Y%m%dT%H%M%S%fZ"
    )
    if args.audit_only:
        for cohort in ("screening", "validation"):
            audit(directory / cohort)
        finish(directory)
        return
    directory.mkdir(parents=True, exist_ok=args.resume)
    print(f"Study: {directory.resolve()}", flush=True)
    config = load_config(args.config.resolve())
    with (ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for cohort in ("screening", "validation"):
            (directory / cohort).mkdir(exist_ok=True)
        if not args.resume:
            write_report(
                directory / "freshness.json",
                freshness_evidence(SCREEN_SEEDS + VALIDATION_SEEDS, directory),
            )
            (directory / "config.toml").write_text(args.config.read_text())
            (directory / "plan.md").write_text(
                (ROOT / "docs/control/mpcc_local_tuning_plan.md").read_text()
            )
        screening_path = directory / "screening"
        # A completed screening report is immutable after selection; do not rewrite on resume.
        if (directory / "selection.json").exists():
            screening = json.loads((screening_path / "report.json").read_text())
            assert screening["manifest"] == fingerprint(config, SCREEN_SEEDS, CASES)
            validate(screening, complete=True)
        else:
            screening = study(
                config, screening_path, resume=(screening_path / "report.json").exists()
            )
        audit(screening_path)
        selected = select_challenger(screening)
        selection = dict(
            selection=selected,
            frozen_at=common.now(),
            screening_report_sha256=hashlib.sha256(
                (screening_path / "report.json").read_bytes()
            ).hexdigest(),
        )
        selection_path = directory / "selection.json"
        if selection_path.exists():
            saved = json.loads(selection_path.read_text())
            assert saved["selection"] == selected
            assert saved["screening_report_sha256"] == selection["screening_report_sha256"]
        else:
            write_report(selection_path, selection)
        challenger = selected["selected"]
        print(f"Frozen challenger: {challenger}; independent validation follows", flush=True)
        validation_path = directory / "validation"
        study(
            config,
            validation_path,
            resume=(validation_path / "report.json").exists(),
            seeds=VALIDATION_SEEDS,
            cases={name: CASES[name] for name in (INCUMBENT, challenger)},
        )
        audit(validation_path)
        result = finish(directory)
        print(f"Recommended: {result['recommended']}", flush=True)
        print(f"Recommendation: {(directory / 'recommendation.json').resolve()}", flush=True)


if __name__ == "__main__":
    main()

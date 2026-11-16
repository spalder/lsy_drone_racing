"""Independently audit a completed fixed MPCC matrix and export readable comparisons."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.compare_mpcc import CASES, COHORTS, ROOT
from scripts.tune_mpcc import write_report


def audit(directory: Path) -> dict:
    """Recalculate counts, summaries, comparisons and CSV contents from episode records."""
    report = json.loads((directory / "report.json").read_text())
    assert report["status"] == "completed"
    assert report["planned_episodes"] == 896
    assert report["manifest"]["cohorts"] == COHORTS
    assert list(report["manifest"]["cases"]) == list(CASES)
    for relative, expected in report["manifest"]["source_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    evaluations = report["evaluations"]
    assert [(e["cohort"], e["configuration"]) for e in evaluations] == [
        (cohort, name) for cohort in COHORTS for name in CASES
    ]
    reference_config = report["manifest"]["cases"]["baseline"]
    expected_mpcc = evaluations[0]["effective_settings"]["mpcc"]
    outcomes = {}
    total = 0
    for evaluation in evaluations:
        cohort, name = evaluation["cohort"], evaluation["configuration"]
        config = evaluation["config"]
        assert config == report["manifest"]["cases"][name]
        assert config["env"] == reference_config["env"]
        assert config["sim"] == reference_config["sim"]
        assert {k: v for k, v in config.items() if k != "controller"} == {
            k: v for k, v in reference_config.items() if k != "controller"
        }
        assert config["controller"]["mpcc"] == {"obstacle_clearance": 0.26}
        snap, lift, pole = CASES[name]
        options = dict(gate_center_snap=snap, over_gate_lift=lift, observed_obstacle_clearance=pole)
        assert config["controller"]["mpcc_experiment"] == options
        assert evaluation["effective_settings"] == dict(mpcc=expected_mpcc, mpcc_experiment=options)
        assert evaluation["status"] == "completed"
        episodes = evaluation["episodes"]
        assert [e["seed"] for e in episodes] == COHORTS[cohort]
        total += len(episodes)
        successful = []
        for episode in episodes:
            assert episode["outcome"] in ("success", "terminated", "timeout")
            assert episode["elapsed_s"] == episode["steps"] / config["env"]["freq"]
            assert episode["steps"] > 0
            assert 0 <= episode["failed_solve_ticks"] <= episode["steps"]
            assert (episode["gates_passed"] == 5) == (episode["outcome"] == "success")
            assert len(episode["command_sha256"]) == 64
            if episode["outcome"] == "success":
                successful.append(episode["elapsed_s"])
        summary = evaluation["summary"]
        assert summary["runs"] == len(episodes)
        assert summary["completed"] == len(successful)
        assert summary["completion_rate"] == len(successful) / len(episodes)
        if successful:
            assert math.isclose(
                summary["average_success_time_s"], sum(successful) / len(successful), abs_tol=1e-12
            )
        else:
            assert summary["average_success_time_s"] is None
        assert summary["failed_solve_ticks"] == sum(e["failed_solve_ticks"] for e in episodes)
        outcomes[cohort, name] = {e["seed"]: e for e in episodes}
    assert total == 896
    with (directory / "episodes.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == total
    expected_rows = [
        dict(cohort=e["cohort"], configuration=e["configuration"], **episode)
        for e in evaluations
        for episode in e["episodes"]
    ]
    for actual, expected in zip(rows, expected_rows):
        assert actual == {key: str(value) for key, value in expected.items()}
    with (directory / "summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 16
    for actual, evaluation in zip(rows, evaluations):
        expected = dict(
            cohort=evaluation["cohort"],
            configuration=evaluation["configuration"],
            **evaluation["summary"],
        )
        assert actual == {k: "" if v is None else str(v) for k, v in expected.items()}
    details = {}
    for cohort, comparisons in report["comparisons"].items():
        assert len(comparisons) == 14
        details[cohort] = []
        for comparison in comparisons:
            a = outcomes[cohort, comparison["reference"]]
            b = outcomes[cohort, comparison["candidate"]]
            sa = {s for s in a if a[s]["outcome"] == "success"}
            sb = {s for s in b if b[s]["outcome"] == "success"}
            assert comparison["newly_completed_seeds"] == sorted(sb - sa)
            assert comparison["regressed_seeds"] == sorted(sa - sb)
            shared = sorted(sa & sb)
            assert comparison["shared_success_seeds"] == shared
            differences = {str(s): b[s]["elapsed_s"] - a[s]["elapsed_s"] for s in shared}
            assert comparison["paired_time_differences_s"] == differences
            if shared:
                assert math.isclose(
                    comparison["mean_paired_time_difference_s"],
                    sum(differences.values()) / len(shared),
                    abs_tol=1e-12,
                )
            else:
                assert comparison["mean_paired_time_difference_s"] is None
            assert comparison["numerical_failure_tick_difference"] == (
                sum(e["failed_solve_ticks"] for e in b.values())
                - sum(e["failed_solve_ticks"] for e in a.values())
            )
            detail = dict(comparison)
            detail["changed_outcomes"] = [
                dict(seed=s, reference=a[s], candidate=b[s]) for s in sorted(sa ^ sb)
            ]
            detail["numerical_failure_episodes_reference"] = [
                a[s] for s in a if a[s]["failed_solve_ticks"]
            ]
            detail["numerical_failure_episodes_candidate"] = [
                b[s] for s in b if b[s]["failed_solve_ticks"]
            ]
            details[cohort].append(detail)
    interactions = {}
    for cohort in COHORTS:
        successes = {
            name: {s for s, e in outcomes[cohort, name].items() if e["outcome"] == "success"}
            for name in CASES
        }
        interactions[cohort] = []
        for pair, singles in (
            ("recenter_and_height", ["recenter_only", "height_only"]),
            ("recenter_and_observed_poles", ["recenter_only", "observed_poles_only"]),
            ("height_and_observed_poles", ["height_only", "observed_poles_only"]),
            ("all_three", ["recenter_and_height", "observed_poles_only"]),
        ):
            union = set().union(*(successes[s] for s in singles))
            interactions[cohort].append(
                dict(
                    configuration=pair,
                    constituents=singles,
                    completed_beyond_constituent_union=sorted(successes[pair] - union),
                    lost_from_constituent_union=sorted(union - successes[pair]),
                )
            )
    result = dict(
        status="validated",
        episodes=total,
        diagnostic_episodes=96,
        fresh_episodes=800,
        input_sha256={
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("report.json", "summary.csv", "episodes.csv")
        },
        execution_definitions=dict(
            episode_seed="env.reset(seed=episode.seed); config.env.seed=6 seeds shared environment construction only",
            controller="new MeasuredMPCC (an ExperimentalMPCC subclass recording settings) per episode",
            order="serial; complete diagnostic cohort, then fresh cohort; same ordered seeds for every configuration",
            observed_poles="0.30 m for revealed poles on replans only; initial and unrevealed poles retain 0.26 m",
        ),
        timing_definitions=dict(
            race_time="completed environment steps / 50 Hz; stop at the completion callback",
            successful_mean="arithmetic mean of successful episodes; subsets may differ",
            paired_difference="candidate minus reference race time on shared successful seeds",
            control_quantiles="p50/p95 of perf_counter compute_control durations, in milliseconds; "
            "exclude construction, environment stepping and callbacks; wall times depend on machine load",
        ),
        infrastructure_errors=report["infrastructure_errors"],
        comparisons=details,
        interactions=interactions,
        checks=[
            "ordered seeds, exact matrix and 896 unique episode keys",
            "all effective optimizer settings identical; only declared factors differ",
            "current source hashes match execution manifest",
            "summary counts, rates, means, failure ticks independently recalculated",
            "summary and episode CSV exports exactly match JSON",
            "all newly completed, regressed and shared seed sets and paired times recalculated",
        ],
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    write_report(directory / "analysis.json", result)
    lines = [
        "# MPCC combination study: measured comparisons",
        "",
        "Diagnostic seeds are deliberately selected; fresh seeds are 101–200. "
        "Paired time differences are candidate minus reference on shared successful seeds.",
        "",
        "| Configuration | Diagnostic completion | Fresh completion | Fresh mean success time (s) | Failure ticks (diagnostic / fresh) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    by_key = {(e["cohort"], e["configuration"]): e["summary"] for e in evaluations}
    for name in CASES:
        d, f = by_key["diagnostic", name], by_key["fresh", name]
        lines.append(
            f"| {name} | {d['completed']}/12 | {f['completed']}/100 ({f['completion_rate']:.0%}) | "
            f"{f['average_success_time_s']:.6f} | {d['failed_solve_ticks']} / {f['failed_solve_ticks']} |"
        )
    for cohort in COHORTS:
        lines += [
            "",
            f"## {cohort.capitalize()} paired comparisons",
            "",
            "| Reference → candidate | Newly completed seeds | Regressed seeds | Shared finishes | Mean paired Δ (ms) |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for c in details[cohort]:
            delta = c["mean_paired_time_difference_s"]
            time_text = f"{1000 * delta:.3f}" if delta is not None else "n/a"
            lines.append(
                f"| {c['reference']} → {c['candidate']} | {c['newly_completed_seeds']} | "
                f"{c['regressed_seeds']} | {len(c['shared_success_seeds'])} | "
                f"{time_text} |"
            )
        lines += ["", "Interactions relative to the union of constituent completion sets:", ""]
        for interaction in interactions[cohort]:
            lines.append(
                f"- {interaction['configuration']}: beyond union "
                f"{interaction['completed_beyond_constituent_union']}; lost from union "
                f"{interaction['lost_from_constituent_union']}."
            )
    lines += [
        "",
        "## Validation and limits",
        "",
        "All 896 episodes passed independent validation. JSON and CSV agree. "
        "Race failures and numerical failure ticks remain measured outcomes; "
        f"infrastructure error records: {len(report['infrastructure_errors'])}.",
        "",
        "Successful-run means use different seed subsets and must not be interpreted as speed comparisons. "
        "Paired race times have 20 ms episode resolution at 50 Hz. "
        "These are nominal-course level-2 simulations with 100 fresh seeds, "
        "not deployment validation or evidence of generalization to other tracks. "
        "Diagnostic results are selected examples and must not be pooled with the fresh cohort. "
        "The same fresh cohort compares and selects candidates; selection can be optimistic.",
        "",
        "See `analysis.json` for every regression/rescue episode, numerical-failure episode, "
        "per-seed paired difference and interaction set. `report.json` contains the complete "
        "execution manifest, exact configurations, effective optimizer settings and source hashes.",
        "",
    ]
    (directory / "analysis.md").write_text("\n".join(lines))
    print(f"Validated {total} episodes: {directory.resolve() / 'analysis.json'}")
    return result


def historical_replays(directory: Path) -> dict:
    """Check matching diagnostic episodes against the studies that motivated this matrix."""
    current = json.loads((directory / "report.json").read_text())
    matches = []
    sources = {}
    for name in ("isolated-20261102", "20261102T152057339212Z", "20261102T153152610204Z"):
        path = ROOT / "logs/mpcc-tuning" / name / "report.json"
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        old = json.loads(path.read_text())
        for controller in ("attitude_mpcc.py", "attitude_mpcc_experimental.py"):
            key = f"lsy_drone_racing/control/{controller}"
            assert old["source_sha256"][key] == current["manifest"]["source_sha256"][key]
        for evaluation in current["evaluations"]:
            if evaluation["cohort"] != "diagnostic":
                continue
            for prior in old["evaluations"]:
                if evaluation["config"]["controller"] != prior["controller_config"]:
                    continue
                previous = {e["seed"]: e for e in prior["episodes"]}
                for episode in evaluation["episodes"]:
                    seed = episode["seed"]
                    if seed not in previous:
                        continue
                    checks = {
                        key: episode[key] == previous[seed][key]
                        for key in (
                            "outcome",
                            "gates_passed",
                            "steps",
                            "elapsed_s",
                            "failed_solve_ticks",
                            "command_sha256",
                        )
                    }
                    assert all(checks.values()), (name, evaluation["configuration"], seed, checks)
                    matches.append(
                        dict(
                            source=name,
                            parameter=prior["parameter"],
                            value=prior["value"],
                            configuration=evaluation["configuration"],
                            seed=seed,
                            checks=checks,
                        )
                    )
    result = dict(
        status="validated",
        source_report_sha256=sources,
        matched_records=len(matches),
        unique_replayed_episodes=len({(m["configuration"], m["seed"]) for m in matches}),
        matches=matches,
    )
    write_report(directory / "historical-replay-check.json", result)
    print(
        f"Historical replay: {result['unique_replayed_episodes']} unique episodes matched exactly"
    )
    return result


def main():
    """Write the independent audit and historical replay check beside a completed report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    directory = parser.parse_args().directory
    audit(directory)
    historical_replays(directory)


if __name__ == "__main__":
    main()

"""Run the fixed, serial eight-configuration MPCC combination study with safe resume."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from lsy_drone_racing.control.attitude_mpcc_experimental import ExperimentalMPCC
from lsy_drone_racing.utils import load_config
from scripts.probe_mpcc import create_environment, run_episode
from scripts.tune_mpcc import ROOT, simulation_output, write_report

CASES = {
    "baseline": (1.0, 0.0, None),
    "recenter_only": (0.0, 0.0, None),
    "height_only": (1.0, 0.05, None),
    "observed_poles_only": (1.0, 0.0, 0.30),
    "recenter_and_height": (0.0, 0.05, None),
    "recenter_and_observed_poles": (0.0, 0.0, 0.30),
    "height_and_observed_poles": (1.0, 0.05, 0.30),
    "all_three": (0.0, 0.05, 0.30),
}
COHORTS = {
    "diagnostic": [6, 8, 9, 10, 12, 18, 19, 55, 72, 76, 80, 1337],
    "fresh": list(range(101, 201)),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def candidate_config(config, values):
    candidate = deepcopy(config)
    candidate.sim.render = False
    candidate.env.seed = COHORTS["diagnostic"][0]
    candidate.controller.file = "attitude_mpcc_experimental.py"
    candidate.controller.mpcc = dict(candidate.controller.get("mpcc", {}), obstacle_clearance=0.26)
    candidate.controller.mpcc_experiment = dict(
        zip(("gate_center_snap", "over_gate_lift", "observed_obstacle_clearance"), values)
    )
    return candidate


class MeasuredMPCC(ExperimentalMPCC):
    """Capture the effective optimizer defaults without changing control behavior."""

    effective = None

    def __init__(self, obs, info, config):
        super().__init__(obs, info, config)
        type(self).effective = dict(
            mpcc=self.settings,
            mpcc_experiment=dict(
                gate_center_snap=self.gate_center_snap,
                over_gate_lift=self.over_gate_lift,
                observed_obstacle_clearance=self.observed_obstacle_clearance,
            ),
        )


def fingerprint(config, cohorts):
    paths = sorted(
        set(
            list((ROOT / "lsy_drone_racing").rglob("*.py"))
            + list((ROOT / "lsy_drone_racing").rglob("*.xml"))
            + list((ROOT / "config").rglob("*.toml"))
            + [
                ROOT / "scripts" / name
                for name in ("compare_mpcc.py", "probe_mpcc.py", "tune_mpcc.py")
            ]
            + list((ROOT / "acados/lib").glob("*.so"))
        )
    )
    return dict(
        cases={name: candidate_config(config, values).to_dict() for name, values in CASES.items()},
        cohorts=cohorts,
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
        runtime=dict(
            python=platform.python_version(),
            platform=platform.platform(),
            packages={
                name: importlib.metadata.version(name)
                for name in (
                    "numpy",
                    "scipy",
                    "jax",
                    "jaxlib",
                    "mujoco",
                    "crazyflow",
                    "gymnasium",
                    "acados-template",
                )
            },
            environment={
                k: os.environ.get(k)
                for k in (
                    "JAX_PLATFORM_NAME",
                    "JAX_ENABLE_X64",
                    "XLA_FLAGS",
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                )
            },
        ),
    )


def summarize(episodes):
    times = [e["elapsed_s"] for e in episodes if e["outcome"] == "success"]
    return dict(
        runs=len(episodes),
        completed=len(times),
        completion_rate=len(times) / len(episodes),
        average_success_time_s=mean(times) if times else None,
        failed_solve_ticks=sum(e["failed_solve_ticks"] for e in episodes),
    )


def csv_exports(directory, report):
    for filename, rows in (
        (
            "episodes.csv",
            [
                dict(cohort=e["cohort"], configuration=e["configuration"], **row)
                for e in report["evaluations"]
                for row in e["episodes"]
            ],
        ),
        (
            "summary.csv",
            [
                dict(cohort=e["cohort"], configuration=e["configuration"], **e["summary"])
                for e in report["evaluations"]
                if e["status"] == "completed"
            ],
        ),
    ):
        if not rows:
            continue
        temporary = directory / (filename + ".tmp")
        with temporary.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(directory / filename)


def validate(report, complete=False):
    manifest = report["manifest"]
    expected = [(cohort, name) for cohort in manifest["cohorts"] for name in CASES]
    assert [(e["cohort"], e["configuration"]) for e in report["evaluations"]] == expected
    count = 0
    for evaluation in report["evaluations"]:
        seeds = manifest["cohorts"][evaluation["cohort"]]
        episodes = evaluation["episodes"]
        assert [e["seed"] for e in episodes] == seeds[: len(episodes)]
        assert evaluation["config"] == manifest["cases"][evaluation["configuration"]]
        for episode in episodes:
            assert episode["outcome"] in ("success", "terminated", "timeout")
            assert episode["elapsed_s"] == episode["steps"] / evaluation["config"]["env"]["freq"]
            assert 0 <= episode["failed_solve_ticks"] <= episode["steps"]
            assert (episode["gates_passed"] == 5) == (episode["outcome"] == "success")
        if evaluation["status"] == "completed":
            assert len(episodes) == len(seeds)
            assert evaluation["summary"] == summarize(episodes)
        if complete:
            assert evaluation["status"] == "completed"
            effective = evaluation["effective_settings"]
            assert effective["mpcc"]["obstacle_clearance"] == 0.26
            assert (
                effective["mpcc_experiment"]
                == evaluation["config"]["controller"]["mpcc_experiment"]
            )
            assert effective["mpcc"] == report["evaluations"][0]["effective_settings"]["mpcc"]
        count += len(episodes)
    if complete:
        assert count == report["planned_episodes"]
    return dict(
        validated_episodes=count,
        expected_episodes=report["planned_episodes"],
        complete=complete,
        checked_at=now(),
    )


def compare(reference, candidate):
    a = {e["seed"]: e for e in reference["episodes"]}
    b = {e["seed"]: e for e in candidate["episodes"]}
    assert a.keys() == b.keys()
    sa = {s for s in a if a[s]["outcome"] == "success"}
    sb = {s for s in b if b[s]["outcome"] == "success"}
    shared = sorted(sa & sb)
    return dict(
        reference=reference["configuration"],
        candidate=candidate["configuration"],
        newly_completed_seeds=sorted(sb - sa),
        regressed_seeds=sorted(sa - sb),
        shared_success_seeds=shared,
        mean_paired_time_difference_s=mean(b[s]["elapsed_s"] - a[s]["elapsed_s"] for s in shared)
        if shared
        else None,
        paired_time_differences_s={str(s): b[s]["elapsed_s"] - a[s]["elapsed_s"] for s in shared},
        numerical_failure_tick_difference=candidate["summary"]["failed_solve_ticks"]
        - reference["summary"]["failed_solve_ticks"],
    )


def analyze(report):
    comparisons = {}
    for cohort in report["manifest"]["cohorts"]:
        items = {e["configuration"]: e for e in report["evaluations"] if e["cohort"] == cohort}
        pairs = [("baseline", name) for name in CASES if name != "baseline"]
        for pair, singles in (
            ("recenter_and_height", ("recenter_only", "height_only")),
            ("recenter_and_observed_poles", ("recenter_only", "observed_poles_only")),
            ("height_and_observed_poles", ("height_only", "observed_poles_only")),
        ):
            pairs.extend((single, pair) for single in singles)
        pairs.append(("recenter_and_height", "all_three"))
        comparisons[cohort] = [compare(items[a], items[b]) for a, b in pairs]
    return comparisons


def study(config, directory, resume=False, cohorts=None):
    cohorts = COHORTS if cohorts is None else cohorts
    manifest = fingerprint(config, cohorts)
    path = directory / "report.json"
    print(f"Report: {path.resolve()}", flush=True)
    if resume:
        report = json.loads(path.read_text())
        if report["manifest"] != manifest:
            raise ValueError("Resume rejected: source, runtime, seeds, or settings differ.")
        validate(report)
    else:
        if path.exists():
            raise FileExistsError(path)
        report = dict(
            schema_version=1,
            status="running",
            started_at=now(),
            manifest=manifest,
            planned_episodes=sum(map(len, cohorts.values())) * len(CASES),
            time_definition="elapsed_s = completed control steps / env.freq; completion callback stops race",
            average_time_definition="mean elapsed_s over successful episodes only; not a paired speed comparison",
            paired_time_definition="candidate minus reference elapsed_s on shared successful seeds",
            numerical_failure_definition="control ticks with controller._prediction is None; measured outcome",
            infrastructure_errors=[],
            evaluations=[
                dict(
                    cohort=cohort,
                    configuration=name,
                    config=manifest["cases"][name],
                    status="pending",
                    episodes=[],
                )
                for cohort in cohorts
                for name in CASES
            ],
        )
    report["status"] = "running"
    write_report(path, report)
    env = None
    with (directory / "simulation.log").open("a", buffering=1) as log:
        try:
            for evaluation in report["evaluations"]:
                if evaluation["status"] == "completed":
                    continue
                candidate = candidate_config(config, CASES[evaluation["configuration"]])
                seeds = cohorts[evaluation["cohort"]]
                for seed in seeds[len(evaluation["episodes"]) :]:
                    with simulation_output(log):
                        print(
                            f"{now()} {evaluation['cohort']} {evaluation['configuration']} seed={seed}",
                            flush=True,
                        )
                        if env is None:
                            env = create_environment(candidate)
                        episode = run_episode(env, MeasuredMPCC, candidate, seed)
                    effective = deepcopy(MeasuredMPCC.effective)
                    if "effective_settings" in evaluation:
                        assert evaluation["effective_settings"] == effective
                    evaluation["effective_settings"] = effective
                    evaluation["episodes"].append(episode)
                    write_report(path, report)
                evaluation["summary"] = summarize(evaluation["episodes"])
                evaluation["status"] = "completed"
                write_report(path, report)
                csv_exports(directory, report)
                summary = evaluation["summary"]
                average = summary["average_success_time_s"]
                print(
                    f"{evaluation['cohort']} / {evaluation['configuration']}: "
                    f"{summary['completed']}/{summary['runs']} ({summary['completion_rate']:.1%}); "
                    f"average successful race time {average if average is not None else 'n/a'} s",
                    flush=True,
                )
            report["validation"] = validate(report, complete=True)
            report["comparisons"] = analyze(report)
            report["status"] = "completed"
        except BaseException as error:
            report["status"] = (
                "interrupted" if isinstance(error, KeyboardInterrupt) else "infrastructure_error"
            )
            report["infrastructure_errors"].append(
                dict(
                    at=now(),
                    cohort=evaluation["cohort"],
                    configuration=evaluation["configuration"],
                    seed=seed if "seed" in locals() else None,
                    error=f"{type(error).__name__}: {error}",
                    traceback=traceback.format_exc(),
                )
            )
            raise
        finally:
            report["updated_at"] = now()
            write_report(path, report)
            csv_exports(directory, report)
            if env is not None:
                with simulation_output(log):
                    env.close()
    print(f"Report ({report['status']}): {path.resolve()}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/level2.toml")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.resume and args.output_dir is None:
        parser.error("--resume requires --output-dir")
    directory = args.output_dir or ROOT / "logs/mpcc-tuning" / datetime.now(timezone.utc).strftime(
        "combined-%Y%m%dT%H%M%S%fZ"
    )
    directory.mkdir(parents=True, exist_ok=args.resume)
    # acados uses shared generated files; prohibit concurrent matrix runners.
    with (ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not args.resume:
            (directory / "config.toml").write_text(args.config.read_text())
        study(load_config(args.config.resolve()), directory, args.resume)


if __name__ == "__main__":
    main()

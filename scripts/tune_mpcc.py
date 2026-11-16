"""Tune MPCC parameters separately, using five values and twenty seeds by default."""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING

from lsy_drone_racing.control.attitude_mpcc_experimental import ExperimentalMPCC
from lsy_drone_racing.utils import load_config

if __package__:
    from .probe_mpcc import create_environment, run_episode
else:
    from probe_mpcc import create_environment, run_episode

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRIDS = {
    "observed_obstacle_clearance": [0.26, 0.28, 0.30, 0.32, 0.34],
    "gate_center_snap": [1.0, 0.75, 0.5, 0.25, 0.0],
    "over_gate_lift": [0.0, 0.05, 0.10, 0.15, 0.20],
    "obstacle_clearance": [0.26, 0.28, 0.30, 0.32, 0.34],
}


@contextmanager
def simulation_output(stream: TextIO) -> Iterator[None]:
    """Keep Python, native solver, and compiler chatter in a diagnostic log."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(fd) for fd in (1, 2)]
    try:
        for fd in (1, 2):
            os.dup2(stream.fileno(), fd)
        with redirect_stdout(stream), redirect_stderr(stream):
            yield
    finally:
        stream.flush()
        ctypes.CDLL(None).fflush(None)  # Flush native solver output before restoring the console.
        for fd, original in zip((1, 2), saved):
            os.dup2(original, fd)
            os.close(original)


def isolated_config(baseline: dict, parameter: str, value: float) -> dict:
    """Change exactly one parameter from the declared neutral configuration."""
    candidate = deepcopy(baseline)
    if parameter == "obstacle_clearance":
        candidate.controller.mpcc[parameter] = value
    else:
        candidate.controller.mpcc_experiment[parameter] = value
    return candidate


def write_report(path: Path, report: dict):
    """Checkpoint structured results atomically after each completed evaluation."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def tune(config: dict, seeds: list[int], grids: dict, output_dir: Path) -> dict:
    """Evaluate each parameter independently, saving summaries and individual outcomes."""
    baseline = deepcopy(config)
    baseline.sim.render = False
    baseline.env.seed = seeds[0]
    options = dict(baseline.controller.get("mpcc", {}))
    options["obstacle_clearance"] = 0.26
    baseline.controller.mpcc = options
    baseline.controller.file = "attitude_mpcc_experimental.py"
    baseline.controller.mpcc_experiment = dict(
        gate_center_snap=1.0, over_gate_lift=0.0, observed_obstacle_clearance=None
    )
    report_path = output_dir / "report.json"
    report = dict(
        schema_version=1,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        design="one parameter at a time; same ordered seeds for every value",
        seeds=seeds,
        parameter_grids=grids,
        planned_evaluations=sum(len(values) for values in grids.values()),
        planned_episodes=len(seeds) * sum(len(values) for values in grids.values()),
        time_definition="completed control steps / frequency; stop on completion callback",
        average_time_definition="mean elapsed_s of successful episodes only; null if none finish",
        completion_rate_definition="successful episodes / runs; fraction from 0 to 1",
        baseline_config=baseline.to_dict(),
        source_sha256={
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ROOT / "scripts/tune_mpcc.py",
                ROOT / "scripts/probe_mpcc.py",
                ROOT / "lsy_drone_racing/control/attitude_mpcc.py",
                ROOT / "lsy_drone_racing/control/attitude_mpcc_experimental.py",
            )
        },
        evaluations=[],
    )
    write_report(report_path, report)
    total = report["planned_evaluations"]
    print(
        f"Tuning {len(grids)} parameters, {total} evaluations, {report['planned_episodes']} runs.",
        flush=True,
    )
    print(f"Report: {report_path.resolve()}", flush=True)
    env = None
    try:
        with (
            (output_dir / "simulation.log").open("w", buffering=1) as log,
            (output_dir / "episodes.csv").open("w", newline="") as episodes_file,
            (output_dir / "summary.csv").open("w", newline="") as summary_file,
        ):
            summary_writer = csv.DictWriter(
                summary_file,
                fieldnames=[
                    "parameter",
                    "value",
                    "runs",
                    "completed",
                    "completion_rate",
                    "average_success_time_s",
                    "failed_solve_ticks",
                ],
            )
            summary_writer.writeheader()
            episode_writer = None
            with simulation_output(log):
                env = create_environment(baseline)
            for parameter, values in grids.items():
                for value in values:
                    candidate = isolated_config(baseline, parameter, value)
                    episodes = []
                    with simulation_output(log):
                        for seed in seeds:
                            episode = dict(parameter=parameter, value=value)
                            episode.update(run_episode(env, ExperimentalMPCC, candidate, seed))
                            episodes.append(episode)
                            if episode_writer is None:
                                episode_writer = csv.DictWriter(
                                    episodes_file, fieldnames=list(episode)
                                )
                                episode_writer.writeheader()
                            episode_writer.writerow(episode)
                            episodes_file.flush()
                    successful_times = [
                        episode["elapsed_s"]
                        for episode in episodes
                        if episode["outcome"] == "success"
                    ]
                    summary = dict(
                        parameter=parameter,
                        value=value,
                        runs=len(episodes),
                        completed=len(successful_times),
                        completion_rate=len(successful_times) / len(episodes),
                        average_success_time_s=mean(successful_times) if successful_times else None,
                        failed_solve_ticks=sum(e["failed_solve_ticks"] for e in episodes),
                    )
                    summary_writer.writerow(summary)
                    summary_file.flush()
                    report["evaluations"].append(
                        dict(
                            **summary,
                            controller_config=candidate.controller.to_dict(),
                            episodes=episodes,
                        )
                    )
                    write_report(report_path, report)
                    average = summary["average_success_time_s"]
                    average_text = (
                        f"{average:.3f} s" if average is not None else "n/a (no completions)"
                    )
                    print(
                        f"[{len(report['evaluations'])}/{total}] {parameter}={value:g}: "
                        f"{len(successful_times)}/{len(episodes)} completed "
                        f"({summary['completion_rate']:.0%}); "
                        f"average successful time {average_text}",
                        flush=True,
                    )
        report["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_report(report_path, report)
        print(f"Report ({report['status']}): {report_path.resolve()}", flush=True)
        if env is not None:
            with (output_dir / "simulation.log").open("a") as log, simulation_output(log):
                env.close()
    return report


def main():
    """Run the default 400-episode tuning study or an explicitly selected subset."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/level2.toml")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 21)))
    parser.add_argument(
        "--parameters", nargs="+", choices=list(DEFAULT_GRIDS), default=list(DEFAULT_GRIDS)
    )
    for flag, parameter in (
        ("observed-clearance", "observed_obstacle_clearance"),
        ("snap", "gate_center_snap"),
        ("lift", "over_gate_lift"),
        ("clearance", "obstacle_clearance"),
    ):
        parser.add_argument(
            f"--{flag}", type=float, nargs="+", dest=parameter, default=DEFAULT_GRIDS[parameter]
        )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs/mpcc-tuning" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
    )
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Seeds must be distinct for paired comparisons.")
    grids = {parameter: getattr(args, parameter) for parameter in args.parameters}
    if any(len(set(values)) != len(values) for values in grids.values()):
        parser.error("Each parameter requires distinct values.")
    for parameter, values in grids.items():
        if any(not isfinite(value) or value < 0 for value in values):
            parser.error(f"{parameter} values must be finite and nonnegative.")
        if parameter == "gate_center_snap" and any(value > 1 for value in values):
            parser.error("gate_center_snap values must be between 0 and 1.")
        if "clearance" in parameter and any(value == 0 for value in values):
            parser.error(f"{parameter} values must be positive.")
    config = load_config(args.config.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "config.toml").write_text(args.config.read_text())
    tune(config, args.seeds, grids, args.output_dir)


if __name__ == "__main__":
    main()

"""Prepare or execute a budgeted, adaptive MPCC optimizer study (serial simulation)."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

import gymnasium
import numpy as np
from ml_collections import ConfigDict

from lsy_drone_racing.utils import load_config
from scripts import compare_mpcc as common
from scripts.probe_mpcc import create_environment, run_episode
from scripts.tune_mpcc import ROOT, simulation_output, write_report

BASE = dict(
    horizon_steps=40,
    reference_speed=1.3,
    max_speed=1.8,
    contour_weight=400.0,
    lag_weight=400.0,
    progress_weight=12.0,
    max_angle=0.6,
    attitude_rate_weight=0.1,
    attitude_slew_weight=0.02,
    thrust_slew_weight=0.1,
    terminal_weight=0.2,
    adaptation_rate=2.0,
    obstacle_clearance=0.26,
)
GRIDS = dict(
    reference_speed=[1.2, 1.3, 1.4, 1.5, 1.6],
    progress_weight=[6, 12, 24],
    attitude_slew_weight=[0.01, 0.02, 0.04],
    thrust_slew_weight=[0.05, 0.1, 0.2],
    max_angle=[0.6, 0.65, 0.7],
    horizon_steps=[30, 40, 60],
    contour_weight=[200, 400, 800],
    lag_weight=[200, 400, 800],
    attitude_rate_weight=[0.05, 0.1, 0.2],
    terminal_weight=[0.1, 0.2, 0.4],
)
# One typical grid step; L1 distance sums absolute departures divided by these scales.
SCALES = dict(
    reference_speed=0.1,
    progress_weight=12,
    attitude_slew_weight=0.02,
    thrust_slew_weight=0.1,
    max_angle=0.05,
    horizon_steps=20,
    contour_weight=400,
    lag_weight=400,
    attitude_rate_weight=0.1,
    terminal_weight=0.2,
    max_speed=0.2,
)
BOUNDS = dict(
    reference_speed=(1.1, 1.7),
    progress_weight=(3, 36),
    attitude_slew_weight=(0.005, 0.06),
    thrust_slew_weight=(0.025, 0.3),
    max_angle=(0.55, 0.75),
    horizon_steps=(20, 70),
    contour_weight=(100, 1200),
    lag_weight=(100, 1200),
    attitude_rate_weight=(0.025, 0.3),
    terminal_weight=(0.05, 0.6),
    max_speed=(1.8, 2.2),
)
STAGES = ["screening", "refinement", "combinations", "challenges", "confirmation", "validation"]
SIZES = [40, 60, 80, 80, 150, 1500]
GEOMETRY = dict(gate_center_snap=0.0, over_gate_lift=0.05, observed_obstacle_clearance=None)
PENALTY = 30.0
LATENCY = dict(max_episode_p99_ms=20.0, max_overrun_fraction=0.01)


def read(path: Path) -> dict:
    """Read a JSON object."""
    return json.loads(Path(path).read_text())


def sha(path: Path) -> str:
    """Hash an existing file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value: dict) -> str:
    """Hash a canonical JSON value."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def case(overrides: dict | None = None) -> dict:
    """Validate and canonicalize optimizer settings."""
    values = dict(BASE, **(overrides or {}))
    assert set(values) == set(BASE)
    assert values["adaptation_rate"] == 2 and values["obstacle_clearance"] == 0.26
    for key, value in values.items():
        assert math.isfinite(value) and value > 0
        if key in BOUNDS:
            assert BOUNDS[key][0] <= value <= BOUNDS[key][1], (key, value)
    assert int(values["horizon_steps"]) == values["horizon_steps"]
    # Canonical numeric types make 400 and 400.0 identical for deduplication.
    return {k: int(v) if k == "horizon_steps" else float(v) for k, v in values.items()}


def name(values: dict) -> str:
    """Name a configuration by its canonical settings."""
    values = case(values)
    return "incumbent" if values == case() else "opt_" + digest(values)[:12]


def unique(values: list[dict]) -> dict:
    """Deduplicate settings while retaining insertion order."""
    result = {}
    for value in values:
        v = case(value)
        result.setdefault(name(v), v)
    return result


def screening_cases() -> dict:
    """Build the 23 isolated screening configurations."""
    return unique([BASE] + [dict(BASE, **{k: v}) for k, grid in GRIDS.items() for v in grid])


def candidate_config(config: dict, values: dict, initial_seed: int) -> dict:
    """Apply optimizer overrides while keeping the incumbent geometry."""
    candidate = common.candidate_config(config, (0.0, 0.05, None))
    candidate.env.seed = initial_seed
    candidate.controller.mpcc = case(values)
    return candidate


class ObservedMPCC(common.MeasuredMPCC):
    """Read-only instrumentation around the original controller call."""

    latest = None

    def __init__(self, obs: dict, info: dict | None, config: dict) -> None:
        """Construct the original controller and allocate diagnostics."""
        super().__init__(obs, info, config)
        self.call_ms, self.replan_ms = [], []
        self.cap_ticks = self.angle_ticks = self.valid_ticks = 0
        self.max_progress_speed = 0.0
        type(self).latest = self

    def compute_control(self, obs: dict, info: dict | None = None) -> np.ndarray:
        """Return the original command and observe timing/saturation."""
        started = time.perf_counter()
        revision = self._path_geometry_revision
        action = super().compute_control(obs, info)
        if self._prediction is not None:
            self.valid_ticks += 1
            speed = float(self._inputs[0, 4])
            self.max_progress_speed = max(self.max_progress_speed, speed)
            self.cap_ticks += int(speed >= 0.98 * self.settings["max_speed"])
            self.angle_ticks += int(np.max(np.abs(action[:3])) >= 0.98 * self.settings["max_angle"])
        elapsed = 1000 * (time.perf_counter() - started)
        self.call_ms.append(elapsed)
        if revision != self._path_geometry_revision:
            self.replan_ms.append(elapsed)
        return action


def measured_episode(env: gymnasium.Env, config: dict, seed: int) -> dict:
    """Reuse the existing episode loop and attach read-only diagnostics."""
    started = time.perf_counter()
    episode = run_episode(env, ObservedMPCC, config, seed)
    controller = ObservedMPCC.latest
    episode.update(
        wall_s=time.perf_counter() - started,
        effective_settings=deepcopy(ObservedMPCC.effective),
        whole_call_p99_ms=float(np.percentile(controller.call_ms, 99)),
        whole_call_max_ms=max(controller.call_ms),
        whole_call_overruns=sum(x > 20 for x in controller.call_ms),
        replan_calls=len(controller.replan_ms),
        replan_max_ms=max(controller.replan_ms, default=0.0),
        valid_solve_ticks=controller.valid_ticks,
        progress_cap_ticks=controller.cap_ticks,
        attitude_bound_ticks=controller.angle_ticks,
        max_progress_speed=controller.max_progress_speed,
    )
    return episode


def summary(episodes: list[dict]) -> dict:
    """Summarize race outcomes, fixed penalties and call latency."""
    s = common.summarize(episodes)
    s.update(
        penalized_mean_s=mean(
            e["elapsed_s"] if e["outcome"] == "success" else PENALTY for e in episodes
        ),
        max_episode_p99_ms=max(e["whole_call_p99_ms"] for e in episodes),
        overrun_fraction=sum(e["whole_call_overruns"] for e in episodes)
        / sum(e["steps"] for e in episodes),
        progress_cap_fraction=sum(e["progress_cap_ticks"] for e in episodes)
        / max(1, sum(e["valid_solve_ticks"] for e in episodes)),
    )
    s["latency_eligible"] = (
        s["max_episode_p99_ms"] <= LATENCY["max_episode_p99_ms"]
        and s["overrun_fraction"] <= LATENCY["max_overrun_fraction"]
    )
    return s


def compare(a: dict, b: dict) -> dict:
    """Compare matched seeds and successful race times."""
    c = common.compare(a, b)
    d = list(c["paired_time_differences_s"].values())
    c.update(
        median_paired_s=float(np.median(d)) if d else None,
        p90_paired_s=float(np.percentile(d, 90)) if d else None,
        p95_paired_s=float(np.percentile(d, 95)) if d else None,
        penalized_mean_difference_s=b["summary"]["penalized_mean_s"]
        - a["summary"]["penalized_mean_s"],
    )
    return c


def rankings(report: dict) -> list[dict]:
    """Apply prespecified eligibility and deterministic ordering."""
    evaluations = report["evaluations"]
    ref = next(e for e in evaluations if e["configuration"] == "incumbent")
    result = []
    for e in evaluations:
        if e is ref:
            continue
        c = compare(ref, e)
        s = e["summary"]
        eligible = (
            s["completed"] >= ref["summary"]["completed"]
            and s["failed_solve_ticks"] <= ref["summary"]["failed_solve_ticks"]
            and s["latency_eligible"]
            and c["mean_paired_time_difference_s"] is not None
        )
        distance = round(
            sum(abs(e["settings"][k] - BASE[k]) / scale for k, scale in SCALES.items()), 10
        )
        result.append(
            dict(
                configuration=e["configuration"],
                settings=e["settings"],
                eligible=eligible,
                completed=s["completed"],
                failed_solve_ticks=s["failed_solve_ticks"],
                latency_eligible=s["latency_eligible"],
                distance=distance,
                paired_s=c["mean_paired_time_difference_s"],
                penalty_s=s["penalized_mean_s"],
            )
        )
    # Noneligible fallback: latency first, numerical ticks, completion, paired speed,
    # distance, name. Saved separately from eligibility to avoid a hidden objective switch.
    result.sort(
        key=lambda r: (
            not r["eligible"],
            r["paired_s"] if r["eligible"] else (0 if r["latency_eligible"] else 1),
            -r["completed"] if r["eligible"] else r["failed_solve_ticks"],
            r["distance"] if r["eligible"] else -r["completed"],
            r["configuration"]
            if r["eligible"]
            else (r["paired_s"] if r["paired_s"] is not None else math.inf),
            0 if r["eligible"] else r["distance"],
            r["configuration"],
        )
    )
    return result


def fresh_inventory(exclude: Path | None = None) -> tuple:
    """Find used/reserved seeds recursively, including prior overnight preparation."""
    used, evidence = set(), {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "seed" in value and isinstance(value["seed"], int):
                used.add(value["seed"])
            for key, item in value.items():
                if key in ("seeds", "smoke_seeds") and isinstance(item, list):
                    used.update(x for x in item if isinstance(x, int))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for path in sorted((ROOT / "logs/mpcc-tuning").rglob("*.json")):
        if path.name not in ("report.json", "plan.json", "replay.json"):
            continue
        if exclude and path.is_relative_to(exclude):
            continue
        value = read(path)
        visit(value)
        evidence[str(path.relative_to(ROOT))] = sha(path)
    return used, evidence


def make_plan(config: dict, start: int = 10000) -> dict:
    """Reserve fresh cohorts, fixed grids, budgets and selection rules."""
    used, evidence = fresh_inventory()
    total = 2 + sum(SIZES)
    while used.intersection(range(start, start + total)):
        start += 1000
    cursor = start + 2
    stages = []
    for stage, size in zip(STAGES, SIZES):
        stages.append(dict(stage=stage, seeds=list(range(cursor, cursor + size))))
        cursor += size
    timeout_steps = gymnasium.spec(config.env.id).max_episode_steps
    assert timeout_steps == 1500 and config.env.freq == 50
    plan = dict(
        schema_version=1,
        created_at=common.now(),
        incumbent=case(),
        geometry=GEOMETRY,
        grids=GRIDS,
        scales=SCALES,
        bounds=BOUNDS,
        latency=LATENCY,
        failure_penalty_s=timeout_steps / config.env.freq,
        timeout_steps=timeout_steps,
        stages=stages,
        smoke_seeds=[start, start + 1],
        budget=dict(
            target_hours=9,
            maximum_hours=10,
            reporting_reserve_s=900,
            forecast_factor=1.35,
            minimum_episode_forecast_s=5.7,
        ),
        limits=dict(
            refinement_new=8,
            combinations_total=12,
            challenges_total=10,
            confirmation_total=3,
            validation_total=2,
        ),
        recommendation_policy=dict(
            minimum_relative_paired_speed_gain=0.01,
            require_paired_bootstrap_upper_below_zero=True,
            require_observed_completion_preserved=True,
            reliability_caveat="observed preservation does not establish noninferiority",
        ),
        stage_rules=dict(
            screening="all 23 isolated cases; 40 seeds; never truncate matrix",
            refinement="<=8 new midpoint/boundary values and <=5 matched references; 60 seeds",
            combinations=(
                "speed/progress core; paired isolated and combined additions; <=12 total; 80 seeds"
            ),
            challenges=(
                "leading parent plus alternate tracking/preview/smoothing values; "
                "<=10 total; 80 seeds; cap branch at >=1% saturation"
            ),
            confirmation=(
                "incumbent plus <=2 distinct finalists; 150 seeds; "
                "speed ranking and explicit fallback"
            ),
            validation=(
                "incumbent plus exactly one frozen challenger; 300-1500 seeds "
                "chosen from reserved prefix using remaining time BEFORE outcomes"
            ),
        ),
        objective="speed among matched completion/numerical/latency eligible candidates",
        selection="paired mean, completion descending, normalized L1 distance, name",
        fallback=(
            "latency eligible, numerical ticks ascending, "
            "completion descending, paired mean, distance, name"
        ),
        timing="completed steps / 50 Hz; callback stops completion; 20 ms episode resolution",
        latency_definition=(
            "parent compute_control plus read-only diagnostics, "
            "including replanning; excludes initialization, "
            "environment step and callbacks; not full-loop "
            "deadline certification"
        ),
        saturation_definition=(
            "successful current first optimized input >=98% "
            "progress cap; any attitude command >=98% bound; not "
            "physical speed"
        ),
        prior_report_sha256=evidence,
        prior_used_seed_count=len(used),
        all_reserved_seed_count=total,
    )
    assert plan["failure_penalty_s"] == PENALTY
    return plan


def fingerprint(config: dict, plan: dict) -> dict:
    """Bind the plan to source, runtime and full incumbent configuration."""
    f = common.fingerprint(config, {s["stage"]: s["seeds"] for s in plan["stages"]})
    f["cases"] = {"incumbent": candidate_config(config, BASE, plan["smoke_seeds"][0]).to_dict()}
    for path in (Path(__file__), ROOT / "scripts/overnight_mpcc_analysis.py"):
        f["source_sha256"][str(path.resolve().relative_to(ROOT))] = sha(path)
    f["plan_sha256"] = digest(plan)
    return f


def export(directory: Path, report: dict) -> None:
    """Write episode/config/summary CSVs; nested fields are canonical JSON cells."""
    for filename, rows in (
        (
            "episodes.csv",
            [
                dict(configuration=e["configuration"], **x)
                for e in report["evaluations"]
                for x in e["episodes"]
            ],
        ),
        (
            "summary.csv",
            [
                dict(configuration=e["configuration"], **e["summary"])
                for e in report["evaluations"]
                if e["status"] == "completed"
            ],
        ),
        (
            "settings.csv",
            [
                dict(configuration=e["configuration"], **e["settings"])
                for e in report["evaluations"]
            ],
        ),
    ):
        if not rows:
            continue
        with (directory / (filename + ".tmp")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(
                {
                    k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                    for k, v in row.items()
                }
                for row in rows
            )
        (directory / (filename + ".tmp")).replace(directory / filename)


def validate_report(report: dict, complete: bool = False) -> None:
    """Validate saved episode prefixes and settings for safe resume."""
    seeds = report["seeds"]
    assert len(seeds) == len(set(seeds))
    assert report["decision_sha256"] == digest(report["decision"])
    assert report["decision"]["cases"] == {
        e["configuration"]: e["settings"] for e in report["evaluations"]
    }
    for e in report["evaluations"]:
        assert e["configuration"] == name(e["settings"])
        assert e["config"]["controller"]["mpcc_experiment"] == GEOMETRY
        assert e["config"]["controller"]["mpcc"] == case(e["settings"])
        assert [x["seed"] for x in e["episodes"]] == seeds[: len(e["episodes"])]
        for x in e["episodes"]:
            assert x["outcome"] in ("success", "terminated", "timeout")
            assert (x["gates_passed"] == 5) == (x["outcome"] == "success")
            assert x["elapsed_s"] == x["steps"] / 50 and 0 < x["steps"] <= 1500
            assert 0 <= x["failed_solve_ticks"] <= x["steps"]
            assert x["effective_settings"] == dict(mpcc=e["settings"], mpcc_experiment=GEOMETRY)
        if e["status"] == "completed":
            assert len(e["episodes"]) == len(seeds)
            assert e["summary"] == summary(e["episodes"])
        if complete:
            assert e["status"] == "completed"
    if complete:
        assert report["status"] == "completed"


def worker(request_path: str, result_fd: int) -> None:
    """Run exactly one configuration in a fresh process; acknowledge each checkpoint."""
    request = read(Path(request_path))
    config = ConfigDict(request["config"])
    env = None
    with os.fdopen(result_fd, "w", buffering=1) as result:
        try:
            for seed in request["seeds"]:
                if time.time() >= request["deadline"]:
                    break
                if env is None:
                    env = create_environment(config)
                    assert int(env.unwrapped.settings.max_episode_steps) == 1500
                print(f"{common.now()} seed={seed}", flush=True)
                episode = measured_episode(env, config, seed)
                result.write(json.dumps({"episode": episode}, allow_nan=False) + "\n")
                # Do not start another episode until the parent commits this one.
                if not sys.stdin.readline():
                    break
        except BaseException as error:
            traceback.print_exc()
            result.write(json.dumps({"error": f"{type(error).__name__}: {error}"}) + "\n")
            raise
        finally:
            if env is not None:
                env.close()


def configuration_episodes(
    config: dict, seeds: list[int], deadline: float, log: object, episode_fn: Callable | None = None
) -> Iterator[dict]:
    """Isolate acados shared-library loads per configuration, while running serially."""
    if episode_fn is not None:
        # Focused tests inject measured outcomes without creating solver workers.
        env = None
        try:
            for seed in seeds:
                if time.time() >= deadline:
                    break
                with simulation_output(log):
                    if env is None:
                        env = create_environment(config)
                        assert int(env.unwrapped.settings.max_episode_steps) == 1500
                    yield episode_fn(env, config, seed)
        finally:
            if env is not None:
                with simulation_output(log):
                    env.close()
        return
    with tempfile.TemporaryDirectory(prefix="mpcc-worker-") as temporary:
        request_path = Path(temporary) / "request.json"
        write_report(
            request_path,
            dict(
                config=config.to_dict(),
                seeds=seeds,
                deadline=deadline if math.isfinite(deadline) else 1e100,
            ),
        )
        read_fd, write_fd = os.pipe()
        command = [
            sys.executable,
            "-c",
            (
                "import sys; from scripts.overnight_mpcc import worker; "
                "worker(sys.argv[1],int(sys.argv[2]))"
            ),
            str(request_path),
            str(write_fd),
        ]
        process = None
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=log,
                pass_fds=(write_fd,),
            )
        finally:
            os.close(write_fd)
            if process is None:
                os.close(read_fd)
        try:
            with os.fdopen(read_fd) as stream:
                for line in stream:
                    message = json.loads(line)
                    if "error" in message:
                        raise RuntimeError(
                            "Solver worker infrastructure error: " + message["error"]
                        )
                    yield message["episode"]
                    process.stdin.write(b"\n")
                    process.stdin.flush()
            code = process.wait()
            if code:
                raise RuntimeError(f"Solver worker exited with code {code}; inspect simulation.log")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdin.close()


def evaluate(
    config: dict,
    directory: Path,
    seeds: list[int],
    decision: dict,
    deadline: float = math.inf,
    episode_fn: Callable | None = None,
) -> dict:
    """Run one immutable decision; deadline/interruption never fabricates an episode."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "report.json"
    cases = decision["cases"]
    print(f"Report: {path.resolve()}", flush=True)
    if path.exists():
        report = read(path)
        if report["decision"] != decision or report["seeds"] != seeds:
            raise ValueError("Resume decision/seeds mismatch")
        for e in report["evaluations"]:
            if e["config"] != candidate_config(config, e["settings"], seeds[0]).to_dict():
                raise ValueError("Resume effective config mismatch")
        validate_report(report)
        if report["status"] == "completed":
            return report
    else:
        report = dict(
            status="running",
            started_at=common.now(),
            seeds=seeds,
            decision=decision,
            decision_sha256=digest(decision),
            infrastructure_errors=[],
            evaluations=[
                dict(
                    configuration=k,
                    settings=v,
                    status="pending",
                    episodes=[],
                    config=candidate_config(config, v, seeds[0]).to_dict(),
                )
                for k, v in cases.items()
            ],
        )
        write_report(path, report)
    current = None
    seed = None
    with (directory / "simulation.log").open("a", buffering=1) as log:
        try:
            for current in report["evaluations"]:
                if current["status"] == "completed":
                    continue
                candidate = candidate_config(config, current["settings"], seeds[0])
                remaining_seeds = seeds[len(current["episodes"]) :]
                configuration_started = time.perf_counter()
                for x in configuration_episodes(
                    candidate, remaining_seeds, deadline, log, episode_fn
                ):
                    seed = x["seed"]
                    assert x["effective_settings"] == dict(
                        mpcc=current["settings"], mpcc_experiment=GEOMETRY
                    )
                    current["episodes"].append(x)
                    report["status"] = "running"
                    write_report(path, report)
                current["configuration_wall_s"] = (
                    current.get("configuration_wall_s", 0)
                    + time.perf_counter()
                    - configuration_started
                )
                if len(current["episodes"]) != len(seeds):
                    report["status"] = "budget_exhausted"
                    return report
                current["summary"] = summary(current["episodes"])
                current["status"] = "completed"
                write_report(path, report)
                export(directory, report)
                s = current["summary"]
                average = s["average_success_time_s"]
                text = f"{average:.4f}s" if average is not None else "n/a"
                paired = ""
                if (
                    current["configuration"] != "incumbent"
                    and report["evaluations"][0]["status"] == "completed"
                ):
                    c = compare(report["evaluations"][0], current)
                    d = c["mean_paired_time_difference_s"]
                    paired = (
                        f"; paired Δ {1000 * d:+.3f}ms" if d is not None else "; no shared finishes"
                    )
                print(
                    f"{directory.name}/{current['configuration']}: {s['completed']}/{s['runs']} "
                    f"({s['completion_rate']:.1%}); successful mean {text}{paired}",
                    flush=True,
                )
            report["status"] = "completed"
            report["completed_at"] = common.now()
        except BaseException as error:
            report["status"] = (
                "interrupted" if isinstance(error, KeyboardInterrupt) else "infrastructure_error"
            )
            report["infrastructure_errors"].append(
                dict(
                    at=common.now(),
                    seed=seed,
                    configuration=current["configuration"] if current else None,
                    error=f"{type(error).__name__}: {error}",
                    traceback=traceback.format_exc(),
                )
            )
            raise
        finally:
            report["updated_at"] = common.now()
            write_report(path, report)
            export(directory, report)
    validate_report(report, complete=True)
    return report


def decision(cases: list[dict], reason: str, parents: dict | None = None) -> dict:
    """Freeze a deduplicated candidate matrix with its parent reports."""
    return dict(cases=unique(cases), reason=reason, parents=parents or {}, frozen_at=common.now())


def stage_proposal(stage: str, completed: dict) -> tuple:
    """Deterministic bounded proposals using only earlier completed cohorts."""
    screen = completed["screening"] if completed else None
    if stage == "screening":
        return list(screening_cases().values()), "23 isolated settings including incumbent"
    rows = rankings(screen)
    eligible = [r for r in rows if r["eligible"]]
    if stage == "refinement":
        proposals = []
        references = [BASE]
        # Noise guard: rank intervals, retain neighbors instead of eliminating them.
        for row in eligible + [r for r in rows if not r["eligible"]]:
            changed = [k for k in GRIDS if row["settings"][k] != BASE[k]]
            if len(changed) != 1:
                continue
            key = changed[0]
            v = row["settings"][key]
            grid = sorted(GRIDS[key])
            i = grid.index(v)
            neighbors = grid[max(0, i - 1) : i] + grid[i + 1 : i + 2]
            proposals.extend(
                dict(
                    BASE,
                    **{
                        key: round((v + n) / 2) if key == "horizon_steps" else round((v + n) / 2, 8)
                    },
                )
                for n in neighbors
            )
            if i in (0, len(grid) - 1) and row["eligible"] and row["paired_s"] < 0:
                neighbor = grid[1] if i == 0 else grid[-2]
                extended = v + (v - neighbor) / 2
                if BOUNDS[key][0] <= extended <= BOUNDS[key][1]:
                    proposals.append(
                        dict(
                            BASE,
                            **{
                                key: int(round(extended))
                                if key == "horizon_steps"
                                else round(extended, 8)
                            },
                        )
                    )
            references.append(row["settings"])
            if len(unique(proposals)) >= 8:
                break
        # No already-tested value counts as a new refinement.
        new = [v for k, v in unique(proposals).items() if k not in screening_cases()][:8]
        return list(
            unique(references[:5] + new).values()
        ), "midpoints and eligible modest boundary extensions; <=8 new and <=5 references"
    all_reports = [completed[k] for k in STAGES if k in completed]
    # Cross-cohort scores guide proposals only, never serve as matched evidence.
    pool = {}
    for report in all_reports:
        for row in rankings(report):
            pool[name(row["settings"])] = row
    ordered = sorted(
        pool.values(),
        key=lambda r: (
            not r["eligible"],
            r["paired_s"] if r["paired_s"] is not None else math.inf,
            -r["completed"],
            r["distance"],
            r["configuration"],
        ),
    )

    def best_for(key: str) -> float:
        choices = [
            r
            for r in ordered
            if r["settings"][key] != BASE[key]
            and all(r["settings"][k] == BASE[k] for k in BASE if k != key)
        ]
        return choices[0]["settings"][key] if choices else BASE[key]

    if stage == "combinations":
        speed = best_for("reference_speed")
        weight = best_for("progress_weight")
        core = dict(BASE, reference_speed=speed, progress_weight=weight)
        values = [BASE, dict(BASE, reference_speed=speed), dict(BASE, progress_weight=weight), core]
        for key in (
            "attitude_slew_weight",
            "thrust_slew_weight",
            "horizon_steps",
            "max_angle",
            "contour_weight",
            "lag_weight",
            "attitude_rate_weight",
            "terminal_weight",
        ):
            values.extend([dict(BASE, **{key: best_for(key)}), dict(core, **{key: best_for(key)})])
            if len(unique(values)) >= 12:
                break
        return list(unique(values).values())[
            :12
        ], "speed × progress core with constituent references and single interacting additions"
    latest = all_reports[-1]
    leading = rankings(latest)[0]["settings"] if rankings(latest) else case()
    if stage == "challenges":
        values = [BASE, leading]
        # Prefer rescuing tracking/preview then revisit inferior alternatives in speed regime.
        for key in (
            "horizon_steps",
            "contour_weight",
            "lag_weight",
            "attitude_slew_weight",
            "thrust_slew_weight",
            "max_angle",
            "attitude_rate_weight",
            "terminal_weight",
        ):
            grid = GRIDS[key]
            alternatives = [v for v in grid if v != leading[key]]
            alternate = (
                max(alternatives)
                if key
                in ("horizon_steps", "contour_weight", "attitude_slew_weight", "thrust_slew_weight")
                else min(alternatives)
            )
            values.append(dict(leading, **{key: alternate}))
        # Binding = >=1% of valid ticks in the leading combination on the prior cohort.
        e = next((e for e in latest["evaluations"] if e["settings"] == leading), None)
        if e and e["summary"]["progress_cap_fraction"] >= 0.01:
            values = values[:8] + [dict(leading, max_speed=2.0), dict(leading, max_speed=2.2)]
            reason = (
                "rejected grid alternatives at leading speed; "
                "measured progress saturation >=1%, cap branch "
                "enabled"
            )
        else:
            reason = (
                "rejected grid alternatives at leading speed; cap "
                "branch skipped (saturation <1% or unavailable)"
            )
        return list(unique(values).values())[:10], reason
    if stage == "confirmation":
        return list(
            unique([BASE] + [r["settings"] for r in ordered[:2]]).values()
        ), "incumbent and at most two distinct finalists; confirmation selects holdout challenger"
    if stage == "validation":
        chosen = rankings(completed["confirmation"])[0]
        return [
            BASE,
            chosen["settings"],
        ], "one frozen confirmation winner; deterministic fallback if no eligible candidate"
    raise ValueError(stage)


def episode_forecast(state: dict, settings: dict) -> float:
    """Conservative measured wall time including construction/generation; horizon aware."""
    n = settings["horizon_steps"]
    observed = []
    for report in state.get("reports", []):
        for e in report["evaluations"]:
            observed.extend(x["wall_s"] * n / e["settings"]["horizon_steps"] for x in e["episodes"])
    smoke = state.get("calibration", {})
    observed.extend(v * n / int(k) for k, v in smoke.items())
    measured = float(np.percentile(observed, 80)) if observed else 5.7 * n / 40
    return max(5.7 * n / 40, measured) * 1.35


def fit_budget(
    cases: list[dict],
    seeds: list[int],
    state: dict,
    now: float | None = None,
    optional: bool = True,
) -> tuple:
    """Keep incumbent/references first; shrink optional case count, never holdout seeds."""
    now = time.time() if now is None else now
    incumbent_cost = episode_forecast(state, BASE)
    # Future unknown challenger is conservatively forecast at the largest allowed horizon.
    validation_reserve = 300 * (
        incumbent_cost + episode_forecast(state, dict(BASE, horizon_steps=70))
    )
    confirmation_reserve = 150 * (
        incumbent_cost + episode_forecast(state, dict(BASE, horizon_steps=70))
    )
    reserve = state["budget"]["reporting_reserve_s"]
    stage = state.get("current_stage")
    if stage != "validation":
        reserve += validation_reserve
    if stage not in ("confirmation", "validation"):
        reserve += confirmation_reserve
    end = state["target_deadline_epoch"] if optional else state["hard_deadline_epoch"]
    available = end - now - reserve
    selected = []
    cost = 0
    for value in cases:
        next_cost = len(seeds) * episode_forecast(state, value)
        if stage == "validation":
            next_cost *= 1.1 / 1.35
        if cost + next_cost > available:
            break
        selected.append(value)
        cost += next_cost
    # Atomic stage: a lone incumbent provides no comparison. Screening is never trimmed.
    if stage == "screening" and len(selected) != len(cases):
        selected = []
    if stage in ("confirmation", "validation") and len(selected) < 2:
        selected = []
    return selected if len(selected) >= 2 else [], dict(
        available_s=available,
        reserve_s=reserve,
        proposed_cases=len(cases),
        accepted_cases=len(selected) if len(selected) >= 2 else 0,
        forecast_s=cost,
        checked_epoch=now,
    )


def load_prepared(directory: Path) -> tuple:
    """Reject changed code, runtime, settings or plan before execution."""
    plan = read(directory / "plan.json")
    manifest = read(directory / "manifest.json")
    config = load_config((directory / "config.toml").resolve())
    if fingerprint(config, plan) != manifest:
        raise ValueError(
            (
                "Prepared source/runtime/config/plan fingerprint "
                "mismatch; explicit re-preparation required"
            )
        )
    return config, plan, manifest


def prepare(directory: Path) -> None:
    """Run only eight smoke episodes and one action-equivalence replay."""
    directory.mkdir(parents=True, exist_ok=False)
    config_path = ROOT / "config/level2.toml"
    config = load_config(config_path)
    (directory / "config.toml").write_text(config_path.read_text())
    plan = make_plan(config)
    write_report(directory / "plan.json", plan)
    write_report(directory / "manifest.json", fingerprint(config, plan))
    smoke_cases = [
        BASE,
        dict(BASE, horizon_steps=30),
        dict(BASE, horizon_steps=60),
        dict(BASE, reference_speed=1.5),
    ]
    report = evaluate(
        config,
        directory / "smoke",
        plan["smoke_seeds"],
        decision(smoke_cases, "preparation only: horizon and speed smoke"),
    )
    # Prove diagnostics do not change actions; one additional real replay episode.
    seed = plan["smoke_seeds"][0]
    candidate = candidate_config(config, BASE, seed)
    with (directory / "smoke/simulation.log").open("a") as log, simulation_output(log):
        env = create_environment(candidate)
        try:
            replay = run_episode(env, common.MeasuredMPCC, candidate, seed)
        finally:
            env.close()
    expected = report["evaluations"][0]["episodes"][0]
    for key in (
        "outcome",
        "gates_passed",
        "steps",
        "elapsed_s",
        "failed_solve_ticks",
        "command_sha256",
    ):
        assert replay[key] == expected[key], key
    write_report(
        directory / "replay.json",
        dict(
            status="passed",
            episode=replay,
            instrumented_episode_sha256=digest(expected),
            additional_real_episodes=1,
        ),
    )
    calibration = {}
    for e in report["evaluations"]:
        key = str(e["settings"]["horizon_steps"])
        calibration[key] = max(calibration.get(key, 0), max(x["wall_s"] for x in e["episodes"][1:]))
    write_report(
        directory / "calibration.json",
        dict(
            episode_wall_s_by_horizon=calibration,
            smoke_episodes=8,
            replay_episodes=1,
            baseline_historical_s=5.7,
            caution=(
                "two seeds per case; first case includes first "
                "environment/JIT overhead separately in report "
                "timestamps"
            ),
        ),
    )
    from scripts.overnight_mpcc_analysis import audit_stage

    audit_stage(directory / "smoke", fingerprint_manifest=read(directory / "manifest.json"))
    print(
        f"PREPARED ONLY: {directory.resolve()}; 8 smoke + 1 replay episodes; no screening launched",
        flush=True,
    )


def execute(prepared: Path, directory: Path, resume: bool = False) -> None:
    """Execute stages under a persistent deadline and frozen decisions."""
    config, plan, manifest = load_prepared(prepared)
    assert read(prepared / "preflight.json")["status"] == "passed"
    path = directory / "study.json"
    if resume:
        state = read(path)
        if state["manifest"] != manifest or state["prepared"] != str(prepared.resolve()):
            raise ValueError("Resume fingerprint/prepared path mismatch")
    else:
        directory.mkdir(parents=True, exist_ok=False)
        used, evidence = fresh_inventory(exclude=prepared)
        planned = {seed for s in plan["stages"] for seed in s["seeds"]}
        if used.intersection(planned):
            raise ValueError("Reserved study seeds used by another study since preparation")
        started = time.time()
        state = dict(
            status="running",
            prepared=str(prepared.resolve()),
            manifest=manifest,
            started_epoch=started,
            target_deadline_epoch=started + 9 * 3600,
            hard_deadline_epoch=started + 10 * 3600,
            budget=plan["budget"],
            calibration=read(prepared / "calibration.json")["episode_wall_s_by_horizon"],
            freshness=evidence,
            decisions={},
            skipped={},
            reports=[],
            current_stage=None,
        )
        write_report(path, state)
    print(f"Study: {path.resolve()}", flush=True)
    from scripts.overnight_mpcc_analysis import audit_stage, final_report

    completed = {}
    try:
        for stage_spec in plan["stages"]:
            stage = stage_spec["stage"]
            state["current_stage"] = stage
            if stage in state["skipped"]:
                continue
            if stage not in state["decisions"]:
                values, reason = stage_proposal(stage, completed)
                stage_seeds = stage_spec["seeds"]
                if stage == "validation" and len(stage_seeds) >= 300:
                    # Spend remaining target time on independent evidence, not more search.
                    seconds_per_pair = sum(episode_forecast(state, v) / 1.35 for v in values) * 1.1
                    remaining = (
                        state["target_deadline_epoch"]
                        - time.time()
                        - plan["budget"]["reporting_reserve_s"]
                    )
                    size = min(len(stage_seeds), max(300, int(remaining / seconds_per_pair)))
                    stage_seeds = stage_seeds[:size]
                selected, budget = fit_budget(
                    values,
                    stage_seeds,
                    state,
                    optional=stage not in ("screening", "confirmation", "validation"),
                )
                if not selected:
                    state["skipped"][stage] = dict(
                        reason="budget insufficient for atomic matched cohort", forecast=budget
                    )
                    write_report(path, state)
                    if stage in ("screening", "confirmation", "validation"):
                        state["status"] = "incomplete_budget"
                        break
                    continue
                parents = {key: sha(directory / key / "report.json") for key in completed}
                choice = decision(selected, reason, parents)
                choice["budget"] = budget
                choice["seeds"] = stage_seeds
                choice["selection_rows"] = (
                    rankings(completed["confirmation"]) if stage == "validation" else []
                )
                state["decisions"][stage] = choice
                write_report(path, state)  # Freeze before creating any stage report.
            choice = state["decisions"][stage]
            for key, expected in choice["parents"].items():
                assert sha(directory / key / "report.json") == expected, (
                    "Parent report changed after decision"
                )
            report = evaluate(
                config,
                directory / stage,
                choice["seeds"],
                choice,
                deadline=state["hard_deadline_epoch"] - plan["budget"]["reporting_reserve_s"],
            )
            if report["status"] != "completed":
                state["status"] = "incomplete_budget"
                break
            audit_stage(directory / stage, fingerprint_manifest=manifest)
            completed[stage] = report
            state["reports"] = list(completed.values())
            write_report(path, state)
        else:
            state["status"] = "completed" if "validation" in completed else "incomplete_budget"
    except BaseException as error:
        state["status"] = (
            "interrupted" if isinstance(error, KeyboardInterrupt) else "infrastructure_error"
        )
        state.setdefault("infrastructure_errors", []).append(
            dict(at=common.now(), error=str(error), traceback=traceback.format_exc())
        )
        raise
    finally:
        state["updated_at"] = common.now()
        state["elapsed_wall_s"] = time.time() - state["started_epoch"]
        write_report(path, state)
        final_report(directory, allow_incomplete=True)
    print(
        f"Finished {state['status']}: {(directory / 'recommendation.json').resolve()}", flush=True
    )


def main() -> None:
    """Prepare, run, resume or audit the serial study."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output-dir", type=Path)
    run = sub.add_parser("run")
    run.add_argument("--prepared", type=Path, required=True)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--resume", action="store_true")
    audit = sub.add_parser("audit")
    audit.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "audit":
        from scripts.overnight_mpcc_analysis import audit_study

        audit_study(args.output_dir.resolve())
        return
    prefix = "overnight-prep" if args.action == "prepare" else "overnight"
    directory = args.output_dir or ROOT / "logs/mpcc-tuning" / datetime.now(timezone.utc).strftime(
        prefix + "-%Y%m%dT%H%M%S%fZ"
    )
    if args.action == "run" and args.resume and args.output_dir is None:
        parser.error("--resume requires --output-dir")
    with (ROOT / "logs/mpcc-tuning/.combination.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "prepare":
            prepare(directory.resolve())
        else:
            execute(args.prepared.resolve(), directory.resolve(), args.resume)


if __name__ == "__main__":
    main()

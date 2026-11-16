"""Compare small MPCC path changes on identical explicit simulation seeds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import time
from copy import deepcopy
from pathlib import Path

import gymnasium
import numpy as np
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

from lsy_drone_racing.control.attitude_mpcc import AttitudeMPCC
from lsy_drone_racing.control.attitude_mpcc_experimental import ExperimentalMPCC
from lsy_drone_racing.utils import load_config


def create_environment(config: dict) -> gymnasium.Env:
    """Create the shared headless race environment used by parameter probes."""
    return JaxToNumpy(
        gymnasium.make(
            config.env.id,
            freq=config.env.freq,
            sim_config=config.sim,
            sensor_range=config.env.sensor_range,
            control_mode=config.env.control_mode,
            track=config.env.track,
            disturbances=config.env.get("disturbances"),
            randomizations=config.env.get("randomizations"),
            seed=config.env.seed,
        )
    )


def run_episode(env: gymnasium.Env, controller_cls: type, config: dict, seed: int) -> dict:
    """Use sim.py's callback order; report elapsed completed steps explicitly."""
    obs, info = env.reset(seed=seed)
    controller = controller_cls(obs, info, config)
    steps, failed_solves = 0, 0
    durations = []
    commands = hashlib.sha256()
    while True:
        started = time.perf_counter()
        action = controller.compute_control(obs, info)
        durations.append(time.perf_counter() - started)
        failed_solves += int(controller._prediction is None)
        commands.update(np.asarray(action, dtype=np.float64).tobytes())
        obs, reward, terminated, truncated, info = env.step(action)
        finished = controller.step_callback(action, obs, reward, terminated, truncated, info)
        steps += 1
        if terminated or truncated or finished:
            break
    controller.episode_callback()
    success = int(obs["n_gates_passed"]) == len(obs["gate_sequence"])
    controller.episode_reset()
    return dict(
        seed=seed,
        outcome="success" if success else "terminated" if terminated else "timeout",
        gates_passed=int(obs["n_gates_passed"]),
        steps=steps,
        elapsed_s=steps / config.env.freq,
        failed_solve_ticks=failed_solves,
        control_p50_ms=1000 * float(np.median(durations)),
        control_p95_ms=1000 * float(np.percentile(durations, 95)),
        command_sha256=commands.hexdigest(),
    )


def main():
    """Write one CSV row per variant and seed, plus the exact input configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/level2.toml"))
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 1337])
    parser.add_argument("--snap", type=float, nargs="+", default=[0.0])
    parser.add_argument("--lift", type=float, nargs="+", default=[0.0])
    parser.add_argument("--clearance", type=float, nargs="+", default=[0.26])
    parser.add_argument(
        "--observed-clearance",
        type=float,
        nargs="+",
        default=[None],
        help="Pole clearance override on replans for revealed poles only (meters)",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    # A new directory protects earlier results. Run serially: acados uses a
    # shared generated-code path relative to the working directory.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    config = load_config(args.config.resolve())
    config.sim.render = False
    config.env.seed = args.seeds[0]
    (args.output_dir / "config.toml").write_text(args.config.read_text())
    (args.output_dir / "sweep.json").write_text(
        json.dumps(
            dict(
                seeds=args.seeds,
                snap=args.snap,
                lift=args.lift,
                clearance=args.clearance,
                observed_clearance=args.observed_clearance,
            ),
            indent=2,
        )
    )
    env = create_environment(config)
    variants = [("archived", AttitudeMPCC, deepcopy(config), "", "", "", "")]
    for snap, lift, clearance, observed_clearance in itertools.product(
        args.snap, args.lift, args.clearance, args.observed_clearance
    ):
        candidate = deepcopy(config)
        candidate.controller.mpcc_experiment = dict(
            gate_center_snap=snap,
            over_gate_lift=lift,
            observed_obstacle_clearance=observed_clearance,
        )
        options = dict(candidate.controller.get("mpcc", {}))
        options["obstacle_clearance"] = clearance
        candidate.controller.mpcc = options
        variants.append(
            ("experimental", ExperimentalMPCC, candidate, snap, lift, clearance, observed_clearance)
        )
    try:
        with (args.output_dir / "episodes.csv").open("w", newline="") as stream:
            writer = None
            for name, cls, candidate, snap, lift, clearance, observed_clearance in variants:
                for seed in args.seeds:
                    row = dict(
                        variant=name,
                        snap=snap,
                        lift=lift,
                        clearance=clearance,
                        observed_clearance=observed_clearance,
                    )
                    row.update(run_episode(env, cls, candidate, seed))
                    if writer is None:
                        writer = csv.DictWriter(stream, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    stream.flush()
                    print(row, flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()

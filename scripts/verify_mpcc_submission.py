"""Local verification of the fixed MPCC submission in an isolated checkout.

Run with that checkout's activated environment. This driver does not import the
historical study runners, accept tuning overrides, or modify official scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

SUBMISSION_FILES = (
    "config/level2.toml",
    "lsy_drone_racing/control/attitude_mpcc_v1.py",
    "lsy_drone_racing/control/mpcc_v1_geometry.py",
    "lsy_drone_racing/control/mpcc_v1_solver.py",
)


def sha(path: Path) -> str:
    """Fingerprint an exact file, without modifying it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_tree(root: Path) -> dict:
    """Reject changed baseline files outside the submission allowlist."""

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args])

    base = git("rev-parse", "origin/main").decode().strip()
    if git("rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("Verification requires the uncommitted candidate directly on origin/main.")
    baseline = git("ls-tree", "-r", "--name-only", base).decode().splitlines()
    hashes = {}
    for rel in baseline:
        path = root / rel
        expected = git("show", f"{base}:{rel}")
        if rel not in SUBMISSION_FILES and (not path.is_file() or path.read_bytes() != expected):
            raise ValueError(f"Baseline file changed: {rel}")
        hashes[rel] = hashlib.sha256(expected).hexdigest()
    old = git("show", f"{base}:config/level2.toml").decode().splitlines()
    new = (root / "config/level2.toml").read_text().splitlines()
    if len(old) != len(new) or any(
        a != b for i, (a, b) in enumerate(zip(old, new)) if i not in {6, 47}
    ):
        raise ValueError("Unauthorized TOML line change")
    extras = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    if set(extras) - set(SUBMISSION_FILES):
        raise ValueError(f"Unexpected untracked files: {extras}")
    if (root / "lsy_drone_racing/envs/mjx_compat.py").exists():
        raise ValueError("Simulator compatibility patch is present")
    return dict(
        base=base,
        baseline_sha256=hashes,
        submission_sha256={p: sha(root / p) for p in SUBMISSION_FILES},
    )


def run_episode(
    env: object, controller_cls: type, config: object, seed: int, max_steps: int
) -> dict:
    """Use official callback order; record both official and study time conventions."""
    import numpy as np

    obs, info = env.reset(seed=seed)
    controller = controller_cls(obs, info, config)
    effective = dict(
        mpcc=dict(controller.settings),
        mpcc_experiment=dict(
            gate_center_snap=controller.gate_center_snap,
            over_gate_lift=controller.over_gate_lift,
            observed_obstacle_clearance=controller.observed_obstacle_clearance,
        ),
    )
    durations, statuses = [], []
    commands = hashlib.sha256()
    numerical_ticks = 0
    for step in range(max_steps):
        started = time.perf_counter()
        action = controller.compute_control(obs, info)
        durations.append(1000 * (time.perf_counter() - started))
        statuses.append(controller.last_solver_status)
        numerical_ticks += int(controller._prediction is None)
        commands.update(np.asarray(action, dtype=np.float64).tobytes())
        obs, reward, terminated, truncated, info = env.step(action)
        finished = controller.step_callback(action, obs, reward, terminated, truncated, info)
        if terminated or truncated or finished:
            break
    else:
        raise RuntimeError(f"Smoke bound reached: seed={seed}, max_steps={max_steps}")
    controller.episode_callback()
    success = int(obs["n_gates_passed"]) == len(obs["gate_sequence"])
    controller.episode_reset()
    return dict(
        seed=seed,
        outcome="success" if success else "terminated" if terminated else "timeout",
        steps=step + 1,
        gates_passed=int(obs["n_gates_passed"]),
        official_time_s=step / config.env.freq,
        completed_step_time_s=(step + 1) / config.env.freq,
        effective_settings=effective,
        failed_solve_ticks=numerical_ticks,
        solver_statuses=statuses,
        command_sha256=commands.hexdigest(),
        control_p99_ms=float(np.percentile(durations, 99)),
        control_max_ms=max(durations),
        control_overruns=sum(t > 20 for t in durations),
    )


def main() -> None:
    """Freeze each request before loading package code; preserve failure evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--max-steps", type=int, default=1600)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.max_steps < 1 or len(set(args.seeds)) != len(args.seeds):
        parser.error("Use positive bounds and unique ordered seeds")
    root, out = args.checkout.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    request = dict(
        checkout=str(root),
        seeds=args.seeds,
        max_steps=args.max_steps,
        smoke=args.smoke,
        driver_sha256=sha(Path(__file__)),
        python=sys.executable,
        platform=platform.platform(),
        packages={
            n: importlib.metadata.version(n)
            for n in (
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
    )
    (out / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    result = dict(status="started", episodes=[])
    env = None
    try:
        result["tree"] = verify_tree(root)
        os.chdir(root)
        sys.path.insert(0, str(root))
        import lsy_drone_racing.envs.race_core as core
        from lsy_drone_racing.control import attitude_mpcc_v1 as entry
        from lsy_drone_racing.control import mpcc_v1_geometry, mpcc_v1_solver
        from lsy_drone_racing.utils import load_config, load_controller

        modules = (entry, mpcc_v1_geometry, mpcc_v1_solver, core)
        for module in modules:
            if not Path(module.__file__).resolve().is_relative_to(root):
                raise ValueError(f"Import escaped checkout: {module.__file__}")
        forbidden = ("mjx_compat", "attitude_mpcc_experimental", ".corridor", ".track_geometry")
        if any(any(part in name for part in forbidden) for name in sys.modules):
            raise ValueError("Experimental or patch module imported")
        result["module_origins"] = {m.__name__: m.__file__ for m in modules}
        config = load_config(root / "config/level2.toml")
        if config.controller.file != "attitude_mpcc_v1.py" or config.env.control_mode != "attitude":
            raise ValueError("Unexpected controller selection/control mode")
        controller_cls = load_controller(root / "lsy_drone_racing/control" / config.controller.file)
        result["controller"] = controller_cls.__name__
        result["embedded_settings"] = dict(
            mpcc=entry.TUNED_SETTINGS, mpcc_experiment=entry.GEOMETRY_SETTINGS
        )
        if args.smoke:
            import gymnasium
            from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

            config.sim.render = False
            config.env.seed = args.seeds[0]
            env = JaxToNumpy(
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
            for seed in args.seeds:
                episode = run_episode(env, controller_cls, config, seed, args.max_steps)
                if episode["effective_settings"] != result["embedded_settings"]:
                    raise ValueError("Effective settings differ from embedded settings")
                result["episodes"].append(episode)
                (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
        result["status"] = "passed"
    except Exception:
        result["status"] = "blocked"
        result["traceback"] = traceback.format_exc()
        (out / "failure.txt").write_text(result["traceback"])
        raise
    finally:
        if env is not None:
            env.close()
        (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

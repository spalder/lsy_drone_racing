"""Explicit v2 isolated worker and checkpoint driver for the bounded four-case screen.

CLI: python scripts/mpcc_v2_study.py --plan PLAN --output DIRECTORY
Each plan freezes checkout, source hashes, cases, seeds, deadline and environment.
No resume: an existing output directory is refused. Worker exceptions are infrastructure.
"""

# ruff: noqa: ANN001, ANN201, D103, E501
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    p = Path(p)
    temp = p.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(p)


def verify(plan):
    for path, expected in plan["hashes"].items():
        if sha(path) != expected:
            raise ValueError("Provenance mismatch: " + path)
    root = Path(plan["checkout"])
    baseline = json.loads(Path(plan["baseline_manifest"]).read_text())
    for rel, expected in baseline.items():
        if rel == "config/level2.toml":
            continue
        if sha(root / rel) != expected:
            raise ValueError("Official baseline changed: " + rel)
    original = Path(plan["official_config"]).read_text().splitlines()
    actual = (root / "config/level2.toml").read_text().splitlines()
    assert len(original) == len(actual)
    assert all(a == b for i, (a, b) in enumerate(zip(original, actual)) if i not in (6, 47))


def episode(env, cls, config, seed):
    import numpy as np

    obs, info = env.reset(seed=seed)
    controller = cls(obs, info, config)
    effective = dict(
        mpcc=dict(controller.settings),
        mpcc_experiment={
            k: getattr(controller, k)
            for k in ("gate_center_snap", "over_gate_lift", "observed_obstacle_clearance")
        },
    )
    durations, statuses, failures = [], [], []
    commands = hashlib.sha256()
    for step in range(1500):
        started = time.perf_counter_ns()
        action = controller.compute_control(obs, info)
        durations.append((time.perf_counter_ns() - started) / 1e6)
        assert np.all(np.isfinite(action))
        statuses.append(int(controller.last_solver_status))
        if controller._prediction is None:
            failures.append(step)
        commands.update(np.asarray(action, dtype=np.float64).tobytes())
        obs, reward, terminated, truncated, info = env.step(action)
        finished = controller.step_callback(action, obs, reward, terminated, truncated, info)
        if finished or terminated or truncated:
            break
    controller.episode_callback()
    success = int(obs["n_gates_passed"]) == 5
    controller.episode_reset()
    return dict(
        seed=seed,
        outcome="success" if success else "terminated" if terminated else "timeout",
        steps=step + 1,
        gates_passed=int(obs["n_gates_passed"]),
        official_time_s=step / 50,
        completed_step_time_s=(step + 1) / 50,
        penalized_time_s=(step + 1) / 50 if success else 30,
        effective_settings=effective,
        failed_solve_ticks=len(failures),
        failed_solve_indices=failures,
        solver_statuses=statuses,
        compute_durations_ms=durations,
        control_p99_ms=float(np.percentile(durations, 99)),
        control_max_ms=max(durations),
        control_overruns=sum(t > 20 for t in durations),
        command_sha256=commands.hexdigest(),
        controller_class=type(controller).__qualname__,
        controller_module=type(controller).__module__,
    )


def worker(request, fd):
    plan = json.loads(Path(request).read_text())
    stream = os.fdopen(fd, "w", buffering=1)
    env = None
    try:
        verify(plan)
        root = Path(plan["checkout"])
        os.chdir(root)
        sys.path.insert(0, str(root))
        import gymnasium
        from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

        from lsy_drone_racing.control import mpcc_v2_core
        from lsy_drone_racing.utils import load_config, load_controller

        config = load_config(root / "config/level2.toml")
        case = plan["case"]
        fixed = load_controller(root / "lsy_drone_racing/control" / case["file"])
        if case.get("research"):
            from mpcc_v2_research import controller_factory

            cls = controller_factory(case["settings"]["mpcc"], case["settings"]["mpcc_experiment"])
        else:
            cls = fixed
        assert issubclass(cls, mpcc_v2_core.MPCCV2Core) or cls.__name__ == "AttitudeMPCCV1"
        config.sim.render = False
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
                seed=plan["seeds"][0],
            )
        )
        assert config.env.freq == 50 and env.unwrapped.settings.max_episode_steps == 1500
        for seed in plan["seeds"]:
            if time.time() >= plan["deadline"]:
                break
            result = episode(env, cls, config, seed)
            assert result["effective_settings"] == case["settings"]
            origins = {
                name: str(Path(m.__file__).resolve())
                for name, m in list(sys.modules.items())
                if name.startswith("lsy_drone_racing") and getattr(m, "__file__", None)
            }
            assert all(Path(p).is_relative_to(root) for p in origins.values())
            assert not any(
                any(x in n for x in ("mjx_compat", "experimental", ".corridor", ".track_geometry"))
                for n in origins
            )
            result.update(environment_kind=plan["environment_kind"], module_origins=origins)
            stream.write(json.dumps({"episode": result}, allow_nan=False) + "\n")
            if not sys.stdin.readline():
                break
    except BaseException:
        stream.write(json.dumps({"error": traceback.format_exc()}) + "\n")
        raise
    finally:
        if env is not None:
            env.close()
        stream.close()


def run(plan_path, output):
    plan = json.loads(Path(plan_path).read_text())
    verify(plan)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out / "plan.json", plan)
    rows = []
    try:
        for name, case in plan["cases"].items():
            if time.time() + plan.get("minimum_remaining_s", 0) >= plan["deadline"]:
                raise TimeoutError("Insufficient frozen budget")
            request = dict(plan, case=case)
            write(out / f"{name}-request.json", request)
            read_fd, write_fd = os.pipe()
            with (out / f"{name}-console.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        str(out / f"{name}-request.json"),
                        "--fd",
                        str(write_fd),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=log,
                    pass_fds=(write_fd,),
                )
                os.close(write_fd)
                try:
                    with os.fdopen(read_fd) as stream:
                        for line in stream:
                            message = json.loads(line)
                            if "error" in message:
                                raise RuntimeError(message["error"])
                            row = message["episode"]
                            assert (
                                row["seed"] == plan["seeds"][sum(r["case"] == name for r in rows)]
                            )
                            row["case"] = name
                            rows.append(row)
                            write(out / "episodes.json", rows)
                            print(name, row["seed"], row["outcome"], row["steps"], flush=True)
                            process.stdin.write(b"\n")
                            process.stdin.flush()
                    if process.wait() != 0:
                        raise RuntimeError("Worker failed")
                finally:
                    process.stdin.close()
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
            assert sum(r["case"] == name for r in rows) == len(plan["seeds"])
        write(out / "status.json", {"status": "completed"})
    except BaseException:
        write(
            out / "status.json",
            {"status": "infrastructure_or_incomplete", "traceback": traceback.format_exc()},
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--fd", type=int)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.fd)
    else:
        run(args.plan, args.output)


if __name__ == "__main__":
    main()

"""Local v3 packaging verification with an optional fixed two-seed smoke test."""

# ruff: noqa: ANN001, ANN201
from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = (
    "lsy_drone_racing/control/attitude_mpcc_v3.py",
    "lsy_drone_racing/control/mpcc_v3_settings.py",
    "lsy_drone_racing/control/mpcc_v3_model.py",
    "lsy_drone_racing/control/mpcc_v3_geometry.py",
    "lsy_drone_racing/control/mpcc_v3_solver.py",
    "config/level2.toml",
)
SEEDS = [1603800, 1603801]
SELECTED_PLAN = (
    ROOT / "logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1/screen/plan.json"
)


def sha(path):
    """Hash one exact source or runtime file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    """Checkpoint JSON without allowing nonfinite records."""
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run_episode(env, cls, config, seed):
    """Measure actual v3 with public observations and the standard callback order."""
    import numpy as np

    obs, info = env.reset(seed=seed)
    controller = cls(obs, info, config)
    durations, statuses = [], []
    digest = hashlib.sha256()
    for step in range(1500):
        start = time.perf_counter()
        action = controller.compute_control(obs, info)
        durations.append((time.perf_counter() - start) * 1000)
        statuses.append(int(controller.last_solver_status))
        if not np.isfinite(action).all():
            raise RuntimeError("Nonfinite v3 command")
        if np.any(action < controller._ocp.constraints.lbu[:4] - 1e-5) or np.any(
            action > controller._ocp.constraints.ubu[:4] + 1e-5
        ):
            raise RuntimeError("Invalid v3 command")
        digest.update(np.asarray(action, dtype=np.float64).tobytes())
        obs, reward, terminated, truncated, info = env.step(action)
        finished = controller.step_callback(action, obs, reward, terminated, truncated, info)
        if finished or terminated or truncated:
            break
    controller.episode_callback()
    return dict(
        seed=seed,
        steps=step + 1,
        gates_passed=int(obs["n_gates_passed"]),
        success=int(obs["n_gates_passed"]) == len(obs["gate_sequence"]),
        official_time_s=step / 50,
        completed_step_time_s=(step + 1) / 50,
        numerical_ticks=sum(status != 0 for status in statuses),
        solver_statuses=statuses,
        latency_p99_ms=float(np.percentile(durations, 99)),
        latency_max_ms=max(durations),
        command_sha256=digest.hexdigest(),
        library=str(controller._solver.shared_lib._name),
        effective=dict(
            mpcc=controller.settings,
            prediction=controller.prediction_settings,
            numerics=controller.numerical_settings,
        ),
    )


def main():
    """Freeze sources, check discovery and settings, then run only requested smoke."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    request = dict(
        classification="local_packaging_smoke_not_independent_confirmation",
        root=str(ROOT),
        base=base,
        seeds=SEEDS,
        max_steps=1500,
        smoke=args.smoke,
        submission_allowlist=ALLOW,
        source_sha256={p: sha(ROOT / p) for p in ALLOW},
        driver_sha256=sha(__file__),
        selected_plan_sha256=sha(SELECTED_PLAN),
        runtime={
            k: os.environ.get(k)
            for k in (
                "ACADOS_SOURCE_DIR",
                "LD_LIBRARY_PATH",
                "SCIPY_ARRAY_API",
                "PYTHONDONTWRITEBYTECODE",
                "OMP_NUM_THREADS",
                "XLA_FLAGS",
            )
        },
        packages={
            p: importlib.metadata.version(p)
            for p in ("numpy", "scipy", "jax", "jaxlib", "mujoco", "crazyflow", "acados-template")
        },
    )
    write(out / "request.json", request)
    report = dict(status="started", episodes=[])
    env = None
    try:
        sys.path.insert(0, str(ROOT))
        from lsy_drone_racing.control import mpcc_v3_settings as settings
        from lsy_drone_racing.utils import load_config, load_controller

        selected = json.loads(SELECTED_PLAN.read_text())["cases"]["drag_030"]
        actual = dict(
            mpcc=settings.MPCC_SETTINGS,
            mpcc_experiment=settings.GEOMETRY_SETTINGS,
            prediction=settings.PREDICTION_SETTINGS,
            numerics=settings.NUMERICAL_SETTINGS,
        )
        assert actual == selected
        old_lines = subprocess.check_output(
            ["git", "show", base + ":config/level2.toml"], cwd=ROOT, text=True
        ).splitlines()
        new_lines = (ROOT / "config/level2.toml").read_text().splitlines()
        assert len(old_lines) == len(new_lines)
        assert all(a == b for i, (a, b) in enumerate(zip(old_lines, new_lines)) if i not in (6, 47))
        dependencies = {}
        for rel in ALLOW:
            if not rel.endswith(".py"):
                continue
            for node in ast.walk(ast.parse((ROOT / rel).read_text())):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                if node.module.startswith("lsy_drone_racing"):
                    dep = node.module.replace(".", "/") + ".py"
                    if not (ROOT / dep).exists():
                        dep = node.module.replace(".", "/") + "/__init__.py"
                    assert (ROOT / dep).exists()
                    assert (
                        dep in ALLOW
                        or subprocess.run(
                            ["git", "cat-file", "-e", base + ":" + dep], cwd=ROOT
                        ).returncode
                        == 0
                    )
                    dependencies[node.module] = dep
        report.update(effective_settings=actual, dependency_map=dependencies)
        config = load_config(ROOT / "config/level2.toml")
        assert config.controller.file == "attitude_mpcc_v3.py"
        cls = load_controller(ROOT / "lsy_drone_racing/control" / config.controller.file)
        assert cls.__name__ == "AttitudeMPCCV3"
        report["controller"] = dict(
            name=cls.__name__, module=cls.__module__, path=sys.modules[cls.__module__].__file__
        )
        protected = ["scripts/sim.py", "scripts/evaluate.py", "lsy_drone_racing/envs/race_core.py"]
        report["development_deviations_from_fork"] = [
            p
            for p in protected
            if subprocess.check_output(["git", "show", base + ":" + p], cwd=ROOT)
            != (ROOT / p).read_bytes()
        ]
        report["official_environment_validation"] = "deferred_until_submission_preparation"
        if args.smoke:
            import gymnasium
            from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

            config.sim.render = False
            with (ROOT / "logs/mpcc-tuning/.combination.lock").open() as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                os.chdir(out)
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
                        seed=SEEDS[0],
                    )
                )
                for seed in SEEDS:
                    report["episodes"].append(run_episode(env, cls, config, seed))
                    write(out / "report.json", report)
        report["status"] = "passed"
        report["module_origins"] = {
            name: mod.__file__
            for name, mod in list(sys.modules.items())
            if (name.startswith("lsy_drone_racing.control.mpcc_v3") or name == "controller")
            and getattr(mod, "__file__", None)
        }
        for rel, expected in request["source_sha256"].items():
            assert sha(ROOT / rel) == expected
    except BaseException:
        report.update(status="failed", traceback=traceback.format_exc())
        raise
    finally:
        if env is not None:
            env.close()
        write(out / "report.json", report)


if __name__ == "__main__":
    main()

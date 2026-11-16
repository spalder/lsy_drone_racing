"""Six fixed-seed diagnostic episodes for the unchanged v3 controller."""

# ruff: noqa: ANN001, ANN201
from __future__ import annotations

import fcntl
import gzip
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local/mpcc-study/v3-safe-robustness-continuation-v1"
SEEDS = list(range(1605203, 1605206))
MAX_STEPS = 1500


def write(path, value):
    """Checkpoint finite JSON."""
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    """Fingerprint a source or loaded library."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    """Freeze the unchanged controller, then diagnose six episodes under the lock."""
    sys.path.insert(0, str(ROOT))
    import gymnasium
    import numpy as np
    from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
    from scipy.spatial.transform import Rotation
    from scipy.stats import beta

    from lsy_drone_racing.control import mpcc_v3_safe_settings as mpcc_v3_settings
    from lsy_drone_racing.utils import load_config, load_controller

    OUT.mkdir(parents=True, exist_ok=False)
    sources = [
        ROOT / "lsy_drone_racing/control/attitude_mpcc_v3.py",
        *sorted((ROOT / "lsy_drone_racing/control").glob("mpcc_v3_*.py")),
    ]
    # Other agents' alternative controllers are outside this experiment.
    sources = [p for p in sources if "_alt_" not in p.name]
    sources.append(ROOT / "lsy_drone_racing/control/attitude_mpcc_v3_safe.py")
    sources += [
        ROOT / p
        for p in (
            ".local/mpcc-study/v3-safe-robustness-v1/safe-level2.toml",
            "scripts/evaluate.py",
            "scripts/sim.py",
            "lsy_drone_racing/envs/race_core.py",
            "lsy_drone_racing/envs/mjx_compat.py",
        )
    ]
    fingerprints = {str(p): sha(p) for p in sources}
    used, checked = set(), []
    for tree in (ROOT / "logs", ROOT / ".local/mpcc-study"):
        for path in tree.rglob("plan.json"):
            if OUT in path.parents:
                continue
            value = json.loads(path.read_text())
            if isinstance(value, dict):
                used.update(s for s in value.get("seeds", []) if type(s) is int)
            checked.append(str(path))
    assert (
        SEEDS
        == json.loads(
            (ROOT / ".local/mpcc-study/v3-evaluation-diagnosis-v1/plan.json").read_text()
        )["seeds"][3:]
    )
    config = load_config(ROOT / ".local/mpcc-study/v3-safe-robustness-v1/safe-level2.toml")
    assert config.controller.file == "attitude_mpcc_v3_safe.py"
    config.sim.render = False
    expected = dict(
        mpcc=mpcc_v3_settings.MPCC_SETTINGS,
        prediction=mpcc_v3_settings.PREDICTION_SETTINGS,
        numerics=mpcc_v3_settings.NUMERICAL_SETTINGS,
    )
    write(
        OUT / "plan.json",
        dict(
            classification="six_seed_diagnosis_not_tuning_or_reliability_confirmation",
            seeds=SEEDS,
            max_steps=MAX_STEPS,
            no_parameter_changes_during_check=True,
            paired_parent_plan=str(ROOT / ".local/mpcc-study/v3-evaluation-diagnosis-v1/plan.json"),
            source_sha256=fingerprints,
            driver_sha256=sha(__file__),
            effective_settings=expected,
            checked_seed_plans=checked,
            runtime={
                k: os.environ.get(k)
                for k in (
                    "ACADOS_SOURCE_DIR",
                    "LD_LIBRARY_PATH",
                    "SCIPY_ARRAY_API",
                    "OMP_NUM_THREADS",
                    "XLA_FLAGS",
                )
            },
            packages={
                p: importlib.metadata.version(p)
                for p in (
                    "numpy",
                    "scipy",
                    "jax",
                    "jaxlib",
                    "mujoco",
                    "crazyflow",
                    "acados-template",
                )
            },
            environment="Development environment; existing collision compatibility patch",
            constraint_tolerance=1e-5,
        ),
    )
    result = dict(status="started", episodes=[])
    env = None
    try:
        with (ROOT / "logs/mpcc-tuning/.combination.lock").open() as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            os.chdir(OUT)
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
            cls = load_controller(ROOT / "lsy_drone_racing/control" / config.controller.file)
            result["controller_origin"] = sys.modules[cls.__module__].__file__
            for seed in SEEDS:
                assert all(sha(p) == h for p, h in fingerprints.items())
                obs, info = env.reset(seed=seed)
                c = cls(obs, info, config)
                assert (
                    dict(
                        mpcc=c.settings,
                        prediction=c.prediction_settings,
                        numerics=c.numerical_settings,
                    )
                    == expected
                )
                assert all(
                    c._solver.constraints_get(i, "ubx")[-1] == c._length for i in range(1, 41)
                )
                library = str(c._solver.shared_lib._name)
                records, qp_events, rti_records = [], [], []
                original_solve = c._solver.solve
                current_tick = 0
                current_pass = 0

                def solve() -> int:
                    nonlocal current_pass
                    s = c._solver
                    current_pass += 1
                    pre = {key: np.asarray(s.get_flat(key)).copy() for key in ("x", "u", "p")}
                    x0 = pre["x"].reshape(41, 17)[0]
                    assert np.array_equal(s.constraints_get(0, "lbx"), x0)
                    assert np.array_equal(s.constraints_get(0, "ubx"), x0)
                    before = time.perf_counter()
                    status = original_solve()
                    solver_ms = (time.perf_counter() - before) * 1000
                    q = dict(
                        tick=current_tick,
                        rti_pass=current_pass,
                        status=int(status),
                        solver_call_ms=solver_ms,
                    )
                    if status != 0:
                        folder = OUT / "failed-QPs"
                        folder.mkdir(exist_ok=True)
                        qp = s.get_last_qp()
                        np.savez_compressed(
                            folder / f"seed-{seed}-tick-{current_tick}-pass-{current_pass}.npz",
                            **{"qp." + k: v for k, v in qp.items()},
                            **{"pre." + k: v for k, v in pre.items()},
                            status=np.array(status),
                            seed=np.array(seed),
                        )
                        qp_events.append([current_tick, current_pass, int(status)])
                    else:
                        x = np.asarray(s.get_flat("x")).reshape(41, 17)
                        u = np.asarray(s.get_flat("u")).reshape(40, 5)
                        sl = np.asarray(s.get_flat("sl")).reshape(-1, 3)
                        su = np.asarray(s.get_flat("su")).reshape(-1, 3)
                        finite = all(np.isfinite(a).all() for a in (x, u, sl, su))
                        hard = max(
                            0.0,
                            float(np.max(c._ocp.constraints.lbu - u)),
                            float(np.max(u - c._ocp.constraints.ubu)),
                            float(np.max(-x[1:, 12])),
                            float(np.max(x[1:, 12] - c._length)),
                            float(np.max(np.abs(x[0] - x0))),
                            float(np.max(np.abs(x[1:, 3:6]) - [0.975, 1.025, 0.975])),
                        )
                        soft = max(
                            0.0,
                            float(np.max(-0.875 - x[1:, 3:6] - sl)),
                            float(np.max(x[1:, 3:6] - 0.875 - su)),
                            float(-sl.min()),
                            float(-su.min()),
                        )
                        q.update(
                            finite=bool(finite),
                            hard_violation=hard,
                            soft_violation=soft,
                            max_slack=float(max(sl.max(), su.max())),
                            attitude_excess=np.maximum(np.abs(x[1:, 3:6]) - 0.875, 0)
                            .max(axis=0)
                            .tolist(),
                        )
                    rti_records.append(q)
                    return status

                c._solver.solve = solve
                initial = {k: np.asarray(v).tolist() for k, v in obs.items()}
                for current_tick in range(MAX_STEPS):
                    current_pass = 0
                    pre_obs = {k: np.asarray(v).copy() for k, v in obs.items()}
                    before = time.perf_counter()
                    action = c.compute_control(obs, info)
                    compute_ms = (time.perf_counter() - before) * 1000
                    progress = c._progress
                    point = c._path(progress)
                    tangent = c._path_derivative(progress)
                    error = pre_obs["pos"] - point
                    tangent = tangent / max(np.linalg.norm(tangent), 1e-12)
                    lag = float(error @ tangent)
                    gate_index = int(pre_obs["n_gates_passed"])
                    gate_id = int(pre_obs["gate_sequence"][min(gate_index, 4)])
                    gate = c.track_geometry.gates[gate_id]
                    local = (pre_obs["pos"] - gate.planning_pose.position) @ Rotation.from_quat(
                        gate.planning_pose.quaternion
                    ).as_matrix()
                    valid = bool(
                        np.isfinite(action).all()
                        and np.all(action >= c._ocp.constraints.lbu[:4] - 1e-5)
                        and np.all(action <= c._ocp.constraints.ubu[:4] + 1e-5)
                    )
                    records.append(
                        dict(
                            tick=current_tick,
                            crossing=gate_index + 1,
                            position=pre_obs["pos"].tolist(),
                            velocity=pre_obs["vel"].tolist(),
                            attitude=Rotation.from_quat(pre_obs["quat"]).as_euler("xyz").tolist(),
                            gate_local=local.tolist(),
                            gate_detected=gate.detected,
                            contour_error=float(np.sqrt(max(0.0, error @ error - lag**2))),
                            speed=float(np.linalg.norm(pre_obs["vel"])),
                            command=action.tolist(),
                            attitude_saturated=bool(np.any(np.abs(action[:3]) >= 0.875 * 0.99)),
                            solver_status=int(c.last_solver_status),
                            fallback=c._prediction is None,
                            valid_command=valid,
                            compute_ms=compute_ms,
                        )
                    )
                    obs, reward, terminated, truncated, info = env.step(action)
                    finished = c.step_callback(action, obs, reward, terminated, truncated, info)
                    if finished or terminated or truncated:
                        break
                c.episode_callback()
                success = int(obs["n_gates_passed"]) == len(obs["gate_sequence"])
                ok = [q for q in rti_records if q["status"] == 0]
                episode = dict(
                    seed=seed,
                    steps=current_tick + 1,
                    gates_passed=int(obs["n_gates_passed"]),
                    success=success,
                    terminated=bool(terminated),
                    truncated=bool(truncated),
                    failure_crossing=None if success else records[-1]["crossing"],
                    numerical_ticks=sum(r["solver_status"] != 0 for r in records),
                    fallback_ticks=sum(r["fallback"] for r in records),
                    invalid_commands=sum(not r["valid_command"] for r in records),
                    qp_events=qp_events,
                    constraint_events=[
                        q
                        for q in ok
                        if not q["finite"] or max(q["hard_violation"], q["soft_violation"]) > 1e-5
                    ],
                    max_slack=max(q["max_slack"] for q in ok),
                    max_contour_error=max(r["contour_error"] for r in records),
                    saturated_ticks=sum(r["attitude_saturated"] for r in records),
                    last_pre_action=records[-1],
                    latency_p99_ms=float(np.percentile([r["compute_ms"] for r in records], 99)),
                    latency_note="Compute includes diagnostic getters; solver_call_ms is separate",
                    official_time_s=current_tick / 50,
                    study_time_s=(current_tick + 1) / 50,
                    library=library,
                    library_sha256=sha(library),
                )
                with gzip.open(OUT / f"seed-{seed}-records.json.gz", "wt") as f:
                    json.dump(
                        dict(initial=initial, ticks=records, rti=rti_records), f, allow_nan=False
                    )
                result["episodes"].append(episode)
                write(OUT / "report.json", result)
                c.episode_reset()
            assert all(sha(p) == h for p, h in fingerprints.items())
        n = len(result["episodes"])
        k = sum(e["success"] for e in result["episodes"])
        result.update(
            status="completed",
            n=n,
            finishes=k,
            exact95=[
                float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0,
                float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0,
            ],
            failed_crossings=dict(
                Counter(str(e["failure_crossing"]) for e in result["episodes"] if not e["success"])
            ),
        )
    except BaseException:
        result.update(status="failed", traceback=traceback.format_exc())
        raise
    finally:
        if env is not None:
            env.close()
        write(OUT / "report.json", result)


if __name__ == "__main__":
    main()

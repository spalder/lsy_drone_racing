"""Race mpccpp at slow settings and record per-race characteristics.

Usage: python .mpcc_dev/slow_runs.py '<json overrides>' <seed_lo>:<seed_hi> or <s1,s2,...> <out.json> [workers] [timeout_s]
"""
import json
import os
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import tune_mpccpp as T  # noqa: E402

TIMEOUT = 40.0


def init_worker(controller_path):
    """Set up the tuner's worker; MPCC_CONTROLLER=<file> races another copy of the controller."""
    T._init_worker("level2.toml")
    if controller_path:
        from lsy_drone_racing.utils import load_controller
        T._CONTROLLER = load_controller(Path(controller_path))


def race(task):
    params, seed, traj_dir = task
    from scipy.spatial.transform import Rotation as R

    T._CONFIG.controller["mpccpp"] = params
    obs, info = T._ENV.reset(seed=seed)
    ctrl = T._CONTROLLER(obs, info, T._CONFIG)
    freq = T._CONFIG.env.freq
    max_steps = int(TIMEOUT * freq)
    pos, vel, tilt, gate_t, cmds = [], [], [], [], []
    steps, terminated, gates_prev = 0, False, 0
    while steps < max_steps:
        action = ctrl.compute_control(obs, info)
        obs, reward, terminated, truncated, info = T._ENV.step(action)
        ctrl.step_callback(action, obs, reward, terminated, truncated, info)
        steps += 1
        pos.append(obs["pos"].copy()); vel.append(obs["vel"].copy()); cmds.append(np.asarray(action))
        rpy = R.from_quat(obs["quat"]).as_euler("xyz")
        tilt.append(float(np.hypot(rpy[0], rpy[1])))
        g = int(obs["n_gates_passed"])
        if g > gates_prev:
            gate_t.append(steps / freq); gates_prev = g
        if terminated or truncated:
            break
    gates = int(obs["n_gates_passed"])
    finished = gates == len(obs["gate_sequence"])
    pos, vel = np.array(pos), np.array(vel)
    speed = np.linalg.norm(vel, axis=1)
    if finished:
        outcome = "finished"
    elif steps >= max_steps:
        outcome = "timeout"
    elif terminated:
        outcome = "crash"
    else:
        outcome = "truncated"
    np.savez(Path(traj_dir) / f"{seed}.npz", pos=pos, vel=vel, cmds=np.array(cmds),
             gates_pos=obs["gates_pos"], gates_quat=obs["gates_quat"], obstacles_pos=obs["obstacles_pos"], gate_t=np.array(gate_t))
    st = np.array(ctrl.solve_times) * 1e3
    return {
        "seed": seed, "outcome": outcome, "time": steps / freq, "gates": gates,
        "gate_times": gate_t, "end_pos": pos[-2 if len(pos) > 1 else -1].round(3).tolist(),
        "mean_speed": float(speed.mean()), "max_speed": float(speed.max()),
        "max_tilt_deg": float(np.degrees(max(tilt))),
        "min_z_after_1s": float(pos[freq:, 2].min()) if len(pos) > freq else None,
        "solver_failures": int(ctrl.solver_failures),
        "recoveries": int(getattr(ctrl, "hold_count", 0)),
        "solve_ms_p50": float(np.percentile(st, 50)), "solve_ms_p99": float(np.percentile(st, 99)),
        "solve_ms_max": float(st.max()),
    }


def main():
    params = json.loads(sys.argv[1])
    if ":" in sys.argv[2]:
        lo, hi = map(int, sys.argv[2].split(":"))
        seeds = list(range(lo, hi))
    else:  # Comma-separated list
        seeds = [int(x) for x in sys.argv[2].split(",")]
    out = Path(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    global TIMEOUT
    if len(sys.argv) > 5:
        TIMEOUT = float(sys.argv[5])
    traj_dir = out.with_suffix("")
    traj_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with mp.get_context("spawn").Pool(workers, initializer=init_worker, initargs=(os.environ.get("MPCC_CONTROLLER"),)) as pool:
        res = pool.map(race, [(params, s, str(traj_dir)) for s in seeds], chunksize=1)
    out.write_text(json.dumps({"params": params, "timeout": TIMEOUT, "races": res}, indent=1))
    for r in res:
        print(f"{r['seed']} {r['outcome']:9s} t={r['time']:6.2f} gates={r['gates']} "
              f"v_mean={r['mean_speed']:.2f} v_max={r['max_speed']:.2f} tilt={r['max_tilt_deg']:5.1f} "
              f"fail={r['solver_failures']} rec={r['recoveries']} p99={r['solve_ms_p99']:.1f}ms gate_t={[round(g,1) for g in r['gate_times']]} end={r['end_pos']}")
    fin = [r for r in res if r["outcome"] == "finished"]
    from collections import Counter
    print(f"\n{Counter(r['outcome'] for r in res)}  success {len(fin)}/{len(res)}"
          + (f"  mean {np.mean([r['time'] for r in fin]):.2f}s  sd {np.std([r['time'] for r in fin]):.2f}" if fin else "")
          + f"  wall {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

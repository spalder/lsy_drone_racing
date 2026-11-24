"""Replay one episode of the 2026-11-12 MPCC campaign (docs/control/mpcc_campaign_20261112_v1).

Uses the campaign's archived controller/env sources, the exact recorded settings of the
candidate, the recorded level-2 environment config and the episode seed. A fresh acados build
directory is used per run (the campaign verified this reproduces actions bit-exactly).

Opens a viewer and plays the episode at 0.25x real time by default.

usage (from the repository root):
    .pixi/envs/default/bin/python scripts/replay_mpcc_campaign_episode.py <candidate> <seed>
        [--stage A|B|C] [--speed 0.25] [--headless]
"""

import argparse
import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
D = R / "docs/control/mpcc_campaign_20261112_v1"
EVIDENCE = R / "docs/control/mpcc_assessment_20261112_v1/cohort_evidence.jsonl.gz"
CANDIDATES = {"F1_2": "config_2470aab06585d4ce", "G07_pole_width_0p4375": "config_3742dfc435fa9211"}
os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                  JAX_PLATFORMS="cpu", ACADOS_SOURCE_DIR=str(R / "acados"))
# The dynamic loader reads LD_LIBRARY_PATH only at startup, so restart with acados/lib on it.
if str(R / "acados/lib") not in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
    os.environ["LD_LIBRARY_PATH"] = ":".join(filter(None, [str(R / "acados/lib"), os.environ.get("LD_LIBRARY_PATH")]))
    os.execv(sys.executable, [sys.executable, *sys.argv])
sys.path.insert(0, str(D / "source"))

import gymnasium  # noqa: E402
import jax  # noqa: E402
import lsy_drone_racing  # noqa: E402, F401  (registers the archived envs)
import numpy as np  # noqa: E402
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy  # noqa: E402
from crazyflow.sim.visualize import draw_line, draw_points  # noqa: E402
from lsy_drone_racing.control.mpcc_broad_core import MPCCBroadCore  # noqa: E402
from ml_collections import ConfigDict  # noqa: E402


def recorded_identity(name):
    with gzip.open(EVIDENCE, "rt") as f:
        for line in f:
            rec = json.loads(line)
            if rec["configuration_id"] == CANDIDATES[name] and rec["case_name"] == name:
                return rec["identity"]
    raise KeyError(name)


def path_points(c):
    return c._path(np.linspace(0, c._length, 120))


def draw_planning(sim, c, old_path, trail):
    """Overlay planning state; reads the controller only, so the replay stays identical.

    green: current path, orange: path before the last replan, blue: MPC prediction (replanned
    every tick), red: progress reference, white: flown trail, yellow/magenta: gate/pole
    positions the planner currently uses.
    """
    if old_path is not None:
        draw_line(sim, old_path, rgba=(1, 0.5, 0, 0.8), start_size=2.0, end_size=2.0)
    c.render_callback(sim)
    if len(trail) > 1:
        draw_line(sim, np.asarray(trail[-200:]), rgba=(1, 1, 1, 0.8), start_size=2.0, end_size=2.0)
    geo = c.track_geometry
    draw_points(sim, np.array([g.planning_pose.position for g in geo.gates]), rgba=(1, 1, 0, 1), size=0.03)
    poles = np.array([o.planning_pose.position for o in geo.obstacles])
    draw_points(sim, poles, rgba=(1, 0, 1, 1), size=0.03)


def check_initial_state(env, stage, seed):
    ref = D / stage / "states" / f"{seed}.npz"
    if not ref.exists():
        return "no reference state"
    leaves = jax.tree_util.tree_leaves(env.unwrapped.data)
    ref = np.load(ref)
    worst = 0.0
    for i, x in enumerate(leaves):
        x = jax.random.key_data(x) if jax.dtypes.issubdtype(x.dtype, jax.dtypes.prng_key) else x
        x, y = np.asarray(x), ref[str(i)]
        if x.shape != y.shape or x.dtype != y.dtype:
            return f"MISMATCH (leaf {i} shape/dtype)"
        if not np.array_equal(x, y):
            x, y = x.astype(np.float64), y.astype(np.float64)
            worst = max(worst, float(np.max(np.abs(x - y) / np.maximum(np.abs(y), 1.0))))
    # Float32 last-bit differences (gate quaternions, inverse inertia) occur across machines.
    if worst == 0:
        return "matches campaign exactly"
    return f"matches campaign up to float32 rounding ({worst:.1e} rel)" if worst < 1e-6 else f"MISMATCH ({worst:.1e} rel)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("candidate", choices=sorted(CANDIDATES))
    p.add_argument("seed", type=int)
    p.add_argument("--stage", choices=["A", "B", "C"], help="verify initial state against this stage")
    p.add_argument("--speed", type=float, default=0.25, help="playback speed relative to real time")
    p.add_argument("--headless", action="store_true", help="no viewer, run as fast as possible")
    a = p.parse_args()

    ident = recorded_identity(a.candidate)
    settings = ident["settings"]
    cfg = ConfigDict(ident["environment"]["config"])
    render = not a.headless
    cfg.sim.render = render
    cfg.controller = ConfigDict({})
    env = JaxToNumpy(gymnasium.make(
        cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
        control_mode=cfg.env.control_mode, track=cfg.env.track, disturbances=cfg.env.disturbances,
        randomizations=cfg.env.randomizations, seed=a.seed))
    obs, info = env.reset(seed=a.seed)
    if a.stage:
        print("initial state:", check_initial_state(env, a.stage, a.seed))
    os.chdir(tempfile.mkdtemp(prefix=f"replay_{a.candidate}_{a.seed}_"))
    c = MPCCBroadCore(obs, info, cfg, settings=settings["mpcc"], geometry=settings["mpcc_experiment"])
    fallback = 0
    revision, old_path, trail = c._path_geometry_revision, None, []
    dt = 1 / (cfg.env.freq * a.speed)
    deadline = time.perf_counter()
    for tick in range(1500):
        action = c.compute_control(obs, info)
        fallback += c._prediction is None
        if c._path_geometry_revision != revision:
            if tick > 0:
                print(f"t={tick / cfg.env.freq:5.2f}s  path replanned (revision {c._path_geometry_revision}),"
                      f" gates seen {np.asarray(obs['gates_visited']).astype(int).tolist()},"
                      f" poles seen {np.asarray(obs['obstacles_visited']).astype(int).tolist()}")
                old_path = new_path
            revision = c._path_geometry_revision
        new_path = path_points(c) if render else None
        trail.append(np.asarray(obs["pos"], dtype=float).copy())
        obs, reward, terminated, truncated, info = env.step(action)
        if render:
            draw_planning(env.unwrapped.sim, c, old_path, trail)
            env.render()
            deadline += dt
            time.sleep(max(0.0, deadline - time.perf_counter()))
        if c.step_callback(action, obs, reward, terminated, truncated, info) or terminated or truncated:
            break
    c.episode_callback()
    gates = int(obs["n_gates_passed"])
    success = gates == len(obs["gate_sequence"])
    print(json.dumps(dict(candidate=a.candidate, seed=a.seed, success=success, steps=tick + 1,
                          race_time_s=(tick + 1) / 50, gates_passed=gates, terminated=bool(terminated),
                          truncated=bool(truncated), fallback_ticks=int(fallback),
                          final_pos=np.round(obs["pos"], 3).tolist())))
    if render:
        time.sleep(2.0)  # keep the final frame visible before the viewer closes
    env.close()


if __name__ == "__main__":
    main()

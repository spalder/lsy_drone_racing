"""Watch one level 2 race of mpccpp in the viewer, with the same env setup as slow_runs.py.

usage (from the repository root):
    .pixi/envs/default/bin/python .mpcc_dev/watch_mpccpp.py <seed> [--speed 0.5]
        [--settings '{"reference_speed":0.7,"max_speed":1.0,"unobserved_speed":0.7}'] [--headless] [--full-walls]

Overlays: green = centerline, red lines = tunnel walls over the MPC horizon (lateral free extent
of the drone center on each side, bright red low to whitish red high; --full-walls draws them
along the whole track), orange = MPC prediction, white = flown trail, balls = pole positions the
planner uses, by pole ID 0-3: deep blue, light blue, light yellow, deep yellow. Balls at
the gate centers = gate positions the planner uses, white while nominal, red once the gate is
detected. Every track rebuild (gate or pole revealed) is printed with its time.
Viewer keys: space = pause/resume, right arrow = one step.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ACADOS_SOURCE_DIR", str(ROOT / "acados"))
# The dynamic loader reads LD_LIBRARY_PATH only at startup, so restart with acados/lib on it.
if str(ROOT / "acados/lib") not in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
    os.environ["LD_LIBRARY_PATH"] = ":".join(
        filter(None, [str(ROOT / "acados/lib"), os.environ.get("LD_LIBRARY_PATH")])
    )
    os.execv(sys.executable, [sys.executable, *sys.argv])

import gymnasium  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from crazyflow.sim.visualize import (  # noqa: E402
    _rotation_matrix_from_points,
    draw_line,
    draw_points,
)
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy  # noqa: E402

from lsy_drone_racing.control.mpccpp import THETA  # noqa: E402
from lsy_drone_racing.utils import load_config, load_controller  # noqa: E402

SLOW = '{"reference_speed":0.7,"max_speed":1.0,"unobserved_speed":0.7}'
# Pole markers by pole ID 0-3: deep blue, light blue, light yellow, deep yellow
POLE_RGBA = [(0.0, 0.1, 0.6, 1.0), (0.45, 0.75, 1.0, 1.0), (1.0, 0.95, 0.55, 1.0), (0.9, 0.65, 0.0, 1.0)]
GATE_NOMINAL_RGBA, GATE_SEEN_RGBA = (1.0, 1.0, 1.0, 1.0), (1.0, 0.0, 0.0, 1.0)
WALL_WIDTH = 4.0  # Line width of the tunnel walls, draw_line default is 3
# Tunnel walls are colored by altitude: deep red at WALL_Z_RANGE[0] and below, very light red at
# WALL_Z_RANGE[1] and above (short gates are at 0.7 m, tall gates at 1.2 m)
WALL_Z_RANGE = (0.5, 1.3)
WALL_LOW_RGB, WALL_HIGH_RGB = np.array([0.5, 0.0, 0.0]), np.array([0.55, 0.42, 0.42])  # Lit, renders ~2x brighter


def draw_altitude_line(sim, points, width: float):
    """Draw a line whose segments are colored by the altitude of their midpoints."""
    if sim.viewer is None:
        return
    start, end = points[:-1], points[1:]
    fraction = np.clip(
        (0.5 * (start[:, 2] + end[:, 2]) - WALL_Z_RANGE[0]) / (WALL_Z_RANGE[1] - WALL_Z_RANGE[0]),
        0.0,
        1.0,
    )
    rgb = WALL_LOW_RGB + fraction[:, None] * (WALL_HIGH_RGB - WALL_LOW_RGB)
    mats = _rotation_matrix_from_points(start, end).as_matrix().reshape(-1, 9)
    lengths = np.linalg.norm(end - start, axis=-1)
    for i in range(len(start)):
        sim.viewer.viewer.add_marker(
            type=mujoco.mjtGeom.mjGEOM_LINE,
            size=np.array([width, width, lengths[i]]),
            pos=start[i],
            mat=mats[i],
            rgba=np.append(rgb[i], 1.0),
        )


def draw_overlays(sim, c, full_walls: bool = False):
    """Draw the centerline, the tunnel walls and the MPC prediction.

    The walls are drawn only over the horizon (from just behind the drone to the end of the
    prediction) unless full_walls is set. Over the whole track they overlap where the track passes
    a gate twice and where they fold on the inside of tight turns.
    """
    t = c._track
    idx = np.arange(0, len(t.s), 5)
    draw_line(sim, t.pos[idx], rgba=(0.0, 1.0, 0.0, 1.0))
    if not full_walls:
        end = c._theta + 1.0 if c._x is None else c._x[:, THETA].max()
        idx = idx[(t.s[idx] >= c._theta - 0.1) & (t.s[idx] <= end + 0.2)]
    if len(idx) > 1:
        for side, sign in ((0, -1), (1, 1)):
            wall = t.pos[idx] + sign * t.extents[idx, side : side + 1] * t.normal[idx]
            draw_altitude_line(sim, wall, WALL_WIDTH)
    if c._x is not None:
        draw_line(sim, c._x[:, :3], rgba=(1.0, 0.35, 0.0, 1.0))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("seed", type=int)
    p.add_argument("--speed", type=float, default=0.5, help="playback speed relative to real time")
    p.add_argument("--settings", default=SLOW, help="JSON overrides of MPCCPlusPlus.SETTINGS")
    p.add_argument("--timeout", type=float, default=40.0, help="simulated seconds")
    p.add_argument("--headless", action="store_true", help="no viewer, run as fast as possible")
    p.add_argument(
        "--full-walls", action="store_true", help="draw the tunnel walls along the whole track"
    )
    a = p.parse_args()

    os.chdir(ROOT)  # the solver build cache lives in c_generated_code/
    cfg = load_config(ROOT / "config/level2.toml")
    render = not a.headless
    cfg.sim.render = render
    cfg.env.control_mode = "attitude"
    cfg.controller["mpccpp"] = json.loads(a.settings)
    controller_cls = load_controller(ROOT / "lsy_drone_racing/control/mpccpp.py")
    env = JaxToNumpy(
        gymnasium.make(
            cfg.env.id,
            freq=cfg.env.freq,
            sim_config=cfg.sim,
            sensor_range=cfg.env.sensor_range,
            control_mode="attitude",
            track=cfg.env.track,
            disturbances=cfg.env.get("disturbances"),
            randomizations=cfg.env.get("randomizations"),
            seed=0,
        )
    )
    # Each drawn line segment is one geom. Centerline, tunnel walls and trail exceed the default
    # 1000. The viewer is created on the first render, so this must be set before it.
    env.unwrapped.sim.max_visual_geom = 5000
    obs, info = env.reset(seed=a.seed)
    c = controller_cls(obs, info, cfg)
    freq = cfg.env.freq
    track, trail = c._track, []
    dt = 1 / (freq * a.speed)
    deadline = time.perf_counter()
    terminated = truncated = False
    for tick in range(int(a.timeout * freq)):
        action = c.compute_control(obs, info)
        if c._track is not track:
            track = c._track
            print(
                f"t={tick / freq:5.2f}s  track rebuilt, gates seen "
                f"{np.asarray(obs['gates_visited']).astype(int).tolist()}, poles seen "
                f"{np.asarray(obs['obstacles_visited']).astype(int).tolist()}"
            )
        trail.append(np.asarray(obs["pos"], dtype=float).copy())
        last_obs = obs
        obs, reward, terminated, truncated, info = env.step(action)
        c.step_callback(action, obs, reward, terminated, truncated, info)
        if render:
            sim = env.unwrapped.sim
            draw_overlays(sim, c, a.full_walls)
            if len(trail) > 1:
                draw_line(sim, np.asarray(trail[::-5][::-1]), rgba=(1, 1, 1, 0.8))
            for pole, rgba in zip(np.asarray(obs["obstacles_pos"]), POLE_RGBA):
                draw_points(sim, pole[None], rgba=rgba, size=0.03)
            # Assumed gate centers: nominal until the gate is in sensor range, then the true pose
            for gate, seen in zip(np.asarray(obs["gates_pos"]), obs["gates_visited"]):
                rgba = GATE_SEEN_RGBA if seen else GATE_NOMINAL_RGBA
                draw_points(sim, gate[None], rgba=rgba, size=0.03)
            env.render()
            # After a pause (space in the viewer) continue from now instead of catching up
            deadline = max(deadline + dt, time.perf_counter())
            time.sleep(max(0.0, deadline - time.perf_counter()))
        if terminated or truncated:
            break
    gates = int(obs["n_gates_passed"])
    finished = gates == len(obs["gate_sequence"])
    outcome = "finished" if finished else "crash" if terminated else "timeout"
    print(
        json.dumps(
            dict(
                seed=a.seed,
                outcome=outcome,
                time_s=(tick + 1) / freq,
                gates_passed=gates,
                solver_failures=int(c.solver_failures),
                final_pos=np.round(last_obs["pos"], 3).tolist(),
            )
        )
    )
    if render:
        time.sleep(2.0)  # keep the final frame visible before the viewer closes
    env.close()


if __name__ == "__main__":
    main()

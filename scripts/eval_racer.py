"""Lap-time evaluation of an RL racer checkpoint: full courses from the start, deployed policy.

Flies one course per world with the mean action of actor.npz (numpy forward pass, as racer_rl.py
does in deployment) and reports success rate, lap times and where failed courses end. Training-only
rules (invisible gate wall, wrong-way crash, hover cutoff, vias) are off; only real crashes count.

Start modes: "ground" (competition start, on the takeoff spot) or "hover" (at rest mid-air above the
takeoff spot, rotors at hover speed; for policies not trained on takeoff yet).
    .pixi/envs/tests/bin/python scripts/eval_racer.py --run runs/racer/20261124-210945
    .pixi/envs/tests/bin/python scripts/eval_racer.py --run ... --start ground --config level2.toml
"""

from __future__ import annotations

from pathlib import Path

import fire
import jax.numpy as jp
import numpy as np
from crazyflow.dynamics import load_params as load_dynamics_params

from lsy_drone_racing.control.racer_env import RacerEnv
from lsy_drone_racing.utils import load_config

ROOT = Path(__file__).parents[1]


class Actor:
    """Numpy forward pass of an actor.npz export (mean action)."""

    def __init__(self, path: Path):
        """Load weights, observation statistics and the thrust mapping the actor was trained with."""
        a = np.load(path)
        self.layers = [(a[f"W{i}"], a[f"b{i}"]) for i in range(3)]
        self.mean, self.std, self.clip = a["obs_mean"], a["obs_std"], float(a["obs_clip"])
        self.c_offset = float(a["c_offset"]) if "c_offset" in a else 10.19
        self.c_scale = float(a["c_scale"]) if "c_scale" in a else 8.6

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        """Network outputs (N, 3) for observations (N, 50).

        Run 18's actor has a 51st input, the drone mass; it gets the nominal mass (0.5).
        """
        if self.mean.shape[0] > obs.shape[-1]:
            obs = np.concatenate([obs, np.full((*obs.shape[:-1], 1), 0.5, obs.dtype)], -1)
        h = np.clip((obs - self.mean) / self.std, -self.clip, self.clip)
        for W, b in self.layers:
            h = np.tanh(h @ W.T + b)
        return h


def hover_start(env: RacerEnv, height: float):
    """Move every world's drone to `height` above its takeoff spot, at rest with hover rotor speed."""
    params = load_dynamics_params(env.sim.dynamics, env.sim.drone)
    c0, c1, c2 = (float(c) for c in params["rpm2thrust"])
    f = float(params["mass"]) * 9.81 / 4
    hover_rotor = (-c1 + np.sqrt(c1**2 - 4 * c2 * (c0 - f))) / (2 * c2)
    d = env.data
    pos = d.sim_data.states.pos.at[..., 2].set(height)
    states = d.sim_data.states.replace(
        pos=pos,
        vel=jp.zeros_like(pos),
        ang_vel=jp.zeros_like(pos),
        rotor_vel=jp.full_like(d.sim_data.states.rotor_vel, hover_rotor),
    )
    env.data = d.replace(
        sim_data=d.sim_data.replace(states=states), last_drone_pos=pos, takeoff_pos=pos
    )


def evaluate(
    run: str,
    start: str = "hover",
    config: str = "level2_racer_train.toml",
    n: int = 256,
    height: float = 0.5,
    seed: int = 0,
):
    """Fly n courses and print success rate, lap times and failure points.

    Args:
        run: Run directory with actor.npz.
        start: "hover" (mid-air above the takeoff spot) or "ground".
        config: Env config in config/. level2.toml randomizes gates and poles.
        n: Number of courses (parallel worlds).
        height: Hover start height in m.
        seed: Seed of the randomization.
    """
    actor = Actor(ROOT / run / "actor.npz")
    cfg = load_config(ROOT / "config" / config)
    env = RacerEnv(
        num_envs=n,
        freq=cfg.env.freq,
        sim_config=cfg.sim,
        track=cfg.env.track,
        sensor_range=cfg.env.sensor_range,
        disturbances=cfg.env.get("disturbances"),
        randomizations=cfg.env.get("randomizations"),
        seed=seed,
        air_start_frac=0.0,
        c_offset=actor.c_offset,
        c_scale=actor.c_scale,
    )
    env.reset(seed=seed)
    if start == "hover":
        hover_start(env, height)
    elif start != "ground":
        raise ValueError(f"start must be 'hover' or 'ground', not {start!r}")
    # Observation of the (possibly moved) start state
    obs = np.asarray(env._build_obs({k: v[:, 0] for k, v in _race_obs(env).items()}))
    n_pass = int(env.data.gate_sequence.shape[0])
    dt = 1.0 / cfg.env.freq

    done = np.zeros(n, dtype=bool)
    lap = np.full(n, np.nan)
    outcome = np.full(n, "timeout", dtype=object)
    last_gate = np.zeros(n, dtype=int)
    for t in range(int(30 * cfg.env.freq)):  # 30 s, the env's episode limit
        obs, _, term, trunc, info = env.step(jp.asarray(actor(obs), dtype=jp.float32))
        obs = np.asarray(obs)
        live = ~done
        gates = np.asarray(info["gates_passed"])
        last_gate[live] = gates[live]
        fin = np.asarray(info["finished"]) & live
        lap[fin] = (t + 1) * dt
        outcome[fin] = "finished"
        crash = np.asarray(info["crashed"]) & live
        outcome[crash] = "crashed"
        ended = fin | crash | ((np.asarray(term) | np.asarray(trunc)) & live)
        done |= ended
        if done.all():
            break
    env.close()

    ok = outcome == "finished"
    print(f"{run}: {n} courses, {start} start, config {config}")
    print(f"  finished {ok.mean():6.1%}   crashed {(outcome == 'crashed').mean():6.1%}   "
          f"timeout {(outcome == 'timeout').mean():6.1%}")
    if ok.any():
        q = np.quantile(lap[ok], [0.1, 0.5, 0.9])
        print(f"  lap time: median {q[1]:.2f} s, best {lap[ok].min():.2f} s, "
              f"10-90% {q[0]:.2f}-{q[2]:.2f} s, mean {lap[ok].mean():.2f} s")
    failed = ~ok
    if failed.any():
        stuck = np.bincount(last_gate[failed], minlength=n_pass + 1)[:n_pass]
        print("  failed courses by target pass: "
              + "  ".join(f"pass {k}: {c}" for k, c in enumerate(stuck)))


def _race_obs(env: RacerEnv) -> dict:
    """Raw race observations of the current env state."""
    from lsy_drone_racing.envs.race_core import obs as race_obs

    return race_obs(env.data)


if __name__ == "__main__":
    fire.Fire(evaluate)

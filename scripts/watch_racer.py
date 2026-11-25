"""Watch the RL racer in the training env: same start states (mid-air along the route or ground).

Uses the newest runs/racer/*/checkpoint.pt unless --run is given. Needs torch (tests env):
    .pixi/envs/tests/bin/python scripts/watch_racer.py
    .pixi/envs/tests/bin/python scripts/watch_racer.py --stochastic True --air_start_frac 1.0
"""

from __future__ import annotations

import time
from pathlib import Path

import fire
import jax.numpy as jp
import numpy as np
import torch

from lsy_drone_racing.control.racer_env import RacerEnv
from lsy_drone_racing.control.train_racer import Agent
from lsy_drone_racing.utils import load_config

ROOT = Path(__file__).parents[1]


def via_pass_dist(args: dict) -> tuple[float, ...]:
    """Via distances per pass from the training args (older checkpoints stored via_gates)."""
    if "via_pass_dist" in args:
        return tuple(args["via_pass_dist"])
    if args.get("via_gates"):
        order = [1, 2, 3, 4, 2]  # Level 2 gate order (signed, 1-based)
        return tuple(args["via_dist"] if abs(g) - 1 in args["via_gates"] else 0.0 for g in order)
    return ()


def watch(
    run: str | None = None,
    config: str = "level2_racer_train.toml",
    air_start_frac: float | None = None,
    air_start_sigma: float | None = None,
    front_start_frac: float | None = None,
    stochastic: bool = False,
    episodes: int = 20,
    speed: float = 1.0,
    seed: int = 0,
    render: bool = True,
):
    """Render episodes of the latest (or given) checkpoint with training-like start states.

    Args:
        run: Run directory containing checkpoint.pt. Defaults to the newest under runs/racer/.
        config: Training config in config/.
        air_start_frac: Fraction of mid-air starts. Defaults to the checkpoint's training setting.
        air_start_sigma: Std of the route-start noise in m. Defaults to the training setting.
        front_start_frac: Fraction of mid-air starts in front of the target gate. Defaults to the
            training setting.
        stochastic: Sample actions like during training instead of using the mean action.
        episodes: Number of episodes to show.
        speed: Playback speed relative to real time.
        seed: Seed of the start states.
        render: Open the viewer (False only prints the episode outcomes).
    """
    path = Path(run) if run else sorted((ROOT / "runs" / "racer").glob("*/checkpoint.pt"))[-1].parent
    ck = torch.load(path / "checkpoint.pt", weights_only=False)
    args = ck["args"]
    agent = Agent(50, 3, args["hidden"], tuple(args["logstd_init"]))
    agent.load_state_dict(ck["agent"])
    obs_mean = ck["obs_mean"].float()
    obs_std = torch.sqrt(ck["obs_var"] + 1e-8).float()
    print(f"Checkpoint: {path} ({'stochastic' if stochastic else 'mean'} actions)")

    cfg = load_config(ROOT / "config" / config)
    cfg.sim.render = render
    env = RacerEnv(
        num_envs=1,
        freq=cfg.env.freq,
        sim_config=cfg.sim,
        track=cfg.env.track,
        sensor_range=cfg.env.sensor_range,
        disturbances=cfg.env.get("disturbances"),
        randomizations=cfg.env.get("randomizations"),
        seed=seed,
        air_start_frac=args.get("air_start_frac", 0.5) if air_start_frac is None else air_start_frac,
        air_start_sigma=args.get("air_start_sigma", 0.283) if air_start_sigma is None else air_start_sigma,
        front_start_frac=(
            args.get("front_start_frac", 0.0) if front_start_frac is None else front_start_frac
        ),
        # Thrust mapping the checkpoint was trained with; older checkpoints used 10.19 / 8.6
        stall_time=args.get("stall_time", 0.0),
        height_weight=args.get("height_weight", 1.0),
        approach_dist=args.get("approach_dist", 0.0),
        via_pass_dist=via_pass_dist(args),
        via_radius=args.get("via_radius", 0.25),
        via_bonus=args.get("via_bonus", 2.0),
        wrong_way_crash=args.get("wrong_way_crash", False),
        wall_crash=args.get("wall_crash", False),
        stall_penalty=args.get("stall_penalty", 10.0),
        c_offset=args.get("c_offset", 10.19),
        c_scale=args.get("c_scale", 8.6),
    )
    dt = 1.0 / cfg.env.freq
    n_pass = env.data.gate_sequence.shape[0]

    def describe_start() -> tuple[int, str]:
        p = np.asarray(env.data.sim_data.states.pos[0, 0])
        n0 = int(env.data.n_gates_passed[0, 0])
        kind = "mid-air" if p[2] > 0.1 else "ground "
        return n0, f"{kind} start at {np.round(p, 2)} -> target pass {n0}"

    obs, _ = env.reset(seed=seed)
    n0, start_text = describe_start()
    t_ep, ep, reported = 0, 0, False
    while ep < episodes:
        t_wall = time.perf_counter()
        x = torch.clamp((torch.tensor(np.asarray(obs)) - obs_mean) / obs_std, -5, 5)
        with torch.no_grad():
            action, _, _, _ = agent.get_action_and_value(x, deterministic=not stochastic)
        obs, reward, term, trunc, info = env.step(jp.asarray(action.numpy()))
        t_ep += 1
        if not bool(info["valid"][0]):  # Auto-reset step: a new episode starts here
            n0, start_text = describe_start()
            t_ep, reported = 0, False
            continue
        # The env reports a timeout on two consecutive steps; count the episode once
        if (bool(term[0]) or bool(trunc[0])) and not reported:
            reported = True
            n = int(info["gates_passed"][0])
            if n >= n_pass:
                outcome = "FINISHED"
            elif bool(info.get("wrong_way", [False])[0]):
                outcome = "wrongway"
            elif bool(info.get("wall", [False])[0]):
                outcome = "wall    "
            elif bool(info["crashed"][0]):
                outcome = "crashed "
            elif bool(info.get("stalled", [False])[0]):
                outcome = "stalled "
            else:
                outcome = "timeout "
            print(f"ep {ep:3d}: {start_text:52s} | {outcome} after {t_ep * dt:5.2f} s, "
                  f"gates passed {n - n0}")
            ep += 1
        if render:
            env.render()
            time.sleep(max(0.0, dt / speed - (time.perf_counter() - t_wall)))
    env.close()


if __name__ == "__main__":
    fire.Fire(watch)

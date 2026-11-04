"""Closed-loop prediction accuracy: actual position vs MPC prediction made k steps earlier."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np, gymnasium, fire
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.utils import load_config
from lsy_drone_racing.control.mpccpp import MPCCPlusPlus, POS


def main(seed=11, n=3, **overrides):
    cfg = load_config(Path("config/level2mpc.toml")); cfg.sim.render = False
    cfg.controller["mpccpp"] = overrides
    env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
        control_mode=cfg.env.control_mode, track=cfg.env.track, disturbances=cfg.env.get("disturbances"),
        randomizations=cfg.env.get("randomizations"), seed=seed))
    for ep in range(n):
        obs, info = env.reset()
        c = MPCCPlusPlus(obs, info, cfg)
        preds, actual, slack = [], [], []
        while True:
            a = c.compute_control(obs, info)
            preds.append(None if c._x is None else c._x[:, POS].copy())
            obs, r, term, trunc, info = env.step(a)
            actual.append(obs["pos"].copy())
            if term or trunc:
                break
        actual = np.array(actual)
        for k in (5, 10, 15):
            errs = [np.linalg.norm(preds[t][k] - actual[t + k - 1]) for t in range(len(actual) - k) if preds[t] is not None]
            print(f"ep {ep} k={k} ({k*0.02:.1f}s): mean {np.mean(errs):.3f} m, p90 {np.percentile(errs, 90):.3f} m")
        print(f"ep {ep} passed {obs['n_gates_passed']} gates, residual {np.round(c._residual, 2)}")


fire.Fire(main)

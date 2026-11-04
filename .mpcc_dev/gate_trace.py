"""Trace a failing episode: planned vs actual gate-frame offsets near the crash."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np, gymnasium, fire
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from scipy.spatial.transform import Rotation as Rot
from lsy_drone_racing.utils import load_config
from lsy_drone_racing.control.mpccpp import MPCCPlusPlus, POS, THETA


def main(seed=11, n=10, **overrides):
    cfg = load_config(Path("config/level2mpc.toml")); cfg.sim.render = False
    cfg.controller["mpccpp"] = overrides
    env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
        control_mode=cfg.env.control_mode, track=cfg.env.track, disturbances=cfg.env.get("disturbances"),
        randomizations=cfg.env.get("randomizations"), seed=seed))
    for ep in range(n):
        obs, info = env.reset()
        c = MPCCPlusPlus(obs, info, cfg)
        log = []
        while True:
            target = obs["gate_sequence"][obs["n_gates_passed"]] if obs["n_gates_passed"] < 5 else 1
            a = c.compute_control(obs, info)
            log.append((obs["pos"].copy(), None if c._x is None else c._x.copy(), target, obs["gates_pos"].copy(), obs["gates_quat"].copy(), obs["gates_visited"].copy()))
            obs, r, term, trunc, info = env.step(a)
            if term or trunc:
                break
        if obs["n_gates_passed"] == 5:
            continue
        print(f"== ep {ep} failed after {obs['n_gates_passed']} gates")
        g = log[-1][2]
        for pos, x, target, gp, gq, vis in log[-20:]:
            rot = Rot.from_quat(gq[g])
            loc = rot.inv().apply(pos - gp[g])
            plan = rot.inv().apply(x[:, POS] - gp[g]) if x is not None else None
            # planned crossing of the gate plane
            cross = ""
            if plan is not None:
                idx = np.flatnonzero((plan[:-1, 0] < 0) & (plan[1:, 0] >= 0))
                if len(idx):
                    k = idx[0]; w = -plan[k, 0] / (plan[k + 1, 0] - plan[k, 0])
                    pc = plan[k] + w * (plan[k + 1] - plan[k])
                    cross = f"plan crosses at y={pc[1]:+.3f} z={pc[2]:+.3f} in {k} steps"
            print(f"  gate{g} vis={vis[g]} actual local {np.round(loc, 3)}  {cross}")
        tr = c._track
        k = np.argmin(np.abs(tr.s - tr.gate_s[min(log[-1][2] and list(c._gate_order).index(g), 4)]))
        break


fire.Fire(main)

"""Fly the time-optimal trajectory with the state interface (onboard tracking controller)."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np, gymnasium, fire
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.utils import load_config


def main(config="level0.toml", stretch=1.0, n=5, seed=1, delay=0.0):
    cfg = load_config(Path("config") / config); cfg.sim.render = False
    tr = np.load(".mpcc_dev/racing_traj.npz")
    t, pos, vel, acc = tr["t"] * stretch, tr["pos"], tr["vel"] / stretch, tr["acc"] / stretch**2
    env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=50, sim_config=cfg.sim, sensor_range=0.7, control_mode="state",
        track=cfg.env.track, disturbances=cfg.env.get("disturbances"), randomizations=cfg.env.get("randomizations"), seed=seed))
    res = []
    for ep in range(n):
        obs, _ = env.reset()
        i = 0
        while True:
            tc = max(i / 50 - delay, 0.0)
            p = np.array([np.interp(tc, t, pos[:, j]) for j in range(3)])
            v = np.array([np.interp(tc, t, vel[:, j]) for j in range(3)])
            a = np.array([np.interp(tc, t, acc[:, j]) for j in range(3)])
            if tc > t[-1]:  # Keep flying straight on after the end of the trajectory
                p = pos[-1] + vel[-1] * (tc - t[-1]); v = vel[-1]; a = np.zeros(3)
            action = np.concatenate((p, v, a, [0, 0, 0, 1], np.zeros(3))).astype(np.float32)
            obs, r, term, trunc, info = env.step(action)
            i += 1
            if term or trunc or i > 500:
                break
        ok = obs["n_gates_passed"] == 5
        res.append(i / 50 if ok else None)
        print(f"  ep {ep}: {'OK ' if ok else 'FAIL'} t={i/50:.2f}s gates={obs['n_gates_passed']}", flush=True)
    okt = [x for x in res if x]
    print(f"{config} stretch {stretch}: success {len(okt)}/{n}, mean {np.mean(okt) if okt else float('nan'):.3f}s")


if __name__ == "__main__":
    fire.Fire(main)

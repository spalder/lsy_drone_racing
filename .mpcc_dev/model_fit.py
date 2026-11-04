"""Fit thrust lag, attitude command lag and attitude gain of the MPC model to the simulator."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import itertools
import numpy as np, gymnasium
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from scipy.spatial.transform import Rotation as R
from crazyflow.dynamics import Dynamics, load_params
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from lsy_drone_racing.utils import load_config

cfg = load_config(Path("config/level0.toml")); cfg.sim.render = False
env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=50, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
    control_mode="attitude", track=cfg.env.track, disturbances=None, randomizations=None, seed=1))
p = load_params(Dynamics.so_rpy, cfg.sim.drone)
m, g = p["mass"], 9.81
hover = m * g / p["cmd_f_coef"]
rng = np.random.default_rng(0)
data = []  # (x0, cmds, observed states)
for trial in range(12):
    obs, _ = env.reset()
    for i in range(100):
        e = 1.2 - obs["pos"][2]
        obs, *_ = env.step(np.array([0, 0, 0, hover * (1 + 0.5 * e - 0.3 * obs["vel"][2])], dtype=np.float32))
    # random piecewise constant commands, 0.1 s each, 0.6 s total
    cmds = np.repeat(np.column_stack((rng.uniform(-0.8, 0.8, (6, 2)), np.zeros(6), rng.uniform(0.25, 0.8, 6))), 5, axis=0)
    x0 = np.concatenate((obs["pos"], R.from_quat(obs["quat"]).as_euler("xyz"), obs["vel"], ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])))
    states = []
    for u in cmds:
        obs, *_ = env.step(u.astype(np.float32))
        states.append(np.concatenate((obs["pos"], R.from_quat(obs["quat"]).as_euler("xyz"), obs["vel"])))
    data.append((x0, cmds, np.array(states)))


def rollout(x0, cmds, k_t, k_r, gain, sub=10, dt=0.02):
    x = x0.copy(); thrust = hover; c = np.zeros(3); out = []
    h = dt / sub
    for u in cmds:
        for _ in range(sub):
            thrust += h * k_t * (u[3] - thrust) if k_t else (u[3] - thrust)
            c += h * k_r * (u[:3] - c) if k_r else (u[:3] - c)
            rot = R.from_euler("xyz", x[3:6]).as_matrix()
            acc = rot @ np.array([0, 0, p["cmd_f_coef"] * thrust]) / m + p["gravity_vec"]
            ddrpy = p["rpy_coef"] * x[3:6] + p["rpy_rates_coef"] * x[9:12] + gain * p["cmd_rpy_coef"] * c
            x = x + h * np.concatenate((x[6:9], x[9:12], acc, ddrpy))
        out.append(x[:9].copy())
    return np.array(out)


def score(k_t, k_r, gain):
    err_v, err_a = 0.0, 0.0
    for x0, cmds, obs in data:
        pred = rollout(x0, cmds, k_t, k_r, gain)
        err_v += np.mean((pred[:, 6:9] - obs[:, 6:9]) ** 2)
        err_a += np.mean((pred[:, 3:5] - obs[:, 3:5]) ** 2)
    return err_v / len(data), err_a / len(data)

print("baseline so_rpy      ", np.round(score(0, 0, 1.0), 4))
print("so_rpy_rotor (19.3)  ", np.round(score(19.3, 0, 1.0), 4))
best = min(((score(kt, kr, gn), kt, kr, gn) for kt, kr, gn in itertools.product([5, 7, 8.5, 10, 12], [20, 25, 30], [0.95, 1.0, 1.05])),
           key=lambda r: r[0][0] + 0.5 * r[0][1])
print("best fit", best)

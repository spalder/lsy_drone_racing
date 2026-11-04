"""Compare so_rpy model rollouts with the first_principles sim for attitude step commands."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np, gymnasium, casadi as ca
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from scipy.spatial.transform import Rotation as R
from crazyflow.dynamics import Dynamics, load_params
from crazyflow.dynamics.so_rpy import symbolic_dynamics_euler
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from lsy_drone_racing.utils import load_config

cfg = load_config(Path("config/level0.toml")); cfg.sim.render = False
cfg.env.control_mode = "attitude"
env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=50, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
    control_mode="attitude", track=cfg.env.track, disturbances=None, randomizations=None, seed=1))
p = load_params(Dynamics.so_rpy, cfg.sim.drone)
Xd, X, U, _ = symbolic_dynamics_euler(**{k: p[k] for k in ["mass","gravity_vec","acc_coef","cmd_f_coef","rpy_coef","rpy_rates_coef","cmd_rpy_coef"]})
f = ca.Function("f", [X, U], [Xd])
def step(x, u, dt=0.02, sub=10):
    h = dt / sub
    for _ in range(sub):
        k1 = f(x, u); k2 = f(x + h/2*k1, u); k3 = f(x + h/2*k2, u); k4 = f(x + h*k3, u)
        x = x + h/6*(k1+2*k2+2*k3+k4)
    return np.array(x).ravel()
hover = p["mass"] * 9.81 / p["cmd_f_coef"]
for roll, pitch, thrust_scale in [(0.3, 0.0, 1.05), (0.6, 0.0, 1.2), (0.9, 0.0, 1.5), (0.6, 0.6, 1.5), (0.0, -0.9, 1.8)]:
    obs, _ = env.reset()
    # take off to 1 m with a simple hover first
    for i in range(100):
        e = 1.0 - obs["pos"][2]
        obs, *_ = env.step(np.array([0, 0, 0, hover * (1 + 0.5 * e - 0.3 * obs["vel"][2])], dtype=np.float32))
    x = np.concatenate((obs["pos"], R.from_quat(obs["quat"]).as_euler("xyz"), obs["vel"], ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])))
    u = np.array([roll, pitch, 0.0, min(hover * thrust_scale, 0.8)])
    errs = []
    for i in range(15):  # 0.3 s
        obs, *_ = env.step(u.astype(np.float32))
        x = step(x, u)
        rpy = R.from_quat(obs["quat"]).as_euler("xyz")
        if i in (2, 5, 9, 14):
            errs.append(f"t={0.02*(i+1):.2f} rpy sim {np.round(rpy[:2],2)} model {np.round(x[3:5],2)} | vel sim {np.round(obs['vel'],2)} model {np.round(x[6:9],2)}")
    print(f"cmd roll {roll} pitch {pitch} thrust {u[3]:.2f}N (hover {hover:.2f})"); print("\n".join("   " + e for e in errs))

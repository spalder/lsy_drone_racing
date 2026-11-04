import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np, gymnasium
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.utils import load_config
from lsy_drone_racing.control.mpccpp import MPCCPlusPlus
cfg = load_config(Path("config/level2mpc.toml")); cfg.sim.render = False
cfg.controller["mpccpp"] = dict(slack_l1=5000., slack_l2=1e5, residual_gain=0., max_speed=4., reference_speed=4.)
env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=cfg.env.freq, sim_config=cfg.sim, sensor_range=cfg.env.sensor_range,
    control_mode=cfg.env.control_mode, track=cfg.env.track, disturbances=cfg.env.get("disturbances"),
    randomizations=cfg.env.get("randomizations"), seed=2))
obs, info = env.reset()
c = MPCCPlusPlus(obs, info, cfg)
print("gate_sequence", obs["gate_sequence"], "visited", obs["gates_visited"], "gate_s", c._track.gate_s)
for i in range(60):
    a = c.compute_control(obs, info)
    obs, *_ = env.step(a)
    if i % 5 == 0:
        ub = [c._solver.constraints_get(k, "ubx") if hasattr(c._solver, "constraints_get") else None for k in (1, 15, 29)]
        print(i, "theta", round(c._theta, 2), "vtheta", np.round(c._x[[1, 15, 29], 13], 2), "ubx", ub, "z", round(obs["pos"][2], 2))

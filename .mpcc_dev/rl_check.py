"""Build the racing line route on the nominal track and report length, timing and clearances."""
import crazyflow  # noqa
import sys, time; sys.path.insert(0, ".")
import numpy as np, gymnasium
from pathlib import Path
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.utils import load_config
from lsy_drone_racing.control import mpccpp as M
cfg = load_config(Path("config/level2.toml")); cfg.sim.render = False
cfg.controller["mpccpp"] = {k: float(v) for k, v in (a.split("=") for a in sys.argv[1:])}
env = JaxToNumpy(gymnasium.make(cfg.env.id, freq=50, sim_config=cfg.sim, sensor_range=0.7, control_mode="attitude",
    track=cfg.env.track, disturbances=None, randomizations=None, seed=1))
obs, info = env.reset()
t0 = time.time(); c = M.MPCCPlusPlus(obs, info, cfg); print(f"controller init {time.time()-t0:.2f}s")
tr = c._track
print(f"length {tr.length:.2f} m, gates at {np.round(tr.gate_s, 2)}")
cl = M.free_space(tr.pos, obs["gates_pos"], obs["gates_quat"], obs["obstacles_pos"], c._limits, np.zeros(4),
                  M.drone_footprint(0.9, obs["gates_quat"]))
bad = np.flatnonzero(cl < 0.02)
print(f"min free space {cl.min():.3f} m; points with free space < 0.02: {len(bad)}", np.round(tr.pos[bad[::20]], 2) if len(bad) else "")
for leg, r in c._route.items():
    print(f"  leg {leg}: {len(r['via'])} via points, passage angle {r.get('angle', 0):.1f} deg")
print("leg 0 via:", [(g, np.round(p, 2)) for g, p in c._route[0]["via"]])
print("start", np.round(c._start, 2))

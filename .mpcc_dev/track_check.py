import crazyflow  # noqa: F401  (sets SCIPY_ARRAY_API)
import sys, time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation as R
sys.path.insert(0, "/home/spalder/Work/lsy_drone_racing")
from lsy_drone_racing.utils import load_config
from lsy_drone_racing.control import mpccpp as m

cfg = load_config(Path("/home/spalder/Work/lsy_drone_racing/config/level2.toml"))
gp = np.array([g["pos"] for g in cfg.env.track.gates]); gq = R.from_euler("xyz", [g["rpy"] for g in cfg.env.track.gates]).as_quat()
op = np.array([o["pos"] for o in cfg.env.track.obstacles])
order = np.array([0, 1, 2, 3, 1])
s = dict(m.MPCCPlusPlus.SETTINGS)
for a in sys.argv[1:]:
    k, v = a.split("="); s[k] = float(v)
local = {}
for leg, r in m.build_route(s).items():
    vl = []
    for p_, g in r.get("via", []):
        p_ = np.array(p_, float)
        if g >= 0: p_ = R.from_quat(gq[g]).inv().apply(p_ - gp[g])
        vl.append((g, p_))
    local[leg] = {**r, "via": vl}
lim = (np.array([-2.5, -1.5, 0.0]), np.array([2.5, 1.5, 2.0]))
t0 = time.time()
tr = m.Track(np.array([-1.5, 0.75, 0.01]), gp, gq, op, np.full(4, 0.21), np.zeros((4, 3)), order, local, s, lim)
print(f"build {time.time()-t0:.3f}s length {tr.length:.2f} m gates at {np.round(tr.gate_s,2)}")
c = m.clearance(tr.pos, gp, gq, op, lim, np.full(4, 0.21))
bounds = np.concatenate(([0], tr.gate_s, [tr.length]))
for i in range(len(bounds) - 1):
    mask = (tr.s >= bounds[i]) & (tr.s < bounds[i+1])
    k = np.flatnonzero(mask)[np.argmin(c[mask])]
    print(f"leg {i}: s {bounds[i]:.2f}-{bounds[i+1]:.2f} min clearance {c[k]:.3f} at s={tr.s[k]:.2f} {np.round(tr.pos[k],2)}  ext {np.round(tr.extents[k],2)}")
# curvature
d2 = np.gradient(tr.tangent, tr.ds, axis=0)
kappa = np.linalg.norm(d2, axis=1)
print("max curvature", kappa.max().round(2), "at", tr.s[kappa.argmax()].round(2), "r_min", (1/kappa.max()).round(3))
for g in tr.gate_s:
    k = int(g / tr.ds); print("gate extents", np.round(tr.extents[k], 3))

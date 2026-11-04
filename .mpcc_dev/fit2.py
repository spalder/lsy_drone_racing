import sys; sys.path.insert(0, ".mpcc_dev")
import model_id as M
import numpy as np
from scipy.optimize import minimize
exec(open(".mpcc_dev/fit.py").read().split("for names, x0 in [")[0].split("import model_id as M")[1].replace("from scipy.optimize import minimize", ""))
names, x0 = ["thrust_gain", "cmd_gain", "k_t", "k_r", "drag_x", "drag_y"], [1.03, 0.96, 60.0, 100.0, 0.4, 0.2]
data = M.samples(K, {})
idx = rng.choice(len(data[0]), 1500, replace=False)
res = minimize(cost, x0, args=(names, idx, data), method="Nelder-Mead", options={"maxiter": 500, "xatol": 1e-3, "fatol": 1e-5})
print(f"{names}: -> {res.fun:.4f}  {np.round(res.x, 3)}")
M.turn_bias(make(res.x, names), 30)

import sys; sys.path.insert(0, ".mpcc_dev")
import model_id as M
import numpy as np
from scipy.optimize import minimize

K = 30
rng = np.random.default_rng(0)


def make(v, names):
    th = {}
    for name, x in zip(names, v):
        if name.startswith("drag"):
            th.setdefault("drag", np.zeros(3))
            th["drag"]["xyz".index(name[-1])] = x
        else:
            th[name] = x
    return th


def cost(v, names, idx, data):
    th = make(v, names)
    if "k_t" in th:  # The lag states of the samples depend on the lag constants
        data = M.samples(K, th)
    X0, T0, C0, U, Y, Ms = (a[idx] for a in data)
    pred = M.rollout(X0, T0, C0, U, Ms, th)
    return np.mean(np.linalg.norm(pred[:, :, :3] - Y[:, :, :3], axis=2))


for names, x0 in [
    (["thrust_gain", "cmd_gain"], [1.0, 1.0]),
    (["thrust_gain", "cmd_gain", "k_t", "k_r"], [1.0, 1.0, 7.0, 20.0]),
    (["thrust_gain", "cmd_gain", "k_t", "k_r", "drag_x", "drag_y", "drag_z"], [1.0, 1.0, 7.0, 20.0, 0.0, 0.0, 0.0]),
]:
    # Lag states depend on k_t, k_r: rebuild samples inside the objective only when they are fitted
    data = M.samples(K, {})
    idx = rng.choice(len(data[0]), 1500, replace=False)
    base = cost(x0, names, idx, data)
    res = minimize(cost, x0, args=(names, idx, data), method="Nelder-Mead", options={"maxiter": 400, "xatol": 1e-3, "fatol": 1e-5})
    print(f"{names}: {base:.4f} -> {res.fun:.4f}  {np.round(res.x, 3)}")
    th = make(res.x, names)
    print("   validation (all samples):")
    M.turn_bias(th, 30)

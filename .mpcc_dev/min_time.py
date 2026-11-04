"""Time-optimal point-mass flight through the level 2 gates: a lower bound on the lap time."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
from pathlib import Path
import casadi as ca, numpy as np, fire
from scipy.spatial.transform import Rotation as R
from lsy_drone_racing.utils import load_config


def main(max_tilt: float = 0.9, thrust_scale: float = 1.0, window: float = 0.1, clearance: float = 0.15, n: int = 30):
    cfg = load_config(Path("config/level2.toml"))
    gates = [(np.array(g["pos"]), R.from_euler("xyz", g["rpy"]).as_matrix()) for g in cfg.env.track.gates]
    poles = np.array([o["pos"] for o in cfg.env.track.obstacles])
    order = [0, 1, 2, 3, 1]
    start = np.array(cfg.env.track.drones[0]["pos"])
    g = np.array([0, 0, -9.81])
    f_max = 4 * 0.2 * 0.9459 / 0.0434 * thrust_scale  # Max collective thrust acceleration, m/s^2

    opti = ca.Opti()
    legs = len(order)
    T = opti.variable(legs)
    P = [opti.variable(3, n + 1) for _ in range(legs)]
    V = [opti.variable(3, n + 1) for _ in range(legs)]
    A = [opti.variable(3, n) for _ in range(legs)]
    opti.minimize(ca.sum1(T))
    opti.subject_to(T >= 0.2)
    opti.subject_to(P[0][:, 0] == start)
    opti.subject_to(V[0][:, 0] == 0)
    # Initial guess from the MPCC++ centerline, which avoids all poles
    from lsy_drone_racing.control import mpccpp as M
    settings = dict(M.MPCCPlusPlus.SETTINGS)
    gq = np.array([R.from_matrix(r).as_quat() for _, r in gates])
    gp = np.array([p for p, _ in gates])
    route = {}
    for leg, r in M.build_route(settings).items():
        via = [(gi, R.from_quat(gq[gi]).inv().apply(np.array(pt) - gp[gi]) if gi >= 0 else np.array(pt)) for pt, gi in r.get("via", [])]
        route[leg] = {**r, "via": via}
    lim = (np.array([-2.5, -1.5, -1.0]), np.array([2.5, 1.5, 2.0]))
    track = M.Track(start, gp, gq, poles, np.zeros(len(poles)), np.zeros((4, 3)), np.array(order), route, settings, lim)
    bounds = np.concatenate(([0.0], track.gate_s))
    for k in range(legs):
        dt = T[k] / n
        if k > 0:
            opti.subject_to(P[k][:, 0] == P[k - 1][:, -1])
            opti.subject_to(V[k][:, 0] == V[k - 1][:, -1])
        for j in range(n):
            a = A[k][:, j]
            opti.subject_to(P[k][:, j + 1] == P[k][:, j] + V[k][:, j] * dt + 0.5 * a * dt**2)
            opti.subject_to(V[k][:, j + 1] == V[k][:, j] + a * dt)
            f = a - g  # Thrust acceleration
            opti.subject_to(ca.sumsqr(f) <= f_max**2)
            opti.subject_to(f[2] >= np.cos(max_tilt) * ca.sqrt(ca.sumsqr(f) + 1e-6))
        for j in range(n + 1):
            p = P[k][:, j]
            opti.subject_to(p[2] >= 0.0)
            for pole in poles:
                opti.subject_to(ca.sumsqr(p[:2] - pole[:2]) >= clearance**2)
        pos, rot = gates[order[k]]
        d = P[k][:, -1] - pos
        opti.subject_to(ca.dot(d, rot[:, 0]) == 0)
        opti.subject_to(opti.bounded(-0.1, ca.dot(d, rot[:, 1]), 0.1))
        opti.subject_to(opti.bounded(-0.1, ca.dot(d, rot[:, 2]), 0.1))
        opti.subject_to(ca.dot(V[k][:, -1], rot[:, 0]) >= 0.5)  # Cross in the forward direction
        s_k = np.linspace(bounds[k], bounds[k + 1], n + 1)
        guess = track.lookup(s_k)[0]
        t_k = (bounds[k + 1] - bounds[k]) / 2.5
        opti.set_initial(P[k], guess.T)
        opti.set_initial(T[k], t_k)
        opti.set_initial(V[k], (np.gradient(guess, axis=0) / (t_k / n)).T)
    opti.solver("ipopt", {"print_time": False}, {"print_level": 0, "max_iter": 3000})
    # Homotopy: solve with a wide gate window first, then shrink it, warm started each time
    win = opti.parameter()
    for k in range(legs):
        pos_, rot_ = gates[order[k]]
        d_ = P[k][:, -1] - pos_
        opti.subject_to(opti.bounded(-win, ca.dot(d_, rot_[:, 1]), win))
        opti.subject_to(opti.bounded(-win, ca.dot(d_, rot_[:, 2]), win))
    sol = None
    for w in sorted({0.1, 0.06, window}, reverse=True):
        if w < window:
            continue
        opti.set_value(win, w)
        try:
            sol = opti.solve()
        except RuntimeError as e:
            print(f"failed at window {w}:", str(e)[-80:]); return
        opti.set_initial(sol.value_variables())
    t = sol.value(T)
    pts = np.hstack([sol.value(P[k]) for k in range(legs)])
    vel = np.hstack([sol.value(V[k]) for k in range(legs)])
    length = np.sum(np.linalg.norm(np.diff(pts, axis=1), axis=0))
    print(f"tilt {max_tilt}, thrust x{thrust_scale}, window {window}: lap {t.sum():.3f} s, legs {np.round(t, 2)}, "
          f"path {length:.2f} m, top speed {np.linalg.norm(vel, axis=0).max():.2f} m/s")
    np.save(".mpcc_dev/racing_line.npy", pts.T)
    # Time-parametrized trajectory: per-node time, position, velocity, acceleration
    times, acc = [], []
    t0 = 0.0
    for k in range(legs):
        dt = t[k] / n
        times.append(t0 + dt * np.arange(n + (1 if k == legs - 1 else 0)))
        acc.append(sol.value(A[k]))
        t0 += t[k]
    pos = np.hstack([sol.value(P[k])[:, : (n + 1 if k == legs - 1 else n)] for k in range(legs)])
    vel_ = np.hstack([sol.value(V[k])[:, : (n + 1 if k == legs - 1 else n)] for k in range(legs)])
    acc_ = np.hstack(acc + [acc[-1][:, -1:]])
    np.savez(".mpcc_dev/racing_traj.npz", t=np.concatenate(times), pos=pos.T, vel=vel_.T, acc=acc_.T, legs=t)


if __name__ == "__main__":
    fire.Fire(main)

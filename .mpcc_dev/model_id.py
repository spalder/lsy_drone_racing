"""Multi-step prediction errors of the MPC model on logged flights, and model fitting."""
import crazyflow  # noqa
import sys; sys.path.insert(0, ".")
import numpy as np
from scipy.spatial.transform import Rotation as Rot
from crazyflow.dynamics import Dynamics, load_params

P = load_params(Dynamics.so_rpy, "cf21B_500")
DT = 0.02
data = np.load(".mpcc_dev/flight_log.npz")
masses = data["masses"]
EPS = [data[f"ep{i}"] for i in range(len(masses))]


def rot_mats(rpy):
    return Rot.from_euler("xyz", rpy).as_matrix()


def f(x, T, c, m, th):
    """Continuous dynamics of the drone part, vectorized over samples. th: model parameters."""
    rpy, vel, drpy = x[:, 3:6], x[:, 6:9], x[:, 9:12]
    Rm = rot_mats(rpy)
    thrust = P["cmd_f_coef"] * T * th.get("thrust_gain", 1.0)
    acc = Rm[:, :, 2] * (thrust / m)[:, None] + P["gravity_vec"]
    if "drag" in th:  # linear drag in body frame
        vb = np.einsum("nji,nj->ni", Rm, vel)
        acc = acc - np.einsum("nij,nj->ni", Rm, th["drag"] * vb)
    cmd_gain = th.get("cmd_gain", 1.0)
    if "sat" in th:  # attitude authority shrinks as the thrust approaches its maximum
        head = np.clip((0.8 - T) / 0.8, 0, 1)
        cmd_gain = cmd_gain * (1 - th["sat"] * (1 - head) ** th.get("sat_pow", 2))
        cmd_gain = cmd_gain[:, None]
    ddrpy = P["rpy_coef"] * rpy + P["rpy_rates_coef"] * drpy + P["cmd_rpy_coef"] * c * cmd_gain
    return np.concatenate((vel, drpy, acc, ddrpy), axis=1)


def rollout(x0, T0, c0, cmds, m, th, k_t=7.0, k_r=20.0):
    """Roll out with RK4 for the drone and the exact solution of the linear command lags."""
    k_t, k_r = th.get("k_t", k_t), th.get("k_r", k_r)
    x, T, c = x0.copy(), T0.copy(), c0.copy()
    out = []
    for j in range(cmds.shape[1]):
        u = cmds[:, j]
        def lag(tau):
            return u[:, 3] + (T - u[:, 3]) * np.exp(-k_t * tau), u[:, :3] + (c - u[:, :3]) * np.exp(-k_r * tau)
        Th, ch = lag(DT / 2)
        Te, ce = lag(DT)
        k1 = f(x, T, c, m, th)
        k2 = f(x + DT / 2 * k1, Th, ch, m, th)
        k3 = f(x + DT / 2 * k2, Th, ch, m, th)
        k4 = f(x + DT * k3, Te, ce, m, th)
        x = x + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        T, c = Te, ce
        out.append(x.copy())
    return np.stack(out, axis=1)


def samples(K, th, k_t=7.0, k_r=20.0):
    """All windows of K steps in flight (z > 0.15) with lag states from the command history."""
    k_t, k_r = th.get("k_t", k_t), th.get("k_r", k_r)
    X0, T0, C0, U, Y, M = [], [], [], [], [], []
    for ep, m in zip(EPS, masses):
        s, u = ep[:, :12], ep[:-1, 12:]
        T, c = np.zeros(len(u) + 1), np.zeros((len(u) + 1, 3))
        for i in range(len(u)):
            T[i + 1] = T[i] + (1 - np.exp(-k_t * DT)) * (u[i, 3] - T[i])
            c[i + 1] = c[i] + (1 - np.exp(-k_r * DT)) * (u[i, :3] - c[i])
        for i in range(len(u) - K):
            if s[i, 2] < 0.15 or i < 10:
                continue
            X0.append(s[i]); T0.append(T[i]); C0.append(c[i]); U.append(u[i:i + K]); Y.append(s[i + 1:i + K + 1]); M.append(m)
    return tuple(map(np.array, (X0, T0, C0, U, Y, M)))


def errors(th, K=10, verbose=False):
    X0, T0, C0, U, Y, M = samples(K, th)
    pred = rollout(X0, T0, C0, U, M, th)
    pos_err = np.linalg.norm(pred[:, -1, :3] - Y[:, -1, :3], axis=1)
    vel_err = np.linalg.norm(pred[:, :, 6:9] - Y[:, :, 6:9], axis=2).mean(axis=1)
    if verbose:
        tilt = np.max(np.abs(Y[:, :, 3:5]).max(axis=2), axis=1)
        thrust = U[:, :, 3].mean(axis=1)
        print(f"  K={K} ({K*DT:.1f}s): pos err mean {pos_err.mean():.3f} m p90 {np.percentile(pos_err, 90):.3f}  (n={len(pos_err)})")
        for lo, hi in ((0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 2)):
            for tlo, thi in ((0, 0.6), (0.6, 0.81)):
                sel = (tilt >= lo) & (tilt < hi) & (thrust >= tlo) & (thrust < thi)
                if sel.sum() > 30:
                    print(f"    tilt {lo:.1f}-{hi:.1f} thrust {tlo:.1f}-{thi:.2f}: pos err {pos_err[sel].mean():.3f} m, share {sel.mean():.0%}")
    return pos_err.mean()


if __name__ == "__main__":
    print("current MPC model:")
    errors({}, K=10, verbose=True)


def turn_bias(th, K=30):
    """Signed error along the predicted turn: positive means the model turns more than the drone."""
    X0, T0, C0, U, Y, M = samples(K, th)
    pred = rollout(X0, T0, C0, U, M, th)
    straight = X0[:, None, :3] + X0[:, None, 6:9] * DT * np.arange(1, K + 1)[None, :, None]
    turn = pred[:, -1, :3] - straight[:, -1]
    turn[:, 2] = 0  # horizontal turn only
    n = np.linalg.norm(turn, axis=1)
    sel = n > 0.05
    d = turn[sel] / n[sel, None]
    err = (pred[sel, -1, :3] - Y[sel, -1, :3])
    along = np.sum(err * d, axis=1)
    pred_turn = n[sel]
    tilt = np.max(np.abs(Y[sel][:, :, 3:5]).max(axis=2), axis=1)
    zerr = pred[sel, -1, 2] - Y[sel, -1, 2]
    print(f"  K={K} ({K*DT:.1f}s): turn-direction error mean {along.mean():+.3f} m "
          f"(predicted turn {pred_turn.mean():.3f} m, ratio {along.sum() / pred_turn.sum():+.1%}), z err {zerr.mean():+.3f} m, n={sel.sum()}")
    for lo, hi in ((0, 0.5), (0.5, 0.7), (0.7, 2)):
        s2 = (tilt >= lo) & (tilt < hi)
        if s2.sum() > 30:
            print(f"    max tilt {lo:.1f}-{hi:.1f}: turn error {along[s2].mean():+.3f} m of {pred_turn[s2].mean():.3f} m ({along[s2].sum()/pred_turn[s2].sum():+.1%}), z err {zerr[s2].mean():+.3f}")

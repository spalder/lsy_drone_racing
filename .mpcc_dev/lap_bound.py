"""Point-mass time-optimal lap time along the centerline (lower bound for following it)."""
import sys
exec(open(".mpcc_dev/track_check.py").read().split("c = m.clearance")[0])
for a_max in (10.0, 14.0):
    kappa = np.linalg.norm(np.gradient(tr.tangent, tr.ds, axis=0), axis=1)
    kappa = np.convolve(kappa, np.ones(5) / 5, mode="same")
    s_end = tr.gate_s[-1]
    n = int(s_end / tr.ds)
    v = np.minimum(np.sqrt(a_max / np.maximum(kappa[:n], 1e-6)), 20.0)
    v[0] = 0.0
    # Forward and backward passes with the remaining acceleration budget (friction circle)
    for i in range(1, n):
        a_lat = v[i - 1] ** 2 * kappa[i - 1]
        a_lon = np.sqrt(max(a_max**2 - a_lat**2, 0.0))
        v[i] = min(v[i], np.sqrt(v[i - 1] ** 2 + 2 * a_lon * tr.ds))
    for i in range(n - 2, 0, -1):
        a_lat = v[i + 1] ** 2 * kappa[i + 1]
        a_lon = np.sqrt(max(a_max**2 - a_lat**2, 0.0))
        v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2 * a_lon * tr.ds))
    t = np.sum(tr.ds / np.maximum(0.5 * (v[1:] + v[:-1]), 1e-3))
    print(f"  a_max {a_max:4.1f} m/s^2: path {s_end:.2f} m, optimal lap {t:.2f} s, mean speed {s_end / t:.2f} m/s, top {v.max():.1f} m/s")

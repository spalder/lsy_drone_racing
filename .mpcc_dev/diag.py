"""Failure diagnostics over many races: what was hit, where, and how late the target gate was seen."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import json, multiprocessing as mp, collections, fire
import numpy as np
import tune_mpccpp as T


def _diag(task):
    params, seed = task
    from scipy.spatial.transform import Rotation as Rot
    T._CONFIG.controller["mpccpp"] = params
    obs, info = T._ENV.reset(seed=seed)
    c = T._CONTROLLER(obs, info, T._CONFIG)
    reveal = {}  # gate -> (distance along track to gate when revealed, speed)
    seen = np.array(obs["gates_visited"], dtype=bool)
    traj = []
    for step in range(600):
        a = c.compute_control(obs, info)
        prev = obs
        obs, r, term, trunc, info = T._ENV.step(a)
        traj.append(obs["pos"].copy())
        new = np.array(obs["gates_visited"], dtype=bool) & ~seen
        for g in np.flatnonzero(new):
            loc = Rot.from_quat(obs["gates_quat"][g]).inv().apply(obs["pos"] - obs["gates_pos"][g])
            reveal[int(g)] = (float(-loc[0]), float(np.linalg.norm(obs["vel"])))
        seen |= new
        if term or trunc:
            break
    n = int(obs["n_gates_passed"])
    if n == 5:
        return {"seed": seed, "ok": True, "time": (step + 1) / 50}
    last = traj[-2] if len(traj) > 1 else traj[-1]
    target = int(obs["gate_sequence"][n])
    rot = Rot.from_quat(obs["gates_quat"][target])
    loc = rot.inv().apply(last - obs["gates_pos"][target])
    true_shift = rot.inv().apply(obs["gates_pos"][target] - np.array(T._CONFIG.env.track.gates[target]["pos"]))
    # what is closest: gate frames of any gate, or poles
    dists = []
    for g in range(4):
        l = Rot.from_quat(obs["gates_quat"][g]).inv().apply(last - obs["gates_pos"][g])
        if abs(l[0]) < 0.2 and max(abs(l[1]), abs(l[2])) < 0.5:
            dists.append((f"gate{g}_frame", 0.0))
    for o, op in enumerate(obs["obstacles_pos"]):
        d = np.linalg.norm(last[:2] - op[:2])
        if d < 0.2 and last[2] < 1.6:
            dists.append((f"pole{o}", d))
    hit = dists[0][0] if dists else ("floor/out" if last[2] < 0.1 else "?")
    return {"seed": seed, "ok": False, "passed": n, "target_gate": target, "local": np.round(loc, 3).tolist(),
            "hit": hit, "reveal": reveal.get(target), "gate_shift_local": np.round(true_shift, 3).tolist()}


def main(seeds: str = "3000:3080", workers: int = 8):
    lo, hi = map(int, seeds.split(":"))
    with mp.get_context("spawn").Pool(workers, initializer=T._init_worker, initargs=("level2.toml",)) as pool:
        res = pool.map(_diag, [({}, s) for s in range(lo, hi)], chunksize=1)
    ok = [r for r in res if r["ok"]]
    print(f"success {len(ok)}/{len(res)}, mean time {np.mean([r['time'] for r in ok]):.3f}")
    fails = [r for r in res if not r["ok"]]
    print("failures by (gates passed, hit):", collections.Counter((r["passed"], r["hit"]) for r in fails))
    for r in sorted(fails, key=lambda r: r["passed"]):
        rv = r["reveal"]
        rv = f"revealed {rv[0]:.2f} m before at {rv[1]:.1f} m/s" if rv else "revealed earlier"
        print(f"  passed {r['passed']} -> gate{r['target_gate']}: hit {r['hit']:12s} local {r['local']}  shift {r['gate_shift_local']}  {rv}")


if __name__ == "__main__":
    fire.Fire(main)

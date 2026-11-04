"""Where along the route each gate and pole gets revealed, relative to where the drone needs it."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import json, multiprocessing as mp, fire
import numpy as np
import tune_mpccpp as T


def _reveal(task):
    params, seed = task
    T._CONFIG.controller["mpccpp"] = params
    obs, info = T._ENV.reset(seed=seed)
    c = T._CONTROLLER(obs, info, T._CONFIG)
    first_pass = {}
    for i, g in enumerate(c._gate_order):
        first_pass.setdefault(int(g), i)
    seen_g = np.array(obs["gates_visited"]); seen_o = np.array(obs["obstacles_visited"])
    gate_rev, obs_rev = {}, {}
    for _ in range(600):
        a = c.compute_control(obs, info)
        obs, r, term, trunc, info = T._ENV.step(a)
        vg = np.array(obs["gates_visited"]); vo = np.array(obs["obstacles_visited"])
        for g in np.flatnonzero(vg & ~seen_g):
            gs = c._track.gate_s[first_pass[int(g)]]
            gate_rev[int(g)] = (float(gs - c._theta), float(np.linalg.norm(obs["vel"])))
        for o in np.flatnonzero(vo & ~seen_o):
            obs_rev[int(o)] = float(c._theta)
        seen_g, seen_o = vg, vo
        if term or trunc:
            break
    return gate_rev, obs_rev, bool(obs["n_gates_passed"] == 5)


def main(seeds: str = "13000:13040", workers: int = 8, variant: str = "{}"):
    lo, hi = map(int, seeds.split(":"))
    params = json.loads(variant) if isinstance(variant, str) else dict(variant)
    with mp.get_context("spawn").Pool(workers, initializer=T._init_worker, initargs=("level2.toml",)) as pool:
        res = pool.map(_reveal, [(params, s) for s in range(lo, hi)], chunksize=1)
    for g in range(4):
        d = [r[0][g] for r in res if g in r[0]]
        if d:
            dist, v = np.array(d).T
            print(f"gate {g}: revealed {np.mean(dist):+.2f} m before its first pass (min {dist.min():+.2f}), speed {np.mean(v):.2f} m/s, in {len(d)}/{len(res)} races")
    print("success", np.mean([r[2] for r in res]))


if __name__ == "__main__":
    fire.Fire(main)

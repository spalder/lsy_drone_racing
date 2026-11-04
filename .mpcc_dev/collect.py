"""Log state/command trajectories of MPCC++ races for model identification."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import multiprocessing as mp, fire
import numpy as np
import tune_mpccpp as T


def _log(task):
    params, seed = task
    from scipy.spatial.transform import Rotation as Rot
    from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
    T._CONFIG.controller["mpccpp"] = params
    obs, info = T._ENV.reset(seed=seed)
    c = T._CONTROLLER(obs, info, T._CONFIG)
    rows = []
    for _ in range(600):
        a = c.compute_control(obs, info)
        rpy = Rot.from_quat(obs["quat"]).as_euler("xyz")
        drpy = ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])
        rows.append(np.concatenate((obs["pos"], rpy, obs["vel"], drpy, a)))
        obs, r, term, trunc, info = T._ENV.step(a)
        if term or trunc:
            break
    rpy = Rot.from_quat(obs["quat"]).as_euler("xyz")
    drpy = ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])
    rows.append(np.concatenate((obs["pos"], rpy, obs["vel"], drpy, np.full(4, np.nan))))
    return np.array(rows), float(T._ENV.unwrapped.data.sim_data.params.mass.reshape(-1)[0]) if hasattr(T._ENV.unwrapped, "data") else np.nan


def main(seeds: str = "9000:9040", workers: int = 8, out: str = ".mpcc_dev/flight_log.npz"):
    lo, hi = map(int, seeds.split(":"))
    with mp.get_context("spawn").Pool(workers, initializer=T._init_worker, initargs=("level2.toml",)) as pool:
        res = pool.map(_log, [({}, s) for s in range(lo, hi)], chunksize=1)
    np.savez(out, **{f"ep{i}": r for i, (r, _) in enumerate(res)}, masses=np.array([m for _, m in res]))
    print("episodes", len(res), "steps", sum(len(r) for r, _ in res), "masses", np.round([m for _, m in res][:5], 4))


if __name__ == "__main__":
    fire.Fire(main)

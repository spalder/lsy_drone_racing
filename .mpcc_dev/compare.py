"""Race parameter sets on identical seeds with the tuner's evaluation code."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import json, multiprocessing as mp, fire
import tune_mpccpp as T


def main(log: str, seeds: str = "320:380", workers: int = 8):
    from lsy_drone_racing.control.mpccpp import MPCCPlusPlus
    lo, hi = map(int, seeds.split(":"))
    rows = [json.loads(l) for l in open(log)]
    val = [r for r in rows if r["phase"] == "validation"]
    defaults = dict(T.FIXED, **{k: MPCCPlusPlus.SETTINGS[k] for k, *_ in T.SPACE})
    defaults["max_speed"] = MPCCPlusPlus.SETTINGS["max_speed"]
    cands = [("defaults", defaults)] + [(f"turbo #{i+1}", r["params"]) for i, r in enumerate(val[:1])]
    with mp.get_context("spawn").Pool(workers, initializer=T._init_worker, initargs=("level2.toml",)) as pool:
        res = T.evaluate(pool, [c for _, c in cands], list(range(lo, hi)))
    for (name, _), r in zip(cands, res):
        print(f"{name:10s} reward {r['reward']:.3f}  success {r['success_rate']:.0%}  mean time {r['mean_time']:.3f}s")


if __name__ == "__main__":
    fire.Fire(main)

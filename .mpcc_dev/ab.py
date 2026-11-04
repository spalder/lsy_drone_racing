"""A/B test setting overrides on identical level 2 tracks with the tuner's evaluation code."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import json, multiprocessing as mp, fire
import tune_mpccpp as T


def main(variants: str, seeds: str = "1000:1060", workers: int = 8):
    variants = json.loads(open(variants).read()) if variants.endswith(".json") else json.loads(variants)
    lo, hi = map(int, seeds.split(":"))
    with mp.get_context("spawn").Pool(workers, initializer=T._init_worker, initargs=("level2.toml",)) as pool:
        res = T.evaluate(pool, list(variants.values()), list(range(lo, hi)))
    for name, r in zip(variants, res):
        t = f"{r['mean_time']:.3f}s" if r["mean_time"] else "-"
        fails = sorted(x["gates"] for x in r["races"] if not x["finished"])
        print(f"{name:22s} reward {r['reward']:7.3f}  success {r['success_rate']:4.0%}  mean time {t}  fail@gates {fails}", flush=True)


if __name__ == "__main__":
    fire.Fire(main)

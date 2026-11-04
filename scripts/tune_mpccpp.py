"""Tune the MPCC++ controller with TuRBO, following Sec. IV-C of the MPCC++ paper.

The controller is treated as a black box. A candidate parameter set is scored by racing it on a
batch of randomized level 2 tracks:

    R(phi) = -mean(episode score) - gamma * solver failure rate

The episode score is the lap time for a finished race. Crashes get a lap time worse than any
finished race, reduced slightly for every gate that was passed so the objective is not flat. All
candidates of one batch race on the same tracks (common random numbers), which keeps the noise out
of the comparison within a batch. Every batch uses new tracks, so the result does not overfit.

TuRBO-m (Eriksson et al., 2019) runs m local Bayesian optimizations at once. Each one keeps a trust
region around its best point, fits a Gaussian process to the nearby observations and proposes the
candidate with the highest upper confidence bound inside its region. Regions grow after repeated
improvements and shrink after repeated failures. The paper uses TuRBO-8 from BoTorch. This is a
dependency free numpy/scipy implementation of the same algorithm.

Run as:

    $ python scripts/tune_mpccpp.py --budget 200 --workers 8

Results are appended to tuning/turbo_<time>.jsonl. Copy the best parameters into
MPCCPlusPlus.SETTINGS to use them.
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import time
from pathlib import Path

import crazyflow  # noqa: F401, must be imported before scipy, see crazyflow/__init__.py
import fire
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize
from scipy.stats import qmc

ROOT = Path(__file__).parents[1]
logger = logging.getLogger(__name__)

# Tuned parameters: name, lower bound, upper bound, log scale
SPACE = [
    ("contour_weight", 1.0, 200.0, True),
    ("lag_weight", 50.0, 3000.0, True),
    ("progress_weight", 1.0, 50.0, True),
    ("reference_speed", 3.0, 8.0, False),
    ("rate_weight", 0.002, 0.5, True),
    ("attitude_slew_weight", 0.004, 0.4, True),
    ("thrust_slew_weight", 0.02, 2.0, True),
    ("unobserved_speed", 1.5, 4.0, False),
    ("tunnel_margin", 0.0, 0.04, False),
    ("residual_gain", 0.05, 0.4, True),
    ("max_angle", 0.75, 1.1, False),
    ("plan_angle", 0.6, 1.1, False),
]
FIXED = {"max_speed": 8.0}  # Progress speed bound, high enough for every reference speed
# Additional parameters when tuning with the racing line (--racing_line)
RACING_LINE_SPACE = [
    ("racing_line_tilt", 0.6, 0.95, False),
    ("racing_line_clearance", 0.2, 0.4, False),
]
# Additional points of the initial design: the fast configuration before the first tuning run
SEED_POINTS = [
    {
        "contour_weight": 20.0,
        "lag_weight": 400.0,
        "progress_weight": 6.0,
        "reference_speed": 4.0,
        "rate_weight": 0.02,
        "attitude_slew_weight": 0.04,
        "thrust_slew_weight": 0.2,
        "unobserved_speed": 2.2,
        "tunnel_margin": 0.015,
        "residual_gain": 0.2,
        "max_angle": 0.9,
        "plan_angle": 0.9,
    }
]
TIMEOUT = 12.0  # Races that take longer count as failed, s
SOLVER_FAIL_PENALTY = 100.0  # gamma in the paper


def to_params(u: np.ndarray) -> dict:
    """Map a point of the unit cube to controller settings."""
    params = dict(FIXED)
    for x, (name, low, high, log) in zip(u, SPACE):
        params[name] = float(
            np.exp(np.log(low) + x * np.log(high / low)) if log else low + x * (high - low)
        )
    return params


def to_unit(params: dict) -> np.ndarray:
    """Map controller settings to the unit cube."""
    u = []
    for name, low, high, log in SPACE:
        v = params[name]
        u.append(np.log(v / low) / np.log(high / low) if log else (v - low) / (high - low))
    return np.clip(np.array(u), 0.0, 1.0)


# region Evaluation

_ENV = None
_CONFIG = None
_CONTROLLER = None


def _init_worker(config_file: str):
    """Create one environment per worker process and reuse it for all races."""
    global _ENV, _CONFIG, _CONTROLLER
    import gymnasium
    from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

    from lsy_drone_racing.utils import load_config, load_controller

    logging.getLogger("controller").setLevel(logging.ERROR)
    _CONFIG = load_config(ROOT / "config" / config_file)
    _CONFIG.sim.render = False
    _CONFIG.env.control_mode = "attitude"
    _CONTROLLER = load_controller(ROOT / "lsy_drone_racing/control/mpccpp.py")
    _ENV = JaxToNumpy(
        gymnasium.make(
            _CONFIG.env.id,
            freq=_CONFIG.env.freq,
            sim_config=_CONFIG.sim,
            sensor_range=_CONFIG.env.sensor_range,
            control_mode="attitude",
            track=_CONFIG.env.track,
            disturbances=_CONFIG.env.get("disturbances"),
            randomizations=_CONFIG.env.get("randomizations"),
            seed=0,
        )
    )


def _race(task: tuple[dict, int]) -> dict:
    """Race one episode with the given settings on the track generated by seed."""
    params, seed = task
    _CONFIG.controller["mpccpp"] = params
    obs, info = _ENV.reset(seed=seed)
    controller = _CONTROLLER(obs, info, _CONFIG)
    steps, max_steps = 0, int(TIMEOUT * _CONFIG.env.freq)
    while steps < max_steps:
        action = controller.compute_control(obs, info)
        obs, reward, terminated, truncated, info = _ENV.step(action)
        controller.step_callback(action, obs, reward, terminated, truncated, info)
        steps += 1
        if terminated or truncated:
            break
    gates = int(obs["n_gates_passed"])
    finished = gates == len(obs["gate_sequence"])
    return {
        "seed": seed,
        "finished": bool(finished),
        "time": steps / _CONFIG.env.freq,
        "gates": gates,
        "solver_failure_rate": controller.solver_failures / max(steps, 1),
    }


# Scoring of crashed races and of low success rates. Set by main().
SCORING = {"fail_time": 10.0, "gate_credit": 0.5, "min_success": 0.0, "success_penalty": 0.0}


def evaluate(pool: mp.pool.Pool, candidates: list[dict], seeds: list[int]) -> list[dict]:
    """Race all candidates on the same seeds in parallel and compute their rewards.

    A finished race scores its lap time, a crash a fixed time minus a small credit per passed gate.
    The crash time sets the trade-off between speed and reliability. Below the minimum success rate
    an additional penalty applies.
    """
    tasks = [(c, s) for c in candidates for s in seeds]
    races = pool.map(_race, tasks, chunksize=1)
    results = []
    for i, params in enumerate(candidates):
        r = races[i * len(seeds) : (i + 1) * len(seeds)]
        sc = SCORING
        scores = [
            x["time"] if x["finished"] else sc["fail_time"] - sc["gate_credit"] * x["gates"]
            for x in r
        ]
        success = np.mean([x["finished"] for x in r])
        score = np.mean(scores) + sc["success_penalty"] * max(sc["min_success"] - success, 0.0)
        fail_rate = np.mean([x["solver_failure_rate"] for x in r])
        times = [x["time"] for x in r if x["finished"]]
        results.append(
            {
                "params": params,
                "reward": float(-score - SOLVER_FAIL_PENALTY * fail_rate),
                "success_rate": float(success),
                "mean_time": float(np.mean(times)) if times else None,
                "races": r,
            }
        )
    return results


# region Gaussian process


class GP:
    """Gaussian process with an ARD Matern-5/2 kernel, fitted by maximizing the marginal likelihood.

    Hyperparameter bounds follow the TuRBO reference implementation.
    """

    def __init__(self, dim: int):
        """Initialize the hyperparameters."""
        self.log_ls = np.full(dim, np.log(0.5))
        self.log_sf2 = 0.0
        self.log_sn2 = np.log(0.1)

    @staticmethod
    def _kernel(a: np.ndarray, b: np.ndarray, log_ls: np.ndarray, log_sf2: float) -> np.ndarray:
        d = np.sqrt(np.sum(((a[:, None] - b[None]) / np.exp(log_ls)) ** 2, axis=-1) + 1e-12)
        r = np.sqrt(5.0) * d
        return np.exp(log_sf2) * (1 + r + r**2 / 3) * np.exp(-r)

    def _nll(self, theta: np.ndarray) -> float:
        d = self.X.shape[1]
        K = self._kernel(self.X, self.X, theta[:d], theta[d])
        K[np.diag_indices_from(K)] += np.exp(theta[d + 1]) + 1e-6
        try:
            c = cho_factor(K, lower=True)
        except np.linalg.LinAlgError:
            return 1e10
        alpha = cho_solve(c, self.y)
        return 0.5 * self.y @ alpha + np.sum(np.log(np.diag(c[0])))

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Standardize the targets and optimize the hyperparameters."""
        self.X = X
        self.y_mean, self.y_std = y.mean(), max(y.std(), 1e-6)
        self.y = (y - self.y_mean) / self.y_std
        d = X.shape[1]
        bounds = [(np.log(0.005), np.log(2.0))] * d + [(np.log(0.05), np.log(20.0))]
        bounds += [(np.log(1e-3), np.log(1.0))]  # The race outcomes are noisy
        best = None
        starts = [np.concatenate((self.log_ls, [self.log_sf2, self.log_sn2]))]
        starts.append(np.concatenate((np.full(d, np.log(0.5)), [0.0, np.log(0.1)])))
        for x0 in starts:
            res = minimize(self._nll, x0, method="L-BFGS-B", bounds=bounds)
            if best is None or res.fun < best.fun:
                best = res
        self.log_ls, self.log_sf2, self.log_sn2 = best.x[:d], best.x[d], best.x[d + 1]
        K = self._kernel(X, X, self.log_ls, self.log_sf2)
        K[np.diag_indices_from(K)] += np.exp(self.log_sn2) + 1e-6
        self._chol = cho_factor(K, lower=True)
        self._alpha = cho_solve(self._chol, self.y)

    def predict(self, Xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior mean and standard deviation of the latent function."""
        Ks = self._kernel(Xs, self.X, self.log_ls, self.log_sf2)
        mu = Ks @ self._alpha
        v = cho_solve(self._chol, Ks.T)
        var = np.maximum(np.exp(self.log_sf2) - np.sum(Ks * v.T, axis=1), 1e-12)
        return mu * self.y_std + self.y_mean, np.sqrt(var) * self.y_std

    @property
    def lengthscales(self) -> np.ndarray:
        """ARD lengthscales in the unit cube."""
        return np.exp(self.log_ls)


# region TuRBO


class TrustRegion:
    """State of one local optimization of TuRBO-m."""

    LENGTH_INIT, LENGTH_MIN, LENGTH_MAX = 0.8, 0.5**7, 1.6
    SUCCESS_TOLERANCE = 3

    def __init__(self, dim: int, center: np.ndarray, best: float):
        """Start a trust region at a point with a known reward."""
        self.dim = dim
        self.length = self.LENGTH_INIT
        self.failure_tolerance = max(4, dim)
        self.successes = self.failures = 0
        self.center, self.best = center, best

    def update(self, x: np.ndarray, reward: float):
        """Grow after repeated improvements, shrink after repeated failures."""
        if reward > self.best + 1e-3 * abs(self.best):
            self.successes, self.failures = self.successes + 1, 0
            self.center, self.best = x, reward
        else:
            self.successes, self.failures = 0, self.failures + 1
        if self.successes == self.SUCCESS_TOLERANCE:
            self.length, self.successes = min(2 * self.length, self.LENGTH_MAX), 0
        elif self.failures == self.failure_tolerance:
            self.length, self.failures = self.length / 2, 0

    @property
    def collapsed(self) -> bool:
        """True if the region has shrunk below its minimum size and should restart."""
        return self.length < self.LENGTH_MIN


def propose(
    tr: TrustRegion, X: np.ndarray, y: np.ndarray, beta: float, rng: np.random.Generator
) -> np.ndarray:
    """Propose the candidate with the highest UCB inside the trust region."""
    # Local model: the observations closest to the center of the trust region
    n_local = min(len(X), max(4 * tr.dim, 40))
    idx = np.argsort(np.linalg.norm(X - tr.center, axis=1))[:n_local]
    gp = GP(tr.dim)
    gp.fit(X[idx], y[idx])
    # The region is stretched along dimensions with long lengthscales, i.e. where the reward
    # changes slowly, with a volume equal to that of a cube of side length L
    w = gp.lengthscales / np.exp(np.mean(np.log(gp.lengthscales)))
    low = np.clip(tr.center - w * tr.length / 2, 0.0, 1.0)
    high = np.clip(tr.center + w * tr.length / 2, 0.0, 1.0)
    sobol = qmc.Sobol(tr.dim, seed=rng.integers(1 << 31)).random(2048)
    candidates = low + (high - low) * sobol
    mu, sigma = gp.predict(candidates)
    return candidates[np.argmax(mu + beta * sigma)]


def main(
    budget: int = 200,
    trust_regions: int = 8,
    episodes: int = 6,
    n_init: int = 20,
    workers: int = 8,
    beta: float = 2.0,
    seed: int = 0,
    config: str = "level2.toml",
    validate_top: int = 3,
    validate_episodes: int = 40,
    fail_time: float = 10.0,
    gate_credit: float = 0.5,
    min_success: float = 0.0,
    success_penalty: float = 0.0,
    racing_line: bool = False,
    unobserved_speed_max: float = 4.0,
):
    """Run TuRBO and validate the best candidates on more races.

    Args:
        budget: Number of candidate evaluations, including the initial design.
        trust_regions: Number of parallel trust regions (TuRBO-m). The paper uses 8.
        episodes: Races per candidate evaluation.
        n_init: Size of the initial Latin hypercube design. Includes the current defaults.
        workers: Parallel simulation processes.
        beta: Exploration weight of the UCB acquisition function.
        seed: Random seed of the optimizer. Race seeds are derived from it.
        config: Level config in config/. The competition uses level 2.
        validate_top: Number of best candidates to race again for validation.
        validate_episodes: Races per validated candidate.
        fail_time: Score of a crash that passed no gate, s. Lower values favor speed.
        gate_credit: Score reduction per passed gate for crashes, s.
        min_success: Success rate below which the success penalty applies.
        success_penalty: Penalty per unit of success rate below min_success, s.
        racing_line: Fly the time-optimal racing line and tune its parameters as well.
        unobserved_speed_max: Upper bound of the speed limit before unobserved gates, m/s.
    """
    global SPACE
    SPACE = [
        (name, low, unobserved_speed_max if name == "unobserved_speed" else high, log)
        for name, low, high, log in SPACE
    ]
    if racing_line:
        SPACE = SPACE + RACING_LINE_SPACE
        FIXED["racing_line"] = 1.0
    SCORING.update(
        fail_time=fail_time,
        gate_credit=gate_credit,
        min_success=min_success,
        success_penalty=success_penalty,
    )
    from lsy_drone_racing.control.mpccpp import MPCCPlusPlus

    rng = np.random.default_rng(seed)
    dim = len(SPACE)
    out = ROOT / "tuning" / f"turbo_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    out.parent.mkdir(exist_ok=True)
    next_seed = seed * 1_000_000

    def seeds(n: int) -> list[int]:
        nonlocal next_seed
        next_seed += n
        return list(range(next_seed - n, next_seed))

    X, y, log = [], [], []

    def record(results: list[dict], phase: str, batch: int):
        for r in results:
            X.append(to_unit(r["params"]))
            y.append(r["reward"])
            entry = {"phase": phase, "batch": batch, **r}
            log.append(entry)
            with out.open("a") as f:
                f.write(json.dumps(entry) + "\n")

    def report(results: list[dict], phase: str):
        best = max(y)
        for r in results:
            t = f"{r['mean_time']:.2f}s" if r["mean_time"] else "  -  "
            print(
                f"  {phase}: reward {r['reward']:7.3f}  success {r['success_rate']:4.0%}  time {t}"
            )
        print(f"  evaluations {len(y)}/{budget}, best reward so far {best:.3f}", flush=True)

    ctx = mp.get_context("spawn")  # JAX does not support fork
    with ctx.Pool(workers, initializer=_init_worker, initargs=(config,)) as pool:
        # Initial design: the current defaults and a Latin hypercube
        defaults = {k: MPCCPlusPlus.SETTINGS[k] for k, *_ in SPACE}
        seeds_ = [{**defaults, **p} for p in SEED_POINTS]
        if racing_line:  # The fastest racing line configuration so far: no speed limit at gates
            seeds_.append({**defaults, "unobserved_speed": unobserved_speed_max})
        init = [to_unit(defaults)] + [to_unit(p) for p in seeds_]
        init += list(qmc.LatinHypercube(dim, seed=seed).random(n_init - len(init)))
        print(f"Initial design: {n_init} candidates x {episodes} races, logging to {out}")
        for i in range(0, n_init, trust_regions):
            batch = init[i : i + trust_regions]
            results = evaluate(pool, [to_params(u) for u in batch], seeds(episodes))
            record(results, "init", i // trust_regions)
            report(results, "init")

        # Start the trust regions at the best initial points
        order = np.argsort(y)[::-1]
        regions = [TrustRegion(dim, X[i], y[i]) for i in order[:trust_regions]]
        batch_idx = 0
        while len(y) < budget:
            batch_idx += 1
            Xa, ya = np.array(X), np.array(y)
            proposals = []
            for i, tr in enumerate(regions):
                if tr.collapsed:  # Restart at a random point
                    regions[i] = TrustRegion(dim, rng.random(dim), -np.inf)
                    proposals.append(regions[i].center)
                else:
                    proposals.append(propose(tr, Xa, ya, beta, rng))
            results = evaluate(pool, [to_params(u) for u in proposals], seeds(episodes))
            record(results, "turbo", batch_idx)
            for tr, u, r in zip(regions, proposals, results):
                tr.update(u, r["reward"])
            print(
                f"Batch {batch_idx}, trust region lengths {[round(t.length, 3) for t in regions]}"
            )
            report(results, "turbo")

        # A single evaluation is noisy. Pick the candidates by the GP posterior mean and race them
        # again on many new tracks.
        Xa, ya = np.array(X), np.array(y)
        gp = GP(dim)
        gp.fit(Xa, ya)
        mu, _ = gp.predict(Xa)
        top = np.argsort(mu)[::-1][:validate_top]
        candidates = [log[i]["params"] for i in top]
        print(f"Validating the {validate_top} best candidates on {validate_episodes} races each")
        results = evaluate(pool, candidates, seeds(validate_episodes))
        for r in results:
            with out.open("a") as f:
                f.write(json.dumps({"phase": "validation", **r}) + "\n")
        report_lines = sorted(results, key=lambda r: r["reward"], reverse=True)
        for r in report_lines:
            t = f"{r['mean_time']:.3f}s" if r["mean_time"] else "-"
            print(f"reward {r['reward']:.3f}, success {r['success_rate']:.0%}, mean time {t}")
            print("  " + json.dumps({k: round(v, 5) for k, v in r["params"].items()}))
    print(f"Full log: {out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    fire.Fire(main)

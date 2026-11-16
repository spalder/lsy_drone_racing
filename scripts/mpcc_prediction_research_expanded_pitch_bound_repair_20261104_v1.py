"""Fresh research runner over the campaign environment and compact observer.

Never edits/resumes a campaign batch. Each case runs in a fresh process and
generated directory, under the existing simulation lock. See the v1 runbook.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v1 as research
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "logs/mpcc-campaign/departure-speed-20261104-v1"
PREP = ROOT / "logs/mpcc-preparation/harnesses-20261103T233438Z-v1"
CHECKOUT = ROOT / ".local/mpcc-study/broad-20261103T152500Z-r2/checkout"
CONFIGS = ROOT / "config/research/mpcc_prediction_v1/expanded-pitch-demand-20261104-v1"
CONTROL = ROOT / "lsy_drone_racing/control"
IDENTITY = "lsy_drone_racing.control.mpcc_prediction_core.MPCCPredictionCore"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    if name in sys.modules:
        value = sys.modules[name]
        if Path(value.__file__).resolve() != Path(path).resolve():
            raise ValueError("Unexpected cached module: " + name)
        return value
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def load_core():
    # Preserve the actual campaign environment, geometry and base model imports.
    # Only these three controller modules come from the new research version.
    sys.path.insert(0, str(CHECKOUT))
    import lsy_drone_racing

    if Path(lsy_drone_racing.__file__).resolve() != CHECKOUT / "lsy_drone_racing/__init__.py":
        raise ValueError("Run this harness in a fresh process; campaign package origin differs")
    for name in ("mpcc_prediction_model", "mpcc_prediction_solver", "mpcc_prediction_core"):
        value = module("lsy_drone_racing.control." + name, CONTROL / (name + ".py"))
    return value


def validate_case(settings, core):
    if set(settings) != {"mpcc", "mpcc_experiment", "prediction", "numerics"}:
        raise ValueError("Complete setting sections required")
    a, b = core.validated_settings(settings["mpcc"], settings["mpcc_experiment"])
    if a != settings["mpcc"] or b != settings["mpcc_experiment"]:
        raise ValueError("Racing settings changed")
    if core.validate_prediction(settings["prediction"]) != settings["prediction"]:
        raise ValueError("Incomplete prediction settings")
    if core.validate_numerics(settings["numerics"]) != settings["numerics"]:
        raise ValueError("Incomplete numerical settings")
    core.ThrustGainFilter(settings["prediction"], settings["mpcc"], 0.02)


def effective(controller, requested):
    actual = dict(
        mpcc=dict(controller.settings),
        mpcc_experiment={k: getattr(controller, k) for k in requested["mpcc_experiment"]},
        prediction=dict(controller.prediction_settings),
        numerics={k: getattr(controller._ocp.solver_options, k) for k in requested["numerics"]},
    )
    if (
        actual != requested
        or type(controller).__module__ + "." + type(controller).__name__ != IDENTITY
    ):
        raise ValueError("Constructed controller/settings differ from request")
    return actual


def verify(plan, *, fingerprints=True):
    if fingerprints:
        for path, expected in plan["hashes"].items():
            if sha(path) != expected:
                raise ValueError("Fingerprint changed: " + path)
    if plan["controller"] != IDENTITY or plan["case_order"] != list(plan["cases"]):
        raise ValueError("Controller/order mismatch")
    seeds = plan["seeds"]
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(type(s) is not int or not 0 <= s < 2**31 for s in seeds)
    ):
        raise ValueError("Invalid seeds")
    minimum = {"smoke": 1, "screen": 30, "confirmation": 100}[plan["stage"]]
    if len(seeds) < minimum:
        raise ValueError("Cohort too small")
    if not set(plan["prediction_seeds"]) <= set(seeds) or len(set(plan["prediction_seeds"])) != len(
        plan["prediction_seeds"]
    ):
        raise ValueError("Prediction diagnostics must be preselected from cohort")
    if plan["policy"] != read(CAMPAIGN / "research-policy-20261104-v2.json"):
        raise ValueError("Evaluation policy differs")
    assert plan["formulations"] == {k: research.formulation(k) for k in plan["cases"]}
    core = load_core()
    parent = read(plan["parent_source"])
    baseline = dict(
        mpcc=parent["mpcc"],
        mpcc_experiment=parent["mpcc_experiment"],
        prediction=core.validate_prediction(),
        numerics=core.validate_numerics(
            read(plan["numerics_source"]) if plan["numerics_source"] else parent.get("numerics")
        ),
    )
    if (not plan.get("diagnostic_only") and plan["case_order"][0] != "baseline_hard") or baseline["mpcc"]["adaptation_rate"] != 2.0:
        raise ValueError("Expected unmodified-model EMA2 baseline first")
    definitions = read(CONFIGS / "cases.json")
    for name, settings in plan["cases"].items():
        validate_case(settings, core)
        reconstructed = copy.deepcopy(baseline)
        for section, overrides in definitions[name].items():
            reconstructed[section].update(overrides)
        if settings != reconstructed:
            raise ValueError("Case differs from supplied parent and declared changes: " + name)
    if plan["environment_config"] != str(CHECKOUT / "config/level2.toml"):
        raise ValueError("Campaign environment config changed")


def prepare(args):
    core = load_core()
    parent = read(args.parent)
    # A complete racing parent, including geometry; no inherited feature toggles.
    if set(parent) - {"mpcc", "mpcc_experiment", "numerics"}:
        raise ValueError("Parent supplies racing settings and optional numerics only")
    baseline = dict(
        mpcc=parent["mpcc"],
        mpcc_experiment=parent["mpcc_experiment"],
        prediction=core.validate_prediction(),
        numerics=core.validate_numerics(
            read(args.numerics) if args.numerics else parent.get("numerics")
        ),
    )
    if baseline["mpcc"]["adaptation_rate"] != 2.0:
        raise ValueError("Baseline requires EMA rate 2")
    definitions = read(CONFIGS / "cases.json")
    selected = args.cases.split(",") if args.cases else list(definitions)
    if "baseline_hard" not in selected:
        selected.insert(0, "baseline_hard")
    if selected[0] != "baseline_hard" or len(set(selected)) != len(selected):
        raise ValueError("Baseline must be first; duplicate case")
    cases = {}
    for name in selected:
        settings = copy.deepcopy(baseline)
        for section, overrides in definitions[name].items():
            settings[section].update(overrides)
        validate_case(settings, core)
        cases[name] = settings
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))
    # Historical campaign cohorts must not be reused as a fresh research cohort.
    historical = {s for p in CAMPAIGN.glob("batch-*/plan.json") for s in read(p)["seeds"]}
    if historical.intersection(seeds):
        raise ValueError("Seeds overlap completed campaign")
    screen_path = None
    if args.stage == "confirmation":
        if not args.screen or len(cases) != 2:
            raise ValueError(
                "Confirmation requires --screen and one frozen candidate plus baseline"
            )
        screen_path = Path(args.screen).resolve() / "plan.json"
        screen = read(screen_path)
        verify(screen)
        if read(screen_path.parent / "analysis-v1/audit.json")["status"] != "passed":
            raise ValueError("Screen must have completed and passed its audit")
        if screen["stage"] != "screen" or set(seeds).intersection(screen["seeds"]):
            raise ValueError("Confirmation must be fresh relative to the screen")
        if any(settings != screen["cases"].get(name) for name, settings in cases.items()):
            raise ValueError("Confirmation must use the exact screened configurations")
    # Reuse frozen runtime pins rather than silently accepting changed dependencies.
    historical_hashes = read(CAMPAIGN / "batch-004/plan.json")["hashes"]
    hashes = {
        p: h
        for p, h in historical_hashes.items()
        if any(part in p for part in (str(CHECKOUT), "/.pixi/", "/acados/"))
    }
    paths = [
        Path(__file__),
        Path(research.__file__),
        Path(__file__).with_name("autonomous_expanded_pitch_bound_repair_20261104_v1.py"),
        Path(__file__).with_name("analyze_expanded_pitch_bound_repair_20261104_v1.py"),
        Path(__file__).with_name("mpcc_prediction_diagnostics.py"),
        Path(args.parent).resolve(),
        CONFIGS / "cases.json",
        CAMPAIGN / "research-policy-20261104-v2.json",
        CAMPAIGN / "analyze-pressure-v1.py",
        PREP / "departure-v1/harness.py",
        PREP / "coordinate-v1/diagnostics.py",
        PREP / "coordinate-v1/audit.py",
    ]
    paths += [CAMPAIGN / "logging-v5" / name for name in ("compact.py", "audit.py")]
    paths += [
        CONTROL / (name + ".py")
        for name in ("mpcc_prediction_core", "mpcc_prediction_model", "mpcc_prediction_solver")
    ]
    if args.numerics:
        paths.append(Path(args.numerics).resolve())
    if screen_path:
        paths.append(screen_path)
    hashes.update({str(p): sha(p) for p in paths})
    plan = dict(
        schema_version=1,
        controller=IDENTITY,
        stage=args.stage,
        parent_source=str(Path(args.parent).resolve()),
        numerics_source=str(Path(args.numerics).resolve()) if args.numerics else None,
        confirmation_of=str(screen_path) if screen_path else None,
        cases=cases,
        case_order=list(cases),
        seeds=seeds,
        prediction_seeds=[int(x) for x in args.prediction_seeds.split(",") if x],
        policy=read(CAMPAIGN / "research-policy-20261104-v2.json"),
        hashes=hashes,
        environment_config=str(CHECKOUT / "config/level2.toml"),
    )
    plan.update(formulations={k:research.formulation(k) for k in cases},logging=research.LOGGING,segments=research.SEGMENTS,analysis=research.ANALYSIS,eligibility=research.ELIGIBILITY)
    verify(plan)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / "plan.json", plan)
    return dict(
        status="prepared",
        batch=str(output),
        episodes=len(seeds) * len(cases),
        plan_sha256=sha(output / "plan.json"),
    )


def worker(request_path, output):
    import numpy as np

    worker_start = time.monotonic()
    request = read(request_path)
    if sha(request["plan"]) != request["plan_sha256"]:
        raise ValueError("Request/plan mismatch")
    plan = read(request["plan"])
    verify(plan)
    core = load_core()
    # Exact campaign environment and compact observer, explicitly selected core.
    import gymnasium
    from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
    from lsy_drone_racing.utils import load_config

    shared = module("prediction_shared_diagnostics", PREP / "coordinate-v1/diagnostics.py")
    compact = module("prediction_compact", CAMPAIGN / "logging-v5/compact.py")
    Recorder = compact.recorder_class(shared.DiagnosticRecorder)
    prediction = module(
        "prediction_diagnostics", Path(__file__).with_name("mpcc_prediction_diagnostics.py")
    )
    settings = plan["cases"][request["case"]]
    config = load_config(Path(plan["environment_config"]))
    config.sim.render = False
    if config.env.freq != 50 or config.env.control_mode != "attitude":
        raise ValueError("Expected 50 Hz attitude environment")
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    generated = out / "generated"
    generated.mkdir()
    os.chdir(generated)
    research.install(core, settings, plan, request["case"], out)
    env = JaxToNumpy(
        gymnasium.make(
            config.env.id,
            freq=config.env.freq,
            sim_config=config.sim,
            sensor_range=config.env.sensor_range,
            control_mode=config.env.control_mode,
            track=config.env.track,
            disturbances=config.env.get("disturbances"),
            randomizations=config.env.get("randomizations"),
            seed=plan["seeds"][0],
        )
    )
    if env.unwrapped.settings.max_episode_steps != 1500:
        env.close()
        raise ValueError("Expected 1500-step episode limit")
    rows = []
    retained = []
    try:
        for index, seed in enumerate(plan["seeds"]):
            obs, info = env.reset(seed=seed)
            research.EPISODE_SEED = seed
            episode_start=time.monotonic()
            controller = core.MPCCPredictionCore(
                obs,
                info,
                config,
                settings=settings["mpcc"],
                geometry=settings["mpcc_experiment"],
                prediction=settings["prediction"],
                numerics=settings["numerics"],
            )
            constructed=time.monotonic()
            controller._research_seed=seed
            controller._research_rich=(seed in plan["prediction_seeds"])
            controller._research_tick_records=[]
            step_walls=[]
            actual = effective(controller, settings)
            runtime = research.inspect_runtime(controller, obs, construction=True)
            write(out / f'runtime-seed-{seed}.json', runtime)
            if plan.get('construction_only'):
                rows.append(dict(seed=seed, requested_settings=settings, effective_settings=actual,
                                 runtime=runtime, construction_s=constructed-episode_start))
                write(out / 'constructions.json', rows)
                # Deliberately keep all instances alive to exercise loader identity.
                retained.append(controller)
                continue
            recorder = Recorder(controller)
            recorder.capture_initial(obs)
            predictor = (
                prediction.PredictionRecorder(controller, actual)
                if seed in plan["prediction_seeds"]
                else None
            )
            initial_state = {
                k: np.asarray(obs[k]).tolist() for k in ("pos", "quat", "vel", "ang_vel")
            }
            durations = []
            for step in range(1500):
                step_start=time.monotonic()
                recorder.before_control(obs)
                before = time.perf_counter_ns()
                action = controller.compute_control(obs, info)
                duration = (time.perf_counter_ns() - before) / 1e6
                durations.append(duration)
                if not np.isfinite(action).all():
                    raise ValueError("Nonfinite action")
                recorder.after_control(obs, action, duration_ms=duration)
                if predictor:
                    predictor.before_action(obs, action)
                obs, reward, terminated, truncated, info = env.step(action)
                if predictor:
                    predictor.after_step(obs)
                finished = controller.step_callback(
                    action, obs, reward, terminated, truncated, info
                )
                step_walls.append(time.monotonic()-step_start)
                if finished or terminated or truncated:
                    break
            episode_end=time.monotonic()
            controller.episode_callback()
            episode_dir = out / f"episode-{index:03d}"
            path = recorder.write(episode_dir)
            research.export(controller, episode_dir, seed)
            # Extend metadata only; keep shared geometry/tick arithmetic untouched.
            with gzip.open(path, "rt") as stream:
                value = json.load(stream)
            value["requested_settings"] = settings
            value["effective_settings"] = actual
            with gzip.open(path, "wt", compresslevel=1) as stream:
                json.dump(value, stream, allow_nan=False, separators=(",", ":"))
            summary = predictor.write(episode_dir) if predictor else None
            rows.append(
                dict(
                    seed=seed,
                    research_runtime=dict(worker_to_first_episode_s=episode_start-worker_start if index==0 else 0.,construction_s=constructed-episode_start,episode_s=episode_end-episode_start,step_walls_s=step_walls),
                    steps=step + 1,
                    gates_passed=int(obs["n_gates_passed"]),
                    success=int(obs["n_gates_passed"]) == 5,
                    requested_settings=settings,
                    effective_settings=actual,
                    solver_options={
                        key: getattr(controller._ocp.solver_options, key)
                        for key in (
                            *settings["numerics"],
                            "N_horizon",
                            "qp_solver_cond_N",
                            "qp_solver_iter_max",
                            "integrator_type",
                            "nlp_solver_type",
                        )
                    },
                    initial_state=initial_state,
                    prediction_summary=summary,
                    compute_durations_ms=durations,
                    controller_class=IDENTITY,
                    controller_source=str(CONTROL / "mpcc_prediction_core.py"),
                )
            )
            controller.episode_reset()
            write(out / "episodes.json", rows)
    finally:
        env.close()
    write(
        out / "generated-sha256.json",
        {str(p.relative_to(generated)): sha(p) for p in generated.rglob("*") if p.is_file()},
    )


def run(batch):
    batch = Path(batch).resolve()
    plan_path = batch / "plan.json"
    plan = read(plan_path)
    verify(plan)
    lock_path = ROOT / "logs/mpcc-tuning/.combination.lock"
    with lock_path.open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        verify(plan)
        out = batch / "run-v1"
        out.mkdir(exist_ok=False)
        write(
            out / "execution-manifest.json",
            dict(
                plan_sha256=sha(plan_path),
                controller=IDENTITY,
                case_order=plan["case_order"],
                seeds=plan["seeds"],
                prediction_seeds=plan["prediction_seeds"],
                lock=str(lock_path),
                runtime={
                    k: os.environ.get(k)
                    for k in (
                        "ACADOS_SOURCE_DIR",
                        "LD_LIBRARY_PATH",
                        "SCIPY_ARRAY_API",
                        "OMP_NUM_THREADS",
                        "XLA_FLAGS",
                    )
                },
            ),
        )
        for name in plan["case_order"]:
            request = out / (name + "-request.json")
            write(request, dict(plan=str(plan_path), plan_sha256=sha(plan_path), case=name))
            with (out / (name + "-console.log")).open("x") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "_worker",
                        str(request),
                        str(out / name),
                    ],
                    check=True,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
        write(
            batch / "execution-completed.json",
            dict(episodes=0 if plan.get("construction_only") else len(plan["seeds"]) * len(plan["cases"]), constructions=len(plan["seeds"]) * len(plan["cases"])),
        )
    return dict(status="completed", batch=str(batch))


def analyze(batch):
    """Audit settings, artifacts, alignment and unchanged numerical-health rules."""
    import numpy as np
    from scipy.spatial.transform import Rotation
    from scipy.stats import beta

    batch = Path(batch).resolve()
    plan = read(batch / "plan.json")
    verify(plan)
    out = batch / "run-v1"
    manifest = read(out / "execution-manifest.json")
    if (
        manifest["plan_sha256"] != sha(batch / "plan.json")
        or manifest["seeds"] != plan["seeds"]
        or manifest["case_order"] != plan["case_order"]
        or manifest["controller"] != IDENTITY
        or not (batch / "execution-completed.json").exists()
    ):
        raise ValueError("Incomplete execution or manifest mismatch")
    audit = module("prediction_compact_audit", CAMPAIGN / "logging-v5/audit.py")
    pairing = module("prediction_pairing", CAMPAIGN / "analyze-pressure-v1.py")
    rows, statistics, initial = {}, {}, {}
    summaries = {}
    for name in plan["case_order"]:
        case = out / name
        records = read(case / "episodes.json")
        expected = plan["cases"][name]
        if [r["seed"] for r in records] != plan["seeds"]:
            raise ValueError("Seed cohort mismatch")
        for file, digest in read(case / "generated-sha256.json").items():
            if sha(case / "generated" / file) != digest:
                raise ValueError("Generated artifact mismatch")
        # Audit the actual generated backend options, not only the requested dict.
        generated_ocp = read(sorted((case / "generated").rglob("ocp.json"))[-1])
        for key, value in expected["numerics"].items():
            if generated_ocp["solver_options"][key] != value:
                raise ValueError("Generated solver option differs: " + key)
        case_predictions = []
        endings = {}
        for i, row in enumerate(records):
            if (
                row["requested_settings"] != expected
                or row["effective_settings"] != expected
                or row["controller_class"] != IDENTITY
            ):
                raise ValueError("Requested/effective settings or identity mismatch")
            expected_options = dict(
                expected["numerics"],
                N_horizon=expected["mpcc"]["horizon_steps"],
                qp_solver_cond_N=expected["mpcc"]["condensing_length"],
                qp_solver_iter_max=expected["mpcc"]["qp_iterations"],
                integrator_type="DISCRETE",
                nlp_solver_type="SQP_RTI",
            )
            if row["solver_options"] != expected_options:
                raise ValueError("Effective solver options differ")
            value = audit.read_episode(case / f"episode-{i:03d}")
            if value["requested_settings"] != expected:
                raise ValueError("Diagnostic request differs")
            ticks = value["tick_records"]
            observed = dict(
                state=row["initial_state"], gate_poses=value["geometry_records"][0]["gate_poses"]
            )
            if name == "baseline_hard":
                initial[row["seed"]] = observed
            elif initial[row["seed"]] != observed:
                raise ValueError("Matched initial observations differ")
            if not row["success"]:
                occurrence = str(ticks[-1]["required_gate_occurrence"])
                endings[occurrence] = endings.get(occurrence, 0) + 1
            path = case / f"episode-{i:03d}/prediction.json.gz"
            if path.exists() != (row["seed"] in plan["prediction_seeds"]):
                raise ValueError("Prediction subset differs from plan")
            if path.exists():
                with gzip.open(path, "rt") as stream:
                    predictions = json.load(stream)
                if (
                    predictions["effective_settings"] != expected
                    or len(predictions["ticks"]) != row["steps"]
                ):
                    raise ValueError("Prediction settings/length mismatch")
                for j, pred in enumerate(predictions["ticks"]):
                    if (
                        pred["tick"] != j
                        or pred["applied_command"] != ticks[j]["command"]
                        or pred["pre_action"]["pos"] != ticks[j]["observation_position_m"]
                    ):
                        raise ValueError("Prediction/action alignment mismatch")
                    if (
                        j + 1 < row["steps"]
                        and pred["next_observation"] != predictions["ticks"][j + 1]["pre_action"]
                    ):
                        raise ValueError("Prediction/next observation misaligned")
                    x = np.asarray(pred["predicted_next_state"], dtype=float)
                    if np.isfinite(x).all():
                        actual = pred["next_observation"]
                        velocity = float(np.linalg.norm(x[6:9] - actual["vel"]))
                        attitude = float(
                            (
                                Rotation.from_euler("xyz", x[3:6]).inv()
                                * Rotation.from_quat(actual["quat"])
                            ).magnitude()
                        )
                        if not np.allclose(
                            [velocity, attitude], list(pred["one_step_error"].values()), atol=1e-12
                        ):
                            raise ValueError("Prediction error arithmetic differs")
                case_predictions.append(predictions["summary"])
        health = audit.audit_case(case)
        n, k = len(records), health["finishes"]
        successful = [r["steps"] / 50 for r in records if r["success"]]
        statistics[name] = dict(
            health,
            n=n,
            completion=k / n,
            completion_exact95=[
                float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0,
                float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0,
            ],
            successful_mean_s=float(np.mean(successful)) if successful else None,
            penalized_mean_s=float(
                np.mean([r["steps"] / 50 if r["success"] else 30 for r in records])
            ),
            failed_required_occurrences=endings,
            meets_completion_and_numerical_floor=(
                plan["stage"] != "smoke" and k / n >= 0.4 and health["numerical_ticks"] == 0
            ),
            latency_role="advisory",
        )
        summaries[name] = case_predictions
        rows[name] = records
    pairs = {
        name: pairing.pair(rows["baseline_hard"], records)
        for name, records in rows.items()
        if name != "baseline_hard"
    }
    report = batch / "analysis-v1"
    report.mkdir(exist_ok=False)
    write(report / "statistics.json", statistics)
    write(report / "pairwise-vs-baseline.json", pairs)
    write(report / "prediction-summaries.json", summaries)
    result = dict(
        status="passed",
        stage=plan["stage"],
        episodes=sum(len(r) for r in rows.values()),
        policy=plan["policy"],
        limitations=[
            "Smoke only verifies plumbing; no performance or numerical repair established.",
            "Promotion requires worthwhile paired speed evidence and fresh confirmation; no automatic winner.",
            "The default fast parent has adverse historical numerical results; this cohort cannot erase them.",
            "Prediction residuals are separate from racing benefits; covariance is exploratory.",
        ],
    )
    write(report / "audit.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--output", required=True)
    prep.add_argument("--parent", default=str(CONFIGS / "parent-fast.json"))
    prep.add_argument("--numerics")
    prep.add_argument("--stage", choices=("smoke", "screen", "confirmation"), required=True)
    prep.add_argument("--seed-start", type=int, required=True)
    prep.add_argument("--seed-count", type=int, required=True)
    prep.add_argument("--prediction-seeds", default="")
    prep.add_argument("--cases")
    prep.add_argument("--screen")
    sub.add_parser("run").add_argument("batch")
    sub.add_parser("analyze").add_argument("batch")
    internal = sub.add_parser("_worker")
    internal.add_argument("request")
    internal.add_argument("output")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args)
    elif args.command == "run":
        result = run(args.batch)
    elif args.command == "analyze":
        result = analyze(args.batch)
    else:
        result = worker(args.request, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

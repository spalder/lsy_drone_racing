"""Local-only verification for the pinned v2 submission; never submitted."""

# ruff: noqa: ANN001, ANN201, D103, E501
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path

BASE = "c8e180920e99893b92fed27317c6285b84e8bda0"
ALLOW = (
    "config/level2.toml",
    "lsy_drone_racing/control/attitude_mpcc_v2.py",
    "lsy_drone_racing/control/mpcc_v2_solver.py",
)
LOCAL = Path(__file__).resolve().parents[1]
EVIDENCE = LOCAL / "logs/mpcc-compliance-v2-20261104"
OFFICIAL = LOCAL / ".local/mpcc-study/broad-20261103T152500Z-r2/baseline.json"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, v):
    Path(p).write_text(json.dumps(v, indent=2, allow_nan=False) + "\n")


def verify_tree(root):
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(root), *args])

    assert git("rev-parse", "HEAD").decode().strip() == BASE
    assert git("branch", "--show-current").decode().strip() == "submission/mpcc-v2-compliance"
    assert not git("diff", "--cached")
    baseline = {}
    for rel in git("ls-tree", "-r", "--name-only", BASE).decode().splitlines():
        b = git("show", BASE + ":" + rel)
        baseline[rel] = hashlib.sha256(b).hexdigest()
        if rel not in ALLOW:
            assert (root / rel).read_bytes() == b, rel
    extras = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    assert not set(extras) - set(ALLOW), extras
    official = json.loads(OFFICIAL.read_text())
    deviations = {}
    for rel, h in official.items():
        if rel == "config/level2.toml":
            continue
        actual = sha(root / rel)
        if actual != h:
            assert rel in {
                "config/level0.toml",
                "tools/setup_acados.sh",
                "lsy_drone_racing/control/state_controller.py",
                "lsy_drone_racing/control/attitude_mpc.py",
            }, rel
            deviations[rel] = dict(official=h, inherited_fork=actual)
    old = (
        (LOCAL / "logs/mpcc-compliance-20261103/official/main/config/level2.toml")
        .read_text()
        .splitlines()
    )
    new = (root / "config/level2.toml").read_text().splitlines()
    assert len(old) == len(new) and all(
        a == b for i, (a, b) in enumerate(zip(old, new)) if i not in (6, 47)
    )
    assert not (root / "lsy_drone_racing/envs/mjx_compat.py").exists()
    project_imports = {}
    for rel in ALLOW:
        if not rel.endswith(".py"):
            continue
        tree = ast.parse((root / rel).read_text())
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.ImportFrom)
                and n.module
                and n.module.startswith("lsy_drone_racing")
            ):
                path = n.module.replace(".", "/") + ".py"
                path = (
                    path if (root / path).is_file() else n.module.replace(".", "/") + "/__init__.py"
                )
                assert (root / path).is_file() and (path in baseline or path in ALLOW), (
                    rel,
                    n.module,
                )
                project_imports[n.module] = dict(
                    path=path,
                    sha256=sha(root / path),
                    source="allowlist" if path in ALLOW else "pinned_fork_base",
                )
    return dict(
        base=BASE,
        baseline_sha256=baseline,
        submission_sha256={p: sha(root / p) for p in ALLOW},
        project_imports=project_imports,
        inherited_official_differences=deviations,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    root = args.checkout.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    expected = json.loads((EVIDENCE / "selected-settings.json").read_text())
    request = dict(
        checkout=str(root),
        seeds=[20262181, 20262182, 20262183, 20262184, 20262185, 20262186],
        max_steps=1500,
        classification="bounded_reused_seed_packaging_smoke_not_independent_validation",
        expected_settings=expected,
        driver_sha256=sha(Path(__file__)),
        base=BASE,
        official_main="3027337d1dc8c342dac4ef7d0db80a5f7fd18179",
        python=sys.executable,
        platform=platform.platform(),
        packages={
            n: importlib.metadata.version(n)
            for n in (
                "numpy",
                "scipy",
                "jax",
                "jaxlib",
                "mujoco",
                "crazyflow",
                "gymnasium",
                "acados-template",
            )
        },
        runtime_libraries={
            str(p): sha(p)
            for p in Path(os.environ["ACADOS_SOURCE_DIR"], "lib").glob("*.so*")
            if p.is_file()
        },
    )
    request["tree"] = verify_tree(root)
    write(out / "request.json", request)
    result = dict(status="started", episodes=[])
    env = None
    try:
        os.chdir(root)
        sys.path.insert(0, str(root))
        from lsy_drone_racing.control import Controller
        from lsy_drone_racing.utils import load_config, load_controller

        config = load_config(root / "config/level2.toml")
        assert (
            config.controller.file == "attitude_mpcc_v2.py"
            and config.env.control_mode == "attitude"
        )
        cls = load_controller(root / "lsy_drone_racing/control/attitude_mpcc_v2.py")
        assert cls.__name__ == "AttitudeMPCCV2" and issubclass(cls, Controller)
        result["controller_identity"] = dict(
            module=cls.__module__, name=cls.__qualname__, file=sys.modules[cls.__module__].__file__
        )
        if args.smoke:
            # Reuse only the proven episode/callback measurement function, passing the actual loaded class.

            import gymnasium
            from gymnasium.wrappers.jax_to_numpy import JaxToNumpy

            spec = importlib.util.spec_from_file_location(
                "v1_episode_measurement", LOCAL / "scripts/verify_mpcc_submission.py"
            )
            harness = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(harness)
            config.sim.render = False
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
                    seed=request["seeds"][0],
                )
            )
            assert config.env.freq == 50 and env.unwrapped.settings.max_episode_steps == 1500
            for seed in request["seeds"]:
                e = harness.run_episode(env, cls, config, seed, 1500)
                assert e["effective_settings"] == expected
                previous = (
                    LOCAL
                    / "logs/mpcc-tuning/speed-first-20261103T222800Z/step-06/C06_v2p6_g0p162_cap"
                )
                old = next(
                    json.loads(p.read_text())
                    for p in previous.glob("episode-*.json")
                    if json.loads(p.read_text())["seed"] == seed
                )
                e["selected_research_comparison"] = {
                    k: dict(research=old[k], submission=e[k], equal=old[k] == e[k])
                    for k in ("steps", "gates_passed", "command_sha256")
                }
                result["episodes"].append(e)
                write(out / "report.json", result)
        origins = {
            n: str(Path(m.__file__).resolve())
            for n, m in list(sys.modules.items())
            if (n.startswith("lsy_drone_racing") or n == "controller")
            and getattr(m, "__file__", None)
        }
        assert all(Path(p).is_relative_to(root) for p in origins.values())
        assert not any(
            any(
                x in n
                for x in (
                    "mjx_compat",
                    "experimental",
                    ".corridor",
                    ".track_geometry",
                    "mpcc_broad",
                )
            )
            for n in origins
        )
        result.update(status="passed", module_origins=origins, final_tree=verify_tree(root))
    except BaseException:
        result.update(status="blocked", traceback=traceback.format_exc())
        write(out / "failure.json", result)
        raise
    finally:
        if env is not None:
            env.close()
        write(out / "report.json", result)


if __name__ == "__main__":
    main()

"""V3_alt preparation only: public-observation solves, with no racing episodes."""

# Test doubles and pytest fixtures use small duck-typed interfaces.
# ruff: noqa: ANN001, ANN201, ANN202
from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import types
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import attitude_mpcc_v3_alt as entry
from lsy_drone_racing.control import mpcc_v3_alt_solver as solver
from lsy_drone_racing.control.mpcc_v3_alt_settings import GEOMETRY_SETTINGS, MPCC_SETTINGS
from lsy_drone_racing.utils import load_config, load_controller

ROOT = Path(__file__).resolve().parents[3]
LOCAL = ROOT / ".local/mpcc-study/v3-alt"
FROZEN = LOCAL / "frozen-source"
PLAN = ROOT / "logs/mpcc-campaign/departure-speed-20261104-v1/batch-003/plan.json"


def load_reference():
    """Load hashed historical source; redirect only helper import names for isolation."""
    for name, filename in [
        ("_alt_reference_geometry", "mpcc_v2_geometry.py"),
        ("_alt_reference_solver", "mpcc_broad_solver.py"),
        ("_alt_reference_core", "mpcc_broad_core.py"),
    ]:
        path = FROZEN / filename
        text = (
            path.read_text()
            .replace("lsy_drone_racing.control.mpcc_v2_geometry", "_alt_reference_geometry")
            .replace("lsy_drone_racing.control.mpcc_broad_solver", "_alt_reference_solver")
        )
        module = types.ModuleType(name)
        # Keep asset resolution equivalent to the historical source's package location.
        module.__file__ = str(ROOT / "lsy_drone_racing/control" / filename)
        sys.modules[name] = module
        exec(compile(text, str(path), "exec"), module.__dict__)
    return module.MPCCBroadCore


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    """Construct two real solvers in a private directory without creating an environment."""
    config = load_config(ROOT / "config/level2.toml")
    selected = json.loads(PLAN.read_text())["cases"]["S28_D20_P9"]
    obs = dict(
        pos=np.array([-1.5, 0.75, 0.01]),
        vel=np.zeros(3),
        quat=np.array([0.0, 0.0, 0.0, 1.0]),
        ang_vel=np.zeros(3),
        n_gates_passed=np.array(0),
        gate_sequence=np.array([0, 1, 2, 3, 1]),
        gates_pos=np.array([g["pos"] for g in config.env.track.gates]),
        gates_quat=Rotation.from_euler("xyz", [g["rpy"] for g in config.env.track.gates]).as_quat(),
        obstacles_pos=np.array([o["pos"] for o in config.env.track.obstacles]),
        gates_visited=np.zeros(4, dtype=bool),
        obstacles_visited=np.zeros(4, dtype=bool),
    )
    previous = Path.cwd()
    os.chdir(tmp_path_factory.mktemp("v3-alt-solvers"))
    try:
        candidate = entry.AttitudeMPCCV3Alt(obs, {}, config)
        reference = load_reference()(
            obs, {}, config, settings=selected["mpcc"], geometry=selected["mpcc_experiment"]
        )
        yield candidate, reference, obs, config
    finally:
        os.chdir(previous)


def test_frozen_source_hashes():
    """The reference copies match the recorded original campaign hashes."""
    receipt = json.loads((LOCAL / "provenance.json").read_text())
    for path, expected in receipt["frozen_sources"].items():
        assert hashlib.sha256((FROZEN / Path(path).name).read_bytes()).hexdigest() == expected


def test_discovery():
    """The standard loader finds the uniquely named alternative controller."""
    assert load_controller(Path(entry.__file__)).__name__ == "AttitudeMPCCV3Alt"


def test_effective_settings(pair):
    """Every effective optimizer and geometry setting equals the measured case."""
    candidate, reference, _, _ = pair
    expected = json.loads(PLAN.read_text())["cases"]["S28_D20_P9"]
    assert candidate.settings == reference.settings == MPCC_SETTINGS == expected["mpcc"]
    assert GEOMETRY_SETTINGS == expected["mpcc_experiment"]
    assert candidate.gate_center_snap == reference.gate_center_snap
    assert candidate.over_gate_lift == reference.over_gate_lift
    assert candidate.observed_obstacle_clearance == reference.observed_obstacle_clearance


@pytest.mark.parametrize("section", ["mpcc", "mpcc_experiment", "prediction", "numerics"])
def test_overrides_rejected(pair, section):
    """Research settings fail explicitly before solver construction."""
    _, _, obs, config = pair
    config = deepcopy(config)
    config.controller[section] = {"reference_speed": 99}
    with pytest.raises(ValueError, match="embedded settings"):
        entry.AttitudeMPCCV3Alt(obs, {}, config)


def test_public_observation_equivalence(pair):
    """Real solves match the frozen research implementation over identical public inputs."""
    candidate, reference, obs, _ = pair
    candidate.episode_reset()
    reference.episode_reset()
    for i in range(8):
        current = deepcopy(obs)
        current["pos"] += [i * 0.008, 0, i * 0.03]
        current["vel"] = np.array([0.1, 0, 0.1])
        if i in (2, 3):
            current["gates_visited"][0] = True
            current["gates_pos"][0] += [0.03, -0.02, 0.01]
        original = deepcopy(current)
        a = candidate.compute_control(current)
        b = reference.compute_control(deepcopy(current))
        assert candidate.last_solver_status == reference.last_solver_status == 0
        np.testing.assert_allclose(a, b, rtol=1e-7, atol=1e-8)
        np.testing.assert_allclose(candidate._path.c, reference._path.c, rtol=0, atol=1e-12)
        for key in original:
            np.testing.assert_array_equal(current[key], original[key])
    assert candidate.track_geometry.gates[0].detected
    candidate.episode_reset()
    assert not candidate.track_geometry.gates[0].detected
    assert candidate._prediction is None and candidate._progress == 0


def test_solver_failure_and_completion(pair):
    """Fallback and completion use the original semantics."""
    candidate, _, obs, _ = pair
    with patch.object(candidate._solver, "solve", return_value=1):
        action = candidate.compute_control(obs)
    np.testing.assert_array_equal(action, [0, 0, 0, candidate._hover])
    assert candidate._prediction is None
    assert not candidate.step_callback(action, obs, 0, True, False, {})
    finished = deepcopy(obs)
    finished["n_gates_passed"] = 5
    assert candidate.step_callback(action, finished, 0, False, False, {})


def test_active_math_ast():
    """Packaging preserves executable methods and optimizer mathematics."""
    old = ast.parse((FROZEN / "mpcc_broad_core.py").read_text())
    new = ast.parse(Path(entry.__file__).read_text())

    def methods(tree):
        return {
            n.name: ast.dump(n)
            for c in tree.body
            if isinstance(c, ast.ClassDef)
            for n in c.body
            if isinstance(n, ast.FunctionDef) and n.name != "__init__"
        }

    assert methods(old) == methods(new)
    text = (
        (FROZEN / "mpcc_broad_solver.py")
        .read_text()
        .replace("attitude_mpcc_broad", "attitude_mpcc_v3_alt")
    )
    old = ast.parse(text)
    function = next(
        n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == "create_mpcc_solver"
    )
    function.body = [
        n
        for n in function.body
        if not (isinstance(n, ast.If) and "qp_tolerance_scale" in ast.unparse(n.test))
    ]
    new = ast.parse(Path(solver.__file__).read_text())

    def functions(tree):
        return {n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}

    assert MPCC_SETTINGS["qp_tolerance_scale"] == 1
    assert functions(old) == functions(new)

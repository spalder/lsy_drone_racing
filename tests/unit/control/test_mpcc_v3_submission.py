"""Independent v3 packaging, real solver, and public-observation replay checks."""

import ast
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import attitude_mpcc_v3 as entry
from lsy_drone_racing.control import mpcc_v3_settings as settings
from lsy_drone_racing.utils import load_config, load_controller

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1/screen/plan.json"


def observation(config: object) -> dict:
    return dict(
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


@pytest.fixture(scope="module")
def actual(tmp_path_factory: pytest.TempPathFactory) -> tuple:
    import os

    previous = Path.cwd()
    os.chdir(tmp_path_factory.mktemp("v3-real-solver"))
    try:
        config = load_config(ROOT / "config/level2.toml")
        obs = observation(config)
        yield entry.AttitudeMPCCV3(obs, {}, config), config, obs
    finally:
        os.chdir(previous)


def test_loader_and_complete_frozen_settings(actual: tuple) -> None:
    c, config, _ = actual
    assert config.controller.file == "attitude_mpcc_v3.py"
    assert load_controller(Path(entry.__file__)).__name__ == "AttitudeMPCCV3"
    expected = json.loads(PLAN.read_text())["cases"]["drag_030"]
    assert c.settings == expected["mpcc"]
    assert settings.GEOMETRY_SETTINGS == expected["mpcc_experiment"]
    assert c.prediction_settings == expected["prediction"]
    assert c.numerical_settings == expected["numerics"]
    assert not any("mpcc_prediction" in name for name in entry.__dict__)


@pytest.mark.parametrize("section", ["mpcc", "mpcc_experiment", "prediction", "numerics"])
def test_research_overrides_rejected(actual: tuple, section: str) -> None:
    _, config, obs = actual
    changed = deepcopy(config)
    changed.controller[section] = {"reference_speed": 99}
    with pytest.raises(ValueError, match="embedded settings"):
        entry.AttitudeMPCCV3(obs, {}, changed)
    with pytest.raises(TypeError):
        entry.AttitudeMPCCV3(obs, {}, config, settings={})


def test_live_soft_bounds_and_penalties(actual: tuple) -> None:
    c, _, _ = actual
    s, o = c._solver, c._ocp
    g = json.loads((Path(o.code_export_directory) / "ocp.json").read_text())
    assert g["constraints"]["idxsbx"] == g["constraints"]["idxsbx_e"] == [0, 1, 2]
    assert g["constraints"]["idxbx_0"] == g["constraints"]["idxbxe_0"] == list(range(17))
    assert o.solver_options.qp_solver_ric_alg == 0
    assert o.solver_options.levenberg_marquardt == 1e-4
    assert g["solver_options"]["cost_scaling"] == [0.02] * 40 + [1.0]
    np.testing.assert_array_equal(s.constraints_get(0, "C"), np.zeros((3, 17)))
    for i in range(1, 41):
        np.testing.assert_array_equal(s.constraints_get(i, "lbx"), o.constraints.lbx)
        np.testing.assert_array_equal(s.constraints_get(i, "ubx"), o.constraints.ubx)
        np.testing.assert_array_equal(s.constraints_get(i, "ug"), [0.975, 1.025, 0.975])
        for name in ("Zl", "Zu"):
            np.testing.assert_array_equal(
                s.cost_get(i, name).ravel(), [10000.0 if i == 40 else 500000.0] * 3
            )


def test_unique_libraries_and_exact_path_bounds(actual: tuple) -> None:
    c, config, obs = actual
    changed = deepcopy(obs)
    changed["pos"][0] += 0.013
    other = entry.AttitudeMPCCV3(changed, {}, config)
    assert c._solver.shared_lib._name != other._solver.shared_lib._name
    assert c._solver.shared_lib._handle != other._solver.shared_lib._handle
    assert c._length != other._length
    for controller in (c, other):
        for i in range(1, 41):
            assert controller._solver.constraints_get(i, "ubx")[-1] == controller._length


def test_public_observation_replay_matches_selected_research(
    actual: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lsy_drone_racing.control import mpcc_prediction_core as reference
    from lsy_drone_racing.control import mpcc_prediction_solver as reference_solver

    spec = importlib.util.spec_from_file_location(
        "v3_reference_instrument",
        ROOT / "scripts/mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v2.py",
    )
    instrument = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instrument)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    monkeypatch.setattr(reference_solver, "AcadosOcpSolver", reference_solver.AcadosOcpSolver)
    monkeypatch.setattr(
        reference.MPCCPredictionCore,
        "compute_control",
        reference.MPCCPredictionCore.compute_control,
    )
    plan = json.loads(PLAN.read_text())
    expected = plan["cases"]["drag_030"]
    instrument.EPISODE_SEED = 1603803
    instrument.install(reference, expected, plan, "drag_030", tmp_path)
    c, config, obs = actual
    c.episode_reset()
    old = reference.MPCCPredictionCore(
        deepcopy(obs),
        {},
        config,
        settings=expected["mpcc"],
        geometry=expected["mpcc_experiment"],
        prediction=expected["prediction"],
        numerics=expected["numerics"],
    )
    old._research_rich = False
    old._research_seed = 1603803
    old._research_tick_records = []
    for tick in range(10):
        public = deepcopy(obs)
        public["pos"][2] += 0.02 * tick
        public["vel"][2] = 0.02
        if tick >= 3:
            public["gates_visited"][0] = True
            public["gates_pos"][0] += [0.03, -0.02, 0.01]
        if tick >= 6:
            public["obstacles_visited"][0] = True
            public["obstacles_pos"][0] += [0.02, 0.01, 0]
        original = deepcopy(public)
        np.testing.assert_allclose(
            c.compute_control(public), old.compute_control(deepcopy(public)), rtol=0, atol=1e-10
        )
        assert c.last_solver_status == old.last_solver_status == 0
        assert c._thrust_gain == old._thrust_gain
        for key in public:
            np.testing.assert_array_equal(public[key], original[key])
        np.testing.assert_array_equal(c._path.c, old._path.c)
    # Detection persists if the next observation hides the previously revealed object.
    c.track_geometry.update(deepcopy(obs))
    assert c.track_geometry.gates[0].detected
    c.episode_reset()
    assert not c.track_geometry.gates[0].detected
    assert c._prediction is None and c._inputs is None and c._thrust_gain == 1


def test_fallback_and_gate_completion(actual: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _, obs = actual
    c.episode_reset()
    monkeypatch.setattr(c._solver, "solve", lambda: 4)
    np.testing.assert_array_equal(c.compute_control(deepcopy(obs)), [0, 0, 0, c._hover])
    assert c._prediction is None and c._inputs is None and c.last_solver_status == 4
    assert not c.step_callback(None, obs, 0.0, False, False, {})
    finished = deepcopy(obs)
    finished["n_gates_passed"] = 5
    assert c.step_callback(None, finished, 0.0, False, False, {})


def test_submission_imports_are_independent() -> None:
    paths = [Path(entry.__file__), *Path(entry.__file__).parent.glob("mpcc_v3*.py")]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    word in node.module
                    for word in (
                        "scripts",
                        "mpcc_prediction",
                        "mpcc_v1",
                        "mpcc_v2",
                        "experimental",
                        "mjx_compat",
                    )
                ), (path, node.module)

"""Focused prediction/adaptation v1 checks, with a short real-solver replay."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import casadi as ca
import numpy as np
import pytest
from crazyflow.dynamics import Dynamics, load_params
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import mpcc_prediction_core as core
from lsy_drone_racing.control import mpcc_prediction_model as model
from lsy_drone_racing.control import mpcc_prediction_solver as solver
from lsy_drone_racing.utils import load_config

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / ".local/mpcc-study/broad-20261103T152500Z-r2/checkout"
PARENT = json.loads((ROOT / "config/research/mpcc_prediction_v1/parent-fast.json").read_text())
SETTINGS = PARENT["mpcc"]
PARAMETERS = load_params(Dynamics.so_rpy, "cf21B_500")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


@pytest.fixture(scope="module")
def reference():
    module(
        "lsy_drone_racing.control.mpcc_broad_solver",
        FROZEN / "lsy_drone_racing/control/mpcc_broad_solver.py",
    )
    return module(
        "prediction_reference_core", FROZEN / "lsy_drone_racing/control/mpcc_broad_core.py"
    )


def observation(config):
    return dict(
        pos=np.array([-1.5, 0.75, 0.7]),
        vel=np.array([0.2, -0.1, 0.03]),
        quat=Rotation.from_euler("xyz", [0.05, -0.04, 0.02]).as_quat(),
        ang_vel=np.zeros(3),
        n_gates_passed=0,
        gate_sequence=np.array(config.env.track.gate_order),
        gates_pos=np.array([g["pos"] for g in config.env.track.gates]),
        gates_quat=Rotation.from_euler("xyz", [g["rpy"] for g in config.env.track.gates]).as_quat(),
        obstacles_pos=np.array([o["pos"] for o in config.env.track.obstacles]),
        gates_visited=np.zeros(4, dtype=bool),
        obstacles_visited=np.zeros(4, dtype=bool),
    )


def test_drag_nominal_frames_and_gain_observation():
    import tomllib
    import crazyflow

    # Read only the installed nominal TOML, never an episode's physical state.
    nominal = tomllib.loads(
        (Path(crazyflow.__file__).parent / "dynamics/first_principles/params.toml").read_text()
    )["cf21B_500"]
    np.testing.assert_array_equal(
        model.NOMINAL_BETA, -np.diag(nominal["drag_matrix"]) / nominal["mass"]
    )
    options = model.validate_prediction(dict(drag_strength=1.0))
    rotation = Rotation.from_euler("xyz", [0.7, -0.5, 0.8]).as_matrix()
    v0 = np.array([3.0, -2.0, 1.0])
    drag = model.drag_acceleration(rotation, v0, options)
    assert drag @ v0 < 0
    np.testing.assert_allclose(rotation.T @ drag, -model.NOMINAL_BETA * (rotation.T @ v0))
    np.testing.assert_allclose(
        model.drag_acceleration(rotation, v0, options, symbolic=True), drag[:, None]
    )
    assert not np.allclose(drag, -model.NOMINAL_BETA * v0)
    np.testing.assert_array_equal(
        model.drag_acceleration(rotation, v0, model.validate_prediction()), np.zeros(3)
    )
    # Solve the trapezoidal interval equation so the known gain must be recovered.
    dt, thrust, true_gain = 0.02, 0.45, 1.13
    damping = rotation @ np.diag(model.NOMINAL_BETA) @ rotation.T
    expected = (
        rotation[:, 2]
        * (PARAMETERS["acc_coef"] + PARAMETERS["cmd_f_coef"] * thrust)
        / PARAMETERS["mass"]
    )
    v1 = np.linalg.solve(
        np.eye(3) + dt * damping / 2,
        (np.eye(3) - dt * damping / 2) @ v0
        + dt * (PARAMETERS["gravity_vec"] + true_gain * expected),
    )
    before = dict(
        pos=np.array([0.0, 0.0, 1.0]), quat=Rotation.from_matrix(rotation).as_quat(), vel=v0
    )
    after = dict(before, vel=v1)
    for mode in ("ema", "kf"):
        f = model.ThrustGainFilter(dict(options, thrust_gain_mode=mode), SETTINGS, dt)
        f.observe(before, thrust, PARAMETERS)
        f.observe(after, thrust, PARAMETERS)
        assert f.accepted
        assert f.raw_gain == pytest.approx(true_gain, abs=2e-14)


def test_attitude_coefficients_only_roll_pitch():
    original = deepcopy(PARAMETERS)
    options = model.validate_prediction(
        dict(attitude_response_scale=0.9, attitude_command_gain_scale=1.1)
    )
    calibrated = model.calibrated_parameters(PARAMETERS, options)
    for key, scale in (
        ("rpy_coef", 0.9**2),
        ("rpy_rates_coef", 0.9),
        ("cmd_rpy_coef", 0.9**2 * 1.1),
    ):
        np.testing.assert_array_equal(calibrated[key][:2], np.asarray(original[key])[:2] * scale)
        assert calibrated[key][2] == original[key][2]
    for key in PARAMETERS:
        np.testing.assert_array_equal(PARAMETERS[key], original[key])
        if key not in ("rpy_coef", "rpy_rates_coef", "cmd_rpy_coef"):
            np.testing.assert_array_equal(calibrated[key], original[key])


def test_kf_rejected_nonfinite_reset_and_bounds():
    f = model.ThrustGainFilter(dict(thrust_gain_mode="kf"), SETTINGS, 0.02)
    prior = 0.0025 + 0.0008 * 0.02
    f.correct(1.2)
    assert f.weight == pytest.approx(prior / (prior + 0.01))
    assert f.gain == pytest.approx(1 + f.weight * 0.2)
    assert f.covariance == pytest.approx((1 - f.weight) * prior)
    gain, covariance = f.gain, f.covariance
    for raw, reason in (
        (None, "altitude"),
        (np.nan, "accepted"),
        (np.inf, "accepted"),
        (0.6, "accepted"),
        (1.5, "accepted"),
    ):
        f.correct(raw, reason)
        covariance += 0.0008 * 0.02
        assert not f.accepted and f.gain == gain and f.weight == 0
        assert f.covariance == pytest.approx(covariance)
    for _ in range(2000):
        f.correct(None, "thrust_change")
    assert f.covariance == f.options["covariance_max"]
    f.correct(1.49)
    assert f.gain <= SETTINGS["adapt_clip_high"]
    for _ in range(2000):
        f.correct(0.61)
    assert f.gain == SETTINGS["adapt_clip_low"]
    f.observe(dict(pos=np.ones(3), vel=np.ones(3), quat=np.full(4, np.nan)), 0.4, PARAMETERS)
    assert f.reason == "nonfinite_observation_or_command" and f.previous is None
    f.reset()
    assert f.gain == 1 and f.covariance == 0.0025 and f.previous is None
    assert not f.accepted


def test_shared_acceptance_and_command_interval():
    options = model.validate_prediction()
    config = load_config(FROZEN / "config/level2.toml")
    obs = observation(config)
    f = model.ThrustGainFilter(options, SETTINGS, 0.02)
    f.observe(obs, 0.4, PARAMETERS)
    assert f.reason == "no_previous_interval"
    f.observe(obs, 0.5, PARAMETERS)
    assert f.reason == "thrust_change"
    low = dict(obs, pos=np.array([0.0, 0.0, 0.15]))
    f.observe(low, 0.5, PARAMETERS)
    assert f.reason == "altitude"
    # Same raw gate and bounds in EMA and KF, including exact boundaries.
    for raw in (np.nan, 0.6, 0.7, 1.0, 1.4, 1.5):
        a = model.ThrustGainFilter(options, SETTINGS, 0.02)
        b = model.ThrustGainFilter(dict(options, thrust_gain_mode="kf"), SETTINGS, 0.02)
        a.correct(raw)
        b.correct(raw)
        assert a.accepted == b.accepted and a.reason == b.reason


def test_symbolic_default_equivalence_and_combination(monkeypatch, reference):
    old_solver = sys.modules["lsy_drone_racing.control.mpcc_broad_solver"]
    monkeypatch.setattr(old_solver, "AcadosOcpSolver", lambda ocp, **kw: None)
    monkeypatch.setattr(solver, "AcadosOcpSolver", lambda ocp, **kw: None)
    _, old = old_solver.create_mpcc_solver(0.02, PARAMETERS, SETTINGS, 20.0)
    _, new = solver.create_mpcc_solver(0.02, PARAMETERS, SETTINGS, 20.0)

    def function(ocp):
        m = ocp.model
        return ca.Function("replay", [m.x, m.u, m.p], [m.disc_dyn_expr])

    a, b = function(old), function(new)
    rng = np.random.default_rng(42)
    for _ in range(20):
        x, u, p = rng.normal(size=17), rng.normal(size=5), rng.normal(size=8)
        np.testing.assert_array_equal(a(x, u, p), b(x, u, p))
    np.testing.assert_array_equal(old.cost.W, new.cost.W)
    np.testing.assert_array_equal(old.cost.W_e, new.cost.W_e)
    _, combined = solver.create_mpcc_solver(
        0.02,
        PARAMETERS,
        SETTINGS,
        20.0,
        prediction=dict(
            drag_strength=1.0,
            attitude_response_scale=1.1,
            attitude_command_gain_scale=1.1,
            thrust_gain_mode="kf",
        ),
        numerics=dict(qp_solver_ric_alg=0, levenberg_marquardt=1e-4),
    )
    assert combined.solver_options.qp_solver_ric_alg == 0
    assert combined.solver_options.qp_solver_cond_ric_alg == 1
    assert combined.solver_options.levenberg_marquardt == 1e-4
    assert not np.array_equal(a(x, u, p), function(combined)(x, u, p))
    np.testing.assert_array_equal(
        np.asarray(a(x, u, p))[[5, 11]], np.asarray(function(combined)(x, u, p))[[5, 11]]
    )


def test_cases_are_single_changes_and_validation():
    definitions = json.loads((ROOT / "config/research/mpcc_prediction_v1/cases.json").read_text())
    assert definitions["baseline"] == {}
    for name, overrides in definitions.items():
        if name not in ("baseline", "combined_example"):
            assert sum(len(v) for v in overrides.values()) == 1
    for options in (
        dict(drag_strength=-1),
        dict(thrust_gain_mode="ekf"),
        dict(initial_covariance=np.nan),
        dict(measurement_variance=0),
        dict(attitude_response_scale=0),
        dict(unknown=1),
    ):
        with pytest.raises(ValueError):
            model.validate_prediction(options)
    for options in (
        dict(qp_solver_ric_alg=True),
        dict(levenberg_marquardt=np.inf),
        dict(levenberg_marquardt=0.001),
        dict(unknown=1),
    ):
        with pytest.raises(ValueError):
            model.validate_numerics(options)


def test_prediction_terminal_alignment_and_recorded_command_rollouts(tmp_path, monkeypatch):
    import gzip

    diagnostics = module(
        "prediction_test_diagnostics", ROOT / "scripts/mpcc_prediction_diagnostics.py"
    )
    monkeypatch.setattr(solver, "AcadosOcpSolver", lambda ocp, **kw: None)
    _, ocp = solver.create_mpcc_solver(0.02, PARAMETERS, SETTINGS, 20.0)
    controller = SimpleNamespace(
        _ocp=ocp,
        _progress=0.0,
        _thrust_gain=1.0,
        _inputs=np.zeros((40, 5)),
        last_solver_status=0,
        prediction_settings=model.validate_prediction(),
        adaptation_diagnostics=dict(
            gain=1.0,
            raw_gain=None,
            accepted=False,
            reason="no_previous_interval",
            covariance=None,
            update_weight=0.0,
        ),
    )
    recorder = diagnostics.PredictionRecorder(controller, {})
    obs = observation(load_config(FROZEN / "config/level2.toml"))
    actions = []
    for tick in range(12):
        action = np.array([0.01 * tick, -0.02 * tick, 0.0, 0.45])
        actions.append(action.tolist())
        before = deepcopy(obs)
        recorder.before_action(obs, action)
        predicted = np.asarray(recorder.records[-1]["predicted_next_state"])
        obs["vel"] = predicted[6:9] + 0.001
        obs["pos"] = predicted[:3]
        obs["quat"] = Rotation.from_euler("xyz", predicted[3:6]).as_quat()
        recorder.after_step(obs)
        np.testing.assert_array_equal(recorder.records[-1]["pre_action"]["vel"], before["vel"])
    summary = recorder.write(tmp_path)
    assert summary["one_step_error"]["velocity_mps"]["n"] == 12
    assert summary["rollout_100ms_error"]["velocity_mps"]["n"] == 8
    assert summary["rollout_200ms_error"]["velocity_mps"]["n"] == 3
    with gzip.open(tmp_path / "prediction.json.gz", "rt") as stream:
        records = json.load(stream)["ticks"]
    assert [r["applied_command"] for r in records] == actions
    for a, b in zip(records, records[1:]):
        assert a["next_observation"] == b["pre_action"]
    # Independently roll the first 100 ms using the changing recorded commands.
    x = np.r_[diagnostics.state(records[0]["pre_action"]), 0.0, actions[0]]
    for action in actions[:5]:
        x = np.asarray(recorder.step(x, np.r_[action, 0.0], np.r_[np.zeros(7), 1.0])).ravel()
    expected = diagnostics.errors(x, records[4]["next_observation"])
    assert records[0]["rollout_100ms_error"] == expected


def test_real_solver_default_actions_deterministic_replay(tmp_path, monkeypatch, reference):
    """Two real generated solvers, same scripted public observations, no physics."""
    monkeypatch.chdir(tmp_path)
    config = load_config(FROZEN / "config/level2.toml")
    obs = observation(config)
    original = reference.MPCCBroadCore(
        obs, {}, config, settings=SETTINGS, geometry=PARENT["mpcc_experiment"]
    )
    new = core.MPCCPredictionCore(
        obs, {}, config, settings=SETTINGS, geometry=PARENT["mpcc_experiment"]
    )
    for tick in range(12):
        current = deepcopy(obs)
        current["vel"] += np.array([0.01, 0.0, -0.005]) * tick
        current["pos"] += obs["vel"] * 0.02 * tick
        current["quat"] = Rotation.from_euler("xyz", [0.05 + 0.002 * tick, -0.04, 0.02]).as_quat()
        old_action = original.compute_control(current)
        new_action = new.compute_control(current)
        np.testing.assert_array_equal(new_action, old_action)
        assert new._thrust_gain == original._thrust_gain
        assert new.last_solver_status == original.last_solver_status == 0
        np.testing.assert_array_equal(new._prediction, original._prediction)
    new.episode_reset()
    assert new._thrust_gain == 1 and new._gain_filter.covariance == 0.0025

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.attitude_mpcc import AttitudeMPCC
from lsy_drone_racing.control.attitude_mpcc_experimental import ExperimentalMPCC
from lsy_drone_racing.utils import load_config


def make_controller(cls: type, *, observed: bool = True, **options: float) -> tuple:
    """Exercise the real path correction without building an optimizer."""
    config = load_config(Path(__file__).parents[3] / "config/level2.toml")
    config.controller.mpcc_experiment = options
    obs = dict(
        pos=np.array([-1.5, 0.75, 0.01]),
        gates_pos=np.array([g["pos"] for g in config.env.track.gates]),
        gates_quat=Rotation.from_euler("xyz", [g["rpy"] for g in config.env.track.gates]).as_quat(),
        obstacles_pos=np.array([o["pos"] for o in config.env.track.obstacles]),
        gates_visited=np.ones(len(config.env.track.gates), dtype=bool),
        obstacles_visited=np.full(len(config.env.track.obstacles), observed, dtype=bool),
    )
    with patch(
        "lsy_drone_racing.control.attitude_mpcc.create_mpcc_solver",
        return_value=(MagicMock(), MagicMock()),
    ):
        return cls(obs, {}, config), obs


def test_defaults_preserve_baseline_after_revelation():
    baseline, obs = make_controller(AttitudeMPCC)
    experiment, _ = make_controller(ExperimentalMPCC)
    obs["gates_pos"][2] += [-0.14, 0.09, 0.06]
    obs["obstacles_pos"][1] += [-0.1, 0.1, 0]
    for controller in (baseline, experiment):
        controller._update_gate_path(obs)
    np.testing.assert_array_equal(experiment._path.c, baseline._path.c)


def test_retained_crossings_fit_eroded_opening_and_are_stable():
    controller, obs = make_controller(ExperimentalMPCC, gate_center_snap=0)
    obs["gates_pos"][1] += [0.15, -0.15, 0.1]
    controller._update_gate_path(obs)
    centers = controller._anchors[2:-1:3]
    ids = controller._gate_ids[1::3]
    rotations = Rotation.from_quat(obs["gates_quat"][ids]).as_matrix()
    delta = controller._path(centers) - obs["gates_pos"][ids]
    local = np.einsum("ni,nij->nj", delta, rotations)
    usable = 0.2 - controller.track_geometry.vehicle.radius_bound - 0.02
    np.testing.assert_allclose(local[:, 0], 0, atol=1e-9)
    assert np.all(np.abs(local[:, 1:]) <= usable + 1e-9)
    assert np.max(np.abs(local[:, 1:])) > 0.01  # Crossings need not be centered.
    previous = controller._path.c.copy()
    controller._update_gate_path(obs)
    np.testing.assert_array_equal(controller._path.c, previous)


def test_lift_raises_return_but_preserves_gate_targets():
    baseline, _ = make_controller(ExperimentalMPCC)
    raised, _ = make_controller(ExperimentalMPCC, over_gate_lift=0.1)
    samples = np.linspace(0, baseline._length, 5000)
    difference = raised._path(samples)[:, 2] - baseline._path(samples)[:, 2]
    assert 0.099 < np.max(difference) < 0.101
    np.testing.assert_allclose(
        raised._path(raised._anchors), baseline._path(baseline._anchors), atol=1e-5
    )


def test_observed_clearance_preserves_initial_path_even_with_visible_poles():
    baseline, _ = make_controller(ExperimentalMPCC)
    candidate, _ = make_controller(ExperimentalMPCC, observed_obstacle_clearance=0.34)
    np.testing.assert_array_equal(candidate._path.c, baseline._path.c)


def test_observed_clearance_activates_on_revelation_and_persists():
    baseline, obs = make_controller(ExperimentalMPCC, observed=False)
    candidate, _ = make_controller(
        ExperimentalMPCC, observed=False, observed_obstacle_clearance=0.34
    )
    np.testing.assert_array_equal(candidate._path.c, baseline._path.c)
    # A gate-only replan must keep baseline clearance for unrevealed poles.
    obs["gates_pos"][2] += [-0.14, 0.09, 0.06]
    for controller in (baseline, candidate):
        controller._update_gate_path(obs)
    np.testing.assert_array_equal(candidate._path.c, baseline._path.c)
    # Revelation at the nominal pose still activates the extra clearance.
    obs["obstacles_visited"][1] = True
    for controller in (baseline, candidate):
        controller._update_gate_path(obs)
    assert not np.allclose(candidate._path.c, baseline._path.c)
    # Revealed knowledge persists on later replans, even outside sensor range.
    obs["obstacles_visited"][1] = False
    obs["gates_pos"][2, 0] += 0.01
    for controller in (baseline, candidate):
        controller._update_gate_path(obs)
    assert candidate.track_geometry.obstacles[1].detected
    assert not np.allclose(candidate._path.c, baseline._path.c)

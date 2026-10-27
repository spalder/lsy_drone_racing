from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.attitude_mpcc import AttitudeMPCC, create_path, gate_anchors
from lsy_drone_racing.utils import load_config, load_controller


class TestPath(TestCase):
    """Check geometric path construction independently of the optimizer."""

    def test_arc_length_and_endpoints(self):
        """Arc-length sampling preserves endpoints and approximately unit tangents."""
        start = np.array([0.0, 0.0, 1.0])
        waypoints = np.array([[1.0, 1.0, 1.0], [2.0, 0.0, 1.0]])
        path = create_path(start, waypoints)
        np.testing.assert_allclose(path(0), start)
        np.testing.assert_allclose(path(path.x[-1]), waypoints[-1], atol=1e-12)
        tangent = path.derivative()(np.linspace(0, path.x[-1], 100))
        np.testing.assert_allclose(np.linalg.norm(tangent, axis=1), 1, atol=1e-3)

    def test_duplicate_waypoints(self):
        """Repeated consecutive points do not introduce zero-length intervals."""
        path = create_path(np.zeros(3), np.array([[0, 0, 0], [1, 0, 0], [1, 0, 0]]))
        self.assertAlmostEqual(path.x[-1], 1)
        np.testing.assert_allclose(path(0.5), [0.5, 0, 0])

    def test_invalid_paths(self):
        """Reject degenerate, nonfinite, and malformed paths."""
        for waypoints in ([[0, 0, 0]], [[np.nan, 1, 0]], [[1, 2]]):
            with self.subTest(waypoints=waypoints), self.assertRaises(ValueError):
                create_path(np.zeros(3), np.array(waypoints))

    def test_gate_anchors_keep_order_and_repeated_passages(self):
        """Repeated gates get separate, increasing path coordinates."""
        config = load_config(Path(__file__).parents[3] / "config/level0.toml")
        path = create_path(np.array([-1.5, 0.75, 0.01]))
        anchors, ids = gate_anchors(path, config.env.track)
        np.testing.assert_array_equal(ids, [0, 1, 2, 3, 1])
        self.assertTrue(np.all(np.diff(anchors) > 0))

    def test_reverse_gate_anchor(self):
        """Negative gate-order entries reverse the required crossing direction."""
        config = load_config(Path(__file__).parents[3] / "config/level0.toml")
        config.env.track.gate_order = [-1]
        config.env.track.gates = [{"pos": [0.5, 0, 1], "rpy": [0, 0, np.pi]}]
        path = create_path(np.array([0, 0, 1]), np.array([[1, 0, 1]]))
        anchors, ids = gate_anchors(path, config.env.track)
        np.testing.assert_allclose(anchors, [0, 0.5, 1], atol=1e-6)
        np.testing.assert_array_equal(ids, [0])


class TestAttitudeMPCC(TestCase):
    """Exercise a real generated solver on a short straight path."""

    @classmethod
    def setUpClass(cls):
        """Build one solver shared by the optimizer regression tests."""
        root = Path(__file__).parents[3]
        config = load_config(root / "config/level0.toml")
        config.env.control_mode = "attitude"
        config.controller.mpcc = {"horizon_steps": 20, "waypoints": [[1.0, 0.0, 1.0]]}
        cls.obs = {
            "pos": np.array([0.0, 0.0, 1.0]),
            "vel": np.zeros(3),
            "quat": np.array([0.0, 0.0, 0.0, 1.0]),
            "ang_vel": np.zeros(3),
            "n_gates_passed": np.array(0),
            "gate_sequence": np.array([0, 1, 0]),
        }
        controller_cls = load_controller(root / "lsy_drone_racing/control/attitude_mpcc.py")
        cls.ctrl = controller_cls(cls.obs, {}, config)

    def setUp(self):
        """Start every test with zero virtual progress."""
        self.ctrl.reset()

    def test_optimizes_progress_and_preserves_observation(self):
        """The optimizer chooses forward flight and leaves input observations intact."""
        original = {k: v.copy() for k, v in self.obs.items()}
        action = self.ctrl.compute_control(self.obs)
        self.assertEqual(self.ctrl.last_solver_status, 0)
        self.assertEqual(action.shape, (4,))
        self.assertTrue(np.all(np.isfinite(action)))
        self.assertGreater(self.ctrl._progress, 0)
        self.assertGreater(self.ctrl._prediction[-1, 0], self.obs["pos"][0])
        # Commands must lie in the physical attitude/thrust bounds.
        self.assertTrue(np.all(action >= self.ctrl._ocp.constraints.lbu[:4] - 1e-6))
        self.assertTrue(np.all(action <= self.ctrl._ocp.constraints.ubu[:4] + 1e-6))
        for key in original:
            np.testing.assert_array_equal(self.obs[key], original[key])
        self.ctrl.compute_control(self.obs)  # Exercise the shifted warm start.
        self.assertEqual(self.ctrl.last_solver_status, 0)

    def test_solver_failure_hovers_and_keeps_progress(self):
        """A failed solve cannot advance progress or return an invalid command."""
        self.ctrl.compute_control(self.obs)
        progress = self.ctrl._progress
        with patch.object(self.ctrl._solver, "solve", return_value=4):
            action = self.ctrl.compute_control(self.obs)
        np.testing.assert_allclose(action, [0, 0, 0, self.ctrl._hover])
        self.assertEqual(self.ctrl._progress, progress)
        self.assertIsNone(self.ctrl._prediction)
        self.ctrl.compute_control(self.obs)
        self.assertEqual(self.ctrl.last_solver_status, 0)

    def test_endpoint_does_not_advance_beyond_path(self):
        """At the endpoint the optimizer stays within the path and hovers."""
        self.ctrl._progress = self.ctrl._length
        obs = self.obs | {"pos": np.array([1.0, 0.0, 1.0])}
        action = self.ctrl.compute_control(obs)
        self.assertEqual(self.ctrl.last_solver_status, 0)
        self.assertLessEqual(self.ctrl._progress, self.ctrl._length)
        np.testing.assert_allclose(action[:3], 0, atol=1e-4)
        self.assertLess(
            np.max(np.linalg.norm(self.ctrl._prediction[:, :3] - obs["pos"], axis=1)), 0.02
        )

    def test_completion_uses_gate_sequence_including_repeated_gates(self):
        """Virtual progress does not substitute for actual ordered gate passages."""
        for passed, expected in ((2, False), (3, True)):
            obs = self.obs | {"n_gates_passed": np.array(passed)}
            finished = self.ctrl.step_callback(np.zeros(4), obs, 0, False, False, {})
            self.assertEqual(finished, expected)

    def test_reset_clears_progress_and_warm_start(self):
        """Episode reset removes both progress and the previous prediction."""
        self.ctrl.compute_control(self.obs)
        self.ctrl.episode_reset()
        self.assertEqual(self.ctrl._progress, 0)
        self.assertIsNone(self.ctrl._prediction)
        self.assertIsNone(self.ctrl.last_solver_status)

    def test_thrust_adaptation_tracks_a_heavier_drone(self):
        """Acceleration feedback identifies a lower thrust-to-mass gain."""
        velocity = np.zeros(3)
        for _ in range(120):
            obs = self.obs | {"vel": velocity.copy()}
            self.ctrl._update_thrust_gain(obs)
            # Hold the issued command constant, simulating 10% less acceleration
            # per newton than predicted, without exposing any simulated mass.
            velocity[2] += (0.9 - 1) * 9.81 * self.ctrl._dt
        self.assertAlmostEqual(self.ctrl._thrust_gain, 0.9, delta=0.002)
        self.assertGreater(self.ctrl._hover, self.ctrl._nominal_hover)

    def test_thrust_adaptation_ignores_ground_contact(self):
        """Ground support must not be interpreted as a thrust/mass change."""
        for _ in range(10):
            self.ctrl._update_thrust_gain(self.obs | {"pos": np.array([0, 0, 0.01])})
        self.assertEqual(self.ctrl._thrust_gain, 1)

    def test_slew_cost_reduces_abrupt_attitude_commands(self):
        """Compare the same position-error response with and without slew costs."""
        self.ctrl._progress = self.ctrl._length
        obs = self.obs | {"pos": np.array([1.02, 0, 1])}
        smooth = self.ctrl.compute_control(obs)
        weight = self.ctrl._ocp.cost.W.copy()
        unsmoothed_weight = weight.copy()
        unsmoothed_weight[-4:, -4:] = 0
        try:
            for k in range(self.ctrl._N):
                self.ctrl._solver.cost_set(k, "W", unsmoothed_weight)
            self.ctrl.reset()
            self.ctrl._progress = self.ctrl._length
            abrupt = self.ctrl.compute_control(obs)
            self.assertLess(np.linalg.norm(smooth[:2]), np.linalg.norm(abrupt[:2]) * 0.5)
        finally:
            for k in range(self.ctrl._N):
                self.ctrl._solver.cost_set(k, "W", weight)


class TestConfiguration(TestCase):
    """Check errors that should be caught before generating solver code."""

    def test_rejects_state_control_mode(self):
        """Avoid returning attitude commands to a state-control environment."""
        config = load_config(Path(__file__).parents[3] / "config/level0.toml")
        config.env.control_mode = "state"
        with self.assertRaisesRegex(ValueError, "control_mode"):
            AttitudeMPCC({}, {}, config)


class TestObservedPath(TestCase):
    """Exercise default-course corrections using only controller observations."""

    @classmethod
    def setUpClass(cls):
        """Create nominal observations and a short solver for path regressions."""
        config = load_config(Path(__file__).parents[3] / "config/level0.toml")
        config.env.control_mode = "attitude"
        config.controller.mpcc = {"horizon_steps": 20}
        cls.obs = {
            "pos": np.array([-1.5, 0.75, 0.01]),
            "vel": np.zeros(3),
            "quat": np.array([0.0, 0.0, 0.0, 1.0]),
            "ang_vel": np.zeros(3),
            "gates_pos": np.array([gate["pos"] for gate in config.env.track.gates]),
            "gates_quat": Rotation.from_euler(
                "xyz", [gate["rpy"] for gate in config.env.track.gates]
            ).as_quat(),
            "obstacles_pos": np.array([pole["pos"] for pole in config.env.track.obstacles]),
        }
        cls.ctrl = AttitudeMPCC(cls.obs, {}, config)

    def test_observed_gate_centers_and_departure_clearance(self):
        """A shifted gate moves the crossing and its post-gate climb clearance."""
        obs = self.obs | {"gates_pos": self.obs["gates_pos"].copy()}
        obs["gates_pos"][2] += [-0.14, 0.09, 0.06]
        self.ctrl._update_gate_path(obs)
        centers = self.ctrl._anchors[2:-1:3]
        ids = self.ctrl._gate_ids[1::3]
        np.testing.assert_allclose(self.ctrl._path(centers), obs["gates_pos"][ids], atol=1e-4)
        progress = centers[2] + np.linspace(0.35, 0.8, 100)
        rotation = Rotation.from_quat(obs["gates_quat"][2]).as_matrix()
        local = (self.ctrl._path(progress) - obs["gates_pos"][2]) @ rotation
        near_frame = (np.abs(local[:, 1]) < 0.3) & (np.abs(local[:, 2]) < 0.3)
        self.assertTrue(np.any(near_frame))
        self.assertTrue(np.all(local[near_frame, 0] > 0.21))

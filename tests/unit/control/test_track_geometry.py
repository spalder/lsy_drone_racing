from itertools import product
from pathlib import Path
from unittest import TestCase

import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.track_geometry import Bounds, TrackGeometry
from lsy_drone_racing.utils import load_config


class TestTrackGeometry(TestCase):
    """Check public geometry independently of any simulator state or OCP."""

    def setUp(self):
        """Start each case with bounded Level 2 geometry and no detections."""
        self.config = load_config(Path(__file__).parents[3] / "config/attitude_mpcc_level2.toml")
        self.geometry = TrackGeometry(self.config)
        self.obs = {
            "gates_pos": np.array([gate["pos"] for gate in self.config.env.track.gates]),
            "gates_quat": Rotation.from_euler(
                "xyz", [gate["rpy"] for gate in self.config.env.track.gates]
            ).as_quat(),
            "gates_visited": np.zeros(4, dtype=bool),
            "obstacles_pos": np.array([pole["pos"] for pole in self.config.env.track.obstacles]),
            "obstacles_visited": np.zeros(4, dtype=bool),
        }

    def test_asset_dimensions_and_capsule_endcaps(self):
        """Include frame, stand, actual box vehicle, and both capsule endcaps."""
        gate = self.geometry.gates[0]
        shapes = {shape.name: shape for shape in gate.primitives}
        self.assertEqual(
            set(shapes), {"col_top", "col_bottom", "col_left", "col_right", "gate_stand"}
        )
        opening_width = (
            shapes["col_right"].center[1]
            - shapes["col_right"].size[1]
            - shapes["col_left"].center[1]
            - shapes["col_left"].size[1]
        )
        self.assertAlmostEqual(opening_width, 0.4)
        np.testing.assert_allclose(self.geometry.vehicle.size, [0.07, 0.07, 0.02])
        self.obs["obstacles_visited"][0] = True
        self.geometry.update(self.obs)
        bounds = self.geometry.obstacles[0].occupied_bounds()[0]
        np.testing.assert_allclose(bounds.low, [-0.015, 0.735, -0.065])
        np.testing.assert_allclose(bounds.high, [0.015, 0.765, 1.565])
        np.testing.assert_allclose(self.geometry.flight_bounds.high, [2.5, 1.5, 2])

    def test_nominal_detection_changes_information_and_shrinks_uncertainty(self):
        """Identical coordinates still reveal a previously unknown object."""
        before = self.geometry.obstacles[0].occupied_bounds()[0]
        self.assertFalse(self.geometry.update(self.obs).changed)
        self.obs["gates_visited"][0] = self.obs["obstacles_visited"][0] = True
        change = self.geometry.update(self.obs)
        self.assertEqual(change.gates, (0,))
        self.assertEqual(change.obstacles, (0,))
        after = self.geometry.obstacles[0].occupied_bounds()[0]
        np.testing.assert_allclose(after.low - before.low, [0.15, 0.15, 0.05])
        np.testing.assert_allclose(before.high - after.high, [0.15, 0.15, 0.05])
        self.assertFalse(self.geometry.update(self.obs).changed)
        self.assertEqual(self.geometry.revision, 1)

    def test_undetected_coordinates_are_ignored_and_detection_persists(self):
        """Only flags reveal poses; leaving range cannot restore uncertainty."""
        self.obs["gates_pos"][0] += [0.1, -0.1, 0.05]
        nominal = self.geometry.gates[0].nominal_pose.position.copy()
        self.geometry.update(self.obs)
        np.testing.assert_array_equal(self.geometry.gates[0].planning_pose.position, nominal)
        self.obs["gates_visited"][0] = True
        self.geometry.update(self.obs)
        revealed = self.geometry.gates[0].planning_pose.position.copy()
        self.obs["gates_visited"][0] = False
        self.obs["gates_pos"][0] = nominal
        self.assertFalse(self.geometry.update(self.obs).changed)
        np.testing.assert_array_equal(self.geometry.gates[0].planning_pose.position, revealed)
        self.assertTrue(self.geometry.gates[0].detected)
        self.geometry.reset()
        self.assertFalse(self.geometry.gates[0].detected)
        np.testing.assert_array_equal(self.geometry.gates[0].planning_pose.position, nominal)

    def test_gate_bounds_cover_rotation_and_translation_intervals(self):
        """Every frame/stand corner remains bounded at extremes and interior angles."""
        gate = self.geometry.gates[2]
        bounds = gate.occupied_bounds()
        angles = gate.rotation_uncertainty
        extremes = np.array(list(product(*zip(angles.low, angles.high))))
        rng = np.random.default_rng(42)
        perturbations = np.vstack((extremes, rng.uniform(angles.low, angles.high, (50, 3))))
        offsets = np.array(
            list(product(*zip(gate.position_uncertainty.low, gate.position_uncertainty.high)))
        )
        nominal_rpy = np.array(self.config.env.track.gates[2]["rpy"])
        for shape, bound in zip(gate.primitives, bounds, strict=True):
            corners = np.array(list(product(*zip(-shape.size, shape.size))))
            local = corners @ shape.rotation.T + shape.center
            for delta in perturbations:
                points = Rotation.from_euler("xyz", nominal_rpy + delta).apply(local)
                points = points[None] + offsets[:, None] + gate.nominal_pose.position
                self.assertTrue(np.all(points >= bound.low - 1e-12))
                self.assertTrue(np.all(points <= bound.high + 1e-12))

    def test_detected_tilted_gate_has_exact_primitive_bounds(self):
        """Revealed roll, pitch and yaw transform each physical box."""
        self.obs["gates_visited"][0] = True
        rotation = Rotation.from_euler("xyz", [0.05, 0.1, -0.7])
        self.obs["gates_quat"][0] = rotation.as_quat()
        self.geometry.update(self.obs)
        gate = self.geometry.gates[0]
        for shape, bound in zip(gate.primitives, gate.occupied_bounds(), strict=True):
            corners = np.array(list(product(*zip(-shape.size, shape.size))))
            points = rotation.apply(corners @ shape.rotation.T + shape.center)
            points += self.obs["gates_pos"][0]
            np.testing.assert_allclose(bound.low, points.min(axis=0))
            np.testing.assert_allclose(bound.high, points.max(axis=0))
        self.obs["gates_quat"][0] *= -1
        self.assertFalse(self.geometry.update(self.obs).changed)

    def test_vehicle_projection_and_explicit_margin(self):
        """Inflation follows the pitched box instead of a fixed horizontal radius."""
        obj = self.geometry.obstacles[0]
        raw = obj.occupied_bounds()[0]
        quat = Rotation.from_euler("y", np.pi / 2).as_quat()
        inflated = obj.inflated_bounds(self.geometry.vehicle, quat, 0.04)[0]
        np.testing.assert_allclose(raw.low - inflated.low, [0.06, 0.11, 0.11])
        np.testing.assert_allclose(inflated.high - raw.high, [0.06, 0.11, 0.11])
        for margin in (-0.01, np.nan):
            with self.assertRaises(ValueError):
                obj.inflated_bounds(self.geometry.vehicle, quat, margin)

    def test_observation_updates_are_atomic_and_owned(self):
        """Malformed observations cannot partially reveal a track or alias its poses."""
        self.obs["gates_visited"][0] = True
        invalid = self.obs | {"obstacles_pos": np.zeros((3, 3))}
        with self.assertRaises(ValueError):
            self.geometry.update(invalid)
        self.assertFalse(self.geometry.gates[0].detected)
        self.assertEqual(self.geometry.revision, 0)
        self.geometry.update(self.obs)
        observed = self.geometry.gates[0].observed_pose.position.copy()
        self.obs["gates_pos"][0] += 1
        np.testing.assert_array_equal(self.geometry.gates[0].observed_pose.position, observed)
        with self.assertRaises(ValueError):
            self.geometry.gates[0].observed_pose.position[0] = 99

    def test_randomization_contract(self):
        """Honor scaled bounds, zero uncertainty, and reject unbounded configurations."""
        bounds = Bounds.from_randomization(
            {"fn": "uniform", "scale": -2, "offset": 1, "kwargs": {"minval": -0.1, "maxval": 0.2}}
        )
        np.testing.assert_allclose(bounds.low, [0.6] * 3)
        np.testing.assert_allclose(bounds.high, [1.2] * 3)
        np.testing.assert_array_equal(Bounds.from_randomization(None).low, np.zeros(3))
        for spec in ({"fn": "normal"}, {"fn": "uniform", "scale": np.inf}):
            with self.assertRaises(ValueError):
                Bounds.from_randomization(spec)
        self.config.env.track.randomize = True
        with self.assertRaisesRegex(ValueError, "fixed nominal layout"):
            TrackGeometry(self.config)

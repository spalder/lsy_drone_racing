from dataclasses import replace
from itertools import product
from pathlib import Path
from unittest import TestCase

import numpy as np
from scipy.optimize import linprog
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.corridor import CorridorPlanner
from lsy_drone_racing.control.track_geometry import TrackGeometry
from lsy_drone_racing.utils import load_config


class TestCorridor(TestCase):
    """Validate complete free-space regions rather than sampled spline clearance."""

    def setUp(self):
        """Use a single physical gate, airborne start, and explicit illustrative margin."""
        self.config = load_config(Path(__file__).parents[3] / "config/attitude_mpcc.toml")
        self.config.env.track.gates = [{"pos": [0, 0, 1], "rpy": [0, 0, 0]}]
        self.config.env.track.obstacles = []
        self.config.env.track.gate_order = [1]
        self.start = np.array([-0.6, 0, 1.0])
        self.finish = np.array([0.6, 0, 1.0])
        self.guides = np.empty((0, 3))

    def planner(self) -> CorridorPlanner:
        """Build a fresh immutable-geometry planning snapshot."""
        return CorridorPlanner(TrackGeometry(self.config), tracking_margin=0.04)

    def test_rotational_uncertainty_contains_perturbed_asset_corners(self):
        """Interval boxes enclose corners over independent Euler and position bounds."""
        config = load_config(Path(__file__).parents[3] / "config/level2.toml")
        geometry = TrackGeometry(config)
        planner = CorridorPlanner(geometry, 0.0, 0.0)
        rng = np.random.default_rng(12)
        signs = np.array(list(product((-1, 1), repeat=3)))
        for index, gate in enumerate(geometry.gates):
            boxes = [box for box in planner.boxes if box.owner == ("gate", index)]
            nominal = Rotation.from_quat(gate.nominal_pose.quaternion).as_euler("xyz")
            for _ in range(100):
                rotation = Rotation.from_euler(
                    "xyz",
                    nominal
                    + rng.uniform(gate.rotation_uncertainty.low, gate.rotation_uncertainty.high),
                )
                position = gate.nominal_pose.position + rng.uniform(
                    gate.position_uncertainty.low, gate.position_uncertainty.high
                )
                for shape, box in zip(gate.primitives, boxes, strict=True):
                    corners = shape.center + (signs * shape.size) @ shape.rotation.T
                    actual = (rotation.apply(corners) + position - box.center) @ box.rotation
                    self.assertTrue(np.all(abs(actual) <= box.half_size + 1e-10))

    def test_single_gate_has_regions_and_continuous_clearance(self):
        """An independent LP finds no intersection of any cell with inflated solids."""
        planner = self.planner()
        result = planner.build(self.start, [1], self.guides, self.finish)
        self.assertEqual(result.status, "certified", result.reason)
        corridor = result.corridor
        self.assertEqual(planner.validate(corridor), ())
        self.assertEqual(len(corridor.passages), 1)
        passage = corridor.passages[0]
        cell = corridor.cells[passage.cell_index]
        midpoint = (cell.start + cell.end) / 2
        self.assertAlmostEqual(midpoint[0], 0)
        self.assertTrue(
            cell.contains(midpoint + [0, 0.02, 0.02], (cell.progress_low + cell.progress_high) / 2)
        )
        for cell in corridor.cells:
            for box in planner.boxes:
                A_box = np.vstack((box.rotation.T, -box.rotation.T))
                b_box = A_box @ box.center + np.tile(box.half_size, 2)
                check = linprog(
                    np.zeros(3),
                    A_ub=np.vstack((cell.A, A_box)),
                    b_ub=np.r_[cell.b, b_box],
                    bounds=[(None, None)] * 3,
                    method="highs",
                )
                self.assertEqual(check.status, 2, "Corridor intersects inflated geometry")

    def test_off_center_asymmetric_passage_around_nearby_pole(self):
        """A pole on one side excludes the center departure but leaves a passage region."""
        self.config.env.track.obstacles = [{"pos": [0.3, 0.115, 1.55]}]
        planner = self.planner()
        finish = np.array([0.7, -0.3, 1])
        result = planner.build(self.start, [1], self.guides, finish)
        self.assertEqual(result.status, "certified", result.reason)
        passage = result.corridor.passages[0]
        cell = result.corridor.cells[passage.cell_index]
        crossing = (cell.start + cell.end) / 2
        self.assertLess(crossing[1], 0)
        progress = (cell.progress_low + cell.progress_high) / 2
        self.assertFalse(cell.contains(np.array([0, 0, 1]), progress))
        self.assertTrue(cell.contains(crossing, progress))

    def test_tilted_gate_regions_follow_full_orientation(self):
        """Rolled and pitched frame surfaces determine the crossing plane and aperture."""
        rpy = [0.12, -0.1, 0.6]
        self.config.env.track.gates[0]["rpy"] = rpy
        normal = Rotation.from_euler("xyz", rpy).as_matrix()[:, 0]
        origin = np.array([0, 0, 1])
        planner = self.planner()
        result = planner.build(origin - normal * 0.6, [1], self.guides, origin + normal * 0.6)
        self.assertEqual(result.status, "certified", result.reason)
        np.testing.assert_allclose(result.corridor.passages[0].normal, normal)
        self.assertEqual(planner.validate(result.corridor), ())

    def test_pole_between_clear_endpoints_requires_detour(self):
        """Interior segment collisions cannot pass an endpoint-only clearance check."""
        self.config.env.track.gates = []
        self.config.env.track.obstacles = [{"pos": [0, 0, 1.55]}]
        planner = self.planner()
        self.assertFalse(planner._free_segments(self.start, self.finish[None], planner.boxes)[0])
        result = planner.build(self.start, [], self.guides, self.finish)
        self.assertEqual(result.status, "certified", result.reason)
        self.assertGreater(len(result.corridor.cells), 1)
        self.assertEqual(planner.validate(result.corridor), ())
        with self.assertRaisesRegex(ValueError, "separated"):
            planner._cell(self.start, self.finish, 0, 0)

    def test_repeated_reverse_passages_and_progress_assignment(self):
        """A physical gate keeps its collisions while each crossing gets a separate index."""
        planner = self.planner()
        result = planner.build(self.start, [1, -1], self.guides, self.start)
        self.assertEqual(result.status, "certified", result.reason)
        self.assertEqual([p.gate_id for p in result.corridor.passages], [0, 0])
        self.assertEqual([p.direction for p in result.corridor.passages], [1, -1])
        second = result.corridor.cells[result.corridor.passages[1].cell_index]
        progress = (second.progress_low + second.progress_high) / 2
        self.assertIs(result.corridor.cell_at(progress, 1), second)
        with self.assertRaisesRegex(ValueError, "occurrence"):
            result.corridor.cell_at(progress, 0)
        self.assertFalse(second.contains(second.start, 0))

    def test_uncertain_gate_requires_observation_and_old_snapshot_expires(self):
        """Revealing an unchanged nominal pose unlocks passage planning."""
        self.config.env.randomizations = {
            "gate_pos": {"fn": "uniform", "kwargs": {"minval": [-0.15] * 3, "maxval": [0.15] * 3}}
        }
        planner = self.planner()
        result = planner.build(self.start, [1], self.guides, self.finish)
        self.assertEqual(result.status, "observation_required")
        self.assertIsNone(result.corridor)
        planner.geometry.update(
            {
                "gates_visited": [True],
                "gates_pos": [[0, 0, 1]],
                "gates_quat": [[0, 0, 0, 1]],
                "obstacles_visited": [],
                "obstacles_pos": np.empty((0, 3)),
            }
        )
        self.assertEqual(planner.build(self.start, [1], self.guides).status, "stale_geometry")
        revealed = CorridorPlanner(planner.geometry, 0.04)
        self.assertEqual(
            revealed.build(self.start, [1], self.guides, self.finish).status, "certified"
        )

    def test_gate_three_extreme_is_not_certified_through_pole(self):
        """The 0.2 m gate/pole spacing never accepts the old fixed exit anchor."""
        self.config = load_config(Path(__file__).parents[3] / "config/attitude_mpcc_level2.toml")
        geometry = TrackGeometry(self.config)
        positions = np.array([gate["pos"] for gate in self.config.env.track.gates])
        poles = np.array([pole["pos"] for pole in self.config.env.track.obstacles])
        positions[2, 0] -= 0.15
        poles[2, 0] += 0.15
        geometry.update(
            {
                "gates_visited": np.ones(4, dtype=bool),
                "gates_pos": positions,
                "gates_quat": Rotation.from_euler(
                    "xyz", [g["rpy"] for g in self.config.env.track.gates]
                ).as_quat(),
                "obstacles_visited": np.ones(4, dtype=bool),
                "obstacles_pos": poles,
            }
        )
        planner = CorridorPlanner(geometry, 0.04)
        start = positions[2] + [0.5, 0, 0]
        result = planner.build(start, [3], self.guides, np.array([-1.8, -0.25, 1.2]))
        self.assertEqual(result.status, "route_not_found", result.reason)
        self.assertIsNone(result.corridor)
        self.assertIn("passage", result.reason)

    def test_post_gate_frame_and_mutated_cells_are_rejected(self):
        """Passing the center does not remove the frame; expanded cells lose certification."""
        planner = self.planner()
        result = planner.build(self.start, [1], self.guides, self.finish)
        self.assertEqual(result.status, "certified")
        self.assertFalse(
            planner._free_segments(
                np.array([0.02, 0, 1]), np.array([[0.02, 0, 1.6]]), planner.boxes
            )[0]
        )
        cell = result.corridor.cells[0]
        unsafe = replace(cell, A=cell.A[:8], b=cell.b[:8])
        changed = replace(result.corridor, cells=(unsafe,) + result.corridor.cells[1:])
        self.assertTrue(planner.validate(changed))
        missing = replace(result.corridor, passages=())
        self.assertIn("missing or out-of-order gate passages", planner.validate(missing))
        passage_index = result.corridor.passages[0].cell_index
        passage_cell = result.corridor.cells[passage_index]
        # Frame-separation planes also imply the opening limits. Remove both
        # those certificates and the explicit aperture to create an unsafe cell.
        no_aperture = replace(passage_cell, A=passage_cell.A[:8], b=passage_cell.b[:8])
        cells = list(result.corridor.cells)
        cells[passage_index] = no_aperture
        self.assertIn(
            "missing physical aperture boundary",
            planner.validate(replace(result.corridor, cells=tuple(cells))),
        )

    def test_envelope_contains_continuous_tilt_and_yaw_samples(self):
        """The analytic support envelope contains box corners across the permitted attitudes."""
        planner = self.planner()
        envelope = planner.envelope
        vertices = np.array(list(product(*zip(-envelope.vehicle.size, envelope.vehicle.size))))
        rng = np.random.default_rng(21)
        directions = rng.normal(size=(50, 3))
        for tilt in np.linspace(0, envelope.max_tilt, 8):
            for yaw, spin in rng.uniform(-np.pi, np.pi, (8, 2)):
                rotation = Rotation.from_euler("ZYZ", [yaw, tilt, spin])
                points = rotation.apply(vertices)
                support = (directions @ points.T).max(axis=1)
                self.assertTrue(np.all(support <= envelope.support(directions) + 1e-12))

    def test_airborne_and_margin_contract(self):
        """Takeoff and overlarge margins fail explicitly rather than relaxing boundaries."""
        planner = self.planner()
        result = planner.build(np.array([-0.6, 0, 0.01]), [1], self.guides)
        self.assertEqual(result.status, "route_not_found")
        self.assertIn("takeoff", result.reason)
        planner = CorridorPlanner(planner.geometry, 0.2)
        result = planner.build(self.start, [1], self.guides, self.finish)
        self.assertEqual(result.status, "route_not_found")
        with self.assertRaises(ValueError):
            CorridorPlanner(planner.geometry, -0.1)

    def test_full_nominal_course_keeps_all_ordered_passages(self):
        """The default route supplies guides, while cells include all frames and poles."""
        self.config = load_config(Path(__file__).parents[3] / "config/attitude_mpcc.toml")
        planner = self.planner()
        guides = np.array(
            [
                [-1, 0.75, 0.4],
                [0.3, 0.35, 0.7],
                [1.3, -0.15, 0.9],
                [0.85, 0.85, 1.2],
                [-0.5, -0.05, 0.7],
                [-1.2, -0.2, 0.8],
                [-1.2, -0.2, 1.2],
                [0, -0.7, 1.2],
                [1.2, -0.15, 1.2],
                [1.05, 0.75, 1.2],
                [0.25, 1.25, 1.2],
            ]
        )
        result = planner.build(np.array([-1.5, 0.75, 0.25]), [1, 2, 3, 4, 2], guides, guides[-1])
        self.assertEqual(result.status, "certified", result.reason)
        self.assertEqual([p.gate_id for p in result.corridor.passages], [0, 1, 2, 3, 1])
        self.assertEqual(planner.validate(result.corridor), ())

    def test_unknown_pole_uses_bounds_until_detection(self):
        """A conservative detour can shorten after a nominal-position detection."""
        self.config.env.track.gates = []
        self.config.env.track.obstacles = [{"pos": [0, 0.3, 1.55]}]
        self.config.env.randomizations = {
            "obstacle_pos": {
                "fn": "uniform",
                "kwargs": {"minval": [-0.15, -0.15, -0.05], "maxval": [0.15, 0.15, 0.05]},
            }
        }
        planner = self.planner()
        before = planner.build(self.start, [], self.guides, self.finish)
        self.assertEqual(before.status, "certified", before.reason)
        self.assertGreater(len(before.corridor.cells), 1)
        planner.geometry.update(
            {
                "gates_visited": [],
                "gates_pos": np.empty((0, 3)),
                "gates_quat": np.empty((0, 4)),
                "obstacles_visited": [True],
                "obstacles_pos": [[0, 0.3, 1.55]],
            }
        )
        revealed = CorridorPlanner(planner.geometry, 0.04)
        after = revealed.build(self.start, [], self.guides, self.finish)
        self.assertEqual(after.status, "certified", after.reason)
        self.assertEqual(len(after.corridor.cells), 1)
        self.assertLess(
            after.corridor.cells[-1].progress_high, before.corridor.cells[-1].progress_high
        )

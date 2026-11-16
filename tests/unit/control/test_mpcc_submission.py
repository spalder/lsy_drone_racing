"""Packaging, observation and harness regressions; no simulator patches required.

This file can run directly with an isolated checkout's Python and PYTHONPATH.
Historical source is read only for AST comparisons, never imported there.
"""

# Test doubles intentionally use small duck-typed interfaces.
# ruff: noqa: ANN001, ANN002, ANN202

from __future__ import annotations

import ast
import importlib.util
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import crazyflow  # noqa: F401, initializes the required SciPy array API before SciPy imports
import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import attitude_mpcc_v1 as entry
from lsy_drone_racing.utils import load_config, load_controller

LOCAL_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path(entry.__file__).resolve().parents[2]
HISTORY = LOCAL_ROOT / "logs/mpcc-compliance-20261103/historical-source"
PLAN = LOCAL_ROOT / "logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/plan.json"


def observation(config: object) -> dict:
    """Construct only public observations; no environment or hidden state."""
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


class TestSubmission(unittest.TestCase):
    """Exercise actual assets and an actual Acados solver on public observations."""

    @classmethod
    def setUpClass(cls):
        """Build one solver in a private generated-code directory."""
        cls.directory = tempfile.TemporaryDirectory(prefix="mpcc-v1-tests-")
        cls.previous = Path.cwd()
        os.chdir(cls.directory.name)
        cls.config = load_config(ROOT / "config/level2.toml")
        cls.obs = observation(cls.config)
        cls.controller = entry.AttitudeMPCCV1(cls.obs, {}, cls.config)

    @classmethod
    def tearDownClass(cls):
        """Release the temporary solver directory."""
        os.chdir(cls.previous)
        cls.directory.cleanup()

    def setUp(self):
        """Reset solver and geometry state before each test."""
        self.controller.episode_reset()

    def test_discovery(self):
        """The real loader finds exactly one local controller."""
        found = load_controller(Path(entry.__file__))
        self.assertEqual(found.__name__, "AttitudeMPCCV1")

    def test_recorded_effective_settings(self):
        """Effective settings match the independently audited selected case."""
        expected = json.loads(PLAN.read_text())["cases"]["combined"]["controller"]
        self.assertEqual(self.controller.settings, expected["mpcc"])
        self.assertEqual(entry.GEOMETRY_SETTINGS, expected["mpcc_experiment"])

    def test_override_rejected_before_solver_creation(self):
        """Research knobs and waypoints cannot override the submission."""
        for section, value in [
            ("mpcc", {"reference_speed": 99}),
            ("mpcc", {"waypoints": [[1, 2, 3]]}),
            ("mpcc_experiment", {"gate_center_snap": 0}),
        ]:
            config = deepcopy(self.config)
            config.controller[section] = value
            with (
                self.subTest(section=section, value=value),
                self.assertRaisesRegex(ValueError, "embedded settings"),
            ):
                entry.AttitudeMPCCV1(self.obs, {}, config)

    def test_real_solver_and_observation_ownership(self):
        """A real solve succeeds without mutating observations or aliasing commands."""
        original = deepcopy(self.obs)
        action = self.controller.compute_control(self.obs)
        self.assertEqual(self.controller.last_solver_status, 0)
        self.assertTrue(np.all(np.isfinite(action)))
        self.assertEqual(action.shape, (4,))
        self.assertIsNotNone(self.controller._prediction)
        for key in original:
            np.testing.assert_array_equal(self.obs[key], original[key])
        action[:] = 999
        self.assertTrue(np.all(self.controller._last_action != 999))

    def test_geometry_revelation_persistence_and_reset(self):
        """Revealed poses persist until the episode boundary."""
        controller = self.controller
        obs = deepcopy(self.obs)
        obs["gates_visited"][0] = True
        obs["gates_pos"][0] += [0.03, -0.02, 0.01]
        controller._update_gate_path(obs)
        revision = controller.track_geometry.revision
        pose = controller.track_geometry.gates[0].planning_pose.position.copy()
        path = controller._path.c.copy()
        controller._update_gate_path(self.obs)
        self.assertEqual(controller.track_geometry.revision, revision)
        np.testing.assert_array_equal(
            controller.track_geometry.gates[0].planning_pose.position, pose
        )
        np.testing.assert_array_equal(controller._path.c, path)
        controller.episode_reset()
        self.assertFalse(controller.track_geometry.gates[0].detected)
        self.assertEqual(controller._progress, 0)
        controller._update_gate_path(self.obs)
        self.assertGreater(controller.track_geometry.revision, revision)

    def test_solver_failure_returns_hover(self):
        """An unsuccessful solve clears predictions and returns hover."""
        with patch.object(self.controller._solver, "solve", return_value=1):
            action = self.controller.compute_control(self.obs)
        self.assertIsNone(self.controller._prediction)
        np.testing.assert_array_equal(action, [0, 0, 0, self.controller._hover])

    def test_completion_callback(self):
        """Completion follows gate observations rather than termination alone."""
        obs = deepcopy(self.obs)
        self.assertFalse(self.controller.step_callback(None, obs, 0, True, False, {}))
        obs["n_gates_passed"] = np.array(5)
        self.assertTrue(self.controller.step_callback(None, obs, 0, False, False, {}))


class TestPreservedMath(unittest.TestCase):
    """Compare executable ASTs with the frozen validated implementation."""

    def test_active_methods(self):
        """Active method ASTs remain identical to the validated source."""

        def methods(path):
            tree = ast.parse(path.read_text())
            return {
                n.name: n
                for c in tree.body
                if isinstance(c, ast.ClassDef)
                for n in c.body
                if isinstance(n, ast.FunctionDef)
            }

        original = methods(HISTORY / "lsy_drone_racing/control/attitude_mpcc.py")
        original.update(methods(HISTORY / "lsy_drone_racing/control/attitude_mpcc_experimental.py"))
        candidate = methods(Path(entry.__file__))
        for name in [
            "reset",
            "episode_reset",
            "_update_thrust_gain",
            "_update_gate_path",
            "compute_control",
            "step_callback",
            "render_callback",
        ]:
            with self.subTest(method=name):
                self.assertEqual(ast.dump(original[name]), ast.dump(candidate[name]))

    def test_solver_math(self):
        """Only code-generation names differ in the extracted solver."""
        old = (HISTORY / "lsy_drone_racing/control/attitude_mpcc.py").read_text()
        old = old.replace('"attitude_mpcc"', '"attitude_mpcc_v1"').replace(
            "c_generated_code/attitude_mpcc", "c_generated_code/attitude_mpcc_v1"
        )
        new = (ROOT / "lsy_drone_racing/control/mpcc_v1_solver.py").read_text()

        def functions(s):
            return {
                n.name: ast.dump(n) for n in ast.parse(s).body if isinstance(n, ast.FunctionDef)
            }

        self.assertEqual(functions(old), functions(new))


class TestLocalHarness(unittest.TestCase):
    """Exercise episode semantics with a small deterministic interface fixture."""

    def test_callback_order_and_time_conventions(self):
        """The driver preserves callback order and both timing definitions."""
        spec = importlib.util.spec_from_file_location(
            "verify_mpcc_submission", LOCAL_ROOT / "scripts/verify_mpcc_submission.py"
        )
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        events = []

        class Environment:
            def reset(self, seed):
                events.append(("reset", seed))
                return {}, {}

            def step(self, action):
                events.append("step")
                return dict(n_gates_passed=1, gate_sequence=[0]), 0, False, False, {}

        class Control:
            def __init__(self, obs, info, config):
                self.settings = {}
                self.gate_center_snap, self.over_gate_lift = 0.75, 0.15
                self.observed_obstacle_clearance = None
                self._prediction, self.last_solver_status = True, 0

            def compute_control(self, obs, info):
                events.append("compute")
                return np.zeros(4)

            def step_callback(self, *args):
                events.append("step_callback")
                return True

            def episode_callback(self):
                events.append("episode_callback")

            def episode_reset(self):
                events.append("episode_reset")

        result = harness.run_episode(
            Environment(), Control, SimpleNamespace(env=SimpleNamespace(freq=50)), 123, 2
        )
        self.assertEqual(
            events,
            [
                ("reset", 123),
                "compute",
                "step",
                "step_callback",
                "episode_callback",
                "episode_reset",
            ],
        )
        self.assertEqual(result["official_time_s"], 0)
        self.assertEqual(result["completed_step_time_s"], 0.02)
        self.assertEqual(result["failed_solve_ticks"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

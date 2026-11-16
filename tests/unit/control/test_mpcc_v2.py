"""V2 preservation and parameter application checks using actual solvers."""

# ruff: noqa
import ast
import importlib.util
import unittest
from pathlib import Path
from copy import deepcopy
import numpy as np
from lsy_drone_racing.control import mpcc_v2_core as core
from lsy_drone_racing.utils import load_controller
from scripts.mpcc_v2_research import controller_factory

spec = importlib.util.spec_from_file_location(
    "v1_tests", Path(__file__).with_name("test_mpcc_submission.py")
)
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
v1.entry = core
core.AttitudeMPCCV1 = core.MPCCV2Core


class TestV2(v1.TestSubmission):
    def test_discovery(self):
        from lsy_drone_racing.control import attitude_mpcc_v2

        self.assertEqual(
            load_controller(Path(attitude_mpcc_v2.__file__)).__name__, "AttitudeMPCCV2"
        )

    def test_bounds(self):
        for key, value in [
            ("contour_weight", float("nan")),
            ("horizon_steps", 41),
            ("reference_speed", 3),
        ]:
            settings = dict(core.TUNED_SETTINGS, **{key: value})
            with self.assertRaises(ValueError):
                core.validated_settings(settings)
        with self.assertRaises(ValueError):
            core.validated_settings(geometry={"gate_center_snap": 2})

    def test_actual_supported_application(self):
        settings = dict(core.TUNED_SETTINGS, contour_weight=1000)
        shape = dict(core.GEOMETRY_SETTINGS, gate_center_snap=1.0)
        cls = controller_factory(settings, shape)
        other = cls(self.obs, {}, self.config)
        self.assertEqual(other.settings, settings)
        self.assertEqual(other.gate_center_snap, 1.0)
        self.assertFalse(np.array_equal(other._path.c, self.controller._path.c))
        self.assertFalse(np.array_equal(other._ocp.cost.W, self.controller._ocp.cost.W))
        self.assertTrue(np.all(np.isfinite(other.compute_control(self.obs))))

    def test_preserved_active_ast(self):
        root = Path(core.__file__).parent

        def methods(p):
            return {
                n.name: ast.dump(n)
                for c in ast.parse(p.read_text()).body
                if isinstance(c, ast.ClassDef)
                for n in c.body
                if isinstance(n, ast.FunctionDef)
            }

        old, new = methods(root / "attitude_mpcc_v1.py"), methods(root / "mpcc_v2_core.py")
        for key in old:
            if key != "__init__":
                self.assertEqual(old[key], new[key])
        self.assertEqual(
            (root / "mpcc_v1_solver.py")
            .read_text()
            .replace("attitude_mpcc_v1", "attitude_mpcc_v2"),
            (root / "mpcc_v2_solver.py").read_text(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

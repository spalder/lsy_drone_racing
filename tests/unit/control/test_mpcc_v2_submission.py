"""Actual isolated v2 loader, solver and preservation regressions; local-only."""

# ruff: noqa
from pathlib import Path
import os, sys, json, ast, importlib.util, unittest, tempfile
from copy import deepcopy
from unittest.mock import patch

WORK = Path("/home/askho/repos/lsy_drone_racing-mpcc-v2")
LOCAL = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORK))
from lsy_drone_racing.control import attitude_mpcc_v2 as entry
from lsy_drone_racing.control import mpcc_v2_solver as solver
from lsy_drone_racing.utils import load_config, load_controller
import numpy as np

# Reuse established behavioral fixtures only; v1 files and assertions remain unchanged on disk.
source = (LOCAL / "tests/unit/control/test_mpcc_submission.py").read_text()
source = source.replace(
    "from lsy_drone_racing.control import attitude_mpcc_v1 as entry",
    "from lsy_drone_racing.control import attitude_mpcc_v2 as entry",
).replace("AttitudeMPCCV1", "AttitudeMPCCV2")
module = type(sys)("v2_behavior_fixtures")
module.__file__ = str(LOCAL / "tests/unit/control/test_mpcc_submission.py")
exec(compile(source, module.__file__, "exec"), module.__dict__)
EXPECTED = json.loads(
    (LOCAL / "logs/mpcc-compliance-v2-20261104/selected-settings.json").read_text()
)
RESEARCH = LOCAL / ".local/mpcc-study/broad-20261103T152500Z-r2/checkout/lsy_drone_racing/control"


def parsed(path):
    return ast.parse(path.read_text())


def clean(node):
    class Normalize(ast.NodeTransformer):
        def visit_Expr(self, n):
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                return None
            return self.generic_visit(n)

        def visit_Assign(self, n):
            if any(
                isinstance(t, ast.Attribute) and t.attr == "adaptation_sample_accepted"
                for t in n.targets
            ):
                return None
            if any(
                isinstance(t, ast.Attribute) and t.attr == "last_geometry_update" for t in n.targets
            ):
                return ast.Expr(value=self.visit(n.value))
            return self.generic_visit(n)

    return ast.dump(Normalize().visit(deepcopy(node)))


class TestV2Behavior(module.TestSubmission):
    def test_recorded_effective_settings(self):
        self.assertEqual(self.controller.settings, EXPECTED["mpcc"])
        self.assertEqual(entry.GEOMETRY_SETTINGS, EXPECTED["mpcc_experiment"])

    def test_fixed_python_constructor(self):
        with self.assertRaises(TypeError):
            entry.AttitudeMPCCV2(self.obs, {}, self.config, settings={"reference_speed": 99})

    def test_active_ast_preserved(self):
        def methods(tree):
            return {
                n.name: n
                for c in tree.body
                if isinstance(c, ast.ClassDef)
                for n in c.body
                if isinstance(n, ast.FunctionDef)
            }

        original = methods(parsed(RESEARCH / "mpcc_broad_core.py"))
        new = methods(parsed(Path(entry.__file__)))
        for name in original:
            if name != "__init__":
                self.assertEqual(clean(original[name]), clean(new[name]), name)

    def test_solver_ast_and_baseline_helpers(self):
        old = (
            (RESEARCH / "mpcc_broad_solver.py")
            .read_text()
            .replace("attitude_mpcc_broad", "attitude_mpcc_v2_submission")
        )
        tree = ast.parse(old)
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "create_mpcc_solver"
        )
        fn.body = [
            n
            for n in fn.body
            if not (isinstance(n, ast.If) and "qp_tolerance_scale" in ast.unparse(n.test))
        ]
        new = next(
            n
            for n in parsed(Path(solver.__file__)).body
            if isinstance(n, ast.FunctionDef) and n.name == "create_mpcc_solver"
        )
        self.assertEqual(clean(fn), clean(new))
        from lsy_drone_racing.control import mpcc_v1_solver, attitude_mpc

        oldf = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for n in parsed(Path(mpcc_v1_solver.__file__)).body:
            if isinstance(n, ast.FunctionDef) and n.name in ("create_path", "gate_anchors"):
                self.assertEqual(clean(oldf[n.name]), clean(n))
        oldmodel = next(
            n
            for n in parsed(RESEARCH / "attitude_mpc.py").body
            if isinstance(n, ast.FunctionDef) and n.name == "create_acados_model"
        )
        model = next(
            n
            for n in parsed(Path(attitude_mpc.__file__)).body
            if isinstance(n, ast.FunctionDef) and n.name == "create_acados_model"
        )
        self.assertEqual(clean(oldmodel), clean(model))

    def test_public_observation_replay_matches_research(self):
        # Test-only comparator imports. These never appear in a submitted module or the smoke process.
        from lsy_drone_racing.control import mpcc_v1_geometry

        sys.modules["lsy_drone_racing.control.mpcc_v2_geometry"] = mpcc_v1_geometry
        for name, file in [
            ("lsy_drone_racing.control.mpcc_broad_solver", "mpcc_broad_solver.py"),
            ("research_v2_comparator", "mpcc_broad_core.py"),
        ]:
            spec = importlib.util.spec_from_file_location(name, RESEARCH / file)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        research = sys.modules["research_v2_comparator"].MPCCBroadCore(
            deepcopy(self.obs),
            {},
            self.config,
            settings=EXPECTED["mpcc"],
            geometry=EXPECTED["mpcc_experiment"],
        )
        for tick in range(8):
            obs = deepcopy(self.obs)
            obs["pos"][2] += 0.02 * tick
            obs["vel"][2] = 0.02
            if tick >= 3:
                obs["gates_visited"][0] = True
                obs["gates_pos"][0] += [0.03, -0.02, 0.01]
            np.testing.assert_allclose(
                self.controller.compute_control(deepcopy(obs)),
                research.compute_control(deepcopy(obs)),
                rtol=0,
                atol=1e-10,
            )
        np.testing.assert_array_equal(self.controller._path.c, research._path.c)


class TestEpisodeProtocol(module.TestLocalHarness):
    pass


if __name__ == "__main__":
    unittest.main(verbosity=2)

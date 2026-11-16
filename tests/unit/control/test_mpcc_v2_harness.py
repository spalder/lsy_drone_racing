"""Checkpoint provenance, callback and malformed-record regressions."""

# ruff: noqa
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from scripts import mpcc_v2_study as h
from scripts import mpcc_v2_audit as a


class TestHarness(unittest.TestCase):
    def test_callback_order_and_bounds(self):
        events = []

        class Env:
            def reset(self, seed):
                events.append("reset")
                return {}, {}

            def step(self, action):
                events.append("step")
                return dict(n_gates_passed=5), 0, False, False, {}

        class Controller:
            def __init__(self, *args):
                self.settings = {}
                self.gate_center_snap = 0.75
                self.over_gate_lift = 0.15
                self.observed_obstacle_clearance = None
                self._prediction = True
                self.last_solver_status = 0

            def compute_control(self, *args):
                events.append("compute")
                return np.zeros(4)

            def step_callback(self, *args):
                events.append("step_callback")
                return True

            def episode_callback(self):
                events.append("episode_callback")

            def episode_reset(self):
                events.append("episode_reset")

        e = h.episode(Env(), Controller, None, 1)
        self.assertEqual(
            events,
            ["reset", "compute", "step", "step_callback", "episode_callback", "episode_reset"],
        )
        self.assertEqual(e["official_time_s"], 0)
        self.assertEqual(e["completed_step_time_s"], 0.02)

    def test_atomic_checkpoint_and_changed_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "record.json"
            h.write(p, {"seed": 4})
            self.assertEqual(json.loads(p.read_text()), {"seed": 4})
            self.assertFalse(p.with_suffix(".tmp").exists())
            p.write_text("changed")
            with self.assertRaisesRegex(ValueError, "Provenance mismatch"):
                h.verify({"hashes": {str(p): "wrong"}})

    def test_deadline_no_worker_and_output_reuse_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            out = Path(d) / "out"
            p.write_text(json.dumps(dict(cases={"A": {}}, deadline=0)))
            with patch.object(h, "verify"), patch.object(h.subprocess, "Popen") as launch:
                with self.assertRaises(TimeoutError):
                    h.run(p, out)
                launch.assert_not_called()
                with self.assertRaises(FileExistsError):
                    h.run(p, out)
            self.assertEqual(
                json.loads((out / "status.json").read_text())["status"],
                "infrastructure_or_incomplete",
            )

    def test_malformed_audit_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "plan.json").write_text(json.dumps({"cases": {"A": {}}, "seeds": [1]}))
            (p / "episodes.json").write_text("[]")
            (p / "status.json").write_text('{"status":"completed"}')
            with self.assertRaises(AssertionError):
                a.audit(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)

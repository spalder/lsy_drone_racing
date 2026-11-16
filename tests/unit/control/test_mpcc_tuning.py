import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lsy_drone_racing.utils import load_config
from scripts import tune_mpcc


def test_tuning_isolates_parameters_and_reports_completed_evaluations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
):
    config = load_config(Path(__file__).parents[3] / "config/level2.toml")
    original = deepcopy(config.to_dict())
    env = MagicMock()
    monkeypatch.setattr(tune_mpcc, "create_environment", lambda _: env)
    seen = []

    def episode(_env, _cls, candidate: dict, seed: int) -> dict:
        settings = dict(candidate.controller.mpcc_experiment)
        settings["obstacle_clearance"] = candidate.controller.mpcc.obstacle_clearance
        defaults = dict(
            obstacle_clearance=0.26,
            observed_obstacle_clearance=None,
            gate_center_snap=1.0,
            over_gate_lift=0.0,
        )
        assert sum(settings[key] != defaults[key] for key in defaults) <= 1
        seen.append(seed)
        print("individual episode noise")
        os.write(1, b"native episode noise\n")
        success = seed == 1 and settings["over_gate_lift"] != 0.2
        return dict(
            seed=seed,
            outcome="success" if success else "terminated",
            elapsed_s=10.0 if success else 3.0,
            failed_solve_ticks=0,
        )

    monkeypatch.setattr(tune_mpcc, "run_episode", episode)
    report = tune_mpcc.tune(config, [1, 2], tune_mpcc.DEFAULT_GRIDS, tmp_path)
    assert config.to_dict() == original
    assert seen == [1, 2] * 20
    assert report["status"] == "completed"
    assert len(report["evaluations"]) == 20
    for result in report["evaluations"]:
        if result["parameter"] == "over_gate_lift" and result["value"] == 0.2:
            assert result["completion_rate"] == 0
            assert result["average_success_time_s"] is None
        else:
            assert result["completion_rate"] == 0.5
            assert result["average_success_time_s"] == 10.0
    assert json.loads((tmp_path / "report.json").read_text()) == report
    output = capfd.readouterr()
    assert len([line for line in output.out.splitlines() if line.startswith("[")]) == 20
    assert "episode noise" not in output.out + output.err
    assert "native episode noise" in (tmp_path / "simulation.log").read_text()
    assert str(tmp_path / "report.json") in output.out
    assert len((tmp_path / "summary.csv").read_text().splitlines()) == 21
    assert len((tmp_path / "episodes.csv").read_text().splitlines()) == 41
    env.close.assert_called_once()


def test_tuning_preserves_completed_results_if_a_later_evaluation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = load_config(Path(__file__).parents[3] / "config/level2.toml")
    env = MagicMock()
    monkeypatch.setattr(tune_mpcc, "create_environment", lambda _: env)

    def episode(_env, _cls, candidate: dict, seed: int) -> dict:
        if candidate.controller.mpcc_experiment.over_gate_lift > 0:
            raise RuntimeError("solver setup failed")
        return dict(seed=seed, outcome="success", elapsed_s=10.0, failed_solve_ticks=0)

    monkeypatch.setattr(tune_mpcc, "run_episode", episode)
    with pytest.raises(RuntimeError, match="solver setup failed"):
        tune_mpcc.tune(config, [1, 2], {"over_gate_lift": [0, 0.1]}, tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "failed"
    assert len(report["evaluations"]) == 1
    assert report["error"] == "RuntimeError: solver setup failed"
    env.close.assert_called_once()


def test_cli_accepts_two_height_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / "height-sweep"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tune_mpcc.py",
            "--parameters",
            "over_gate_lift",
            "--lift",
            "0",
            "0.05",
            "--seeds",
            "51",
            "52",
            "--output-dir",
            str(output),
        ],
    )
    runner = MagicMock()
    monkeypatch.setattr(tune_mpcc, "tune", runner)
    tune_mpcc.main()
    _, seeds, grids, directory = runner.call_args.args
    assert seeds == [51, 52]
    assert grids == {"over_gate_lift": [0.0, 0.05]}
    assert directory == output
    assert (output / "config.toml").exists()

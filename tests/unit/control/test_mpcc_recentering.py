"""Exercise the refinement grid, checkpoint recovery, freshness checks and audit."""

import json
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lsy_drone_racing.utils import load_config
from scripts import refine_mpcc_recentering as sweep


def test_refinement_resume_settings_and_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    config = load_config(sweep.ROOT / "config/level2.toml")
    original = deepcopy(config.to_dict())
    seeds = [900001, 900002]
    env = MagicMock()
    seen = []
    interrupted = False
    monkeypatch.setattr(sweep, "create_environment", lambda _: env)
    monkeypatch.setattr(sweep, "freshness_evidence", lambda *_: {"overlap": []})

    def episode(_env, cls: type, candidate: dict, seed: int) -> dict:
        nonlocal interrupted
        options = candidate.controller.mpcc_experiment.to_dict()
        assert options["over_gate_lift"] == 0.05
        assert options["observed_obstacle_clearance"] is None
        assert candidate.controller.mpcc.obstacle_clearance == 0.26
        value = options["gate_center_snap"]
        if value == 0.10 and seed == seeds[1] and not interrupted:
            interrupted = True
            raise RuntimeError("infrastructure test")
        seen.append((value, seed))
        cls.effective = dict(mpcc={"obstacle_clearance": 0.26}, mpcc_experiment=options)
        success = seed == seeds[0] or value >= 0.15
        print("individual episode chatter")
        os.write(1, b"native chatter\n")
        return dict(
            seed=seed,
            outcome="success" if success else "terminated",
            gates_passed=5 if success else 3,
            steps=500 if success else 100,
            elapsed_s=10.0 if success else 2.0,
            failed_solve_ticks=int(seed == seeds[1]),
            command_sha256="0" * 64,
        )

    monkeypatch.setattr(sweep, "run_episode", episode)
    with pytest.raises(RuntimeError, match="infrastructure test"):
        sweep.study(config, tmp_path, seeds=seeds)
    partial = json.loads((tmp_path / "report.json").read_text())
    assert sum(len(e["episodes"]) for e in partial["evaluations"]) == 5
    assert partial["status"] == "infrastructure_error"
    report = sweep.study(config, tmp_path, resume=True, seeds=seeds)
    assert sweep.VALUES == [0, 0.05, 0.10, 0.15, 0.20, 0.25]
    assert len(seen) == len(set(seen)) == 12
    assert config.to_dict() == original
    assert report["validation"]["validated_episodes"] == 12
    assert len(report["comparisons"]) == 15
    pair = next(c for c in report["comparisons"] if c["candidate"] == "recenter_0.15")
    assert pair["reference"] == "recenter_0.00"
    assert pair["newly_completed_seeds"] == [seeds[1]]
    assert pair["regressed_seeds"] == []
    assert pair["mean_paired_time_difference_s"] == 0
    assert pair["exact_paired_completion_p_value_unadjusted"] == 1
    audit = sweep.audit(tmp_path)
    assert audit["status"] == "validated"
    assert len((tmp_path / "episodes.csv").read_text().splitlines()) == 13
    assert len((tmp_path / "summary.csv").read_text().splitlines()) == 7
    assert len((tmp_path / "comparisons.csv").read_text().splitlines()) == 16
    output = capfd.readouterr()
    assert "chatter" not in output.out + output.err
    assert "native chatter" in (tmp_path / "simulation.log").read_text()
    sweep.study(config, tmp_path, resume=True, seeds=seeds)
    assert len(seen) == 12
    changed = deepcopy(config)
    changed.env.freq = 25
    with pytest.raises(ValueError, match="Resume rejected"):
        sweep.study(changed, tmp_path, resume=True, seeds=seeds)
    manifest = sweep.fingerprint(config, seeds)
    manifest["source_sha256"]["scripts/refine_mpcc_recentering.py"] = "changed"
    monkeypatch.setattr(sweep, "fingerprint", lambda *_: manifest)
    with pytest.raises(ValueError, match="Resume rejected"):
        sweep.study(config, tmp_path, resume=True, seeds=seeds)
    path = tmp_path / "episodes.csv"
    path.write_text(path.read_text().replace("10.0", "11.0", 1))
    with pytest.raises(AssertionError):
        sweep.audit(tmp_path)


def test_freshness_rejects_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sweep, "ROOT", tmp_path)
    prior = tmp_path / "logs/mpcc-tuning/prior"
    prior.mkdir(parents=True)
    path = prior / "report.json"
    path.write_text(json.dumps({"evaluations": [{"episodes": [{"seed": 201}]}]}))
    with pytest.raises(ValueError, match="Fresh seed overlap"):
        sweep.freshness_evidence([201], tmp_path / "new")
    evidence = sweep.freshness_evidence([202], tmp_path / "new")
    assert evidence["overlap"] == []
    assert len(evidence["prior_report_sha256"]) == 1


def test_exact_paired_completion_statistic() -> None:
    evaluations = []
    for index, name in enumerate(sweep.CASES):
        episodes = [
            dict(
                seed=seed,
                outcome="success" if index else "terminated",
                elapsed_s=10.0,
                failed_solve_ticks=0,
            )
            for seed in range(6)
        ]
        evaluations.append(
            dict(configuration=name, episodes=episodes, summary=sweep.common.summarize(episodes))
        )
    result = sweep.comparisons({"evaluations": evaluations})
    assert result[0]["exact_paired_completion_p_value_unadjusted"] == 0.03125
    assert result[0]["mean_paired_time_difference_s"] is None
    assert result[-1]["exact_paired_completion_p_value_unadjusted"] == 1.0
    assert result[-1]["mean_paired_time_difference_s"] == 0


def test_cli_import_order() -> None:
    import subprocess
    import sys

    environment = os.environ.copy()
    environment.pop("SCIPY_ARRAY_API", None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.refine_mpcc_recentering", "--help"],
        cwd=sweep.ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert "--resume" in result.stdout

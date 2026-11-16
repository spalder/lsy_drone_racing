"""Check the fixed matrix, interruption recovery, and matched-seed analysis."""

import json
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lsy_drone_racing.utils import load_config
from scripts import compare_mpcc as matrix


def test_matrix_resume_and_interactions(tmp_path, monkeypatch, capfd):
    config = load_config(matrix.ROOT / "config/level2.toml")
    original = deepcopy(config.to_dict())
    cohorts = {"diagnostic": [8, 9], "fresh": [101, 102]}
    seen = []
    env = MagicMock()
    monkeypatch.setattr(matrix, "create_environment", lambda _: env)
    interrupted = False

    def episode(_env, cls, candidate, seed):
        nonlocal interrupted
        settings = candidate.controller.mpcc_experiment.to_dict()
        key = (
            settings["gate_center_snap"],
            settings["over_gate_lift"],
            settings["observed_obstacle_clearance"],
        )
        assert key in matrix.CASES.values()
        assert candidate.controller.mpcc.obstacle_clearance == 0.26
        if key == matrix.CASES["height_only"] and seed == 9 and not interrupted:
            interrupted = True
            raise RuntimeError("infrastructure test")
        seen.append((key, seed))
        cls.effective = dict(mpcc={"obstacle_clearance": 0.26}, mpcc_experiment=settings)
        success = seed in [8, 101] or key[0] == 0
        print("sim chatter")
        os.write(1, b"native chatter\n")
        return dict(
            seed=seed,
            outcome="success" if success else "terminated",
            elapsed_s=10.0 if success else 2.0,
            steps=500 if success else 100,
            gates_passed=5 if success else 2,
            failed_solve_ticks=int(seed == 102),
        )

    monkeypatch.setattr(matrix, "run_episode", episode)
    with pytest.raises(RuntimeError, match="infrastructure test"):
        matrix.study(config, tmp_path, cohorts=cohorts)
    partial = json.loads((tmp_path / "report.json").read_text())
    assert partial["status"] == "infrastructure_error"
    assert len(partial["evaluations"][2]["episodes"]) == 1
    report = matrix.study(config, tmp_path, resume=True, cohorts=cohorts)
    assert len(seen) == len(set(seen)) == 32
    assert report["validation"]["validated_episodes"] == 32
    assert report["status"] == "completed"
    assert config.to_dict() == original
    pair = report["comparisons"]["fresh"][0]
    assert pair["newly_completed_seeds"] == [102]
    assert pair["regressed_seeds"] == []
    assert pair["mean_paired_time_difference_s"] == 0
    assert len((tmp_path / "episodes.csv").read_text().splitlines()) == 33
    assert len((tmp_path / "summary.csv").read_text().splitlines()) == 17
    assert "chatter" not in capfd.readouterr().out
    assert "native chatter" in (tmp_path / "simulation.log").read_text()
    matrix.study(config, tmp_path, resume=True, cohorts=cohorts)
    assert len(seen) == 32  # Completed episodes are never repeated.
    changed = deepcopy(config)
    changed.env.freq = 25
    with pytest.raises(ValueError, match="Resume rejected"):
        matrix.study(changed, tmp_path, resume=True, cohorts=cohorts)
    damaged = deepcopy(report)
    damaged["evaluations"][0]["summary"]["completed"] += 1
    with pytest.raises(AssertionError):
        matrix.validate(damaged, complete=True)


def test_paired_comparison_excludes_nonshared_successes():
    def evaluation(name, successes, times):
        episodes = [
            dict(
                seed=s,
                outcome="success" if s in successes else "terminated",
                elapsed_s=t,
                failed_solve_ticks=0,
            )
            for s, t in enumerate(times)
        ]
        return dict(configuration=name, episodes=episodes, summary=matrix.summarize(episodes))

    a = evaluation("a", {0, 1}, [10, 9, 2])
    b = evaluation("b", {1, 2}, [1, 8.5, 12])
    comparison = matrix.compare(a, b)
    assert comparison["newly_completed_seeds"] == [2]
    assert comparison["regressed_seeds"] == [0]
    assert comparison["shared_success_seeds"] == [1]
    assert comparison["mean_paired_time_difference_s"] == -0.5


def test_independent_audit_accepts_zero_finishes_and_rejects_csv_tampering(tmp_path):
    from scripts.analyze_mpcc_combinations import audit

    config = load_config(matrix.ROOT / "config/level2.toml")
    report = dict(
        status="completed",
        planned_episodes=896,
        manifest=matrix.fingerprint(config, matrix.COHORTS),
        infrastructure_errors=[],
        evaluations=[],
    )
    for cohort, seeds in matrix.COHORTS.items():
        for name, values in matrix.CASES.items():
            candidate = matrix.candidate_config(config, values)
            episodes = [
                dict(
                    seed=seed,
                    outcome="success" if cohort == "fresh" else "terminated",
                    steps=500,
                    elapsed_s=10.0,
                    gates_passed=5 if cohort == "fresh" else 2,
                    failed_solve_ticks=0,
                    command_sha256="0" * 64,
                )
                for seed in seeds
            ]
            report["evaluations"].append(
                dict(
                    cohort=cohort,
                    configuration=name,
                    config=candidate.to_dict(),
                    status="completed",
                    effective_settings=dict(
                        mpcc={"obstacle_clearance": 0.26},
                        mpcc_experiment=candidate.controller.mpcc_experiment.to_dict(),
                    ),
                    episodes=episodes,
                    summary=matrix.summarize(episodes),
                )
            )
    report["comparisons"] = matrix.analyze(report)
    matrix.write_report(tmp_path / "report.json", report)
    matrix.csv_exports(tmp_path, report)
    result = audit(tmp_path)
    assert result["episodes"] == 896
    assert "n/a" in (tmp_path / "analysis.md").read_text()
    path = tmp_path / "episodes.csv"
    path.write_text(path.read_text().replace("10.0", "11.0", 1))
    with pytest.raises(AssertionError):
        audit(tmp_path)

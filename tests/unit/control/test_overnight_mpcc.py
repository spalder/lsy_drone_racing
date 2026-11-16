"""Exercise the autonomous study without spending its reserved simulation seeds."""

from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lsy_drone_racing.utils import load_config
from scripts import overnight_mpcc as run
from scripts import overnight_mpcc_analysis as analysis


def fake_environment() -> MagicMock:
    """Mock the actual environment timeout."""
    env = MagicMock()
    env.unwrapped.settings.max_episode_steps = 1500
    return env


def fake_episode(env: object, config: dict, seed: int) -> dict:
    """Deterministic measured outcome, including a failed episode and fake chatter."""
    settings = config.controller.mpcc.to_dict()
    success = seed % 2 == 0
    steps = (500 if settings["reference_speed"] == 1.3 else 480) if success else 100
    print("simulator chatter")
    os.write(1, b"native chatter\n")
    return dict(
        seed=seed,
        outcome="success" if success else "terminated",
        gates_passed=5 if success else 3,
        steps=steps,
        elapsed_s=steps / 50,
        failed_solve_ticks=0,
        command_sha256="0" * 64,
        control_p50_ms=1.0,
        control_p95_ms=2.0,
        whole_call_p99_ms=3.0,
        whole_call_max_ms=4.0,
        whole_call_overruns=0,
        replan_calls=2,
        replan_max_ms=4.0,
        valid_solve_ticks=steps,
        progress_cap_ticks=0,
        attitude_bound_ticks=0,
        max_progress_speed=1.3,
        wall_s=0.01,
        effective_settings=dict(mpcc=settings, mpcc_experiment=run.GEOMETRY),
    )


def config() -> dict:
    """Load the real baseline config."""
    return load_config(run.ROOT / "config/level2.toml")


def test_grid_and_geometry() -> None:
    original = config()
    before = deepcopy(original.to_dict())
    cases = run.screening_cases()
    assert len(cases) == 23
    assert len(run.unique([run.BASE, dict(run.BASE, contour_weight=400)])) == 1
    for values in cases.values():
        candidate = run.candidate_config(original, values, 10000)
        assert candidate.controller.mpcc_experiment.to_dict() == run.GEOMETRY
        assert candidate.controller.mpcc.obstacle_clearance == 0.26
        assert candidate.controller.mpcc.to_dict() == values
        assert sum(values[k] != run.BASE[k] for k in values) <= 1
    assert original.to_dict() == before
    with pytest.raises(AssertionError):
        run.case({"obstacle_clearance": 0.3})
    with pytest.raises(AssertionError):
        run.case({"horizon_steps": 40.5})


def test_recovery_audit_and_suppression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    cases = [run.BASE, dict(run.BASE, reference_speed=1.4)]
    choice = run.decision(cases, "test")
    seeds = [900000, 900001]
    count = 0
    seen = []

    def episode(env: object, candidate: dict, seed: int) -> dict:
        nonlocal count
        count += 1
        if count == 3:
            raise RuntimeError("infrastructure interruption")
        seen.append((run.name(candidate.controller.mpcc.to_dict()), seed))
        return fake_episode(env, candidate, seed)

    with pytest.raises(RuntimeError):
        run.evaluate(config(), tmp_path, seeds, choice, episode_fn=episode)
    assert sum(len(e["episodes"]) for e in run.read(tmp_path / "report.json")["evaluations"]) == 2
    report = run.evaluate(config(), tmp_path, seeds, choice, episode_fn=episode)
    assert len(seen) == len(set(seen)) == 4
    assert len(report["infrastructure_errors"]) == 1
    audit = analysis.audit_stage(tmp_path)
    assert audit["episodes"] == 4
    assert report["evaluations"][0]["summary"]["penalized_mean_s"] == 20
    assert run.rankings(report)[0]["eligible"]
    assert run.rankings(report)[0]["paired_s"] < 0
    unchanged = run.digest(report)
    run.evaluate(config(), tmp_path, seeds, choice, episode_fn=episode)
    assert run.digest(run.read(tmp_path / "report.json")) == unchanged
    with pytest.raises(ValueError, match="mismatch"):
        run.evaluate(config(), tmp_path, [900002], choice, episode_fn=episode)
    changed = config()
    changed.sim.freq = 250
    with pytest.raises(ValueError, match="mismatch"):
        run.evaluate(changed, tmp_path, seeds, choice, episode_fn=episode)
    out = capfd.readouterr()
    assert "chatter" not in out.out + out.err
    assert "native chatter" in (tmp_path / "simulation.log").read_text()
    csv = tmp_path / "episodes.csv"
    csv.write_text(csv.read_text().replace("10.0", "11.0", 1))
    with pytest.raises(AssertionError):
        analysis.audit_stage(tmp_path)


def test_deadline_and_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    now = [10.0]
    monkeypatch.setattr(run.time, "time", lambda: now[0])
    calls = []

    def episode(env: object, candidate: dict, seed: int) -> dict:
        calls.append(seed)
        now[0] = 30
        return fake_episode(env, candidate, seed)

    choice = run.decision([run.BASE, dict(run.BASE, reference_speed=1.4)], "deadline")
    report = run.evaluate(
        config(), tmp_path, [900000, 900001], choice, deadline=20, episode_fn=episode
    )
    assert calls == [900000]
    assert report["status"] == "budget_exhausted"
    assert not report["infrastructure_errors"]
    state = dict(
        budget={"reporting_reserve_s": 900},
        current_stage="challenges",
        reports=[],
        calibration={},
        target_deadline_epoch=30000,
        hard_deadline_epoch=36000,
    )
    values = list(run.screening_cases().values())[:10]
    selected, budget = run.fit_budget(values, list(range(80)), state, now=24000)
    assert not selected
    assert budget["reserve_s"] > 600 * 5.7
    state["current_stage"] = "validation"
    selected, budget = run.fit_budget(
        values[:2], list(range(300)), state, now=25000, optional=False
    )
    assert len(selected) == 2
    assert budget["reserve_s"] == 900
    selected, _ = run.fit_budget(values[:2], list(range(300)), state, now=35500, optional=False)
    assert not selected


def test_freshness_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "ROOT", tmp_path)
    p = tmp_path / "logs/mpcc-tuning/old"
    p.mkdir(parents=True)
    run.write_report(p / "report.json", {"evaluations": [{"episodes": [{"seed": 10000}]}]})
    plan = run.make_plan(config_from_repo())
    allocated = plan["smoke_seeds"] + [s for stage in plan["stages"] for s in stage["seeds"]]
    assert min(allocated) >= 11000
    assert len(allocated) == len(set(allocated)) == 1912
    assert plan["failure_penalty_s"] == 30


def config_from_repo() -> dict:
    """Load config independently of a patched artifact root."""
    return load_config(Path(__file__).resolve().parents[3] / "config/level2.toml")


def test_end_to_end_adaptation_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute all six synthetic stages, freeze holdout, and audit completed resume."""
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    cfg = config()
    plan = run.make_plan(cfg)
    # Tiny disjoint cohorts exercise full orchestration without real simulations.
    for i, spec in enumerate(plan["stages"]):
        spec["seeds"] = [900000 + 2 * i, 900001 + 2 * i]
    (prepared / "config.toml").write_text((run.ROOT / "config/level2.toml").read_text())
    run.write_report(prepared / "plan.json", plan)
    run.write_report(prepared / "manifest.json", run.fingerprint(cfg, plan))
    run.write_report(prepared / "preflight.json", {"status": "passed"})
    run.write_report(prepared / "calibration.json", {"episode_wall_s_by_horizon": {"40": 5.7}})
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    original_configuration_episodes = run.configuration_episodes

    def fake_worker(
        candidate: dict, seeds: list[int], deadline: float, log: object, episode_fn: object = None
    ) -> object:
        return original_configuration_episodes(candidate, seeds, deadline, log, fake_episode)

    monkeypatch.setattr(run, "configuration_episodes", fake_worker)
    directory = tmp_path / "study"
    run.execute(prepared, directory)
    state = run.read(directory / "study.json")
    assert state["status"] == "completed"
    assert len(state["decisions"]["validation"]["cases"]) == 2
    selection = state["decisions"]["validation"]
    assert selection["frozen_at"] <= run.read(directory / "validation/report.json")["started_at"]
    baseline_deadline = state["hard_deadline_epoch"]
    episode_hashes = {
        s: run.digest(
            [e["episodes"] for e in run.read(directory / s / "report.json")["evaluations"]]
        )
        for s in run.STAGES
    }
    run.execute(prepared, directory, resume=True)
    assert run.read(directory / "study.json")["hard_deadline_epoch"] == baseline_deadline
    assert episode_hashes == {
        s: run.digest(
            [e["episodes"] for e in run.read(directory / s / "report.json")["evaluations"]]
        )
        for s in run.STAGES
    }
    result = analysis.audit_study(directory)
    assert result["status"] == "completed"
    assert result["recommended"] != "incumbent"
    assert result["validation"]["completion_difference"] == 0
    assert result["validation"]["paired_mean_bootstrap_95ci_s"][1] < 0
    # Explicit source mismatch refuses resume before any episode runs.
    manifest = run.read(prepared / "manifest.json")
    manifest["source_sha256"]["scripts/overnight_mpcc.py"] = "changed"
    run.write_report(prepared / "manifest.json", manifest)
    with pytest.raises(ValueError, match="fingerprint"):
        run.execute(prepared, directory, resume=True)


def test_statistics_zero_discordance_and_no_shared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    report = run.evaluate(
        config(),
        tmp_path,
        [900001, 900003],
        run.decision([run.BASE, dict(run.BASE, reference_speed=1.4)], "no shared"),
        episode_fn=fake_episode,
    )
    a, b = report["evaluations"]
    c = analysis.paired(a, b, bootstrap=True)
    assert c["paired_mean_s"] is None
    assert c["paired_mean_bootstrap_95ci_s"] is None
    assert c["exact_completion_p"] == 1
    assert (
        c["completion_difference_conservative_95ci"][0]
        < 0
        < c["completion_difference_conservative_95ci"][1]
    )


def test_cli_cold_import() -> None:
    env = os.environ.copy()
    env.pop("SCIPY_ARRAY_API", None)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.overnight_mpcc", "--help"],
        cwd=run.ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "prepare" in result.stdout and "run" in result.stdout


def test_eligibility_rejects_latency_numerics_and_completion_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    choice = run.decision([run.BASE, dict(run.BASE, reference_speed=1.4)], "eligibility")
    report = run.evaluate(config(), tmp_path, [900000, 900001], choice, episode_fn=fake_episode)
    assert run.rankings(report)[0]["eligible"]
    candidate = report["evaluations"][1]
    for field, value in [("latency_eligible", False), ("failed_solve_ticks", 1), ("completed", 0)]:
        saved = candidate["summary"][field]
        candidate["summary"][field] = value
        assert not run.rankings(report)[0]["eligible"]
        candidate["summary"][field] = saved
    assert run.rankings(report)[0]["eligible"]


def test_challenge_cap_requires_measured_saturation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "create_environment", lambda _: fake_environment())
    report = run.evaluate(
        config(),
        tmp_path,
        [900000, 900001],
        run.decision([run.BASE, dict(run.BASE, reference_speed=1.4)], "cap"),
        episode_fn=fake_episode,
    )
    completed = {"screening": report, "combinations": report}
    values, reason = run.stage_proposal("challenges", completed)
    assert "skipped" in reason and all(v["max_speed"] == 1.8 for v in values)
    report["evaluations"][1]["summary"]["progress_cap_fraction"] = 0.02
    values, reason = run.stage_proposal("challenges", completed)
    assert "enabled" in reason
    assert {v["max_speed"] for v in values} >= {1.8, 2.0, 2.2}
    assert len(values) <= 10


def test_budget_scales_with_horizon_and_never_truncates_screening() -> None:
    state = dict(
        budget={"reporting_reserve_s": 900},
        current_stage="screening",
        reports=[],
        calibration={"40": 6.0},
        target_deadline_epoch=10000,
        hard_deadline_epoch=10000,
    )
    assert run.episode_forecast(state, dict(run.BASE, horizon_steps=60)) > run.episode_forecast(
        state, run.BASE
    )
    selected, forecast = run.fit_budget(
        list(run.screening_cases().values()), list(range(40)), state, now=0, optional=False
    )
    assert not selected
    assert forecast["accepted_cases"] == 0

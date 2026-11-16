"""Adaptive decisions tested with synthetic outcomes; never creates simulations."""

from copy import deepcopy

import pytest

from scripts import mpcc_max_speed_safety as study


def row(settings: dict, finishes: int, seconds: float = 7.0) -> dict:
    return dict(
        settings=settings,
        configuration=str(settings),
        summary=dict(
            completed=finishes,
            completion_rate=finishes / 16,
            failed_solve_ticks=0,
            latency_eligible=True,
            average_success_time_s=seconds,
        ),
        episodes=[
            dict(
                seed=i,
                outcome="success" if i < finishes else "terminated",
                elapsed_s=seconds,
                gates_passed=5 if i < finishes else 0,
            )
            for i in range(16)
        ],
    )


def test_mutability_and_fixed_reference():
    plan = study.harness.read(study.PLAN)
    b = study.baseline(plan)
    c = study.config_for(plan, dict(b, max_speed=3.5), 90000)
    assert c["controller"]["mpcc"]["reference_speed"] == 1.8
    assert c["env"]["track"] == plan["baseline_config"]["env"]["track"]
    with pytest.raises(AssertionError):
        study.config_for(plan, dict(b, reference_speed=2.0), 90000)


def test_frontier_and_recovery():
    b = study.baseline(study.harness.read(study.PLAN))
    fast = dict(b, max_speed=2.4)
    report = dict(evaluations=[row(b, 12), row(fast, 8, 6.8)])
    assert study.frontier(report) == (fast, True)
    repairs = dict(evaluations=[row(fast, 8, 6.8), row(dict(fast, gate_center_snap=0.5), 11, 6.9)])
    assert len(study.recovery_rows(repairs)) == 1
    repairs["evaluations"][1]["summary"]["failed_solve_ticks"] = 1
    assert not study.recovery_rows(repairs)


def test_no_gain_and_budget():
    b = study.baseline(study.harness.read(study.PLAN))
    assert study.frontier(dict(evaluations=[row(b, 12), row(dict(b, max_speed=2.4), 12)])) == (
        b,
        False,
    )
    assert study.delta(row(b, 4), row(b, 4)) is None
    assert not study.fit([b, b], 16, 100, 6.5, False)
    assert len(study.fit([b, b, b], 50, 700, 6.5, True)) == 2


def test_proposal_paths_and_finalists():
    plan = study.harness.read(study.PLAN)
    b = study.baseline(plan)
    probe = dict(evaluations=[row(b, 12), row(dict(b, max_speed=2.4), 9, 6.8)])
    reports = {"cap_probe": probe}
    singles, _ = study.proposals("safety_singles", reports, plan)
    assert len(singles) == 6
    reports["safety_singles"] = dict(
        evaluations=[row(c, 12 if i else 9, 6.8) for i, c in enumerate(singles)]
    )
    combined, _ = study.proposals("safety_combinations", reports, plan)
    assert len(combined) == 3
    assert sum(combined[2][k] != combined[0][k] for k in study.FIELDS[1:]) >= 2
    caps, _ = study.proposals("cap_reescalation", reports, plan)
    assert len(caps) == 3
    finals, _ = study.proposals("fresh_validation", reports, plan)
    assert finals[0] == b
    assert 2 <= len(finals) <= 3
    for c in combined + caps + finals:
        study.config_for(plan, c, 1)
    before = deepcopy(reports)
    study.proposals("fresh_validation", reports, plan)
    assert reports == before

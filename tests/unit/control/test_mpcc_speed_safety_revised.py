"""Tests for the explicitly revised speed ladder, without simulations."""

import pytest

from scripts import mpcc_speed_safety_revised as study


def test_ladder_and_safety_only_mutability():
    plan = study.harness.read(study.PLAN)
    cases, _ = study.proposals("cap_probe", {}, plan)
    assert [c["reference_speed"] for c in cases] == [1.8, 2.0, 2.2, 2.4]
    for c in cases:
        config = study.config_for(plan, c, 123)
        assert config["controller"]["mpcc"]["max_speed"] == round(c["reference_speed"] + 0.3, 1)
        assert config["controller"]["mpcc"]["reference_speed"] == c["reference_speed"]
        assert set(config["controller"]["mpcc_experiment"]) == {
            "gate_center_snap",
            "over_gate_lift",
            "observed_obstacle_clearance",
        }
    with pytest.raises(AssertionError):
        study.config_for(plan, dict(cases[0], max_speed=2.5), 1)


def test_new_reservations_and_remaining_budget():
    plan = study.harness.read(study.PLAN)
    b = study.baseline(plan)
    assert not study.fit([b, b, b], 50, 500, 6.5, True)
    assert len(study.fit([b, b, b], 50, 1005, 6.5, True)) == 3
    assert plan["revision"]["reuse_measured_episodes"] is False
    assert plan["revision"]["original_started_epoch"] == 1793698813

"""Safety boundaries for adaptive simulation configs; no simulations are launched."""

from copy import deepcopy

import pytest

from scripts import mpcc_adaptive_batch as batch


def test_supported_changes_preserve_environment():
    base = batch.h.read(batch.PARENT)["evaluations"][1]["config"]
    saved = deepcopy(base)
    c = batch.config_for(base, dict(max_angle=0.7, contour_weight=600, horizon_steps=50))
    assert base == saved
    assert c["env"] == base["env"] and c["sim"] == base["sim"]
    assert c["controller"]["mpcc"]["reference_speed"] == 2.2
    assert c["controller"]["mpcc"]["max_angle"] == 0.7


@pytest.mark.parametrize(
    "changes",
    [{"algorithm": "new"}, {"horizon_steps": 40.5}, {"max_angle": 2.0}, {"reference_speed": 5.0}],
)
def test_reject_unsupported(changes: dict):
    base = batch.h.read(batch.PARENT)["evaluations"][1]["config"]
    with pytest.raises(AssertionError):
        batch.config_for(base, changes)

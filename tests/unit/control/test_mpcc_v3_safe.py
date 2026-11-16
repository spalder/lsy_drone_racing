"""Fixed safe settings, discovery, and the CasADi random-name regression."""

import inspect
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import casadi as ca
import numpy as np
import pytest
from crazyflow.dynamics import Dynamics, load_params

from lsy_drone_racing.control import attitude_mpcc_v3_safe as entry
from lsy_drone_racing.control import mpcc_v3_safe_settings as safe
from lsy_drone_racing.control import mpcc_v3_safe_solver as solver
from lsy_drone_racing.control import mpcc_v3_settings as parent
from lsy_drone_racing.utils import load_config, load_controller

ROOT = Path(__file__).resolve().parents[3]


def test_safe_speed_and_preserved_formulation_settings() -> None:
    changes = {k: v for k, v in safe.MPCC_SETTINGS.items() if v != parent.MPCC_SETTINGS[k]}
    assert changes == {"reference_speed": 2.8, "max_speed": 3.0}
    assert safe.GEOMETRY_SETTINGS == parent.GEOMETRY_SETTINGS
    assert safe.PREDICTION_SETTINGS == parent.PREDICTION_SETTINGS
    assert safe.NUMERICAL_SETTINGS == parent.NUMERICAL_SETTINGS
    assert safe.MPCC_SETTINGS["attitude_slew_weight"] == 0.02


def test_loader_and_fixed_constructor() -> None:
    found = load_controller(Path(entry.__file__))
    assert found.__name__ == "AttitudeMPCCV3Safe"
    assert list(inspect.signature(found).parameters) == ["obs", "info", "config"]


@pytest.mark.parametrize("section", ["mpcc", "mpcc_experiment", "prediction", "numerics"])
def test_override_fails_before_constructing_solver(section: str) -> None:
    config = deepcopy(load_config(ROOT / "config/level2.toml"))
    config.controller[section] = {"unexpected": 99}
    with pytest.raises(ValueError, match="embedded settings"):
        entry.AttitudeMPCCV3Safe({}, {}, config)


def test_random_directory_underscores_never_enter_casadi_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reproduce the exact invalid-name cause without compiling a solver."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(solver.tempfile, "mkdtemp", lambda **_: str(tmp_path / "instance__tf3mvb9"))
    captured = {}

    def backend(ocp: object, **kwargs: object) -> MagicMock:
        captured["ocp"] = ocp
        captured["function"] = ca.Function(
            ocp.model.name + "_dyn_disc_phi_fun",
            [ocp.model.x, ocp.model.u, ocp.model.p],
            [ocp.model.disc_dyn_expr],
        )
        return MagicMock()

    monkeypatch.setattr(solver, "AcadosOcpSolver", backend)
    monkeypatch.setattr(solver, "restore_progress_bounds", lambda *_: None)
    config = load_config(ROOT / "config/level2.toml")
    params = load_params(Dynamics.so_rpy, config.sim.drone)
    solver.create_mpcc_solver(
        0.02,
        params,
        safe.MPCC_SETTINGS,
        12.2,
        prediction=safe.PREDICTION_SETTINGS,
        numerics=safe.NUMERICAL_SETTINGS,
    )
    ocp = captured["ocp"]
    assert "__" not in ocp.model.name
    assert "safe" in ocp.model.name
    assert captured["function"].name().startswith(ocp.model.name)
    assert ocp.cost.yref[14] == 2.8
    assert ocp.constraints.ubu[4] == 3.0
    np.testing.assert_array_equal(ocp.constraints.ug, [0.975, 1.025, 0.975])

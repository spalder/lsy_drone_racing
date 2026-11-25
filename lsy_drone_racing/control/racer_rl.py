"""RL racer controller: runs the actor trained by train_racer.py with numpy (no torch needed).

Loads the actor.npz given by the RACER_ACTOR environment variable, or the newest one under
runs/racer/. Observations and the action mapping come from racer_core, shared with training.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lsy_drone_racing.control import Controller
from lsy_drone_racing.control.racer_core import ActionMap, build_obs

if TYPE_CHECKING:
    from numpy.typing import NDArray


def find_actor() -> Path:
    """Path of the actor export to load."""
    if path := os.environ.get("RACER_ACTOR"):
        return Path(path)
    runs = sorted((Path(__file__).parents[2] / "runs" / "racer").glob("*/actor.npz"))
    if not runs:
        raise FileNotFoundError("No actor.npz under runs/racer/ and RACER_ACTOR is not set")
    return runs[-1]


class RacerRL(Controller):
    """Deterministic (mean) action of the trained actor."""

    def __init__(self, obs: dict[str, NDArray[np.floating]], info: dict, config: dict):
        """Load the actor weights and the frozen observation statistics."""
        super().__init__(obs, info, config)
        path = find_actor()
        print(f"RacerRL: loading {path}")
        actor = np.load(path)
        self.layers = [(actor[f"W{i}"], actor[f"b{i}"]) for i in range(3)]
        self.obs_mean, self.obs_std = actor["obs_mean"], actor["obs_std"]
        self.obs_clip = float(actor["obs_clip"])
        # Thrust mapping the actor was trained with; exports without it used 10.19 / 8.6
        c_offset = float(actor["c_offset"]) if "c_offset" in actor else 10.19
        c_scale = float(actor["c_scale"]) if "c_scale" in actor else 8.6
        self.action_map = ActionMap(config.sim.drone, config.sim.dynamics, c_offset, c_scale)

    def compute_control(
        self, obs: dict[str, NDArray[np.floating]], info: dict | None = None
    ) -> NDArray[np.floating]:
        """Attitude command [roll, pitch, yaw, thrust] from the network's mean action."""
        # The true mass is unknown in deployment: the mass input is the nominal mass (0.5).
        # Actors trained before the mass input take the first 50 entries.
        x = np.asarray(build_obs({k: np.asarray(v)[None] for k, v in obs.items()}))[0]
        x = x[: self.obs_mean.shape[0]]
        h = np.clip((x - self.obs_mean) / self.obs_std, -self.obs_clip, self.obs_clip)
        for W, b in self.layers:
            h = np.tanh(W @ h + b)  # Every actor layer, including the output, ends in tanh
        return np.asarray(self.action_map(h), dtype=np.float32)

    def step_callback(
        self,
        action: NDArray[np.floating],
        obs: dict[str, NDArray[np.floating]],
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict,
    ) -> bool:
        """The policy never ends the episode itself; the env ends it on finish, crash or timeout."""
        return False

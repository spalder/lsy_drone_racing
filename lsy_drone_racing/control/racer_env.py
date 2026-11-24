"""Training environment for the RL racer: race env with network actions, observations and reward.

Reward (Song et al. 2023, eq. 5), computed from the true env state:
    progress = |g - p_prev| - |g - p| toward the true center of the target gate before the step
    r = progress - rate_coef * |omega|      normal step
    r = progress - ... + finish_bonus       step in which the last gate is passed
    r = -crash_penalty                      step in which the drone crashes (contact or out of bounds)
    r = 0                                   step after finishing (env disables the drone one step late)

The env auto-resets one step after a termination. That step ignores the action and returns the first
observation of a new episode; info["valid"] is False for it and it must be masked out of training.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import jax
import jax.numpy as jp
import numpy as np
from gymnasium import spaces
from gymnasium.vector.utils import batch_space

from lsy_drone_racing.control.racer_core import OBS_DIM, ActionMap, build_obs
from lsy_drone_racing.envs.drone_race import VecDroneRaceEnv

if TYPE_CHECKING:
    from jax import Array

    from lsy_drone_racing.envs.race_core import EnvData


@partial(jax.jit, static_argnames=("rate_coef", "crash_penalty", "finish_bonus"))
def racer_reward(
    prev: EnvData, data: EnvData, rate_coef: float, crash_penalty: float, finish_bonus: float
) -> tuple[Array, dict[str, Array]]:
    """Reward and episode flags for the transition prev -> data."""
    n_pass = prev.gate_sequence.shape[-1]
    n_prev = prev.n_gates_passed[:, 0]
    n_now = data.n_gates_passed[:, 0]
    batch = jp.arange(n_prev.shape[0])
    # Distances to the target gate before the step, also on the step in which it is passed
    gate_id = jp.broadcast_to(prev.gate_sequence, (n_prev.shape[0], n_pass))[
        batch, jp.clip(n_prev, 0, n_pass - 1)
    ]
    gate = prev.gates_pos[batch, gate_id]
    p_prev = prev.sim_data.states.pos[:, 0]
    p = data.sim_data.states.pos[:, 0]
    progress = jp.linalg.norm(gate - p_prev, axis=-1) - jp.linalg.norm(gate - p, axis=-1)
    rate_pen = rate_coef * jp.linalg.norm(data.sim_data.states.ang_vel[:, 0], axis=-1)

    just_finished = (n_prev < n_pass) & (n_now >= n_pass)
    after_finish = n_prev >= n_pass
    crashed = data.disabled_drones[:, 0] & ~after_finish & ~just_finished
    reward = progress - rate_pen + finish_bonus * just_finished
    reward = jp.where(crashed, -crash_penalty, reward)
    reward = jp.where(after_finish, 0.0, reward)
    info = {
        "valid": ~prev.marked_for_reset,
        "finished": just_finished,
        "crashed": crashed,
        "gates_passed": n_now,
        "progress": progress,
    }
    return reward, info


class RacerEnv(VecDroneRaceEnv):
    """Vectorized race env taking network actions in [-1, 1]^3 and returning (N, 50) observations."""

    def __init__(
        self,
        *args: object,
        rate_coef: float = 0.01,
        crash_penalty: float = 10.0,
        finish_bonus: float = 10.0,
        **kwargs: object,
    ):
        """Create the race env in attitude mode. Remaining arguments go to VecDroneRaceEnv."""
        super().__init__(*args, control_mode="attitude", **kwargs)
        self._action_map = jax.jit(ActionMap(self.sim.drone, self.sim.dynamics).__call__)
        self._build_obs = jax.jit(build_obs)
        self._reward = partial(
            racer_reward,
            rate_coef=rate_coef,
            crash_penalty=crash_penalty,
            finish_bonus=finish_bonus,
        )
        self.single_action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)
        self.action_space = batch_space(self.single_action_space, self.num_envs)
        self.single_observation_space = spaces.Box(-np.inf, np.inf, shape=(OBS_DIM,))
        self.observation_space = batch_space(self.single_observation_space, self.num_envs)

    def reset(self, seed: int | None = None, options: dict | None = None) -> tuple[Array, dict]:
        """Reset all worlds and return network observations."""
        obs, info = super().reset(seed=seed, options=options)
        return self._build_obs(obs), info

    def step(self, action: Array) -> tuple[Array, Array, Array, Array, dict]:
        """Step all worlds with network actions (N, 3)."""
        prev = self.data
        obs, _, terminated, truncated, _ = super().step(self._action_map(action))
        reward, info = self._reward(prev, self.data)
        return self._build_obs(obs), reward, terminated, truncated, info

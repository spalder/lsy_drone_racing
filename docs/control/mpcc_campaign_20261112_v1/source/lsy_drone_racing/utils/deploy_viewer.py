"""Live visualization for real-world deployments."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lsy_drone_racing.envs.race_core import RaceCoreEnv


class DeployViewer:
    """Mirror the measured race state in a single-world CPU simulation."""

    def __init__(self, env: RaceCoreEnv):
        """Take ownership of a render-only core environment.

        Args:
            env: Single-world, single-drone CPU environment used for rendering.
        """
        self._env = env

    def warm_up(self):
        """Compile rendering and open the window before the real drone is armed."""
        data = self._env.data
        sim_data = self._env.sim.data.replace(
            core=self._env.sim.data.core.replace(
                mjx_synced=self._env.sim.data.core.mjx_synced.at[...].set(False)
            )
        )
        self._env.data = data.replace(sim_data=sim_data)
        self._env.render()

    def set_track(self, gates_pos: NDArray, gates_quat: NDArray, obstacles_pos: NDArray):
        """Update the simulation with the measured track poses.

        Args:
            gates_pos: Gate positions of shape (n_gates, 3).
            gates_quat: Gate quaternions in SciPy xyzw order with shape (n_gates, 4).
            obstacles_pos: Obstacle positions of shape (n_obstacles, 3).
        """
        data = self._env.data
        self._env.data = data.replace(
            gates_pos=data.gates_pos.at[0].set(gates_pos),
            gates_quat=data.gates_quat.at[0].set(gates_quat),
            obstacles_pos=data.obstacles_pos.at[0].set(obstacles_pos),
        )

    def update(self, pos: NDArray, quat: NDArray):
        """Update the measured drone pose and render it.

        Args:
            pos: Drone position of shape (3,).
            quat: Drone quaternion in SciPy xyzw order with shape (4,).
        """
        data = self._env.data
        sim_data = data.sim_data
        states = sim_data.states.replace(
            pos=sim_data.states.pos.at[0, 0].set(pos), quat=sim_data.states.quat.at[0, 0].set(quat)
        )
        sim_data = sim_data.replace(
            states=states,
            core=sim_data.core.replace(mjx_synced=sim_data.core.mjx_synced.at[...].set(False)),
        )
        self._env.data = data.replace(sim_data=sim_data)
        self._env.render()

    def close(self):
        """Close the simulation and its viewer window."""
        self._env.close()

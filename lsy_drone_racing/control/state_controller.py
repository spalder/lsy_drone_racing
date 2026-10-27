"""Controller that follows a pre-defined trajectory.

It uses a cubic spline interpolation to generate a smooth trajectory through a series of waypoints.
At each time step, the controller computes the next desired position by evaluating the spline.

.. note::
    The waypoints are hard-coded in the controller for demonstration purposes. In practice, you
    would need to generate the splines adaptively based on the track layout, and recompute the
    trajectory if you receive updated gate and obstacle poses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from crazyflow.sim.visualize import draw_line, draw_points
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation as R

from lsy_drone_racing.control import Controller

if TYPE_CHECKING:
    from crazyflow import Sim
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

DRONE_RADIUS = 0.086  # m, collision sphere of the cf21B_500
OBSTACLE_RADIUS = 0.015  # m


class StateController(Controller):
    """State controller following a pre-defined trajectory."""

    def __init__(self, obs: dict[str, NDArray[np.floating]], info: dict, config: dict):
        """Initialization of the controller.

        Args:
            obs: The initial observation of the environment's state. See the environment's
                observation space for details.
            info: The initial environment information from the reset.
            config: The race configuration. See the config files for details. Contains additional
                information such as disturbance configurations, randomizations, etc.
        """
        super().__init__(obs, info, config)
        self._freq = config.env.freq

        # Waypoints based on the attitude controller's, with extra via points that keep the path
        # clear of the obstacles under (almost) worst-case randomization. Obstacles 0 and 2 sit on
        # the approach/exit lines of gates 0 and 2, so full worst-case clearance there would cost
        # gate clearance instead.
        start_pos = obs["pos"]
        waypoints = np.array(
            [
                start_pos,
                [-1.71, 0.43, 0.69],
                [0.3, 0.35, 0.7],
                [1.27, -0.45, 0.8],
                [1.28, 0.32, 1.07],
                [0.85, 0.85, 1.2],
                [-0.3, 0.1, 0.7],
                [-1.2, -0.2, 0.8],
                [-1.35, 0.14, 1.03],
                [-1.14, -0.22, 1.2],
                [-0.31, -0.51, 1.23],
                [-0.0, -0.7, 1.2],
                [1.45, 0.22, 1.2],
                [1.29, 0.38, 1.2],
                [1.05, 0.75, 1.2],
                [0.25, 1.25, 1.2],
            ]
        )
        # Gate each waypoint is attached to, or -1 for free waypoints. Attached waypoints move
        # rigidly with their gate when its true pose is revealed.
        self._waypoint_gates = np.array([-1, -1, 0, -1, -1, 1, -1, 2, -1, -1, -1, 3, -1, -1, 1, -1])
        self._t_total = 23.0  # s
        # Original 12 waypoints are evenly spaced in time, the via points sit halfway in between
        t_base = np.linspace(0, self._t_total, 12)
        self._t_waypoints = np.sort(
            np.concatenate((t_base, 0.5 * (t_base[[3, 6, 7, 9]] + t_base[[4, 7, 8, 10]])))
        )
        self._des_pos_spline = CubicSpline(self._t_waypoints, waypoints)
        self._des_vel_spline = self._des_pos_spline.derivative()
        self._t_spline_start = 0.0
        self._last_yaw = 0.0

        # Express the gate-attached waypoints in their nominal gate frame
        self._waypoints = waypoints
        self._waypoints_local = np.zeros_like(waypoints)
        for i, gate in enumerate(self._waypoint_gates):
            if gate >= 0:
                rot = R.from_quat(obs["gates_quat"][gate])
                self._waypoints_local[i] = rot.inv().apply(waypoints[i] - obs["gates_pos"][gate])
        self._gates_visited = np.array(obs["gates_visited"], dtype=bool)

        randomizations = config.env.get("randomizations") or {}
        obstacle_rand = randomizations.get("obstacle_pos")
        max_shift = np.array(obstacle_rand.kwargs.maxval[:2]) if obstacle_rand else np.zeros(2)
        self._check_obstacle_clearance(obs["obstacles_pos"], max_shift)

        self._tick = 0
        self._finished = False

    def compute_control(
        self, obs: dict[str, NDArray[np.floating]], info: dict | None = None
    ) -> NDArray[np.floating]:
        """Compute the next desired state of the drone.

        Args:
            obs: The current observation of the environment. See the environment's observation space
                for details.
            info: Optional additional information as a dictionary.

        Returns:
            The drone state [x, y, z, vx, vy, vz, ax, ay, az, qx, qy, qz, qw, wx, wy, wz] as a
            numpy array.
        """
        t = min(self._tick / self._freq, self._t_total)
        if t >= self._t_total:  # Maximum duration reached
            self._finished = True

        gates_visited = np.array(obs["gates_visited"], dtype=bool)
        if np.any(gates_visited & ~self._gates_visited):
            self._replan(t, obs["gates_pos"], obs["gates_quat"])
        self._gates_visited = gates_visited

        des_pos = self._des_pos_spline(t)
        des_vel = self._des_vel_spline(t)
        des_acc = self._des_pos_spline(t, 2)
        # Face the direction of travel. Keep the last yaw at low horizontal speeds, where atan2
        # would be noisy.
        if np.linalg.norm(des_vel[:2]) > 0.05:
            self._last_yaw = np.arctan2(des_vel[1], des_vel[0])
        des_quat = R.from_euler("z", self._last_yaw).as_quat()
        action = np.concatenate(
            (des_pos, des_vel, des_acc, des_quat, np.zeros(3)), dtype=np.float32
        )
        return action

    def _check_obstacle_clearance(self, obstacles_pos: NDArray, max_shift: NDArray):
        """Warn if the spline passes an obstacle closer than its worst-case displacement allows.

        The obstacles can be shifted inside a box of +-max_shift around their nominal position. The
        worst-case shift towards the path is the projection of that box onto the direction from
        the obstacle to the closest point on the path.
        """
        ts = np.linspace(0, self._t_total, 3000)
        pos = self._des_pos_spline(ts)[:, :2]
        for i, obstacle in enumerate(obstacles_pos[:, :2]):
            dist = np.linalg.norm(pos - obstacle, axis=-1)
            k = np.argmin(dist)
            normal = (pos[k] - obstacle) / dist[k]
            required = np.abs(normal) @ max_shift + DRONE_RADIUS + OBSTACLE_RADIUS
            if dist[k] < required:
                logger.warning(
                    f"Obstacle {i}: path passes at {dist[k]:.3f} m (t={ts[k]:.1f} s), worst case "
                    f"needs {required:.3f} m"
                )

    def _replan(self, t: float, gates_pos: NDArray, gates_quat: NDArray):
        """Move gate-attached waypoints to the observed gate poses and refit the remaining spline.

        The new spline starts at the current setpoint with the current desired velocity, so the
        reference stays continuous.
        """
        for i, gate in enumerate(self._waypoint_gates):
            if gate >= 0:
                rot = R.from_quat(gates_quat[gate])
                self._waypoints[i] = gates_pos[gate] + rot.apply(self._waypoints_local[i])
        # Skip waypoints that are (almost) reached already
        remaining = self._t_waypoints > t + 0.05
        if not np.any(remaining):
            return
        t_knots = np.concatenate(([t], self._t_waypoints[remaining]))
        knots = np.concatenate(([self._des_pos_spline(t)], self._waypoints[remaining]))
        v0 = self._des_vel_spline(t)
        self._des_pos_spline = CubicSpline(t_knots, knots, bc_type=((1, v0), "not-a-knot"))
        self._des_vel_spline = self._des_pos_spline.derivative()
        self._t_spline_start = t

    def step_callback(
        self,
        action: NDArray[np.floating],
        obs: dict[str, NDArray[np.floating]],
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict,
    ) -> bool:
        """Increment the time step counter.

        Returns:
            True if the controller is finished, False otherwise.
        """
        self._tick += 1
        return self._finished

    def episode_callback(self):
        """Reset the internal state."""
        self._tick = 0
        self._last_yaw = 0.0

    def render_callback(self, sim: Sim):
        """Visualize the desired trajectory and the current setpoint."""
        setpoint = self._des_pos_spline(self._tick / self._freq).reshape(1, -1)
        draw_points(sim, setpoint, rgba=(1.0, 0.0, 0.0, 1.0), size=0.02)
        trajectory = self._des_pos_spline(np.linspace(self._t_spline_start, self._t_total, 100))
        draw_line(sim, trajectory, rgba=(0.0, 1.0, 0.0, 1.0))

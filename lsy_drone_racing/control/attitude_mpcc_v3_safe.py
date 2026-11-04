# Copyright (c) 2024 Learning Systems and Robotics Lab (LSY)
# SPDX-License-Identifier: MIT
# Derived from the project MPCC implementation; see repository LICENSE.

"""Conservative speed-demand variant of the fixed expanded-soft MPCC v3 safe controller."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from crazyflow.dynamics import Dynamics, load_params
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from crazyflow.sim.visualize import draw_line, draw_points
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import Controller
from lsy_drone_racing.control.mpcc_v3_geometry import TrackGeometry
from lsy_drone_racing.control.mpcc_v3_model import (
    ThrustGainFilter,
    validate_numerics,
    validate_prediction,
)
from lsy_drone_racing.control.mpcc_v3_safe_solver import (
    create_mpcc_solver,
    create_path,
    gate_anchors,
)

if TYPE_CHECKING:
    from crazyflow import Sim
    from numpy.typing import NDArray

from lsy_drone_racing.control.mpcc_v3_safe_settings import (
    GEOMETRY_SETTINGS,
    MPCC_SETTINGS,
    NUMERICAL_SETTINGS,
    PREDICTION_SETTINGS,
)

logger = logging.getLogger(__name__)


class AttitudeMPCCV3Safe(Controller):
    """Optimize geometric progress using the audited fixed Level 2 settings."""

    def __init__(self, obs: dict[str, NDArray], info: dict, config: dict):
        """Initialize the path, augmented model, and solver."""
        super().__init__(obs, info, config)
        if config.env.freq != 50:
            raise ValueError("MPCC v3 safe requires 50 Hz control.")
        if config.env.control_mode != "attitude":
            raise ValueError("AttitudeMPCC requires env.control_mode = 'attitude'.")
        # Fail explicitly instead of silently accepting research tuning overrides.
        if any(
            config.controller.get(k) for k in ("mpcc", "mpcc_experiment", "prediction", "numerics")
        ):
            raise ValueError(
                "MPCC v3 safe uses embedded settings; remove controller tuning sections."
            )
        if list(config.env.track.gate_order) != [1, 2, 3, 4, 2]:
            raise ValueError("MPCC v3 safe requires the nominal Level 2 gate order.")
        self.settings, geometry = dict(MPCC_SETTINGS), dict(GEOMETRY_SETTINGS)
        self.prediction_settings = validate_prediction(PREDICTION_SETTINGS)
        self.numerical_settings = validate_numerics(NUMERICAL_SETTINGS)
        self.gate_center_snap = geometry["gate_center_snap"]
        self.over_gate_lift = geometry["over_gate_lift"]
        self.observed_obstacle_clearance = geometry["observed_obstacle_clearance"]
        self._N = self.settings["horizon_steps"]
        self._dt = 1.0 / config.env.freq
        self._path = create_path(obs["pos"])
        self._path_derivative = self._path.derivative()
        self._length = float(self._path.x[-1])
        self._base_path = self._path
        crossings, ids = gate_anchors(self._path, config.env.track)
        self._gate_offsets = np.tile(
            [-self.settings["gate_offset"], 0, self.settings["gate_offset"]], len(ids)
        )
        self._gate_ids = np.repeat(ids, 3)
        self._gate_directions = np.repeat(np.sign(config.env.track.gate_order), 3)
        self._anchors = np.r_[0, np.repeat(crossings[1:-1], 3) + self._gate_offsets, self._length]
        # Local Gaussian deformations preserve the original route between gates.
        self._warp_width = self.settings["warp_width"]
        delta = self._anchors[:, None] - self._anchors[None, :]
        self._warp_inverse = np.linalg.inv(np.exp(-0.5 * (delta / self._warp_width) ** 2))
        delta = self._base_path.x[:, None] - self._anchors[None, :]
        self._warp_basis = np.exp(-0.5 * (delta / self._warp_width) ** 2)
        self.track_geometry = TrackGeometry(config)
        self._path_geometry_revision = -1
        self._update_gate_path(obs)
        self.drone_params = load_params(Dynamics.so_rpy, config.sim.drone)
        self._solver, self._ocp = create_mpcc_solver(
            self._dt,
            self.drone_params,
            self.settings,
            self._length,
            prediction=self.prediction_settings,
            numerics=self.numerical_settings,
        )
        self._nominal_hover = float(
            (
                self.drone_params["mass"] * -self.drone_params["gravity_vec"][-1]
                - self.drone_params["acc_coef"]
            )
            / self.drone_params["cmd_f_coef"]
        )
        self.reset()

    def _update_gate_path(self, obs: dict[str, NDArray]):
        """Update the nominal route from persistent public gate and pole observations."""
        self.last_geometry_update = self.track_geometry.update(obs)
        if self._gate_ids is None or self._path_geometry_revision == self.track_geometry.revision:
            return
        gates = np.array([gate.planning_pose.position for gate in self.track_geometry.gates])
        quaternions = np.array(
            [gate.planning_pose.quaternion for gate in self.track_geometry.gates]
        )
        obstacles = np.array(
            [pole.planning_pose.position for pole in self.track_geometry.obstacles]
        )
        obstacle_clearances = [
            self.observed_obstacle_clearance
            if self._path_geometry_revision >= 0
            and pole.detected
            and self.observed_obstacle_clearance is not None
            else self.settings["obstacle_clearance"]
            for pole in self.track_geometry.obstacles
        ]
        correction = np.zeros((len(self._anchors), 3))
        normals = Rotation.from_quat(quaternions[self._gate_ids]).as_matrix()[:, :, 0]
        targets = (
            gates[self._gate_ids] + normals * (self._gate_offsets * self._gate_directions)[:, None]
        )
        correction[1:-1] = targets - self._base_path(self._anchors[1:-1])
        weights = self._warp_inverse @ correction
        points = self._base_path(self._base_path.x) + self._warp_basis @ weights
        if self.over_gate_lift:
            # Nominal-course experiment: lift the return between the third
            # crossing's departure anchor and the fourth crossing's approach.
            # A smooth bump leaves gate targets and progress coordinates intact.
            start, end = self._anchors[9:11]
            phase = np.clip((self._base_path.x - start) / (end - start), 0, 1)
            points[:, 2] += self.over_gate_lift * np.sin(np.pi * phase) ** 2
        # Repel path sections from poles, projecting each correction to zero at
        # the gate centers, start, and finish. Re-evaluate after each correction.
        for _ in range(self.settings["pole_passes"]):
            path = CubicSpline(self._base_path.x, points)
            offsets = np.zeros_like(points)
            anchor_offsets = np.zeros((len(self._anchors), 3))
            for obstacle, clearance in zip(obstacles, obstacle_clearances):
                distance = np.linalg.norm(points[:, :2] - obstacle[:2], axis=1)
                minima = (
                    np.flatnonzero(
                        (distance[1:-1] <= distance[:-2]) & (distance[1:-1] < distance[2:])
                    )
                    + 1
                )
                for index in minima:
                    if (
                        distance[index] >= clearance
                        or points[index, 2] > obstacle[2] + self.settings["pole_vertical_buffer"]
                    ):
                        continue
                    direction = points[index, :2] - obstacle[:2]
                    if distance[index] < 1e-6:
                        tangent = path.derivative()(self._base_path.x[index])[:2]
                        direction = np.array([-tangent[1], tangent[0]])
                    direction /= max(np.linalg.norm(direction), 1e-9)
                    shift = np.r_[direction * (clearance - distance[index]), 0]
                    progress = self._base_path.x[index]
                    offsets += (
                        np.exp(
                            -0.5
                            * ((self._base_path.x - progress) / self.settings["pole_width"]) ** 2
                        )[:, None]
                        * shift
                    )
                    anchor_offsets += (
                        np.exp(
                            -0.5 * ((self._anchors - progress) / self.settings["pole_width"]) ** 2
                        )[:, None]
                        * shift
                    )
            points += offsets - self._warp_basis @ (self._warp_inverse @ anchor_offsets)
        # The nominal route climbs immediately after gate 3. A translated gate
        # can put its top bar underneath that climb, even after the center has
        # been crossed. Keep the departing path clear of the frame until it has
        # moved outside the frame's lateral/vertical extent.
        for index in range(1, len(self._anchors) - 1, 3):
            gate_id = self._gate_ids[index]
            rotation = Rotation.from_quat(quaternions[gate_id]).as_matrix()
            direction = self._gate_directions[index]
            local = (points - gates[gate_id]) @ rotation
            after = self._base_path.x - self._anchors[index + 1]
            required_depth = self.settings["departure_depth"] * (
                1 - np.exp(-((np.maximum(after, 0) / self.settings["departure_rise"]) ** 2))
            )
            influence = np.clip(
                (self.settings["influence_extent"] - after) / self.settings["influence_taper"], 0, 1
            ) * (after > 0)
            influence *= np.clip(
                (self.settings["lateral_extent"] - np.abs(local[:, 1]))
                / self.settings["lateral_taper"],
                0,
                1,
            )
            influence *= np.clip(
                (self.settings["vertical_extent"] - np.abs(local[:, 2]))
                / self.settings["vertical_taper"],
                0,
                1,
            )
            shift = np.maximum(required_depth - local[:, 0] * direction, 0) * influence
            points += shift[:, None] * rotation[:, 0] * direction
        self._path = CubicSpline(self._base_path.x, points)
        self._path_derivative = self._path.derivative()
        self._path_geometry_revision = self.track_geometry.revision

    def reset(self):
        """Clear virtual progress and warm starts before restarting the same path."""
        self._progress = 0.0
        self._prediction = None
        self._inputs = None
        self._failures = 0
        self.last_solver_status = None
        self._gain_filter = ThrustGainFilter(self.prediction_settings, self.settings, self._dt)
        self._thrust_gain = self._gain_filter.gain
        self._hover = self._nominal_hover / self._thrust_gain
        self._last_action = np.array([0.0, 0.0, 0.0, self._hover])
        self.adaptation_sample_accepted = False
        self._solver.reset()

    def episode_reset(self):
        """Reset the controller between episodes (new tracks need a new instance)."""
        self.track_geometry.reset()
        self.reset()

    def _update_thrust_gain(self, obs: dict[str, NDArray]):
        """Filter acceleration-based thrust effectiveness, excluding ground contact.

        This estimates thrust effectiveness. Attitude calibration remains fixed.
        """
        self._gain_filter.observe(obs, self._last_action[3], self.drone_params)
        self._thrust_gain = self._gain_filter.gain
        self.adaptation_sample_accepted = self._gain_filter.accepted
        self._hover = self._nominal_hover / self._thrust_gain

    def compute_control(self, obs: dict[str, NDArray], info: dict | None = None) -> NDArray:
        """Solve the contouring problem without modifying the observation dictionary."""
        self._update_thrust_gain(obs)
        self._update_gate_path(obs)
        rpy = Rotation.from_quat(obs["quat"]).as_euler("xyz")
        rates = ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])
        state = np.concatenate(
            (obs["pos"], rpy, obs["vel"], rates, [self._progress], self._last_action)
        )
        if self._prediction is None:
            prediction = np.tile(state, (self._N + 1, 1))
            prediction[:, 12] = np.minimum(
                self._progress
                + np.arange(self._N + 1) * self._dt * self.settings["reference_speed"],
                self._length,
            )
            inputs = np.tile([0, 0, 0, self._hover, 0], (self._N, 1))
        else:
            prediction = np.vstack((self._prediction[1:], self._prediction[-1]))
            inputs = np.vstack((self._inputs[1:], self._inputs[-1]))
        prediction[0] = state
        self._solver.set_flat("u", inputs.ravel())
        self._solver.set_flat("x", prediction.ravel())
        self._solver.set(0, "lbx", state)
        self._solver.set(0, "ubx", state)
        # Refresh local path linearizations on all three RTI passes so references follow
        # the optimized progress, rather than advancing according to wall time.
        reference = self._ocp.cost.yref.copy()
        reference[13] = self._hover
        for k in range(self._N):
            self._solver.set(k, "yref", reference)
        for _ in range(self.settings["rti_passes"]):
            progress = np.clip(prediction[:, 12], 0, self._length)
            positions = self._path(progress)
            tangents = self._path_derivative(progress)
            parameters = np.column_stack(
                (positions, tangents, progress, np.full(self._N + 1, self._thrust_gain))
            )
            for k in range(self._N + 1):
                self._solver.set(k, "p", parameters[k])
            self.last_solver_status = self._solver.solve()
            if self.last_solver_status != 0:
                break
            prediction = self._solver.get_flat("x").reshape(self._N + 1, -1)
            if not np.all(np.isfinite(prediction)):
                break
        inputs = self._solver.get_flat("u").reshape(self._N, -1)
        if (
            self.last_solver_status != 0
            or not np.all(np.isfinite(prediction))
            or not np.all(np.isfinite(inputs))
        ):
            self._failures += 1
            if self._failures == 1:
                logger.warning(
                    "MPCC solve failed (status %s); using hover.", self.last_solver_status
                )
            self._prediction = self._inputs = None
            self._solver.reset()
            self._last_action = np.array([0.0, 0.0, 0.0, self._hover])
            return self._last_action.copy()
        self._failures = 0
        self._prediction, self._inputs = prediction, inputs
        self._progress = float(np.clip(prediction[1, 12], 0, self._length))
        self._last_action = inputs[0, :4].copy()
        return self._last_action.copy()

    def step_callback(
        self,
        action: NDArray,
        obs: dict[str, NDArray],
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict,
    ) -> bool:
        """Finish only when the environment reports all required gate passages."""
        return bool(obs["n_gates_passed"] >= len(obs["gate_sequence"]))

    def render_callback(self, sim: Sim):
        """Draw the geometric path, predicted flight, and virtual progress marker."""
        draw_line(sim, self._path(np.linspace(0, self._length, 120)), rgba=(0, 1, 0, 1))
        if self._prediction is not None:
            draw_line(sim, self._prediction[:, :3], rgba=(0, 0.4, 1, 1))
        draw_points(sim, self._path(self._progress).reshape(1, 3), rgba=(1, 0, 0, 1), size=0.02)

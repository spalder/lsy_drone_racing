"""Small path-correction experiments, keeping the archived MPCC optimizer intact.

Only the local correction method is copied from attitude_mpcc.py. With defaults,
its arithmetic is unchanged. This module is limited to the nominal course.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.attitude_mpcc import AttitudeMPCC

if TYPE_CHECKING:
    from numpy.typing import NDArray


class ExperimentalMPCC(AttitudeMPCC):
    """Expose cheap geometry changes via ``[controller.mpcc_experiment]``.

    ``gate_center_snap``: 1 reproduces centering; 0 retains the previous crossing
    projected inside the usable opening. ``over_gate_lift`` adds a smooth vertical
    bump in meters after the third crossing. Pole distance continues to use
    ``[controller.mpcc].obstacle_clearance`` (distance from the pole axis).
    ``observed_obstacle_clearance`` optionally overrides that distance for revealed
    poles on replans, leaving the initial path correction unchanged.
    """

    def __init__(self, obs: dict, info: dict, config: dict):
        """Read experimental knobs before the base constructor builds its path."""
        config = deepcopy(config)
        options = dict(config.controller.get("mpcc_experiment", {}))
        self.gate_center_snap = options.pop("gate_center_snap", 1.0)
        self.over_gate_lift = options.pop("over_gate_lift", 0.0)
        self.observed_obstacle_clearance = options.pop("observed_obstacle_clearance", None)
        if options:
            raise ValueError(f"Unknown experimental settings: {sorted(options)}")
        if not np.isfinite(self.gate_center_snap) or not 0 <= self.gate_center_snap <= 1:
            raise ValueError("gate_center_snap must be finite and between 0 and 1.")
        if not np.isfinite(self.over_gate_lift) or self.over_gate_lift < 0:
            raise ValueError("over_gate_lift must be finite and nonnegative.")
        if self.observed_obstacle_clearance is not None and (
            not np.isfinite(self.observed_obstacle_clearance)
            or self.observed_obstacle_clearance <= 0
        ):
            raise ValueError("observed_obstacle_clearance must be positive and finite.")
        if config.controller.get("mpcc", {}).get("waypoints") is not None:
            raise ValueError("ExperimentalMPCC requires the default course waypoints.")
        if list(config.env.track.gate_order) != [1, 2, 3, 4, 2]:
            raise ValueError("ExperimentalMPCC requires the nominal course gate order.")
        super().__init__(obs, info, config)

    def _update_gate_path(self, obs: dict[str, NDArray]):
        """Experiment with crossing targets, climb height, and pole separation.

        This preserves the nominal route and gate anchors. It is a local path
        adjustment, not a collision-free global planner or a safety guarantee.
        """
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
        if self.gate_center_snap < 1:
            # Project the previous crossing onto the new gate plane, then clip
            # inside the opening eroded by an all-attitude vehicle radius.
            for first in range(0, len(self._gate_ids), 3):
                gate = self.track_geometry.gates[self._gate_ids[first]]
                rotation = Rotation.from_quat(gate.planning_pose.quaternion).as_matrix()
                shapes = {shape.name: shape for shape in gate.primitives}
                low = np.array(
                    [
                        shapes["col_left"].center[1] + shapes["col_left"].size[1],
                        shapes["col_bottom"].center[2] + shapes["col_bottom"].size[2],
                    ]
                )
                high = np.array(
                    [
                        shapes["col_right"].center[1] - shapes["col_right"].size[1],
                        shapes["col_top"].center[2] - shapes["col_top"].size[2],
                    ]
                )
                margin = self.track_geometry.vehicle.radius_bound + 0.02
                low, high = low + margin, high - margin
                if np.any(low > high):
                    raise ValueError("Vehicle envelope does not fit inside the gate opening.")
                previous = self._path(self._anchors[first + 2])
                local = (previous - gate.planning_pose.position) @ rotation
                yz = np.clip((1 - self.gate_center_snap) * local[1:], low, high)
                targets[first : first + 3] += rotation[:, 1:] @ yz
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
        for _ in range(8):
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
                    if distance[index] >= clearance or points[index, 2] > obstacle[2] + 0.1:
                        continue
                    direction = points[index, :2] - obstacle[:2]
                    if distance[index] < 1e-6:
                        tangent = path.derivative()(self._base_path.x[index])[:2]
                        direction = np.array([-tangent[1], tangent[0]])
                    direction /= max(np.linalg.norm(direction), 1e-9)
                    shift = np.r_[direction * (clearance - distance[index]), 0]
                    progress = self._base_path.x[index]
                    offsets += (
                        np.exp(-0.5 * ((self._base_path.x - progress) / 0.35) ** 2)[:, None] * shift
                    )
                    anchor_offsets += (
                        np.exp(-0.5 * ((self._anchors - progress) / 0.35) ** 2)[:, None] * shift
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
            required_depth = 0.25 * (1 - np.exp(-((np.maximum(after, 0) / 0.18) ** 2)))
            influence = np.clip((1.2 - after) / 0.2, 0, 1) * (after > 0)
            influence *= np.clip((0.60 - np.abs(local[:, 1])) / 0.12, 0, 1)
            influence *= np.clip((0.60 - np.abs(local[:, 2])) / 0.12, 0, 1)
            shift = np.maximum(required_depth - local[:, 0] * direction, 0) * influence
            points += shift[:, None] * rotation[:, 0] * direction
        self._path = CubicSpline(self._base_path.x, points)
        self._path_derivative = self._path.derivative()
        self._path_geometry_revision = self.track_geometry.revision

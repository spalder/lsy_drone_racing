"""MPCC++ controller: model predictive contouring control with tunnel constraints.

Implements the main ideas of Krinner, Romero et al., "MPCC++: Model Predictive Contouring Control
for Time-Optimal Flight with Safety Constraints" (RSS 2024) on the attitude interface:

* Progress maximization along a centerline through the gates (MPCC). The centerline is linearized
  around the progress predicted by the previous solution, so the path enters the solver only as
  stage parameters and can be replaced at runtime when gates or obstacles are observed.
* A tunnel around the centerline as soft half-space constraints (track constraint). Instead of the
  paper's two-level sigmoid width, the tunnel extents are computed from the distance to the actual
  collision geometry of gates, gate stands, obstacles and arena bounds. This shrinks the tunnel at
  gate openings and next to poles, and widens it in free space.
* A residual acceleration term in the dynamics. Instead of a regression fitted offline, it is
  estimated online from the one-step prediction error, which absorbs the randomized mass and the
  mismatch between the identified attitude model and the simulator.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import casadi as ca
import numpy as np
from acados_template import AcadosModel, AcadosOcp, AcadosOcpSolver
from acados_template.builders import ocp_get_default_cmake_builder
from crazyflow.dynamics import Dynamics, load_params
from crazyflow.dynamics.utils import rotation
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d
from scipy.spatial.transform import Rotation as R

from lsy_drone_racing.control import Controller

if TYPE_CHECKING:
    from collections.abc import Iterator

    from crazyflow import Sim
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Collision geometry, see envs/assets/gate.xml and the cf21B_500 model
DRONE_RADIUS = 0.1  # m, half diagonal of the 0.07 x 0.07 m collision box
DRONE_HALF_WIDTH, DRONE_HALF_HEIGHT = 0.07, 0.02  # m, collision box of the cf21B_500
YAW_TOLERANCE = 0.1  # rad, the yaw command is limited to this range
GATE_BOXES = np.array(  # center (gate frame), half extents
    [
        [0.0, 0.0, 0.28, 0.01, 0.36, 0.08],
        [0.0, 0.0, -0.28, 0.01, 0.36, 0.08],
        [0.0, -0.28, 0.0, 0.01, 0.08, 0.36],
        [0.0, 0.28, 0.0, 0.01, 0.08, 0.36],
        [0.0, 0.0, -0.86, 0.05, 0.05, 0.5],  # stand
    ]
)
OBSTACLE_RADIUS = 0.015
OBSTACLE_HEIGHT = 1.52

# Route through the nominal level 2 track. It is assembled from sections with alternative variants,
# selected by the route_* settings. Each leg (0: start -> first gate, i: gate i-1 -> gate i) has
# via points and a straight passage through its gate:
#   via: world points on the nominal track and the gate they are attached to (-1 for none).
#     Attached points move rigidly with their gate when its true pose is observed.
#   angle: angle of the passage line relative to the gate normal, counter-clockwise, deg. Gates 0
#     and 3 have a pole on their axis in front of them and gate 2 one behind it.
#   entry: distance of the entry point before the gate center, m.
ROUTE_SECTIONS = {
    "route_start": {  # Start -> gate 0
        # Detour north of pole 0 and pass gate 0 heading south
        0: {0: {"via": [([-0.3, 1.12, 0.6], -1), ([0.22, 1.0, 0.65], 0)], "angle": -30.0}},
        # Nearly straight from the start, south of pole 0, like the example MPC route
        1: {0: {"via": [([-0.6, 0.78, 0.5], -1)], "angle": 18.0}},
    },
    "route_gate1": {  # Both approaches of gate 1
        # Wide swing east of pole 1 with a long straight final approach
        0: {
            1: {"via": [([1.3, -0.15, 0.95], 1), ([1.6, 0.15, 1.15], 1)], "entry": 0.45},
            4: {"via": [([1.6, 0.15, 1.2], 1)], "entry": 0.45},
        },
        # Tighter swing with a shorter final approach
        1: {
            1: {"via": [([1.3, -0.15, 0.95], 1), ([1.45, 0.2, 1.12], 1)], "entry": 0.3},
            4: {"via": [([1.45, 0.15, 1.2], 1)], "entry": 0.3},
        },
    },
    "route_gate23": {  # Gate 1 -> gate 2 -> gate 3
        # Turn around to the south after gate 2, clear of its frame and of the pole behind it
        0: {
            2: {"via": [([-0.2, 0.25, 0.9], 2)], "angle": 40.0},
            3: {
                "via": [
                    ([-1.4, -0.7, 0.85], 2),
                    ([-1.15, -1.15, 1.1], 2),
                    ([-0.65, -1.15, 1.2], 3),
                ],
                "angle": 35.0,
                "entry": 0.4,
            },
        }
    },
}
GATE_OFFSET = 0.25  # m, distance of the default entry and exit points from the gate center


def build_route(settings: dict) -> dict:
    """Assemble the legs of the route from the selected section variants."""
    legs = {}
    for section, variants in ROUTE_SECTIONS.items():
        legs.update(variants[int(settings[section])])
    return legs


EXTENSION = 0.8  # m, path extension after the last gate


def _box_distance(points: NDArray, center: NDArray, half: NDArray, rot: R) -> NDArray:
    """Distance from points to an oriented box."""
    local = rot.inv().apply(points - center)
    return np.linalg.norm(np.maximum(np.abs(local) - half, 0.0), axis=-1)


def clearance(
    points: NDArray,
    gates_pos: NDArray,
    gates_quat: NDArray,
    obstacles_pos: NDArray,
    limits: tuple,
    obstacles_inflation: NDArray | None = None,
) -> NDArray:
    """Distance from points to the closest collision geometry or arena bound.

    Obstacles can be inflated by their position uncertainty.
    """
    if obstacles_inflation is None:
        obstacles_inflation = np.zeros(len(obstacles_pos))
    low, high = limits
    dist = np.min(np.concatenate((points - low, high - points), axis=-1), axis=-1)
    for pos, quat in zip(gates_pos, gates_quat):
        rot = R.from_quat(quat)
        for box in GATE_BOXES:
            center = pos + rot.apply(box[:3])
            dist = np.minimum(dist, _box_distance(points, center, box[3:], rot))
    for pos, inflation in zip(obstacles_pos, obstacles_inflation):
        radius = OBSTACLE_RADIUS + inflation
        horizontal = np.linalg.norm(points[:, :2] - pos[:2], axis=-1) - radius
        above = np.maximum(points[:, 2] - OBSTACLE_HEIGHT, 0.0)
        dist = np.minimum(dist, np.hypot(np.maximum(horizontal, 0.0), above))
    return dist


def drone_footprint(max_tilt: float, gates_quat: NDArray) -> tuple[float, float, NDArray]:
    """Horizontal and vertical half extents of the drone's collision box.

    The box is flat and its yaw stays close to zero. Vertically it extends at most by its tilted
    half width. Horizontally, the extent towards a gate frame depends on the angle between the box
    and the gate: 0.07 m for aligned gates, 0.099 m for gates at 45 deg.

    Returns:
        The horizontal extent in any direction, the vertical extent, and the horizontal extent
        towards each gate frame.
    """
    vertical = DRONE_HALF_WIDTH * np.sin(max_tilt) + DRONE_HALF_HEIGHT * np.cos(max_tilt)
    yaws = R.from_quat(gates_quat).as_euler("xyz")[:, 2]
    delta = np.linspace(-YAW_TOLERANCE, YAW_TOLERANCE, 21)
    angles = yaws[:, None] + delta[None, :]
    support = DRONE_HALF_WIDTH * (np.abs(np.cos(angles)) + np.abs(np.sin(angles)))
    return DRONE_RADIUS, vertical, support.max(axis=1)


def free_space(
    points: NDArray,
    gates_pos: NDArray,
    gates_quat: NDArray,
    obstacles_pos: NDArray,
    limits: tuple,
    obstacles_inflation: NDArray,
    footprint: tuple[float, float, NDArray],
    gates_inflation: NDArray | None = None,
) -> NDArray:
    """Distance by which the drone centered at the points could move before it touches anything.

    Distances are measured in a metric where the vertical axis is stretched by the ratio of the
    horizontal to the vertical extent of the drone, so a flat drone may get closer to geometry
    above and below than to geometry beside it. Gate frames can be inflated by their position
    uncertainty (in the gate frame), which shrinks the opening to the part that is free for every
    possible gate position.
    """
    if gates_inflation is None:
        gates_inflation = np.zeros((len(gates_pos), 3))
    horizontal, vertical, gate_extent = footprint
    k = horizontal / vertical
    low, high = limits
    free = np.min(np.concatenate((points[:, :2] - low[:2], high[:2] - points[:, :2]), axis=-1), -1)
    free = np.minimum(free - horizontal, k * (high[2] - points[:, 2] - vertical))
    for pos, quat, extent, inflation in zip(gates_pos, gates_quat, gate_extent, gates_inflation):
        rot = R.from_quat(quat)
        scale = np.array([1.0, 1.0, extent / vertical])
        for box in GATE_BOXES:
            local = rot.inv().apply(points - pos - rot.apply(box[:3]))
            half = box[3:] + inflation
            dist = np.linalg.norm(np.maximum(np.abs(local) - half, 0.0) * scale, axis=-1)
            free = np.minimum(free, dist - extent)
    for pos, inflation in zip(obstacles_pos, obstacles_inflation):
        radius = OBSTACLE_RADIUS + inflation
        side = np.maximum(np.linalg.norm(points[:, :2] - pos[:2], axis=-1) - radius, 0.0)
        above = k * np.maximum(points[:, 2] - OBSTACLE_HEIGHT, 0.0)
        free = np.minimum(free, np.hypot(side, above) - horizontal)
    return free


def racing_line(
    track: Track,
    start: NDArray,
    gates_pos: NDArray,
    gates_quat: NDArray,
    obstacles_pos: NDArray,
    gate_order: NDArray,
    settings: dict,
    params: dict,
) -> dict | None:
    """Compute a time-optimal racing line and convert it into a route of gate-attached via points.

    A point mass with the thrust and tilt limits of the drone flies through the gate centers in
    minimum time while keeping a distance to the poles. The hand-made route serves as initial
    guess. Attitude dynamics are neglected, so the tilt limit is chosen below the one of the MPC.

    Returns:
        The route in the format of build_route with via points in the gate frames, or None if the
        optimization failed.
    """
    n, legs = int(settings["racing_line_nodes"]), len(gate_order)
    gravity = np.asarray(params["gravity_vec"])
    f_max = 4 * params["thrust_max"] * params["cmd_f_coef"] / params["mass"]
    cos_tilt = np.cos(settings["racing_line_tilt"])
    clearance = settings["racing_line_clearance"]
    rots = R.from_quat(gates_quat).as_matrix()
    bounds = np.concatenate(([0.0], track.gate_s))

    opti = ca.Opti()
    T = opti.variable(legs)
    P = [opti.variable(3, n + 1) for _ in range(legs)]
    V = [opti.variable(3, n + 1) for _ in range(legs)]
    A = [opti.variable(3, n) for _ in range(legs)]
    opti.minimize(ca.sum1(T))
    opti.subject_to(T >= 0.1)
    opti.subject_to(P[0][:, 0] == start)
    opti.subject_to(V[0][:, 0] == 0)
    for k, gate in enumerate(gate_order):
        dt = T[k] / n
        if k > 0:
            opti.subject_to(P[k][:, 0] == P[k - 1][:, -1])
            opti.subject_to(V[k][:, 0] == V[k - 1][:, -1])
        for j in range(n):
            a = A[k][:, j]
            opti.subject_to(P[k][:, j + 1] == P[k][:, j] + V[k][:, j] * dt + 0.5 * a * dt**2)
            opti.subject_to(V[k][:, j + 1] == V[k][:, j] + a * dt)
            f = a - gravity  # Thrust acceleration
            opti.subject_to(ca.sumsqr(f) <= f_max**2)
            opti.subject_to(f[2] >= cos_tilt * ca.sqrt(ca.sumsqr(f) + 1e-6))
        for j in range(1, n + 1):
            # Stay above the floor, except right after the take off from the ground
            if k > 0 or j > n // 4:
                opti.subject_to(P[k][2, j] >= settings["racing_line_min_height"])
            for pole in obstacles_pos:
                opti.subject_to(ca.sumsqr(P[k][:2, j] - pole[:2]) >= clearance**2)
        # Through the gate plane close to the center. The route passes the exact center anyway,
        # and exact equality constraints make the optimization much less robust.
        d, window = P[k][:, -1] - gates_pos[gate], settings["racing_line_window"]
        opti.subject_to(ca.dot(d, rots[gate][:, 0]) == 0)
        opti.subject_to(opti.bounded(-window, ca.dot(d, rots[gate][:, 1]), window))
        opti.subject_to(opti.bounded(-window, ca.dot(d, rots[gate][:, 2]), window))
        # Cross in the forward direction and at most at the maximum angle to the gate normal
        v_normal = ca.dot(V[k][:, -1], rots[gate][:, 0])
        v_lateral = ca.dot(V[k][:, -1], rots[gate][:, 1])
        tan_max = np.tan(np.deg2rad(settings["racing_line_max_angle"]))
        opti.subject_to(v_normal >= 0.5)
        opti.subject_to(opti.bounded(-tan_max * v_normal, v_lateral, tan_max * v_normal))
        guess = track.lookup(np.linspace(bounds[k], bounds[k + 1], n + 1))[0]
        duration = (bounds[k + 1] - bounds[k]) / 2.5
        opti.set_initial(P[k], guess.T)
        opti.set_initial(V[k], np.gradient(guess, axis=0).T * n / duration)
        opti.set_initial(T[k], duration)
    opti.solver("ipopt", {"print_time": False}, {"print_level": 0, "max_iter": 2000, "sb": "yes"})
    try:
        sol = opti.solve()
    except RuntimeError:
        logger.warning("Racing line optimization failed, using the hand-made route")
        return None

    route, near = {}, settings["racing_line_gate_distance"]
    for k, gate in enumerate(gate_order):
        pts, vel = sol.value(P[k]).T, sol.value(V[k]).T
        previous = gate_order[k - 1] if k > 0 else -1
        via, last = [], pts[0]
        for j in range(1, n):
            # The nodes are equidistant in time and bunch up where the drone is slow. Close via
            # points would make the spline through them oscillate.
            if np.linalg.norm(pts[j] - last) < settings["racing_line_spacing"]:
                continue
            d_end = np.linalg.norm(pts[j] - gates_pos[gate])
            d_prev = np.linalg.norm(pts[j] - (gates_pos[previous] if previous >= 0 else start))
            if d_end < near or (previous >= 0 and d_prev < near):
                continue
            attached = gate if d_end <= d_prev else previous
            local = pts[j] if attached < 0 else rots[attached].T @ (pts[j] - gates_pos[attached])
            via.append((int(attached), local))
            last = pts[j]
        v_local = rots[gate].T @ vel[-1]
        angle = np.rad2deg(np.arctan2(v_local[1], v_local[0]))
        route[k] = {"via": via, "angle": float(angle), "entry": 0.2}
    return route


class Track:
    """Arc-length parametrized centerline with a tunnel around it, sampled on a dense grid."""

    def __init__(
        self,
        start: NDArray,
        gates_pos: NDArray,
        gates_quat: NDArray,
        obstacles_pos: NDArray,
        obstacles_inflation: NDArray,
        gates_inflation: NDArray,
        gate_order: NDArray,
        route: dict,
        settings: dict,
        limits: tuple,
    ):
        """Build the centerline and tunnel for the given gate and obstacle poses."""
        rots = [R.from_quat(q) for q in gates_quat]
        points, gate_flags, via_flags = [start], [False], [False]
        for leg, gate in enumerate(gate_order):
            leg_route = route.get(leg, {})
            for attached, local in leg_route.get("via", []):
                if attached < 0:
                    points.append(local)
                else:
                    points.append(gates_pos[attached] + rots[attached].apply(local))
                gate_flags.append(False)
                via_flags.append(True)
            angle = np.deg2rad(leg_route.get("angle", 0.0))
            direction = np.array([np.cos(angle), np.sin(angle), 0.0])
            entry_distance = leg_route.get("entry", GATE_OFFSET) * settings["entry_scale"]
            entry = -max(entry_distance, 0.1) * direction
            exit_ = (EXTENSION if leg == len(gate_order) - 1 else GATE_OFFSET) * direction
            for offset, is_gate in ((entry, False), (np.zeros(3), True), (exit_, False)):
                points.append(gates_pos[gate] + rots[gate].apply(offset))
                gate_flags.append(is_gate)
                via_flags.append(False)
        points = np.array(points)
        # Shorten the route by pulling the via points towards the midpoint of their neighbors. This
        # cuts detours and tightens turns. The tunnel keeps the path collision-free regardless.
        tighten = settings["route_tighten"]
        if tighten > 0:
            original = points.copy()
            for i in np.flatnonzero(via_flags):
                midpoint = 0.5 * (original[i - 1] + original[i + 1])
                points[i] = original[i] + tighten * (midpoint - original[i])

        # Chord-length spline, then resample uniformly in arc length
        chord = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))))
        spline = CubicSpline(chord, points)
        fine = np.linspace(0, chord[-1], 4000)
        fine_pos = spline(fine)
        self._push_from_obstacles(
            fine_pos,
            obstacles_pos,
            settings["obstacle_clearance"],
            fine,
            chord[np.array(gate_flags)],
        )
        arc = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(fine_pos, axis=0), axis=1))))
        self.length = arc[-1]
        self.ds = settings["grid_step"]
        self.s = np.arange(0.0, self.length, self.ds)
        self.pos = np.stack([np.interp(self.s, arc, fine_pos[:, i]) for i in range(3)], axis=-1)
        self.gate_s = np.interp(chord[np.array(gate_flags)], fine, arc)

        tangent = np.gradient(self.pos, self.ds, axis=0)
        tangent = gaussian_filter1d(tangent, 2.0, axis=0, mode="nearest")
        self.tangent = tangent / np.linalg.norm(tangent, axis=-1, keepdims=True)
        # Horizontal normal and (mostly vertical) binormal. Unlike the Frenet frame, this frame is
        # defined on straight segments and does not flip at inflection points.
        normal = np.cross([0.0, 0.0, 1.0], self.tangent)
        normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-6)
        self.normal = normal
        self.binormal = np.cross(self.tangent, self.normal)
        curvature = np.gradient(self.tangent, self.ds, axis=0)
        self.curvature = gaussian_filter1d(curvature, 3.0, axis=0, mode="nearest")

        obstacles = (obstacles_pos, obstacles_inflation)
        self._gates_inflation = gates_inflation
        self.extents = self._tunnel(gates_pos, gates_quat, obstacles, settings, limits)

    @staticmethod
    def _push_from_obstacles(
        pos: NDArray, obstacles_pos: NDArray, radius: float, s: NDArray, gate_s: NDArray
    ):
        """Push the centerline sideways away from poles closer than radius, keeping gates fixed.

        The push is perpendicular to the path so it does not bunch up the path, smoothed along the
        path so the centerline stays smooth, and repeated a few times because smoothing reduces the
        peak displacement.
        """
        # Fade the push out around the gates so the passages stay where they are
        fade = np.ones(len(s))
        for g in gate_s:
            fade = np.minimum(fade, np.clip((np.abs(s - g) - 0.3) / 0.3, 0.0, 1.0))
        sigma = 0.1 / (s[1] - s[0])
        for _ in range(6):
            tangent = np.gradient(pos[:, :2], axis=0)
            tangent /= np.maximum(np.linalg.norm(tangent, axis=-1, keepdims=True), 1e-9)
            offset = np.zeros_like(pos)
            for obstacle in obstacles_pos:
                delta = pos[:, :2] - obstacle[:2]
                dist = np.linalg.norm(delta, axis=-1)
                push = np.maximum(radius - dist, 0.0) * (pos[:, 2] < OBSTACLE_HEIGHT + 0.1)
                side = delta - np.sum(delta * tangent, axis=-1, keepdims=True) * tangent
                side /= np.maximum(np.linalg.norm(side, axis=-1, keepdims=True), 1e-9)
                offset[:, :2] += side * push[:, None]
            if not np.any(offset):
                return
            pos += gaussian_filter1d(offset, sigma, axis=0, mode="nearest") * fade[:, None]

    def _tunnel(
        self,
        gates_pos: NDArray,
        gates_quat: NDArray,
        obstacles: tuple,
        settings: dict,
        limits: tuple,
    ) -> NDArray:
        """Free extents [-n, +n, -b, +b] of the tunnel cross section at every grid point.

        Rays are cast along the four cross section directions. A ray stops where the drone would
        get closer than its radius plus a margin to any collision geometry.
        """
        max_width, min_width = settings["tunnel_max"], settings["tunnel_min"]
        if settings["footprint"]:
            footprint = drone_footprint(settings["max_angle"], gates_quat)
        else:  # A sphere that contains the drone
            footprint = (DRONE_RADIUS, DRONE_RADIUS, np.full(len(gates_quat), DRONE_RADIUS))
        steps = np.arange(0.0, max_width + 1e-9, 0.01)[1:]
        # Cast rays on a coarser grid, then take the smaller extent of the two neighboring rays
        stride = 4
        coarse = np.arange(0, len(self.s) + stride - 1, stride).clip(max=len(self.s) - 1)
        directions = np.stack((-self.normal, self.normal, -self.binormal, self.binormal))
        points = (
            self.pos[None, None, coarse] + steps[None, :, None, None] * directions[:, None, coarse]
        )  # (direction, step, point, xyz)
        free_dist = free_space(
            points.reshape(-1, 3),
            gates_pos,
            gates_quat,
            obstacles[0],
            limits,
            obstacles[1],
            footprint,
            self._gates_inflation,
        )
        free = np.cumprod(free_dist.reshape(points.shape[:3]) > settings["tunnel_margin"], axis=1)
        extent = np.where(free.any(axis=1), steps[np.maximum(free.sum(axis=1) - 1, 0)], 0.0)
        # The rays only check the axes of the cross section. Shrink it until its corners are free
        # as well, e.g. where the path crosses a gate at an angle and a ray passes behind the frame.
        center, n, b = self.pos[coarse], self.normal[coarse], self.binormal[coarse]
        for _ in range(8):
            ok = np.ones(len(coarse), dtype=bool)
            for i_n, sign_n in ((0, -1), (1, 1)):
                for i_b, sign_b in ((2, -1), (3, 1)):
                    corner = (
                        center
                        + sign_n * extent[i_n, :, None] * n
                        + sign_b * extent[i_b, :, None] * b
                    )
                    corner_free = free_space(
                        corner,
                        gates_pos,
                        gates_quat,
                        obstacles[0],
                        limits,
                        obstacles[1],
                        footprint,
                        self._gates_inflation,
                    )
                    bad = corner_free <= settings["tunnel_margin"]
                    extent[i_n, bad] *= 0.8
                    extent[i_b, bad] *= 0.8
                    ok &= ~bad
            if ok.all():
                break
        lower = np.arange(len(self.s)) // stride
        upper = np.minimum(lower + 1, len(coarse) - 1)
        extents = np.minimum(extent[:, lower], extent[:, upper]).T
        return np.maximum(extents, min_width)

    def lookup(self, s: NDArray) -> tuple[NDArray, ...]:
        """Interpolate centerline position, frame and tunnel extents at progress s."""
        s = np.clip(s, 0.0, self.s[-1])
        idx = np.clip((s / self.ds).astype(int), 0, len(self.s) - 2)
        w = ((s - self.s[idx]) / self.ds)[:, None]

        def interp(a: NDArray) -> NDArray:
            return a[idx] * (1 - w) + a[idx + 1] * w

        return (
            interp(self.pos),
            interp(self.tangent),
            interp(self.normal),
            interp(self.binormal),
            np.minimum(self.extents[idx], self.extents[idx + 1]),
            interp(self.curvature),
        )

    def project(self, pos: NDArray, s_guess: float, window: float = 0.6) -> float:
        """Progress of the closest centerline point within a window around s_guess."""
        mask = np.abs(self.s - s_guess) < window
        if not np.any(mask):
            mask = np.ones(len(self.s), dtype=bool)
        idx = np.flatnonzero(mask)
        k = idx[np.argmin(np.linalg.norm(self.pos[idx] - pos, axis=-1))]
        return float(self.s[k])

    def project_many(self, pos: NDArray, s_guess: NDArray, window: float = 0.5) -> NDArray:
        """Vectorized projection of several points, each within a window around its guess."""
        offsets = np.arange(-window, window + 1e-9, self.ds)
        candidates = np.clip(s_guess[:, None] + offsets[None, :], 0.0, self.s[-1])
        idx = np.clip(np.round(candidates / self.ds).astype(int), 0, len(self.s) - 1)
        dist = np.linalg.norm(self.pos[idx] - pos[:, None, :], axis=-1)
        return self.s[idx[np.arange(len(pos)), np.argmin(dist, axis=1)]]


# Parameters: path position and tangent at the linearization progress, tunnel normal and binormal,
# linearization progress, residual acceleration, tunnel center, stage length, path curvature and
# the identified model corrections (see MPCCPlusPlus.SETTINGS): thrust gain, attitude gain, thrust
# lag, attitude command lag, body drag in x and y
N_PARAMS = 29
P_DT, P_CURVATURE = 19, slice(20, 23)
P_THRUST_GAIN, P_ATTITUDE_GAIN, P_THRUST_LAG, P_RPY_CMD_LAG, P_DRAG = 23, 24, 25, 26, slice(27, 29)
# State layout: drone [pos, rpy, vel, drpy], lagged thrust, lagged rpy command, progress and its
# speed, and the previous command for slew penalties
POS, RPY, VEL, DRPY = slice(0, 3), slice(3, 6), slice(6, 9), slice(9, 12)
THRUST, CMD_RPY, THETA, V_THETA, U_PREV = 12, slice(13, 16), 16, 17, slice(18, 22)
NX = 22
N_COST, N_COST_E = 14, 8  # Residuals of the stage and terminal cost, see create_solver


def create_solver(time_steps: NDArray, params: dict) -> AcadosOcpSolver:
    """Create the MPCC OCP with progress states, slew penalties and soft tunnel constraints.

    Only the structure is compiled. Weights, references, bounds and slack penalties are set at
    runtime by the controller, so tuning them does not require a new build. The length of each
    stage is a parameter, so the horizon can use short stages first and longer ones later.
    """
    n = len(time_steps)
    sym = ca.MX
    x = sym.sym("x", NX)
    cmd = sym.sym("cmd", 4)  # [roll, pitch, yaw, thrust] commands
    a_theta = sym.sym("a_theta")
    p = sym.sym("p", N_PARAMS)
    residual = p[13:16]
    dt = p[P_DT]

    def f(z: ca.MX, thrust_state: ca.MX, rpy_cmd: ca.MX) -> ca.MX:
        """Dynamics of z = [drone state, progress, progress speed] given the lagged commands."""
        rot = rotation.cs_rpy2matrix(z[RPY])
        thrust = params["acc_coef"] + params["cmd_f_coef"] * p[P_THRUST_GAIN] * thrust_state
        # Linear drag in the body frame, identified from flight data
        drag = rot @ (ca.vertcat(p[P_DRAG], 0) * (rot.T @ z[VEL]))
        acc = rot @ ca.vertcat(0, 0, thrust) / params["mass"] + params["gravity_vec"] + residual
        ddrpy = (
            params["rpy_coef"] * z[RPY]
            + params["rpy_rates_coef"] * z[DRPY]
            + params["cmd_rpy_coef"] * p[P_ATTITUDE_GAIN] * rpy_cmd
        )
        return ca.vertcat(z[VEL], z[DRPY], acc - drag, ddrpy, z[13], a_theta)

    # The command lags are linear, so they are solved exactly at the RK4 stage times. Integrating
    # them with RK4 would be unstable for fast lags.
    def lag(tau: float) -> tuple[ca.MX, ca.MX]:
        thrust = cmd[3] + (x[THRUST] - cmd[3]) * ca.exp(-p[P_THRUST_LAG] * tau)
        rpy_cmd = cmd[:3] + (x[CMD_RPY] - cmd[:3]) * ca.exp(-p[P_RPY_CMD_LAG] * tau)
        return thrust, rpy_cmd

    z = ca.vertcat(x[:12], x[THETA], x[V_THETA])
    k1 = f(z, *lag(0.0))
    k2 = f(z + dt / 2 * k1, *lag(dt / 2))
    k3 = f(z + dt / 2 * k2, *lag(dt / 2))
    k4 = f(z + dt * k3, *lag(dt))
    z_next = z + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    x_next = ca.vertcat(z_next[:12], *lag(dt), z_next[12:], cmd)

    model = AcadosModel()
    model.name = "mpccpp"
    model.x = x
    model.u = ca.vertcat(cmd, a_theta)
    model.p = p
    model.disc_dyn_expr = x_next

    pos = x[POS]
    # Second-order expansion of the centerline around the linearization progress
    delta = x[THETA] - p[12]
    ref = p[0:3] + p[3:6] * delta + 0.5 * p[P_CURVATURE] * delta**2
    tangent = p[3:6] + p[P_CURVATURE] * delta
    tangent = tangent / ca.sqrt(ca.dot(tangent, tangent) + 1e-9)
    err = pos - ref
    lag = ca.dot(tangent, err)
    contour = err - lag * tangent
    slew = (cmd - x[U_PREV]) / dt
    model.cost_y_expr = ca.vertcat(contour, lag, x[DRPY], x[5], slew, x[V_THETA], a_theta)
    model.cost_y_expr_e = ca.vertcat(contour, lag, x[DRPY], x[5])
    # Tunnel: offsets of the drone from the centerline along the normal and binormal. The third
    # constraint limits the speed along the path, e.g. before gates that have not been observed.
    constraints = ca.vertcat(
        ca.dot(p[6:9], pos - p[16:19]), ca.dot(p[9:12], pos - p[16:19]), ca.dot(p[3:6], x[VEL])
    )
    model.con_h_expr = constraints
    model.con_h_expr_e = constraints

    ocp = AcadosOcp()
    ocp.model = model
    ocp.parameter_values = np.zeros(N_PARAMS)
    ocp.cost.cost_type = ocp.cost.cost_type_e = "NONLINEAR_LS"
    ocp.cost.W, ocp.cost.W_e = np.eye(N_COST), np.eye(N_COST_E)
    ocp.cost.yref, ocp.cost.yref_e = np.zeros(N_COST), np.zeros(N_COST_E)
    ocp.constraints.idxbu = np.arange(5)
    thrust_min, thrust_max = 4 * params["thrust_min"], 4 * params["thrust_max"]
    ocp.constraints.lbu = np.array([-1.0, -1.0, -0.1, thrust_min, -1.0])
    ocp.constraints.ubu = np.array([1.0, 1.0, 0.1, thrust_max, 1.0])
    # Roll and pitch bounds are soft, the progress speed bound is hard
    ocp.constraints.idxbx = np.array([3, 4, V_THETA])
    ocp.constraints.lbx = np.array([-1.0, -1.0, 0.0])
    ocp.constraints.ubx = np.array([1.0, 1.0, 1.0])
    ocp.constraints.idxsbx = np.array([0, 1])
    ocp.constraints.idxbx_e = np.array([3, 4])
    ocp.constraints.lbx_e = -np.ones(2)
    ocp.constraints.ubx_e = np.ones(2)
    ocp.constraints.idxsbx_e = np.array([0, 1])
    ocp.constraints.x0 = np.zeros(NX)

    # Soft tunnel constraints, bounds are overwritten per stage at runtime
    for suffix in ("", "_e"):
        setattr(ocp.constraints, "lh" + suffix, np.array([-1.0, -1.0, -100.0]))
        setattr(ocp.constraints, "uh" + suffix, np.array([1.0, 1.0, 100.0]))
        setattr(ocp.constraints, "idxsh" + suffix, np.arange(3))
        for name in ("zl", "zu", "Zl", "Zu"):
            setattr(ocp.cost, name + suffix, np.ones(5))  # Soft roll and pitch, then soft h

    opts = ocp.solver_options
    opts.N_horizon = n
    opts.time_steps = np.asarray(time_steps, dtype=float)
    opts.tf = float(np.sum(time_steps))
    opts.integrator_type = "DISCRETE"
    opts.qp_solver = "PARTIAL_CONDENSING_HPIPM"
    opts.hessian_approx = "GAUSS_NEWTON"
    opts.nlp_solver_type = "SQP_RTI"
    opts.qp_solver_warm_start = 1
    opts.qp_solver_iter_max = 30

    cmake_builder = None
    if os.name == "nt":
        cmake_builder = ocp_get_default_cmake_builder()
        cmake_builder.generator = "MinGW Makefiles"
        cmake_builder.build_dir = "build-mingw"
    # The build depends on the horizon, the drone and this file. Parallel processes (e.g. tuning
    # workers) share one build, the lock keeps them from compiling into the same directory at once.
    source = Path(__file__).read_bytes()
    key = repr((list(time_steps), sorted((k, np.asarray(v).tolist()) for k, v in params.items())))
    tag = hashlib.md5(key.encode() + source).hexdigest()[:8]
    ocp.code_export_directory = f"c_generated_code/mpccpp_{tag}"
    json_file = f"c_generated_code/mpccpp_{tag}.json"
    Path("c_generated_code").mkdir(exist_ok=True)
    with _build_lock(f"c_generated_code/mpccpp_{tag}.lock"):
        built = Path(json_file).exists() and any(
            Path(ocp.code_export_directory).glob("libacados_ocp_solver_*")
        )
        return AcadosOcpSolver(
            ocp,
            json_file=json_file,
            verbose=False,
            cmake_builder=cmake_builder,
            generate=not built,
            build=not built,
        )


@contextmanager
def _build_lock(path: str) -> Iterator[None]:
    """Exclusive file lock on POSIX systems, no locking elsewhere."""
    try:
        import fcntl
    except ImportError:  # Windows
        yield
        return
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


_SOLVER_CACHE: dict = {}


class MPCCPlusPlus(Controller):
    """MPCC++ on the collective thrust and attitude interface."""

    # Tuned for speed with scripts/tune_mpccpp.py on the identified model (TuRBO-6, 240 evaluations
    # x 12 races, crash scored as 6.5 s). Validated on 160 level 2 races: 51% success, 5.27 s mean
    # lap time.
    SETTINGS = dict(
        horizon=30,
        horizon_near=30,  # Number of stages with the control period as length
        dt_far=0.04,  # Length of the remaining stages, s
        path_order=2.0,  # 1: linear centerline expansion in the solver, 2: with curvature
        footprint=1.0,  # 1: tunnel from the collision box of the drone, 0: from a 0.1 m sphere
        # Model corrections identified from closed-loop flight data (.mpcc_dev/model_id.py): they
        # halve the 0.6 s position prediction error. The old step-response fit used a thrust lag of
        # 7/s, an attitude command lag of 20/s, unit gains and no drag.
        model_thrust_gain=1.034,
        model_attitude_gain=0.95,
        thrust_lag=20.4,  # 1/s
        rpy_cmd_lag=300.0,  # 1/s, effectively no lag
        drag_x=0.427,  # 1/s, body frame
        drag_y=0.375,
        plan_angle=0.7256,  # Soft roll and pitch bound of the predicted states, rad
        plan_angle_start=5,  # First stage of the soft bound, earlier stages may use max_angle
        contour_weight=42.7,
        lag_weight=228.9,
        rate_weight=0.0189,
        yaw_weight=1.0,
        attitude_slew_weight=0.2098,
        thrust_slew_weight=1.7698,
        progress_weight=5.3216,
        progress_acc_weight=0.01,
        reference_speed=4.214,
        max_speed=8.0,
        max_progress_acc=25.0,
        max_angle=0.926,
        thrust_headroom=1.0,  # Fraction of the maximum thrust the MPC may command
        slack_l1=5000.0,
        slack_l2=1e5,
        tunnel_max=0.4,
        tunnel_min=0.02,
        tunnel_margin=0.0374,
        obstacle_clearance=0.4,
        grid_step=0.01,
        residual_gain=0.1299,
        residual_max=4.0,
        residual_xy=0.0,  # Scale of the horizontal residual estimate, 0 estimates only z
        rti_iterations=2,
        # Speed limit along the path before gates whose true pose is not yet known
        unobserved_speed=2.0877,
        unobserved_distance=1.0,
        route_start=1,  # Route section variants, see ROUTE_SECTIONS
        route_gate1=0,
        route_gate23=0,
        route_tighten=0.0,  # Pulls via points towards their neighbors, 0: as defined, 1: midpoint
        entry_scale=1.0,  # Scales the straight final approach before each gate
        tunnel_at_position=1.0,
        adaptive_caps=0.0,  # 1: speed limits per gate from the reveal model, 0: unobserved_speed
        reveal_acc=8.0,  # m/s^2, lateral acceleration available for corrections after a reveal
        reveal_delay=0.1,  # s, response delay after a reveal
        reveal_margin=0.02,  # m, safety margin between the drone and the opening of a gate
        robust_gates=0.0,  # 1: tunnel through the part of an unobserved gate free for all poses
        racing_line=0.0,  # 1: replace the hand-made route by a time-optimal racing line
        racing_line_tilt=0.8,  # rad, tilt limit of the point mass model
        racing_line_clearance=0.3,  # m, distance of the racing line to the poles
        racing_line_nodes=20,  # Nodes per leg of the racing line optimization
        racing_line_window=0.05,  # m, allowed distance of the racing line to the gate centers
        racing_line_gate_distance=0.35,  # m, via points closer to a gate are dropped
        racing_line_spacing=0.3,  # m, minimum distance between via points of the racing line
        racing_line_max_angle=40.0,  # deg, maximum angle between gate normal and passage
        racing_line_min_height=0.15,  # m
    )

    def __init__(self, obs: dict[str, NDArray[np.floating]], info: dict, config: dict):
        """Build the track from the nominal poses and set up the solver."""
        super().__init__(obs, info, config)
        self.settings = dict(self.SETTINGS)
        self.settings.update(dict(config.controller.get("mpccpp", {})))
        s = self.settings
        self._dt = 1 / config.env.freq
        self._N = int(s["horizon"])
        self._params = load_params(Dynamics.so_rpy, config.sim.drone)
        thrust_coef = self._params["cmd_f_coef"] * s["model_thrust_gain"]
        self._hover = -self._params["mass"] * self._params["gravity_vec"][2] / thrust_coef

        near = min(int(s["horizon_near"]), self._N)
        self._time_steps = np.array([self._dt] * near + [s["dt_far"]] * (self._N - near))
        self._stage_times = np.concatenate(([0.0], np.cumsum(self._time_steps)))
        key = (tuple(self._time_steps), config.sim.drone)
        if key not in _SOLVER_CACHE:
            _SOLVER_CACHE[key] = create_solver(self._time_steps, self._params)
        self._solver = _SOLVER_CACHE[key]
        self._solver.reset()
        self._configure_solver()

        limits = config.env.track.safety_limits
        self._limits = (np.array(limits.pos_limit_low), np.array(limits.pos_limit_high))
        self._limits[0][2] = -1.0  # Floor contacts do not end the race, see race_core.py
        self._gate_order = np.asarray(obs["gate_sequence"])
        # Express the route via points relative to their gate in the nominal track
        nominal_pos = np.array([g["pos"] for g in config.env.track.gates])
        nominal_rot = [R.from_euler("xyz", g["rpy"]) for g in config.env.track.gates]
        self._route = {}
        for leg, leg_route in build_route(s).items():
            local = []
            for point, gate in leg_route.get("via", []):
                point = np.array(point, dtype=float)
                if gate >= 0:
                    point = nominal_rot[gate].inv().apply(point - nominal_pos[gate])
                local.append((gate, point))
            self._route[leg] = {**leg_route, "via": local}

        # Unobserved obstacles may be anywhere within their randomization range. The tunnel avoids
        # all of these positions until the true position is observed.
        randomizations = config.env.get("randomizations") or {}
        obstacle_rand = randomizations.get("obstacle_pos")
        shift = np.abs(obstacle_rand.kwargs.maxval[:2]) if obstacle_rand else np.zeros(2)
        self._obstacle_uncertainty = float(np.linalg.norm(shift))
        self._gate_uncertainty, self._gate_speed_caps = self._gate_reveal_model(config, obs)
        self._start = np.array(obs["pos"])
        self._build_track(obs)
        if s["racing_line"]:
            route = racing_line(
                self._track,
                self._start,
                np.asarray(obs["gates_pos"]),
                np.asarray(obs["gates_quat"]),
                np.asarray(obs["obstacles_pos"]),
                self._gate_order,
                s,
                self._params,
            )
            if route is not None:
                self._route = route
                self._build_track(obs)
        self._gates_visited = np.array(obs["gates_visited"], dtype=bool)
        self._obstacles_visited = np.array(obs["obstacles_visited"], dtype=bool)

        self._residual = np.zeros(3)
        self._theta = self._track.project(obs["pos"], 0.0, window=1.0)
        self._x = None  # Predicted states
        self._u = None  # Predicted inputs
        self._last_cmd = np.array([0.0, 0.0, 0.0, self._hover])
        self._thrust = 0.0  # The motors are off before the first command
        self._cmd_rpy = np.zeros(3)
        self._tick = 0
        self.solve_times = []
        self.solver_failures = 0

    def _configure_solver(self):
        """Set the weights, references, bounds and slack penalties from the settings."""
        s, N = self.settings, self._N
        contour = [s["contour_weight"]] * 3
        rates = [s["rate_weight"]] * 3
        slew = [s["attitude_slew_weight"]] * 3 + [s["thrust_slew_weight"]]
        W = np.diag(
            contour
            + [s["lag_weight"]]
            + rates
            + [s["yaw_weight"]]
            + slew
            + [s["progress_weight"], s["progress_acc_weight"]]
        )
        W_e = np.diag(contour + [s["lag_weight"]] + rates + [s["yaw_weight"]])
        yref = np.zeros(N_COST)
        yref[12] = s["reference_speed"]
        angle, acc = s["max_angle"], s["max_progress_acc"]
        thrust_min = 4 * self._params["thrust_min"]
        thrust_max = 4 * self._params["thrust_max"] * s["thrust_headroom"]
        lbu = np.array([-angle, -angle, -0.1, thrust_min, -acc])
        ubu = np.array([angle, angle, 0.1, thrust_max, acc])
        for k in range(N):
            self._solver.cost_set(k, "W", W)
            self._solver.set(k, "yref", yref)
            self._solver.constraints_set(k, "lbu", lbu)
            self._solver.constraints_set(k, "ubu", ubu)
        self._solver.cost_set(N, "W", W_e)
        # Plan with less tilt than the commands may use. The model overestimates how fast the drone
        # turns at large tilt, and the reserve is left for corrections.
        for k in range(1, N + 1):
            tilt = s["plan_angle"] if k >= s["plan_angle_start"] else 1.5
            lbx, ubx = [-tilt, -tilt], [tilt, tilt]
            if k < N:
                lbx, ubx = lbx + [0.0], ubx + [s["max_speed"]]
            self._solver.constraints_set(k, "lbx", np.array(lbx))
            self._solver.constraints_set(k, "ubx", np.array(ubx))
            l1, l2 = s["slack_l1"], s["slack_l2"]
            self._solver.cost_set(k, "zl", np.full(5, l1))
            self._solver.cost_set(k, "zu", np.full(5, l1))
            self._solver.cost_set(k, "Zl", np.full(5, l2))
            self._solver.cost_set(k, "Zu", np.full(5, l2))

    def _gate_reveal_model(self, config: dict, obs: dict) -> tuple[NDArray, NDArray]:
        """Position uncertainty of each gate in its frame, and the speed limit before its reveal.

        Before a gate is in sensor range, its true position is only known to lie within the
        randomization range around the nominal one. Projected into the gate frame, this gives the
        uncertainty of its normal, lateral and vertical position. The drone may pass the opening
        off center by up to the opening half width minus its own extent. Anything beyond that has
        to be corrected after the reveal. The speed limit is chosen so that this worst-case
        correction fits between the reveal at sensor range and the gate, given a lateral
        acceleration and a response delay.
        """
        s = self.settings
        randomizations = config.env.get("randomizations") or {}
        pos_rand, rpy_rand = randomizations.get("gate_pos"), randomizations.get("gate_rpy")
        shift = np.abs(pos_rand.kwargs.maxval) if pos_rand else np.zeros(3)
        yaw_range = abs(rpy_rand.kwargs.maxval[2]) if rpy_rand else 0.0
        yaws = R.from_quat(np.asarray(obs["gates_quat"])).as_euler("xyz")[:, 2]
        delta = np.linspace(-yaw_range, yaw_range, 11)
        angles = yaws[:, None] + delta[None, :]
        # Worst case projections of the position box onto the gate axes over all possible yaws
        normal = np.max(shift[0] * np.abs(np.cos(angles)) + shift[1] * np.abs(np.sin(angles)), 1)
        lateral = np.max(shift[0] * np.abs(np.sin(angles)) + shift[1] * np.abs(np.cos(angles)), 1)
        uncertainty = np.column_stack((normal, lateral, np.full(len(yaws), shift[2])))
        # Allowed offset from the gate center inside the opening
        _, vertical, _ = drone_footprint(s["max_angle"], np.asarray(obs["gates_quat"]))
        tolerance = YAW_TOLERANCE + yaw_range
        angles = yaws[:, None] + np.linspace(-tolerance, tolerance, 11)[None, :]
        extent = np.max(DRONE_HALF_WIDTH * (np.abs(np.cos(angles)) + np.abs(np.sin(angles))), 1)
        opening = 0.2 - s["reveal_margin"]
        vertical_correction = np.full(len(yaws), shift[2] - (opening - vertical))
        correction = np.maximum.reduce(
            [lateral - (opening - extent), vertical_correction, np.zeros(len(yaws))]
        )
        duration = s["reveal_delay"] + np.sqrt(2 * correction / s["reveal_acc"])
        caps = np.clip(config.env.sensor_range / duration, s["unobserved_speed"], s["max_speed"])
        return uncertainty, caps

    def _build_track(self, obs: dict):
        self._track = Track(
            self._start,
            np.asarray(obs["gates_pos"]),
            np.asarray(obs["gates_quat"]),
            np.asarray(obs["obstacles_pos"]),
            np.where(obs["obstacles_visited"], 0.0, self._obstacle_uncertainty),
            np.where(
                np.asarray(obs["gates_visited"])[:, None],
                0.0,
                self._gate_uncertainty * self.settings["robust_gates"],
            ),
            self._gate_order,
            self._route,
            self.settings,
            self._limits,
        )

    def _state(self, obs: dict) -> NDArray:
        rpy = R.from_quat(obs["quat"]).as_euler("xyz")
        drpy = ang_vel2rpy_rates(obs["quat"], obs["ang_vel"])
        return np.concatenate((obs["pos"], rpy, obs["vel"], drpy))

    def compute_control(
        self, obs: dict[str, NDArray[np.floating]], info: dict | None = None
    ) -> NDArray[np.floating]:
        """Solve the MPCC problem and return [roll, pitch, yaw, thrust]."""
        t0 = time.perf_counter()
        gates_visited = np.array(obs["gates_visited"], dtype=bool)
        obstacles_visited = np.array(obs["obstacles_visited"], dtype=bool)
        if np.any(gates_visited & ~self._gates_visited) or np.any(
            obstacles_visited & ~self._obstacles_visited
        ):
            self._build_track(obs)
        self._gates_visited, self._obstacles_visited = gates_visited, obstacles_visited

        drone = self._state(obs)
        self._update_residual(obs)
        theta_guess = self._theta if self._x is None else self._x[1, THETA]
        theta = self._track.project(obs["pos"], theta_guess)
        theta = max(theta, self._theta)  # Progress never decreases
        self._theta = theta
        v_theta = 0.0 if self._x is None else float(self._x[1, V_THETA])
        x0 = np.concatenate(
            (drone, [self._thrust], self._cmd_rpy, [theta, v_theta], self._last_cmd)
        )

        N = self._N
        if self._x is None:
            x_init = np.tile(x0, (N + 1, 1))
            u_init = np.tile(np.array([0.0, 0.0, 0.0, self._hover, 0.0]), (N, 1))
            iterations = 10
        else:
            x_init, u_init = self._shift(self._x, self._u)
            x_init[:, THETA] += theta - x_init[0, THETA]
            x_init[0] = x0
            iterations = int(self.settings["rti_iterations"])
        for k in range(N + 1):
            self._solver.set(k, "x", x_init[k])
        for k in range(N):
            self._solver.set(k, "u", u_init[k])
        self._solver.set(0, "lbx", x0)
        self._solver.set(0, "ubx", x0)

        for _ in range(iterations):
            x_iter = self._solver.get_flat("x").reshape(N + 1, -1)
            self._set_path(x_iter[:, THETA], x_iter[:, POS])
            status = self._solver.solve()
        x = self._solver.get_flat("x").reshape(N + 1, -1)
        u = self._solver.get_flat("u").reshape(N, -1)
        if status not in (0, 2, 5) or not np.all(np.isfinite(u)):
            logger.warning(f"MPCC solver status {status}")
            self.solver_failures += 1
            self._solver.reset()
            self._x = None
            cmd = np.array([0.0, 0.0, 0.0, self._hover])
        else:
            self._x, self._u = x, u
            cmd = u[0, :4]
        self._last_cmd = cmd.copy()
        # Propagate the lag states with the applied command (exact discretization)
        s = self.settings
        self._thrust += (1 - np.exp(-s["thrust_lag"] * self._dt)) * (cmd[3] - self._thrust)
        self._cmd_rpy += (1 - np.exp(-s["rpy_cmd_lag"] * self._dt)) * (cmd[:3] - self._cmd_rpy)
        self.solve_times.append(time.perf_counter() - t0)
        return cmd.astype(np.float32)

    def _shift(self, x: NDArray, u: NDArray) -> tuple[NDArray, NDArray]:
        """Shift the previous solution by one control period to warm start the next solve.

        The stages have different lengths, so the solution is interpolated in time.
        """
        t = np.minimum(self._stage_times + self._dt, self._stage_times[-1])
        x_new = np.column_stack(
            [np.interp(t, self._stage_times, x[:, i]) for i in range(x.shape[1])]
        )
        idx = np.searchsorted(self._stage_times, t[:-1], side="right") - 1
        return x_new, u[np.clip(idx, 0, len(u) - 1)]

    def _set_path(self, thetas: NDArray, positions: NDArray):
        """Set the path linearization and the tunnel cross sections of all stages.

        The contouring cost is linearized at the predicted progress. The tunnel cross section is
        taken where the predicted position projects onto the track instead. Otherwise the solver
        could let the progress fall behind the drone and use the wide tunnel before a gate to plan
        through its frame.
        """
        thetas = np.clip(thetas, 0.0, self._track.s[-1])
        pos, tangent, _, _, _, curvature = self._track.lookup(thetas)
        tunnel_s = thetas
        if self.settings["tunnel_at_position"]:
            tunnel_s = self._track.project_many(positions, thetas)
        center, _, normal, binormal, extents, _ = self._track.lookup(tunnel_s)
        p = np.zeros((len(thetas), N_PARAMS))
        p[:, 0:3], p[:, 3:6], p[:, 6:9], p[:, 9:12] = pos, tangent, normal, binormal
        p[:, 12] = thetas
        p[:, 13:16] = self._residual
        p[:, 16:19] = center
        p[:, P_DT] = np.append(self._time_steps, self._time_steps[-1])
        s = self.settings
        p[:, P_THRUST_GAIN], p[:, P_ATTITUDE_GAIN] = (
            s["model_thrust_gain"],
            s["model_attitude_gain"],
        )
        p[:, P_THRUST_LAG], p[:, P_RPY_CMD_LAG] = s["thrust_lag"], s["rpy_cmd_lag"]
        p[:, P_DRAG] = s["drag_x"], s["drag_y"]
        if self.settings["path_order"] > 1:
            p[:, P_CURVATURE] = curvature
        self._solver.set_flat("p", p.ravel())
        thetas = tunnel_s  # The speed limit before unobserved gates also uses the tunnel location
        # Limit the speed before gates that have not been observed yet. Their true pose is revealed
        # at sensor range and the drone needs time to correct for the offset.
        s = self.settings
        speed = np.full(len(thetas), 100.0)
        for gate, gate_s in zip(self._gate_order, self._track.gate_s):
            if not self._gates_visited[gate]:
                near = (thetas > gate_s - s["unobserved_distance"]) & (thetas < gate_s + 0.1)
                cap = self._gate_speed_caps[gate] if s["adaptive_caps"] else s["unobserved_speed"]
                speed[near] = np.minimum(speed[near], cap)
        lh = np.column_stack((-extents[:, [0, 2]], np.full(len(thetas), -100.0)))
        uh = np.column_stack((extents[:, [1, 3]], speed))
        for k in range(1, len(thetas)):
            self._solver.constraints_set(k, "lh", lh[k])
            self._solver.constraints_set(k, "uh", uh[k])

    def _update_residual(self, obs: dict):
        """Low-pass filter the one-step acceleration prediction error into the residual."""
        if self._x is None or obs["pos"][2] < 0.05:
            return
        error = (np.asarray(obs["vel"]) - self._x[1, VEL]) / self._dt
        error[:2] *= self.settings["residual_xy"]
        s = self.settings
        self._residual = np.clip(
            self._residual + s["residual_gain"] * error, -s["residual_max"], s["residual_max"]
        )

    def step_callback(
        self,
        action: NDArray[np.floating],
        obs: dict[str, NDArray[np.floating]],
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict,
    ) -> bool:
        """Count ticks. The environment terminates the episode after the last gate."""
        self._tick += 1
        return False

    def render_callback(self, sim: Sim):
        """Draw the centerline, tunnel walls and the predicted trajectory."""
        from crazyflow.sim.visualize import draw_line

        t = self._track
        idx = np.arange(0, len(t.s), 5)
        draw_line(sim, t.pos[idx], rgba=(0.0, 1.0, 0.0, 1.0))
        for side, sign, col in ((0, -1, t.normal), (1, 1, t.normal)):
            wall = t.pos[idx] + sign * t.extents[idx, side : side + 1] * col[idx]
            draw_line(sim, wall, rgba=(0.3, 0.3, 1.0, 0.6))
        if self._x is not None:
            draw_line(sim, self._x[:, :3], rgba=(1.0, 0.0, 0.0, 1.0))

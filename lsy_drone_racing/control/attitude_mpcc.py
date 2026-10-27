"""Attitude MPCC using the drone model and command convention of AttitudeMPC.

The reference is a geometric path, not a timed trajectory. A virtual progress state
and speed input let the optimizer trade forward progress against contour/lag error.
Like the example MPC, the default path is specific to the nominal course. This is
ordinary MPCC: it does not impose obstacle, gate corridor, or terminal-set constraints.
The default path is locally corrected as randomized gate positions become visible.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import casadi as ca
import numpy as np
import scipy.linalg
from acados_template import AcadosOcp, AcadosOcpSolver
from acados_template.builders import ocp_get_default_cmake_builder
from crazyflow.dynamics import Dynamics, load_params
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from crazyflow.sim.visualize import draw_line, draw_points
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control import Controller
from lsy_drone_racing.control.attitude_mpc import create_acados_model

if TYPE_CHECKING:
    from crazyflow import Sim
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def create_path(start_pos: NDArray, waypoints: NDArray | None = None) -> CubicSpline:
    """Reparameterize the example MPC spline by approximate arc length in meters.

    Custom waypoints describe the path after the initial position. Dense sampling
    preserves the original spline's geometry while removing its time schedule.
    """
    if waypoints is None:
        waypoints = np.array(
            [
                [-1.0, 0.75, 0.4],
                [0.3, 0.35, 0.7],
                [1.3, -0.15, 0.9],
                [0.85, 0.85, 1.2],
                [-0.5, -0.05, 0.7],
                [-1.2, -0.2, 0.8],
                [-1.2, -0.2, 1.2],
                [0.0, -0.7, 1.2],
                [1.2, -0.15, 1.2],
                [1.05, 0.75, 1.2],
                [0.25, 1.25, 1.2],
            ]
        )
    waypoints = np.asarray(waypoints, dtype=float)
    if waypoints.ndim != 2 or waypoints.shape[1] != 3:
        raise ValueError("MPCC waypoints must have shape (n, 3).")
    points = np.vstack((start_pos, waypoints))
    if not np.all(np.isfinite(points)):
        raise ValueError("MPCC path must contain only finite coordinates.")
    points = points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-6]]
    if len(points) < 2:
        raise ValueError("MPCC path needs at least two distinct positions.")
    curve = CubicSpline(np.arange(len(points)), points)
    samples = curve(np.linspace(0, len(points) - 1, 200 * (len(points) - 1) + 1))
    distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(samples, axis=0), axis=1))]
    keep = np.r_[True, np.diff(distance) > 1e-9]
    return CubicSpline(distance[keep], samples[keep])


def gate_anchors(path: CubicSpline, track: dict) -> tuple[NDArray, NDArray]:
    """Find ordered forward/reverse gate crossings on the nominal reference path."""
    samples = np.linspace(0, path.x[-1], 3000)
    points = path(samples)
    anchors = [0.0]
    ids = []
    for entry in track.gate_order:
        gate_id = abs(entry) - 1
        gate = track.gates[gate_id]
        normal = Rotation.from_euler("xyz", gate["rpy"]).apply([np.sign(entry), 0, 0])
        distance = (points - gate["pos"]) @ normal
        crossings = np.flatnonzero(
            (distance[:-1] < 0) & (distance[1:] >= 0) & (samples[:-1] > anchors[-1])
        )
        for k in crossings:
            progress = samples[k] - distance[k] * (samples[k + 1] - samples[k]) / (
                distance[k + 1] - distance[k]
            )
            if np.linalg.norm(path(progress) - gate["pos"]) < 0.45:
                anchors.append(progress)
                ids.append(gate_id)
                break
        else:
            raise ValueError(
                "Default MPCC path does not match gate_order; supply custom waypoints."
            )
    return np.array(anchors + [path.x[-1]]), np.array(ids, dtype=int)


def create_mpcc_solver(
    dt: float, parameters: dict, settings: dict, path_length: float
) -> tuple[AcadosOcpSolver, AcadosOcp]:
    """Augment the attitude model with progress and construct a contouring OCP."""
    ocp = AcadosOcp()
    model = create_acados_model(parameters)
    model.name = "attitude_mpcc"
    symbolic = type(model.x)
    progress = symbolic.sym("progress")
    speed = symbolic.sym("progress_speed")
    model.x = ca.vertcat(model.x, progress)
    model.u = ca.vertcat(model.u, speed)
    # Estimate an effective inverse mass/thrust gain online. This also absorbs
    # thrust calibration error without reading hidden simulator parameters.
    model.p = symbolic.sym("path_reference", 8)
    gravity = ca.DM(parameters["gravity_vec"])
    acceleration = gravity + model.p[7] * (model.f_expl_expr[6:9] - gravity)
    derivative = ca.vertcat(model.f_expl_expr[:6], acceleration, model.f_expl_expr[9:12], speed)
    # Store the previous command as a discrete state so slew penalties apply to
    # consecutive commands throughout the horizon, including the applied input.
    dynamics = ca.Function("mpcc_dynamics", [model.x, model.u, model.p], [derivative])
    k1 = dynamics(model.x, model.u, model.p)
    k2 = dynamics(model.x + dt * k1 / 2, model.u, model.p)
    k3 = dynamics(model.x + dt * k2 / 2, model.u, model.p)
    k4 = dynamics(model.x + dt * k3, model.u, model.p)
    next_state = model.x + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
    previous_command = symbolic.sym("previous_command", 4)
    model.x = ca.vertcat(model.x, previous_command)
    model.disc_dyn_expr = ca.vertcat(next_state, model.u[:4])
    model.f_expl_expr = None
    # Stage parameters: path position, derivative, linearization progress, gain.
    reference = model.p[:3] + model.p[3:6] * (progress - model.p[6])
    error = model.x[:3] - reference
    tangent = model.p[3:6] / ca.sqrt(ca.dot(model.p[3:6], model.p[3:6]) + 1e-12)
    lag = ca.dot(tangent, error)
    contour = error - tangent * lag
    # Penalize speed squared and reward progress. Completing the square permits
    # NONLINEAR_LS/Gauss-Newton: w*(speed-v_ref)^2 = w*speed^2-2*w*v_ref*speed+const.
    model.cost_y_expr = ca.vertcat(
        contour,
        lag,
        model.x[3:6],
        model.x[9:12],
        model.u[:4],
        speed,
        (model.u[:4] - previous_command) / dt,
    )
    model.cost_y_expr_e = ca.vertcat(contour, lag, model.x[3:6], model.x[6:12])
    ocp.model = model
    ocp.parameter_values = np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])
    ocp.cost.cost_type = ocp.cost.cost_type_e = "NONLINEAR_LS"
    ocp.cost.W = scipy.linalg.block_diag(
        np.eye(3) * settings["contour_weight"],
        settings["lag_weight"],
        np.diag([1.0, 1.0, 1.0]),
        np.eye(3) * settings["attitude_rate_weight"],
        np.diag([1.0, 1.0, 1.0, 50.0]),
        settings["progress_weight"],
        np.diag([settings["attitude_slew_weight"]] * 3 + [settings["thrust_slew_weight"]]),
    )
    ocp.cost.W_e = (
        scipy.linalg.block_diag(
            np.eye(3) * settings["contour_weight"],
            settings["lag_weight"],
            np.eye(3),
            np.eye(3) * 0.1,
            np.eye(3) * settings["attitude_rate_weight"],
        )
        * settings["terminal_weight"]
    )
    hover = (
        parameters["mass"] * -parameters["gravity_vec"][-1] - parameters["acc_coef"]
    ) / parameters["cmd_f_coef"]
    ocp.cost.yref = np.zeros(19)
    ocp.cost.yref[13] = hover
    ocp.cost.yref[14] = settings["reference_speed"]
    ocp.cost.yref_e = np.zeros(13)

    angle = settings["max_angle"]
    ocp.constraints.idxbu = np.arange(5)
    ocp.constraints.lbu = np.array([-angle, -angle, -angle, 4 * parameters["thrust_min"], 0])
    ocp.constraints.ubu = np.array(
        [angle, angle, angle, 4 * parameters["thrust_max"], settings["max_speed"]]
    )
    ocp.constraints.idxbx = ocp.constraints.idxbx_e = np.array([3, 4, 5, 12])
    ocp.constraints.lbx = ocp.constraints.lbx_e = np.array([-angle, -angle, -angle, 0])
    ocp.constraints.ubx = ocp.constraints.ubx_e = np.array([angle, angle, angle, path_length])
    ocp.constraints.x0 = np.zeros(17)
    ocp.solver_options.N_horizon = settings["horizon_steps"]
    ocp.solver_options.tf = dt * settings["horizon_steps"]
    ocp.solver_options.qp_solver = "PARTIAL_CONDENSING_HPIPM"
    ocp.solver_options.qp_solver_cond_N = min(10, settings["horizon_steps"])
    ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
    ocp.solver_options.integrator_type = "DISCRETE"
    ocp.solver_options.nlp_solver_type = "SQP_RTI"
    ocp.solver_options.nlp_solver_max_iter = 20
    ocp.solver_options.qp_solver_iter_max = 50
    ocp.solver_options.tol = 1e-4
    # Keep the generated solver separate from the example MPC's files.
    ocp.code_export_directory = "c_generated_code/attitude_mpcc"
    builder = None
    if os.name == "nt":
        builder = ocp_get_default_cmake_builder()
        builder.generator = "MinGW Makefiles"
        builder.build_dir = "build-mingw"
    solver = AcadosOcpSolver(
        ocp, json_file="c_generated_code/attitude_mpcc.json", cmake_builder=builder, verbose=False
    )
    return solver, ocp


class AttitudeMPCC(Controller):
    """Optimize progress along a geometric path and return [roll, pitch, yaw, thrust].

    Optional tuning lives in ``[controller.mpcc]``. The default waypoints match
    AttitudeMPC; custom ``waypoints`` exclude the automatically prepended start.
    This controller is for single-drone environments in attitude control mode.
    """

    def __init__(self, obs: dict[str, NDArray], info: dict, config: dict):
        """Initialize the path, augmented model, and solver."""
        super().__init__(obs, info, config)
        if config.env.control_mode != "attitude":
            raise ValueError("AttitudeMPCC requires env.control_mode = 'attitude'.")
        self.settings = dict(
            horizon_steps=40,
            reference_speed=1.3,
            max_speed=1.8,
            contour_weight=400.0,
            lag_weight=400.0,
            progress_weight=12.0,
            max_angle=0.6,
            attitude_rate_weight=0.1,
            attitude_slew_weight=0.02,
            thrust_slew_weight=0.1,
            terminal_weight=0.2,
            adaptation_rate=2.0,
            obstacle_clearance=0.26,
        )
        options = dict(config.controller.get("mpcc", {}))
        waypoints = options.pop("waypoints", None)
        unknown = options.keys() - self.settings.keys()
        if unknown:
            raise ValueError(f"Unknown MPCC settings: {sorted(unknown)}")
        self.settings.update(options)
        for name, value in self.settings.items():
            if not np.isfinite(value) or value < 0 or (value == 0 and name != "adaptation_rate"):
                raise ValueError(f"MPCC {name} must be positive and finite.")
        if int(self.settings["horizon_steps"]) != self.settings["horizon_steps"]:
            raise ValueError("MPCC horizon_steps must be an integer.")
        self._N = int(self.settings["horizon_steps"])
        self.settings["horizon_steps"] = self._N
        self._dt = 1.0 / config.env.freq
        self._path = create_path(obs["pos"], waypoints)
        self._path_derivative = self._path.derivative()
        self._length = float(self._path.x[-1])
        self._base_path = self._path
        self._gate_ids = None
        if waypoints is None:
            crossings, ids = gate_anchors(self._path, config.env.track)
            self._gate_offsets = np.tile([-0.18, 0, 0.18], len(ids))
            self._gate_ids = np.repeat(ids, 3)
            self._gate_directions = np.repeat(np.sign(config.env.track.gate_order), 3)
            self._anchors = np.r_[
                0, np.repeat(crossings[1:-1], 3) + self._gate_offsets, self._length
            ]
            # Local Gaussian deformations preserve the original route between gates.
            self._warp_width = 0.4
            delta = self._anchors[:, None] - self._anchors[None, :]
            self._warp_inverse = np.linalg.inv(np.exp(-0.5 * (delta / self._warp_width) ** 2))
            delta = self._base_path.x[:, None] - self._anchors[None, :]
            self._warp_basis = np.exp(-0.5 * (delta / self._warp_width) ** 2)
        self._observed_gate_positions = None
        self._observed_gate_quaternions = None
        self._observed_obstacles = None
        self._update_gate_path(obs)
        self.drone_params = load_params(Dynamics.so_rpy, config.sim.drone)
        self._solver, self._ocp = create_mpcc_solver(
            self._dt, self.drone_params, self.settings, self._length
        )
        self._nominal_hover = float(
            (
                self.drone_params["mass"] * -self.drone_params["gravity_vec"][-1]
                - self.drone_params["acc_coef"]
            )
            / self.drone_params["cmd_f_coef"]
        )
        self.reset()

    def reset(self):
        """Clear virtual progress and warm starts before restarting the same path."""
        self._progress = 0.0
        self._prediction = None
        self._inputs = None
        self._failures = 0
        self.last_solver_status = None
        self._thrust_gain = 1.0
        self._hover = self._nominal_hover
        self._last_action = np.array([0.0, 0.0, 0.0, self._hover])
        self._previous_observation = None
        self._previous_thrust = self._hover
        self._solver.reset()

    def episode_reset(self):
        """Reset the controller between episodes (new tracks need a new instance)."""
        self.reset()

    def _update_thrust_gain(self, obs: dict[str, NDArray]):
        """Filter acceleration-based thrust effectiveness, excluding ground contact.

        This estimates thrust effectiveness, not the inertia tensor. Changes in
        the attitude response are handled by command slew costs and feedback.
        """
        body_z = Rotation.from_quat(obs["quat"]).as_matrix()[:, 2]
        if self._previous_observation is not None:
            velocity, previous_z, altitude = self._previous_observation
            if (
                min(altitude, obs["pos"][2]) > 0.15
                and abs(self._last_action[3] - self._previous_thrust) < 0.04
            ):
                force = (
                    self.drone_params["acc_coef"]
                    + self.drone_params["cmd_f_coef"] * self._last_action[3]
                )
                expected = (body_z + previous_z) * 0.5 * force / self.drone_params["mass"]
                measured = (obs["vel"] - velocity) / self._dt - self.drone_params["gravity_vec"]
                gain = np.dot(expected, measured) / max(np.dot(expected, expected), 1e-6)
                if np.isfinite(gain) and 0.6 < gain < 1.5:
                    alpha = 1 - np.exp(-self.settings["adaptation_rate"] * self._dt)
                    self._thrust_gain += alpha * (gain - self._thrust_gain)
                    self._thrust_gain = float(np.clip(self._thrust_gain, 0.7, 1.4))
        self._hover = self._nominal_hover / self._thrust_gain
        self._previous_observation = (np.array(obs["vel"], copy=True), body_z, float(obs["pos"][2]))
        self._previous_thrust = self._last_action[3]

    def _update_gate_path(self, obs: dict[str, NDArray]):
        """Correct observed gate centers and locally detour around observed poles.

        This preserves the nominal route and gate anchors. It is a local path
        adjustment, not a collision-free global planner or a safety guarantee.
        """
        if self._gate_ids is None:
            return
        gates = np.asarray(obs["gates_pos"])
        quaternions = np.asarray(obs["gates_quat"])
        obstacles = np.asarray(obs["obstacles_pos"])
        if (
            self._observed_gate_positions is not None
            and np.array_equal(gates, self._observed_gate_positions)
            and np.array_equal(quaternions, self._observed_gate_quaternions)
            and np.array_equal(obstacles, self._observed_obstacles)
        ):
            return
        self._observed_gate_positions = gates.copy()
        self._observed_gate_quaternions = quaternions.copy()
        self._observed_obstacles = obstacles.copy()
        correction = np.zeros((len(self._anchors), 3))
        normals = Rotation.from_quat(quaternions[self._gate_ids]).as_matrix()[:, :, 0]
        targets = (
            gates[self._gate_ids] + normals * (self._gate_offsets * self._gate_directions)[:, None]
        )
        correction[1:-1] = targets - self._base_path(self._anchors[1:-1])
        weights = self._warp_inverse @ correction
        points = self._base_path(self._base_path.x) + self._warp_basis @ weights
        # Repel path sections from poles, projecting each correction to zero at
        # the gate centers, start, and finish. Re-evaluate after each correction.
        for _ in range(8):
            path = CubicSpline(self._base_path.x, points)
            offsets = np.zeros_like(points)
            anchor_offsets = np.zeros((len(self._anchors), 3))
            for obstacle in obstacles:
                distance = np.linalg.norm(points[:, :2] - obstacle[:2], axis=1)
                minima = (
                    np.flatnonzero(
                        (distance[1:-1] <= distance[:-2]) & (distance[1:-1] < distance[2:])
                    )
                    + 1
                )
                for index in minima:
                    if (
                        distance[index] >= self.settings["obstacle_clearance"]
                        or points[index, 2] > obstacle[2] + 0.1
                    ):
                        continue
                    direction = points[index, :2] - obstacle[:2]
                    if distance[index] < 1e-6:
                        tangent = path.derivative()(self._base_path.x[index])[:2]
                        direction = np.array([-tangent[1], tangent[0]])
                    direction /= max(np.linalg.norm(direction), 1e-9)
                    shift = np.r_[
                        direction * (self.settings["obstacle_clearance"] - distance[index]), 0
                    ]
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
        # Refresh local path linearizations twice so curved-path references follow
        # the optimized progress, rather than advancing according to wall time.
        reference = self._ocp.cost.yref.copy()
        reference[13] = self._hover
        for k in range(self._N):
            self._solver.set(k, "yref", reference)
        for _ in range(2):
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

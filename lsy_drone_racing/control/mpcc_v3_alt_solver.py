# Copyright (c) 2024 Learning Systems and Robotics Lab (LSY)
# SPDX-License-Identifier: MIT
# Derived from the project MPCC implementation; see repository LICENSE.

"""Path construction and the unchanged attitude MPCC optimal-control problem."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import casadi as ca
import numpy as np
import scipy.linalg
from acados_template import AcadosOcp, AcadosOcpSolver
from acados_template.builders import ocp_get_default_cmake_builder
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.attitude_mpc import create_acados_model

if TYPE_CHECKING:
    from numpy.typing import NDArray


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
    model.name = "attitude_mpcc_v3_alt"
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
    integration_state = model.x
    sub_dt = dt / settings["integration_substeps"]
    for _ in range(settings["integration_substeps"]):
        k1 = dynamics(integration_state, model.u, model.p)
        k2 = dynamics(integration_state + sub_dt * k1 / 2, model.u, model.p)
        k3 = dynamics(integration_state + sub_dt * k2 / 2, model.u, model.p)
        k4 = dynamics(integration_state + sub_dt * k3, model.u, model.p)
        integration_state = integration_state + sub_dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
    next_state = integration_state
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
        np.diag([settings["contour_horizontal_scale"]] * 2 + [settings["contour_vertical_scale"]])
        * settings["contour_weight"],
        settings["lag_weight"],
        np.diag([settings["attitude_rp_weight"]] * 2 + [settings["attitude_yaw_weight"]]),
        np.eye(3) * settings["attitude_rate_weight"],
        np.diag([settings["command_attitude_weight"]] * 3 + [settings["command_thrust_weight"]]),
        settings["progress_weight"],
        np.diag([settings["attitude_slew_weight"]] * 3 + [settings["thrust_slew_weight"]]),
    )
    ocp.cost.W_e = (
        scipy.linalg.block_diag(
            np.diag(
                [settings["contour_horizontal_scale"]] * 2 + [settings["contour_vertical_scale"]]
            )
            * settings["contour_weight"],
            settings["lag_weight"],
            np.eye(3),
            np.eye(3) * settings["terminal_velocity_weight"],
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
    yaw_angle = angle * settings["yaw_bound_scale"]
    ocp.constraints.idxbu = np.arange(5)
    ocp.constraints.lbu = np.array([-angle, -angle, -yaw_angle, 4 * parameters["thrust_min"], 0])
    ocp.constraints.ubu = np.array(
        [angle, angle, yaw_angle, 4 * parameters["thrust_max"], settings["max_speed"]]
    )
    ocp.constraints.idxbx = ocp.constraints.idxbx_e = np.array([3, 4, 5, 12])
    ocp.constraints.lbx = ocp.constraints.lbx_e = np.array([-angle, -angle, -yaw_angle, 0])
    ocp.constraints.ubx = ocp.constraints.ubx_e = np.array([angle, angle, yaw_angle, path_length])
    ocp.constraints.x0 = np.zeros(17)
    ocp.solver_options.N_horizon = settings["horizon_steps"]
    ocp.solver_options.tf = dt * settings["horizon_steps"]
    ocp.solver_options.qp_solver = "PARTIAL_CONDENSING_HPIPM"
    ocp.solver_options.qp_solver_cond_N = min(
        settings["condensing_length"], settings["horizon_steps"]
    )
    ocp.solver_options.hessian_approx = "GAUSS_NEWTON"
    ocp.solver_options.integrator_type = "DISCRETE"
    ocp.solver_options.nlp_solver_type = "SQP_RTI"
    ocp.solver_options.nlp_solver_max_iter = 20
    ocp.solver_options.qp_solver_iter_max = settings["qp_iterations"]
    ocp.solver_options.tol = settings["solver_tolerance"]
    # Keep the generated solver separate from the example MPC's files.
    ocp.code_export_directory = "c_generated_code/attitude_mpcc_v3_alt"
    builder = None
    if os.name == "nt":
        builder = ocp_get_default_cmake_builder()
        builder.generator = "MinGW Makefiles"
        builder.build_dir = "build-mingw"
    solver = AcadosOcpSolver(
        ocp,
        json_file="c_generated_code/attitude_mpcc_v3_alt.json",
        cmake_builder=builder,
        verbose=False,
    )
    return solver, ocp

# Copyright (c) 2024 Learning Systems and Robotics Lab (LSY)
# SPDX-License-Identifier: MIT
"""Complete frozen expanded-soft drag_030 settings; TOML tuning is rejected."""

MPCC_SETTINGS = {
    "adaptation_rate": 2,
    "attitude_rate_weight": 0.1,
    "attitude_slew_weight": 0.02,
    "contour_weight": 800,
    "horizon_steps": 40,
    "lag_weight": 400,
    "max_angle": 0.875,
    "max_speed": 3.2,
    "obstacle_clearance": 0.26,
    "progress_weight": 12,
    "reference_speed": 3,
    "terminal_weight": 0.2,
    "thrust_slew_weight": 0.1,
    "gate_offset": 0.162,
    "warp_width": 0.4,
    "opening_margin": 0.02,
    "pole_width": 0.39375,
    "pole_passes": 8,
    "pole_vertical_buffer": 0.1,
    "departure_depth": 0.25,
    "departure_rise": 0.18,
    "influence_extent": 1.2,
    "influence_taper": 0.2,
    "lateral_extent": 0.6,
    "lateral_taper": 0.12,
    "vertical_extent": 0.6,
    "vertical_taper": 0.12,
    "contour_horizontal_scale": 1,
    "contour_vertical_scale": 1,
    "attitude_rp_weight": 1,
    "attitude_yaw_weight": 1,
    "command_attitude_weight": 1,
    "command_thrust_weight": 50,
    "terminal_velocity_weight": 0.1,
    "yaw_bound_scale": 1,
    "adapt_altitude": 0.15,
    "adapt_thrust_change": 0.04,
    "adapt_raw_low": 0.6,
    "adapt_raw_high": 1.5,
    "adapt_clip_low": 0.7,
    "adapt_clip_high": 1.4,
    "rti_passes": 3,
    "condensing_length": 10,
    "qp_iterations": 50,
    "solver_tolerance": 0.0001,
    "integration_substeps": 1,
    "qp_tolerance_scale": 1,
}

GEOMETRY_SETTINGS = {
    "gate_center_snap": 1,
    "over_gate_lift": 0.15,
    "observed_obstacle_clearance": None,
}

PREDICTION_SETTINGS = {
    "drag_strength": 0.3,
    "attitude_response_scale": 1,
    "attitude_command_gain_scale": 1,
    "thrust_gain_mode": "ema",
    "initial_gain": 1,
    "initial_covariance": 0.0025,
    "measurement_variance": 0.01,
    "process_noise_rate": 0.0008,
    "covariance_max": 0.01,
}

NUMERICAL_SETTINGS = {
    "qp_solver_cond_ric_alg": 1,
    "qp_solver_ric_alg": 0,
    "levenberg_marquardt": 0.0001,
}

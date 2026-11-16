# Copyright (c) 2024 Learning Systems and Robotics Lab (LSY)
# SPDX-License-Identifier: MIT
"""Fixed nominal drag model and public-observation EMA thrust adaptation for v3."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.mpcc_v3_settings import NUMERICAL_SETTINGS, PREDICTION_SETTINGS

# Nominal cf21B_500 first-principles drag coefficients divided by nominal mass.
NOMINAL_BETA = np.array([0.021643637770852733, 0.021643637770852733, 0.02477138502714662]) / 0.0434


def validate_prediction(options: dict | None = None) -> dict:
    """Return fixed settings, rejecting unsupported model changes."""
    if options is not None and dict(options) != PREDICTION_SETTINGS:
        raise ValueError("MPCC v3 uses embedded prediction settings.")
    return dict(PREDICTION_SETTINGS)


def validate_numerics(options: dict | None = None) -> dict:
    """Return fixed settings, rejecting unsupported numerical changes."""
    if options is not None and dict(options) != NUMERICAL_SETTINGS:
        raise ValueError("MPCC v3 uses embedded numerical settings.")
    return dict(NUMERICAL_SETTINGS)


def drag_acceleration(
    rotation: Any, velocity: Any, options: dict, *, symbolic: bool = False
) -> Any:
    """Compute nominal body-frame damping rotated into world coordinates."""
    if symbolic:
        import casadi as ca

        damping = ca.diag(ca.DM(NOMINAL_BETA))
    else:
        damping = np.diag(NOMINAL_BETA)
    return -options["drag_strength"] * (rotation @ damping @ rotation.T @ velocity)


class ThrustGainFilter:
    """Fixed EMA thrust-gain filter with the validated public sample gate."""

    def __init__(self, options: dict, settings: dict, dt: float):
        """Initialize the fixed filter and its public-observation history."""
        self.options = validate_prediction(options)
        self.settings, self.dt = settings, dt
        if (
            not settings["adapt_clip_low"]
            <= self.options["initial_gain"]
            <= settings["adapt_clip_high"]
        ):
            raise ValueError("Initial gain outside existing gain bounds")
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("Positive finite dt required")
        self.reset()

    def reset(self):
        """Restore nominal gain and clear the previous observation interval."""
        self.gain = self.options["initial_gain"]
        self.covariance = self.options["initial_covariance"]
        self.previous = None
        self.previous_thrust = None
        self.raw_gain = None
        self.accepted = False
        self.reason = "no_previous_interval"
        self.weight = 0.0

    def correct(self, raw_gain: float | None, reason: str = "accepted"):
        """Predict once per tick, even when a sample is rejected or unavailable."""
        s = self.settings
        self.raw_gain, self.accepted, self.weight = raw_gain, False, 0.0
        self.reason = reason
        if reason != "accepted":
            return
        if raw_gain is None or not np.isfinite(raw_gain):
            self.reason = "nonfinite_gain"
            return
        if not s["adapt_raw_low"] < raw_gain < s["adapt_raw_high"]:
            self.reason = "raw_gain_bounds"
            return
        self.accepted = True
        self.weight = 1 - np.exp(-s["adaptation_rate"] * self.dt)
        self.gain += self.weight * (raw_gain - self.gain)
        self.gain = float(np.clip(self.gain, s["adapt_clip_low"], s["adapt_clip_high"]))

    def observe(self, obs: dict, applied_thrust: float, parameters: dict):
        """obs[k] closes the interval driven by the preceding applied command.

        Endpoint-average body z for thrust (as in Broad). With drag enabled,
        trapezoid-average R diag(beta) R.T v at both observed endpoints.
        """
        raw, reason = None, "no_previous_interval"
        valid = (
            all(np.isfinite(obs[k]).all() for k in ("pos", "vel", "quat"))
            and np.linalg.norm(obs["quat"]) > 1e-12
            and np.isfinite(applied_thrust)
        )
        if not valid:
            self.previous = self.previous_thrust = None
            self.correct(None, "nonfinite_observation_or_command")
            return
        rotation = Rotation.from_quat(obs["quat"]).as_matrix()
        body_z = rotation[:, 2]
        if self.previous is not None:
            velocity, previous_rotation, altitude = self.previous
            if min(altitude, obs["pos"][2]) <= self.settings["adapt_altitude"]:
                reason = "altitude"
            elif abs(applied_thrust - self.previous_thrust) >= self.settings["adapt_thrust_change"]:
                reason = "thrust_change"
            else:
                force = parameters["acc_coef"] + parameters["cmd_f_coef"] * applied_thrust
                expected = (body_z + previous_rotation[:, 2]) * 0.5 * force / parameters["mass"]
                measured = (obs["vel"] - velocity) / self.dt - parameters["gravity_vec"]
                if self.options["drag_strength"]:
                    measured = measured - 0.5 * (
                        drag_acceleration(previous_rotation, velocity, self.options)
                        + drag_acceleration(rotation, obs["vel"], self.options)
                    )
                raw = np.dot(expected, measured) / max(np.dot(expected, expected), 1e-6)
                reason = "accepted"
        self.correct(raw, reason)
        self.previous = (np.array(obs["vel"], copy=True), rotation, float(obs["pos"][2]))
        self.previous_thrust = applied_thrust

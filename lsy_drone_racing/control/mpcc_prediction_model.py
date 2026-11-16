"""Small research model/estimator helpers; only nominal constants and public data."""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

# Installed cf21B_500 first_principles params.toml: -diag(drag_matrix)/mass.
# Fixed nominal values, never obtained from an episode's simulator parameters.
NOMINAL_BETA = np.array([0.021643637770852733, 0.021643637770852733, 0.02477138502714662]) / 0.0434
PREDICTION_DEFAULTS = dict(
    drag_strength=0.0,
    attitude_response_scale=1.0,
    attitude_command_gain_scale=1.0,
    thrust_gain_mode="ema",
    initial_gain=1.0,
    initial_covariance=0.0025,
    measurement_variance=0.01,
    process_noise_rate=0.0008,
    covariance_max=0.01,
)
NUMERICAL_DEFAULTS = dict(qp_solver_cond_ric_alg=1, qp_solver_ric_alg=1, levenberg_marquardt=0.0)


def validate_prediction(options=None):
    values = dict(PREDICTION_DEFAULTS)
    if options is not None:
        if set(options) - set(values):
            raise ValueError("Unknown prediction setting")
        values.update(options)
    if values["thrust_gain_mode"] not in ("ema", "kf"):
        raise ValueError("thrust_gain_mode must be ema or kf")
    for key, value in values.items():
        if key == "thrust_gain_mode":
            continue
        zero_allowed = key in ("drag_strength", "process_noise_rate", "initial_covariance")
        if (
            type(value) not in (int, float)
            or not np.isfinite(value)
            or value < 0
            or (value == 0 and not zero_allowed)
        ):
            raise ValueError("Invalid prediction setting: " + key)
    if values["initial_covariance"] > values["covariance_max"]:
        raise ValueError("Initial covariance exceeds bound")
    return values


def validate_numerics(options=None):
    values = dict(NUMERICAL_DEFAULTS)
    if options is not None:
        if set(options) - set(values):
            raise ValueError("Unknown numerical setting")
        values.update(options)
    for key in ("qp_solver_cond_ric_alg", "qp_solver_ric_alg"):
        if type(values[key]) is not int or values[key] not in (0, 1):
            raise ValueError(key)
    lm = values["levenberg_marquardt"]
    if type(lm) not in (int, float) or not np.isfinite(lm) or not 0 <= lm <= 1e-4:
        raise ValueError("levenberg_marquardt must be in [0, 1e-4]")
    return values


def calibrated_parameters(parameters, options):
    result = dict(parameters)
    s, g = options["attitude_response_scale"], options["attitude_command_gain_scale"]
    for key, scale in (("rpy_coef", s * s), ("rpy_rates_coef", s), ("cmd_rpy_coef", s * s * g)):
        result[key] = np.array(parameters[key], dtype=float, copy=True)
        result[key][:2] *= scale
    return result


def drag_acceleration(rotation, velocity, options, *, symbolic=False):
    """R maps body to world; the same expression serves OCP and observation."""
    if symbolic:
        import casadi as ca

        damping = ca.diag(ca.DM(NOMINAL_BETA))
    else:
        damping = np.diag(NOMINAL_BETA)
    return -options["drag_strength"] * (rotation @ damping @ rotation.T @ velocity)


class ThrustGainFilter:
    """EMA or bounded random-walk scalar KF sharing exactly one sample gate."""

    def __init__(self, options, settings, dt):
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
        self.gain = self.options["initial_gain"]
        self.covariance = self.options["initial_covariance"]
        self.previous = None
        self.previous_thrust = None
        self.raw_gain = None
        self.accepted = False
        self.reason = "no_previous_interval"
        self.weight = 0.0

    def correct(self, raw_gain, reason="accepted"):
        """Predict once per tick, even when a sample is rejected or unavailable."""
        o, s = self.options, self.settings
        self.raw_gain, self.accepted, self.weight = raw_gain, False, 0.0
        self.reason = reason
        if o["thrust_gain_mode"] == "kf":
            self.covariance = float(
                np.clip(self.covariance + o["process_noise_rate"] * self.dt, 0, o["covariance_max"])
            )
        if reason != "accepted":
            return
        if raw_gain is None or not np.isfinite(raw_gain):
            self.reason = "nonfinite_gain"
            return
        if not s["adapt_raw_low"] < raw_gain < s["adapt_raw_high"]:
            self.reason = "raw_gain_bounds"
            return
        self.accepted = True
        if o["thrust_gain_mode"] == "kf":
            self.weight = self.covariance / (self.covariance + o["measurement_variance"])
            self.covariance *= 1 - self.weight
        else:
            self.weight = 1 - np.exp(-s["adaptation_rate"] * self.dt)
        self.gain += self.weight * (raw_gain - self.gain)
        self.gain = float(np.clip(self.gain, s["adapt_clip_low"], s["adapt_clip_high"]))

    def observe(self, obs, applied_thrust, parameters):
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

    def diagnostics(self):
        return dict(
            gain=self.gain,
            raw_gain=self.raw_gain,
            accepted=self.accepted,
            reason=self.reason,
            covariance=self.covariance if self.options["thrust_gain_mode"] == "kf" else None,
            update_weight=self.weight,
        )

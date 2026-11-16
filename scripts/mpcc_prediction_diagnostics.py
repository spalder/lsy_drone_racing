"""Prediction sidecar, outside the compute timer; no full horizon retention."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path

import casadi as ca
import numpy as np
from crazyflow.dynamics.utils.rotation import ang_vel2rpy_rates
from scipy.spatial.transform import Rotation
from lsy_drone_racing.control.mpcc_prediction_model import NOMINAL_BETA


def state(obs):
    quat = np.asarray(obs["quat"])
    return np.r_[
        obs["pos"],
        Rotation.from_quat(quat).as_euler("xyz"),
        obs["vel"],
        ang_vel2rpy_rates(quat, np.asarray(obs["ang_vel"])),
    ]


def errors(predicted, obs):
    attitude = (
        Rotation.from_euler("xyz", predicted[3:6]).inv() * Rotation.from_quat(obs["quat"])
    ).magnitude()
    return dict(
        velocity_mps=float(np.linalg.norm(predicted[6:9] - obs["vel"])),
        attitude_rad=float(attitude),
    )


def summarize(records, key):
    values = [r[key] for r in records if r.get(key) is not None]
    return (
        {
            k: dict(
                n=len(values),
                rmse=float(np.sqrt(np.mean([v[k] ** 2 for v in values]))),
                mean=float(np.mean([v[k] for v in values])),
            )
            for k in ("velocity_mps", "attitude_rad")
        }
        if values
        else {"n": 0}
    )


class PredictionRecorder:
    def __init__(self, controller, effective):
        self.controller, self.effective = controller, effective
        model = controller._ocp.model
        self.step = ca.Function(
            "diagnostic_step", [model.x, model.u, model.p], [model.disc_dyn_expr]
        )
        self.records = []

    def before_action(self, obs, action):
        c = self.controller
        x = np.r_[state(obs), c._progress, action]
        # Progress and stored command do not affect the 12 physical derivatives.
        u = np.r_[action, 0.0]
        p = np.r_[np.zeros(7), c._thrust_gain]
        predicted = np.asarray(self.step(x, u, p)).ravel()[:12]
        self.records.append(
            dict(
                tick=len(self.records),
                pre_action={
                    k: np.asarray(obs[k]).tolist() for k in ("pos", "quat", "vel", "ang_vel")
                },
                applied_command=np.asarray(action).tolist(),
                predicted_next_state=predicted.tolist(),
                thrust=dict(c.adaptation_diagnostics),
                solver_status=c.last_solver_status,
                gain_observation_interval=[len(self.records) - 1, len(self.records)]
                if self.records
                else None,
                fallback=c._inputs is None,
            )
        )

    def after_step(self, obs):
        # Called immediately after env.step, including the last observation.
        record = self.records[-1]
        record["next_observation"] = {
            k: np.asarray(obs[k]).tolist() for k in ("pos", "quat", "vel", "ang_vel")
        }
        prediction = np.asarray(record["predicted_next_state"])
        record["one_step_error"] = (
            errors(prediction, obs) if np.isfinite(prediction).all() else None
        )

    def write(self, directory):
        # Shadow rollouts freeze gain at their starting value, then use the actual
        # recorded future commands. They are model scores, not old MPC plan scores.
        for start, record in enumerate(self.records):
            x = np.r_[state(record["pre_action"]), 0.0, record["applied_command"]]
            p = np.r_[np.zeros(7), record["thrust"]["gain"]]
            for offset, future in enumerate(self.records[start : start + 10], 1):
                x = np.asarray(self.step(x, np.r_[future["applied_command"], 0.0], p)).ravel()
                if offset in (5, 10):
                    key = f"rollout_{offset * 20}ms_error"
                    record[key] = (
                        errors(x, future["next_observation"]) if np.isfinite(x).all() else None
                    )
        summary = {
            key: summarize(self.records, key)
            for key in ("one_step_error", "rollout_100ms_error", "rollout_200ms_error")
        }
        summary["gain_sample_reasons"] = dict(Counter(r["thrust"]["reason"] for r in self.records))
        value = dict(
            schema_version=1,
            state_order="pos, rpy_xyz, world_velocity, rpy_rates",
            interval_seconds=0.02,
            effective_settings=self.effective,
            effective_drag_beta_per_second=(
                self.controller.prediction_settings["drag_strength"] * NOMINAL_BETA
            ).tolist(),
            summary=summary,
            ticks=self.records,
            limitations=[
                "Gain fixed at rollout start; recorded future commands used.",
                "Commands are those sent to env.step; unobserved action disturbances and motors are not read.",
            ],
        )

        # Normalize diagnostic nonfinites to explicit nulls, like the shared recorder.
        def clean(v):
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [clean(x) for x in v]
            if isinstance(v, (float, np.floating)):
                return float(v) if np.isfinite(v) else None
            if isinstance(v, np.bool_):
                return bool(v)
            return v

        with gzip.open(Path(directory) / "prediction.json.gz", "xt", compresslevel=1) as stream:
            json.dump(clean(value), stream, allow_nan=False, separators=(",", ":"))
        return clean(summary)

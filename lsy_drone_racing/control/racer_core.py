"""Shared pieces of the RL racer used by both training and deployment.

The network outputs a = [a_c, a_roll, a_pitch] in [-1, 1]^3. The action mapping turns this into the
attitude command [roll, pitch, yaw, thrust] of the race environment. See notes.md for the design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jax.numpy as jp
from crazyflow.dynamics import load_params as load_dynamics_params

if TYPE_CHECKING:
    from jax import Array

# Mass-normalized thrust c = C_OFFSET + C_SCALE * a_c. a_c = 0 is hover at the nominal mass. C_SCALE
# reaches past the thrust limits so that max thrust is reached at a_c ~ 0.96, which tanh can output.
# Checkpoints store the constants they were trained with (runs before this change: 10.19 / 8.6).
C_OFFSET = 9.81
C_SCALE = 9.0
TILT_SCALE = jp.pi / 2  # Full env range, required to lead attitude setpoints

OBS_DIM = 50
GATE_HALF_OPENING = 0.2  # Inner opening is 0.4 m square
# Inner corners in the gate frame, seen by a drone approaching along +x (x forward, y left, z up):
# top-left, top-right, bottom-right, bottom-left. Reverse passes mirror y.
_GATE_CORNERS = GATE_HALF_OPENING * jp.array(
    [[0.0, 1.0, 1.0], [0.0, -1.0, 1.0], [0.0, -1.0, -1.0], [0.0, 1.0, -1.0]]
)


def quat2mat(q: Array) -> Array:
    """Rotation matrices (..., 3, 3) from xyzw quaternions (..., 4)."""
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return jp.stack(
        [
            jp.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
            jp.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
            jp.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1),
        ],
        -2,
    )


def _gate_block(obs: dict[str, Array], seq_idx: Array) -> Array:
    """Relative inner corners (12) and unrevealed flag (1) of the gate at gate_sequence[seq_idx]."""
    batch = jp.arange(seq_idx.shape[0])
    gate_id = obs["gate_sequence"][batch, seq_idx]
    direction = obs["gate_sequence_direction"][batch, seq_idx]
    corners = _GATE_CORNERS * jp.stack(
        [jp.ones_like(direction), direction, jp.ones_like(direction)], -1
    )[:, None, :].astype(_GATE_CORNERS.dtype)
    rot = quat2mat(obs["gates_quat"][batch, gate_id])  # (N, 3, 3)
    corners_world = obs["gates_pos"][batch, gate_id][:, None, :] + corners @ rot.mT
    rel = corners_world - obs["pos"][:, None, :]
    unrevealed = 1.0 - obs["gates_visited"][batch, gate_id].astype(rel.dtype)
    return jp.concatenate([rel.reshape(-1, 12), unrevealed[:, None]], -1)


def build_obs(obs: dict[str, Array]) -> Array:
    """Network input (N, 50) from a batch of race env observations. Layout in notes.md.

    [v (3), R (9), target gate corners (12) + flag (1), next gate corners (12) + flag (1),
     4 poles x (dx, dy, flag) (12)]. All positions are relative to the drone in world axes.
    """
    n_pass = obs["gate_sequence"].shape[-1]
    target = jp.clip(obs["n_gates_passed"], 0, n_pass - 1)  # After finishing, keep the last gate
    nxt = jp.clip(target + 1, 0, n_pass - 1)  # On the last pass, repeat the target gate
    rot = quat2mat(obs["quat"]).reshape(-1, 9)
    poles_rel = obs["obstacles_pos"][..., :2] - obs["pos"][:, None, :2]
    poles_flag = 1.0 - obs["obstacles_visited"].astype(poles_rel.dtype)
    poles = jp.concatenate([poles_rel, poles_flag[..., None]], -1).reshape(-1, 12)
    return jp.concatenate(
        [obs["vel"], rot, _gate_block(obs, target), _gate_block(obs, nxt), poles], -1
    )


class ActionMap:
    """Map network outputs to the environment's attitude command."""

    def __init__(
        self, drone: str, dynamics: str, c_offset: float = C_OFFSET, c_scale: float = C_SCALE
    ):
        """Load the nominal mass and thrust limits of the drone model."""
        params = load_dynamics_params(dynamics, drone)
        self.mass = float(params["mass"])
        self.thrust_min = float(params["thrust_min"]) * 4
        self.thrust_max = float(params["thrust_max"]) * 4
        self.c_offset, self.c_scale = c_offset, c_scale

    def __call__(self, a: Array) -> Array:
        """Convert network outputs (..., 3) into env actions (..., 4) [roll, pitch, yaw, thrust]."""
        c = self.c_offset + self.c_scale * a[..., 0]
        thrust = jp.clip(c * self.mass, self.thrust_min, self.thrust_max)
        roll = TILT_SCALE * a[..., 1]
        pitch = TILT_SCALE * a[..., 2]
        return jp.stack([roll, pitch, jp.zeros_like(roll), thrust], axis=-1)

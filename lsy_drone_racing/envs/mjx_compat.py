# Copyright 2023 DeepMind Technologies Limited
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# https://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Narrow compatibility fix for MuJoCo 3.10's float32 box-contact sentinel.

The upstream `_box_box` replaces infinite contact distances with `finfo(float).max`,
which is float64 even in a float32 JAX simulation. That conversion overflows back
to infinity. Keep the upstream algorithm and select the limit from the result dtype.
Source: https://github.com/google-deepmind/mujoco/blob/3.10.0/mjx/mujoco/mjx/_src/collision_convex.py
Remove this shim once the pinned dependency includes the dtype correction.
"""

import jax.numpy as jp
import mujoco
from mujoco.mjx._src import collision_convex
from mujoco.mjx._src.collision_types import Collision, ConvexInfo


def _box_box(b1: ConvexInfo, b2: ConvexInfo) -> Collision:
    """Use the upstream box algorithm with a representable no-contact distance."""
    to_local_pos = b2.mat.T @ (b1.pos - b2.pos)
    to_local_mat = b2.mat.T @ b1.mat
    dist, pos, normal = collision_convex._box_box_impl(
        to_local_pos + b1.face @ to_local_mat.T,
        b2.face,
        to_local_pos + b1.vert @ to_local_mat.T,
        b2.vert,
        b1.face_normal @ to_local_mat.T,
        b2.face_normal,
        to_local_mat.T,
        jp.eye(3, dtype=b1.pos.dtype),
    )
    pos = b2.pos + pos @ b2.mat.T
    normal = normal @ b2.mat.T
    dist = jp.where(jp.isinf(dist), jp.finfo(dist.dtype).max, dist)
    return dist, pos, normal


def install_box_contact_fix():
    """Patch only the tested affected release, before collision functions are traced."""
    if mujoco.__version__ == "3.10.0":
        collision_convex._box_box = _box_box

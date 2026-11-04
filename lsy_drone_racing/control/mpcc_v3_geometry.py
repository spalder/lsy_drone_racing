# Copyright (c) 2024 Learning Systems and Robotics Lab (LSY)
# SPDX-License-Identifier: MIT
# Derived from the project MPCC implementation; see repository LICENSE.

"""Public-asset geometry and persistent observations used by MPCC v3.

This module only reads geometry; it does not alter simulation assets or collisions.
All quaternions use scipy's XYZW convention. Bounds are closed,
including the endpoints of configured uniform perturbations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import crazyflow.drones
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _array(value: object, shape: tuple[int, ...]) -> NDArray:
    """Own an immutable, finite array of the required shape."""
    result = np.array(value, dtype=float, copy=True)
    if result.shape != shape or not np.all(np.isfinite(result)):
        raise ValueError(f"Expected finite geometry with shape {shape}.")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned closed bounds, in meters or Euler-angle radians."""

    low: NDArray
    high: NDArray

    def __post_init__(self):
        """Validate and detach bounds from caller-owned arrays."""
        object.__setattr__(self, "low", _array(self.low, (3,)))
        object.__setattr__(self, "high", _array(self.high, (3,)))
        if np.any(self.low > self.high):
            raise ValueError("Lower bounds must not exceed upper bounds.")

    @classmethod
    def zero(cls) -> Bounds:
        """Return a known, unperturbed offset."""
        return cls(np.zeros(3), np.zeros(3))

    @classmethod
    def from_randomization(cls, spec: dict | None) -> Bounds:
        """Read the environment's uniform * scale + offset convention.

        Unbounded or unknown distributions cannot provide a robust finite set.
        Negative scale is supported by exchanging the transformed endpoints.
        """
        if spec is None:
            return cls.zero()
        if spec.get("fn") != "uniform":
            raise ValueError("Track geometry requires bounded uniform object randomizations.")
        kwargs = spec.get("kwargs", {})
        if set(kwargs) - {"minval", "maxval"}:
            raise ValueError("Unsupported uniform object randomization arguments.")
        low = np.broadcast_to(np.asarray(kwargs.get("minval", 0), dtype=float), (3,))
        high = np.broadcast_to(np.asarray(kwargs.get("maxval", 1), dtype=float), (3,))
        if np.any(low > high):
            raise ValueError("Randomization minval must not exceed maxval.")
        scale = np.asarray(spec.get("scale", 1), dtype=float)
        offset = np.asarray(spec.get("offset", 0), dtype=float)
        if not all(np.all(np.isfinite(value)) for value in (low, high, scale, offset)):
            raise ValueError("Randomization bounds, scale and offset must be finite.")
        a, b = low * scale + offset, high * scale + offset
        return cls(np.minimum(a, b), np.maximum(a, b))


@dataclass(frozen=True)
class Pose:
    """A stationary object's position and orientation, separate from uncertainty."""

    position: NDArray
    quaternion: NDArray

    def __post_init__(self):
        """Copy position and normalize a nonzero quaternion."""
        object.__setattr__(self, "position", _array(self.position, (3,)))
        quat = _array(self.quaternion, (4,))
        norm = np.linalg.norm(quat)
        if norm < 1e-12:
            raise ValueError("Object quaternion must be nonzero.")
        object.__setattr__(self, "quaternion", _array(quat / norm, (4,)))


@dataclass(frozen=True)
class Primitive:
    """An asset's box or capsule in the owning object's local frame."""

    name: str
    kind: str
    center: NDArray
    rotation: NDArray
    size: NDArray

    def __post_init__(self):
        """Own local geometry and reject unsupported primitive shapes."""
        if self.kind not in {"box", "capsule"}:
            raise ValueError(f"Unsupported collision primitive: {self.kind}")
        for name, shape in (("center", (3,)), ("rotation", (3, 3)), ("size", (3,))):
            object.__setattr__(self, name, _array(getattr(self, name), shape))
        if np.any(self.size < 0):
            raise ValueError("Collision sizes must be nonnegative.")

    @property
    def radius_bound(self) -> float:
        """Bound distance from the object origin, for uncertain rotation."""
        extent = np.linalg.norm(self.size) if self.kind == "box" else sum(self.size[:2])
        return float(np.linalg.norm(self.center) + extent)


def _load_primitives(path: Path, body_name: str, selected: str | None = None) -> tuple:
    """Let MuJoCo resolve MJCF defaults; read only static public asset geometry."""
    model = mujoco.MjModel.from_xml_path(str(path))
    body_id = model.body(body_name).id
    primitives = []
    kinds = {mujoco.mjtGeom.mjGEOM_BOX: "box", mujoco.mjtGeom.mjGEOM_CAPSULE: "capsule"}
    for i in range(model.ngeom):
        if model.geom_bodyid[i] != body_id:
            # Current track assets have no collidable children. Fail closed if that changes.
            if selected is None and (model.geom_contype[i] or model.geom_conaffinity[i]):
                raise ValueError(f"Unsupported collision body in {path}.")
            continue
        name = model.geom(i).name
        if selected is not None:
            if name != selected:
                continue
        elif not (model.geom_contype[i] or model.geom_conaffinity[i]):
            continue
        if model.geom_type[i] not in kinds:
            raise ValueError(f"Unsupported collision geometry {name} in {path}.")
        primitives.append(
            Primitive(
                name,
                kinds[model.geom_type[i]],
                model.geom_pos[i],
                Rotation.from_quat(model.geom_quat[i], scalar_first=True).as_matrix(),
                model.geom_size[i],
            )
        )
    if not primitives:
        raise ValueError(f"No supported collision geometry in {path}.")
    return tuple(primitives)


@dataclass(frozen=True)
class TrackObject:
    """Nominal information plus an optional revealed pose, retained until reset."""

    nominal_pose: Pose
    position_uncertainty: Bounds
    rotation_uncertainty: Bounds
    primitives: tuple[Primitive, ...]
    observed_pose: Pose | None = None

    @property
    def detected(self) -> bool:
        """Whether an observation has revealed this object's stationary pose."""
        return self.observed_pose is not None

    @property
    def planning_pose(self) -> Pose:
        """Use nominal information until detection, then the persistent observation."""
        return self.observed_pose if self.detected else self.nominal_pose


@dataclass(frozen=True)
class GeometryUpdate:
    """Object IDs whose information changed, for local planning invalidation."""

    gates: tuple[int, ...] = ()
    obstacles: tuple[int, ...] = ()

    @property
    def changed(self) -> bool:
        """Whether any planning geometry must be refreshed."""
        return bool(self.gates or self.obstacles)


class TrackGeometry:
    """Persistent course knowledge built solely from configuration and observations."""

    def __init__(self, config: dict):
        """Load static assets and bounded nominal course information."""
        track = config.env.track
        if track.get("randomize", False):
            raise ValueError(
                "TrackGeometry requires a fixed nominal layout (track.randomize=false)."
            )
        randomizations = config.env.get("randomizations", {})
        gate_pos = Bounds.from_randomization(randomizations.get("gate_pos"))
        gate_rpy = Bounds.from_randomization(randomizations.get("gate_rpy"))
        pole_pos = Bounds.from_randomization(randomizations.get("obstacle_pos"))
        assets = Path(__file__).parents[1] / "envs/assets"
        gate_shapes = _load_primitives(assets / "gate.xml", "gate")
        pole_shapes = _load_primitives(assets / "obstacle.xml", "obstacle")
        drone_asset = Path(crazyflow.drones.__file__).parent / f"{config.sim.drone}.xml"
        # RaceCore explicitly enables col_box, although the MJCF default is a sphere.
        self.vehicle = _load_primitives(drone_asset, "drone", "col_box")[0]
        self.flight_bounds = Bounds(
            track.safety_limits.pos_limit_low, track.safety_limits.pos_limit_high
        )
        self.gates = tuple(
            TrackObject(
                Pose(gate["pos"], Rotation.from_euler("xyz", gate["rpy"]).as_quat()),
                gate_pos,
                gate_rpy,
                gate_shapes,
            )
            for gate in track.gates
        )
        self.obstacles = tuple(
            TrackObject(Pose(pole["pos"], [0, 0, 0, 1]), pole_pos, Bounds.zero(), pole_shapes)
            for pole in track.obstacles
        )
        self.revision = 0

    def reset(self):
        """Forget revealed poses at an episode boundary, keeping nominal geometry."""
        self.gates = tuple(replace(obj, observed_pose=None) for obj in self.gates)
        self.obstacles = tuple(replace(obj, observed_pose=None) for obj in self.obstacles)
        self.revision += 1

    def update(self, obs: dict) -> GeometryUpdate:
        """Atomically consume visited flags and public poses; ignore unrevealed poses.

        A false flag never revokes an existing detection. This retains the last
        revealed pose even if a caller later supplies nominal coordinates outside
        sensor range. A true flag also permits refreshed observed poses.
        """
        updated, changes = [], []
        for key, objects in (("gates", self.gates), ("obstacles", self.obstacles)):
            count = len(objects)
            flags = np.asarray(obs[f"{key}_visited"])
            if flags.shape != (count,) or not np.all(np.isin(flags, [False, True])):
                raise ValueError(f"{key}_visited must contain one boolean per object.")
            positions = _array(obs[f"{key}_pos"], (count, 3))
            quats = (
                _array(obs["gates_quat"], (count, 4))
                if key == "gates"
                else np.tile([0, 0, 0, 1], (count, 1))
            )
            group, changed = list(objects), []
            for i, obj in enumerate(objects):
                if not flags[i]:
                    continue
                pose = Pose(positions[i], quats[i])
                old = obj.observed_pose
                same_rotation = old is not None and (
                    np.array_equal(old.quaternion, pose.quaternion)
                    or np.array_equal(old.quaternion, -pose.quaternion)
                )
                if (
                    old is None
                    or not np.array_equal(old.position, pose.position)
                    or not same_rotation
                ):
                    group[i] = replace(obj, observed_pose=pose)
                    changed.append(i)
            updated.append(tuple(group))
            changes.append(tuple(changed))
        change = GeometryUpdate(*changes)
        self.gates, self.obstacles = updated
        if change.changed:
            self.revision += 1
        return change

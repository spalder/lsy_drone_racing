"""Conservative geometric corridors for the fixed nominal racing course.

Regions certify free space for a stated vehicle envelope, not dynamic feasibility.
The bounded roadmap is deliberately incomplete: failure never proves a course is
blocked. No corridor is silently relaxed when geometry or uncertainty prevents one.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import product
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial.transform import Rotation

from lsy_drone_racing.control.track_geometry import Bounds, Primitive, TrackGeometry, _array

if TYPE_CHECKING:
    from numpy.typing import NDArray


@dataclass(frozen=True)
class VehicleEnvelope:
    """Bound the box at arbitrary yaw with body-z tilt at most max_tilt radians."""

    vehicle: Primitive
    max_tilt: float
    tracking_margin: float

    def __post_init__(self):
        """Require an upright body-frame box and explicit finite margin."""
        if self.vehicle.kind != "box" or not np.allclose(self.vehicle.rotation, np.eye(3)):
            raise ValueError("Corridors require a body-aligned vehicle box.")
        if not np.isfinite(self.max_tilt) or not 0 <= self.max_tilt <= np.pi / 2:
            raise ValueError("max_tilt must be between zero and pi/2.")
        if not np.isfinite(self.tracking_margin) or self.tracking_margin < 0:
            raise ValueError("tracking_margin must be finite and nonnegative.")

    def support(self, directions: NDArray) -> NDArray:
        """Return a symmetric support upper bound, valid over the whole tilt range."""
        directions = np.asarray(directions)
        radius = self.vehicle.radius_bound
        vertical = min(
            radius,
            self.vehicle.size[2]
            + np.linalg.norm(self.vehicle.size[:2]) * np.sin(self.max_tilt)
            + np.linalg.norm(self.vehicle.center),
        )
        norm = np.linalg.norm(directions, axis=-1)
        cylinder = radius * np.linalg.norm(directions[..., :2], axis=-1)
        cylinder += vertical * np.abs(directions[..., 2])
        return np.minimum(radius * norm, cylinder) + self.tracking_margin * norm


@dataclass(frozen=True)
class ForbiddenBox:
    """Conservative oriented box of forbidden vehicle-origin positions."""

    owner: tuple[str, int]
    center: NDArray
    rotation: NDArray
    half_size: NDArray

    def __post_init__(self):
        """Detach geometric arrays from mutable source data."""
        for key, shape in (("center", (3,)), ("rotation", (3, 3)), ("half_size", (3,))):
            object.__setattr__(self, key, _array(getattr(self, key), shape))
        if np.any(self.half_size <= 0):
            raise ValueError("Forbidden box dimensions must be positive.")

    def minimum(self, directions: NDArray) -> NDArray:
        """Return minimum projection along each direction."""
        return directions @ self.center - np.abs(directions @ self.rotation) @ self.half_size

    def separating_plane(self, start: NDArray, end: NDArray) -> tuple[NDArray, float]:
        """Find a segment/box separating axis, covering the entire connecting segment."""
        axes = np.vstack((self.rotation.T, np.cross(end - start, self.rotation.T)))
        axes = axes[np.linalg.norm(axes, axis=1) > 1e-12]
        axes /= np.linalg.norm(axes, axis=1)[:, None]
        axes = np.vstack((axes, -axes))
        gaps = self.minimum(axes) - np.maximum(axes @ start, axes @ end)
        best = int(np.argmax(gaps))
        return axes[best], float(gaps[best])


@dataclass(frozen=True)
class CorridorCell:
    """A bounded convex region A*p <= b tied to one ordered progress interval."""

    A: NDArray
    b: NDArray
    start: NDArray
    end: NDArray
    progress_low: float
    progress_high: float
    occurrence: int

    def __post_init__(self):
        """Own finite halfspaces and route endpoints."""
        object.__setattr__(self, "A", _array(self.A, (len(self.b), 3)))
        object.__setattr__(self, "b", _array(self.b, (len(self.b),)))
        object.__setattr__(self, "start", _array(self.start, (3,)))
        object.__setattr__(self, "end", _array(self.end, (3,)))
        if not 0 <= self.progress_low < self.progress_high < np.inf:
            raise ValueError("Cell progress must be a finite, increasing interval.")

    def contains(self, position: NDArray, progress: float) -> bool:
        """Check both spatial and longitudinal progress membership."""
        return bool(
            self.progress_low <= progress <= self.progress_high
            and np.all(self.A @ position <= self.b + 1e-9)
        )


@dataclass(frozen=True)
class GatePassage:
    """A feasible crossing region: intersect cell halfspaces with the gate plane."""

    gate_id: int
    occurrence: int
    direction: int
    origin: NDArray
    normal: NDArray
    cell_index: int

    def __post_init__(self):
        """Own the crossing plane and reject invalid directions."""
        object.__setattr__(self, "origin", _array(self.origin, (3,)))
        object.__setattr__(self, "normal", _array(self.normal, (3,)))
        if self.direction not in (-1, 1) or not np.isclose(np.linalg.norm(self.normal), 1):
            raise ValueError("Passage requires a signed direction and unit normal.")


@dataclass(frozen=True)
class Corridor:
    """Ordered overlapping cells and gate regions for one geometry revision."""

    cells: tuple[CorridorCell, ...]
    passages: tuple[GatePassage, ...]
    revision: int
    envelope: VehicleEnvelope
    gate_order: tuple[int, ...]
    first_occurrence: int

    def cell_at(self, progress: float, occurrence: int) -> CorridorCell:
        """Select the scheduled cell; never search distant cells for a wider opening."""
        for cell in self.cells:
            if cell.progress_low <= progress < cell.progress_high:
                if cell.occurrence != occurrence:
                    raise ValueError("Progress does not belong to the required gate occurrence.")
                return cell
        if self.cells and progress == self.cells[-1].progress_high:
            if occurrence == self.cells[-1].occurrence:
                return self.cells[-1]
        raise ValueError("Progress is outside this corridor.")


@dataclass(frozen=True)
class CorridorResult:
    """A certified geometric corridor or an explicit, non-global failure result."""

    status: str
    corridor: Corridor | None = None
    reason: str = ""
    objects_to_observe: tuple[tuple[str, int], ...] = ()


class CorridorPlanner:
    """Build a revision-specific corridor using route guides and bounded detours."""

    def __init__(self, geometry: TrackGeometry, tracking_margin: float, max_tilt: float = 0.35):
        """Snapshot conservative obstacles, retaining every physical gate and pole."""
        self.geometry = geometry
        self.revision = geometry.revision
        self.envelope = VehicleEnvelope(geometry.vehicle, max_tilt, tracking_margin)
        self.epsilon = 1e-5
        extent = self.envelope.support(np.eye(3))
        self.flight_bounds = Bounds(
            geometry.flight_bounds.low + extent, geometry.flight_bounds.high - extent
        )
        self.boxes = []
        self.unknown = []
        for kind, objects in (("gate", geometry.gates), ("obstacle", geometry.obstacles)):
            for i, obj in enumerate(objects):
                uncertain = not obj.detected and any(
                    np.any(bounds.low != 0) or np.any(bounds.high != 0)
                    for bounds in (obj.position_uncertainty, obj.rotation_uncertainty)
                )
                if uncertain:
                    self.unknown.append((kind, i))
                pose = obj.planning_pose
                rotation = Rotation.from_quat(pose.quaternion).as_matrix()
                translation = Bounds.zero() if obj.detected else obj.position_uncertainty
                midpoint = (translation.low + translation.high) / 2
                half_range = (translation.high - translation.low) / 2
                angles = obj.rotation_uncertainty
                angle = 0 if obj.detected else min(
                    np.sum(np.maximum(np.abs(angles.low), np.abs(angles.high))), np.pi
                )
                for primitive in obj.primitives:
                    axes = rotation @ primitive.rotation
                    size = primitive.size if primitive.kind == "box" else np.array(
                        [primitive.size[0], primitive.size[0], sum(primitive.size[:2])]
                    )
                    padding = 2 * primitive.radius_bound * np.sin(angle / 2)
                    inflated = size + np.abs(axes.T) @ half_range + padding
                    inflated += self.envelope.support(axes.T)
                    self.boxes.append(ForbiddenBox(
                        (kind, i), pose.position + rotation @ primitive.center + midpoint,
                        axes, inflated,
                    ))
        self.boxes = tuple(self.boxes)
        # Connectors must go around gates, not consume an unscheduled passage.
        self.barriers = tuple(
            ForbiddenBox(
                ("gate", i), gate.planning_pose.position,
                Rotation.from_quat(gate.planning_pose.quaternion).as_matrix(),
                np.array([0.002, 0.5, 0.5]),
            ) for i, gate in enumerate(geometry.gates)
        )

    def _free_segments(self, start: NDArray, ends: NDArray, boxes: tuple) -> NDArray:
        """Use exact line/OBB slab intersections, including segment interiors."""
        free = np.all(ends > self.flight_bounds.low, axis=1)
        free &= np.all(ends < self.flight_bounds.high, axis=1)
        for box in boxes:
            origin = (start - box.center) @ box.rotation
            delta = (ends - start) @ box.rotation
            half = box.half_size + 2 * self.epsilon
            parallel = np.abs(delta) < 1e-12
            safe_delta = np.where(parallel, 1, delta)
            a, b = (-half - origin) / safe_delta, (half - origin) / safe_delta
            low, high = np.minimum(a, b), np.maximum(a, b)
            low = np.where(parallel, -np.inf, low)
            high = np.where(parallel, np.inf, high)
            hit = np.maximum(low.max(axis=1), 0) <= np.minimum(high.min(axis=1), 1)
            hit &= ~np.any(parallel & (np.abs(origin) > half), axis=1)
            free &= ~hit
        return free

    def _route(self, start: NDArray, end: NDArray, guides: NDArray) -> NDArray | None:
        """Search a finite visibility roadmap; corners propose alternative passing sides."""
        boxes = self.boxes + self.barriers
        if self._free_segments(start, end[None], boxes)[0]:
            return np.array([start, end])
        signs = np.array(list(product((-1, 1), repeat=3)))
        corners = [
            box.center + (signs * (box.half_size + 0.025)) @ box.rotation.T for box in boxes
        ]
        candidates = np.vstack([guides, *corners]) if corners else guides
        valid = np.all(candidates > self.flight_bounds.low, axis=1)
        valid &= np.all(candidates < self.flight_bounds.high, axis=1)
        for box in boxes:
            local = (candidates - box.center) @ box.rotation
            valid &= np.any(np.abs(local) > box.half_size + 2 * self.epsilon, axis=1)
        nodes = np.vstack((start, end, candidates[valid]))
        costs = np.full(len(nodes), np.inf)
        costs[0] = 0
        parent = np.full(len(nodes), -1, dtype=int)
        queue = [(float(np.linalg.norm(end - start)), 0)]
        closed = set()
        while queue:
            _, i = heapq.heappop(queue)
            if i in closed:
                continue
            if i == 1:
                indices = [1]
                while indices[-1] != 0:
                    indices.append(int(parent[indices[-1]]))
                return nodes[indices[::-1]]
            closed.add(i)
            free = self._free_segments(nodes[i], nodes, boxes)
            distance = np.linalg.norm(nodes - nodes[i], axis=1)
            for j in np.flatnonzero(free & (costs[i] + distance < costs - 1e-10)):
                costs[j] = costs[i] + distance[j]
                parent[j] = i
                heapq.heappush(queue, (float(costs[j] + np.linalg.norm(nodes[j] - end)), int(j)))
        return None

    def _cell(
        self, start: NDArray, end: NDArray, progress: float, occurrence: int,
        aperture: tuple[NDArray, NDArray] | None = None,
        crossing_gate: int | None = None,
    ) -> CorridorCell:
        """Separate the entire seed segment from every inflated primitive."""
        tangent = end - start
        length = np.linalg.norm(tangent)
        tangent /= length
        A = [*np.eye(3), *-np.eye(3), tangent, -tangent]
        b = [*self.flight_bounds.high, *-self.flight_bounds.low,
             tangent @ end + 0.02, -tangent @ start + 0.02]
        boxes = self.boxes + tuple(
            box for box in self.barriers if box.owner != ("gate", crossing_gate)
        )
        for box in boxes:
            axis, gap = box.separating_plane(start, end)
            if gap <= 2 * self.epsilon:
                raise ValueError("Seed segment cannot be separated from inflated geometry.")
            A.append(axis)
            b.append(float(box.minimum(axis) - self.epsilon))
        if aperture is not None:
            A.extend(aperture[0])
            b.extend(aperture[1])
        return CorridorCell(np.array(A), np.array(b), start, end, progress, progress + length, occurrence)

    def _gate_candidates(self, gate_id: int, direction: int) -> list:
        """Propose crossing segments inside the eroded physical opening, never fixed anchors."""
        gate = self.geometry.gates[gate_id]
        shapes = {shape.name: shape for shape in gate.primitives}
        required = ("col_left", "col_right", "col_bottom", "col_top")
        if any(name not in shapes for name in required) or any(
            shapes[name].kind != "box" or not np.allclose(shapes[name].rotation, np.eye(3))
            for name in required
        ):
            raise ValueError("Gate opening must be defined by four local axis-aligned frame boxes.")
        pose = gate.planning_pose
        axes = Rotation.from_quat(pose.quaternion).as_matrix()
        extent = self.envelope.support(axes.T)
        low = np.array([shapes["col_left"].center[1] + shapes["col_left"].size[1],
                        shapes["col_bottom"].center[2] + shapes["col_bottom"].size[2]])
        high = np.array([shapes["col_right"].center[1] - shapes["col_right"].size[1],
                         shapes["col_top"].center[2] - shapes["col_top"].size[2]])
        low += extent[1:] + self.epsilon
        high -= extent[1:] + self.epsilon
        if np.any(low >= high):
            return []
        A = np.vstack((axes[:, 1:].T, -axes[:, 1:].T))
        b = A @ pose.position + np.r_[high, -low]
        depth = max(abs(shapes[name].center[0]) + shapes[name].size[0] for name in required)
        depth += extent[0] + 0.01
        normal = axes[:, 0] * direction
        candidates = []
        for fy, fz in product((0.0, -0.75, 0.75), repeat=2):
            yz = (low + high) / 2 + np.array([fy, fz]) * (high - low) / 2
            crossing = pose.position + axes[:, 1:] @ yz
            start, end = crossing - normal * depth, crossing + normal * depth
            other_barriers = tuple(box for box in self.barriers if box.owner != ("gate", gate_id))
            if self._free_segments(start, end[None], self.boxes + other_barriers)[0]:
                candidates.append((start, end, (A, b)))
        return candidates

    def _failure(self, reason: str) -> CorridorResult:
        """Distinguish unresolved uncertainty from a failed known-layout search."""
        status = "observation_required" if self.unknown else "route_not_found"
        return CorridorResult(status, reason=reason, objects_to_observe=tuple(self.unknown))

    def build(
        self, start: NDArray, gate_order: list[int], guide_points: NDArray,
        finish: NDArray | None = None, first_occurrence: int = 0,
    ) -> CorridorResult:
        """Build remaining ordered passages, including repeated/reverse physical gates.

        Start must already be airborne within the eroded flight bounds. Nonzero
        uncertainty on a required gate requests observation before certifying its
        crossing; uncertain poles and other gates remain inflated during routing.
        """
        if self.geometry.revision != self.revision:
            return CorridorResult("stale_geometry", reason="Rebuild the planner after a geometry update.")
        if not 0 <= first_occurrence <= len(gate_order):
            raise ValueError("Invalid first gate occurrence.")
        if any(int(entry) != entry or not 1 <= abs(entry) <= len(self.geometry.gates) for entry in gate_order):
            raise ValueError("Gate order must contain signed, one-based gate numbers.")
        start = _array(start, (3,))
        guides = _array(guide_points, (len(guide_points), 3))
        finish = None if finish is None else _array(finish, (3,))
        if not self._free_segments(start, start[None], self.boxes)[0]:
            return self._failure("Start is outside cleared airborne space; takeoff/recovery is required.")
        if finish is not None and not self._free_segments(finish, finish[None], self.boxes)[0]:
            return self._failure("Finish is outside cleared space.")
        cells, passages = [], []
        progress, current = 0.0, start
        for occurrence in range(first_occurrence, len(gate_order)):
            entry = gate_order[occurrence]
            gate_id, direction = abs(entry) - 1, int(np.sign(entry))
            if ("gate", gate_id) in self.unknown:
                return CorridorResult(
                    "observation_required", reason=f"Gate occurrence {occurrence} needs a revealed pose.",
                    objects_to_observe=(("gate", gate_id),),
                )
            choices = self._gate_candidates(gate_id, direction)
            if not choices:
                return self._failure(f"No certified passage candidate for gate occurrence {occurrence}.")
            target = finish
            if occurrence + 1 < len(gate_order):
                target = self.geometry.gates[abs(gate_order[occurrence + 1]) - 1].planning_pose.position
            choices.sort(key=lambda choice: np.linalg.norm(choice[0] - current)
                         + (0 if target is None else np.linalg.norm(target - choice[1])))
            route = None
            for entry_point, exit_point, aperture in choices:
                route = self._route(current, entry_point, guides)
                if route is not None:
                    break
            if route is None:
                return self._failure(f"Roadmap found no approach to gate occurrence {occurrence}.")
            for a, b in zip(route[:-1], route[1:], strict=True):
                if np.linalg.norm(b - a) > 1e-8:
                    cell = self._cell(a, b, progress, occurrence)
                    cells.append(cell)
                    progress = cell.progress_high
            cell = self._cell(entry_point, exit_point, progress, occurrence, aperture, gate_id)
            gate = self.geometry.gates[gate_id]
            passages.append(GatePassage(
                gate_id, occurrence, direction, gate.planning_pose.position,
                Rotation.from_quat(gate.planning_pose.quaternion).as_matrix()[:, 0] * direction,
                len(cells),
            ))
            cells.append(cell)
            progress, current = cell.progress_high, exit_point
        if finish is not None and np.linalg.norm(finish - current) > 1e-8:
            route = self._route(current, finish, guides)
            if route is None:
                return self._failure("Roadmap found no final departure route.")
            for a, b in zip(route[:-1], route[1:], strict=True):
                cell = self._cell(a, b, progress, len(gate_order))
                cells.append(cell)
                progress = cell.progress_high
        if not cells:
            return CorridorResult("route_not_found", reason="No nonzero route segment was requested.")
        corridor = Corridor(
            tuple(cells), tuple(passages), self.revision, self.envelope,
            tuple(gate_order), first_occurrence,
        )
        errors = self.validate(corridor)
        if errors:
            return CorridorResult("validation_failed", reason="; ".join(errors))
        return CorridorResult("certified", corridor=corridor)

    def validate(self, corridor: Corridor) -> tuple[str, ...]:
        """Check whole-cell separation, flight bounds, overlap and passage direction.

        A separating halfspace certifies every point of a cell, including the
        continuum between route nodes. This is deliberately stronger than sampled
        centerline checks. Certification is conditional on the stated envelope.
        """
        errors = []
        if corridor.revision != self.revision or self.geometry.revision != self.revision:
            errors.append("stale geometry")
        envelope = corridor.envelope
        if (envelope.max_tilt != self.envelope.max_tilt
            or envelope.tracking_margin != self.envelope.tracking_margin
            or any(not np.array_equal(getattr(envelope.vehicle, key),
                                      getattr(self.envelope.vehicle, key))
                   for key in ("size", "center", "rotation"))):
            errors.append("vehicle envelope does not match planner")
        if not corridor.cells:
            return tuple(errors + ["empty corridor"])
        expected = list(range(corridor.first_occurrence, len(corridor.gate_order)))
        if [p.occurrence for p in corridor.passages] != expected:
            errors.append("missing or out-of-order gate passages")
        if len({p.cell_index for p in corridor.passages}) != len(corridor.passages):
            errors.append("duplicate passage cells")
        if any(not 0 <= p.cell_index < len(corridor.cells) for p in corridor.passages):
            return tuple(errors + ["passage cell index out of range"])
        crossing_gates = {passage.cell_index: passage.gate_id for passage in corridor.passages}
        occurrence = corridor.first_occurrence
        for i, cell in enumerate(corridor.cells):
            if cell.occurrence != occurrence:
                errors.append(f"cell {i}: wrong gate occurrence")
            if i in crossing_gates:
                occurrence += 1
            if not cell.contains(cell.start, cell.progress_low) or not cell.contains(cell.end, cell.progress_high):
                errors.append(f"cell {i}: seed outside region")
            tangent = (cell.end - cell.start) / np.linalg.norm(cell.end - cell.start)
            normals = np.vstack((np.eye(3), -np.eye(3), tangent, -tangent))
            limits = np.r_[self.flight_bounds.high, -self.flight_bounds.low,
                           tangent @ cell.end + 0.02, -tangent @ cell.start + 0.02]
            for normal, limit in zip(normals, limits, strict=True):
                if not np.any(np.all(np.isclose(cell.A, normal, atol=1e-12, rtol=0), axis=1)
                              & (cell.b <= limit + 1e-12)):
                    errors.append(f"cell {i}: missing flight or longitudinal boundary")
            boxes = self.boxes + tuple(
                box for box in self.barriers if box.owner != ("gate", crossing_gates.get(i))
            )
            for box in boxes:
                if not np.any(box.minimum(cell.A) - cell.b >= self.epsilon * 0.9):
                    errors.append(f"cell {i}: no separation certificate for {box.owner}")
            if i:
                previous = corridor.cells[i - 1]
                if (abs(previous.progress_high - cell.progress_low) > 1e-9
                    or not np.allclose(previous.end, cell.start, atol=1e-9, rtol=0)):
                    errors.append(f"cell {i}: disconnected route")
                # Strict interior overlap at the common endpoint, not just touching.
                if (np.min(previous.b - previous.A @ cell.start) <= 0
                    or np.min(cell.b - cell.A @ cell.start) <= 0):
                    errors.append(f"cell {i}: no interior overlap")
        for passage in corridor.passages:
            if not 0 <= passage.occurrence < len(corridor.gate_order):
                errors.append("gate occurrence out of range")
                continue
            entry = corridor.gate_order[passage.occurrence]
            if passage.gate_id != abs(entry) - 1 or passage.direction != np.sign(entry):
                errors.append("gate passage does not match requested order")
                continue
            gate = self.geometry.gates[passage.gate_id]
            normal = Rotation.from_quat(gate.planning_pose.quaternion).as_matrix()[:, 0]
            if (not np.allclose(passage.origin, gate.planning_pose.position)
                or not np.allclose(passage.normal, normal * passage.direction)):
                errors.append("gate passage plane does not match geometry")
            cell = corridor.cells[passage.cell_index]
            if (cell.occurrence != passage.occurrence
                or (cell.start - passage.origin) @ passage.normal >= 0
                or (cell.end - passage.origin) @ passage.normal <= 0):
                errors.append(f"gate occurrence {passage.occurrence}: invalid crossing")
            choices = self._gate_candidates(passage.gate_id, passage.direction)
            if not choices:
                errors.append("no feasible gate aperture")
                continue
            for normal, limit in zip(*choices[0][2], strict=True):
                if not np.any(np.all(np.isclose(cell.A, normal, atol=1e-12, rtol=0), axis=1)
                              & (cell.b <= limit + 1e-12)):
                    errors.append("missing physical aperture boundary")
        return tuple(errors)

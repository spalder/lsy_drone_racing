"""Training environment for the RL racer: race env with network actions, observations and reward.

Reward (Song et al. 2023, eq. 5), computed from the true env state:
    progress = d(t - p_prev) - d(t - p) toward a target point t of the target gate before the step,
               d(v) = sqrt(vx^2 + vy^2 + height_weight * vz^2) (height error counts more).
               t is the true gate center if the drone is in front of the gate (inside a 45 deg cone
               around its pass axis or in front of the opening), otherwise the approach point
               approach_dist in front of the gate on its axis. Both distances use the same t.
               For passes k with via_pass_dist[k] > 0, t is first the via point via_pass_dist[k] in
               front of the gate on its axis, until the drone is within via_radius of it (+via_bonus) or starts its approach
               already in front of the gate (curriculum help, removed in a later phase).
               With unrevealed_speed_cap > 0, progress per step is capped at that speed while the
               target gate is not revealed yet (still at its nominal pose in the observation).
    r = progress_coef * progress - rate_coef * |omega|      normal step
    r = ... + gate_bonus                                    step in which a gate is passed
    r = ... + gate_bonus + finish_bonus                     step in which the last gate is passed
    r = -crash_penalty                      step in which the drone crashes (contact or out of bounds)
                                            or flies backwards through the target gate (if enabled,
                                            ends the episode) or crosses the target gate's plane
                                            from its approach side to its far side without passing
                                            it (invisible gate wall, if enabled, ends the episode)
    r = -stall_penalty                      no gate passed for stall_time s (hover cutoff, ends episode)
    r = 0                                   step after finishing (env disables the drone one step late)

The env auto-resets one step after a termination. That step ignores the action and returns the first
observation of a new episode; info["valid"] is False for it and it must be masked out of training.

Start states: a fraction air_start_frac of the episodes starts mid-air instead of on the ground.
Mid-air starts are of two kinds:
- route (1 - front_start_frac): a random leg of the nominal route (start -> gates in order), a
  uniform point on it plus Gaussian noise (std air_start_sigma per axis), clipped to the arena.
- front (front_start_frac): 0.3-1.0 m in front of a random target gate on its axis (actual gate pose,
  pass direction respected) plus 0.05 m noise.
The target gate is set to the end of the leg / the chosen gate. Candidates too close to gate frames
or poles are rejected. The drone starts at rest with rotors at hover speed.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import jax
import jax.numpy as jp
import numpy as np
from gymnasium import spaces
from gymnasium.vector.utils import batch_space

from crazyflow.dynamics import load_params as load_dynamics_params

from lsy_drone_racing.control.racer_core import (
    C_OFFSET,
    C_SCALE,
    GATE_HALF_OPENING,
    OBS_DIM,
    ActionMap,
    build_obs,
    mass_input,
    quat2mat,
)
from lsy_drone_racing.envs.drone_race import VecDroneRaceEnv
from lsy_drone_racing.envs.race_core import obs as race_obs
from lsy_drone_racing.envs.utils import gate_passed

GATE_DIAGONAL = 2 * GATE_HALF_OPENING * np.sqrt(2)  # Inner opening, 0.566 m
# Spawn box: inside the arena safety limits, above the floor and below the pole tops
SPAWN_LOW = np.array([-2.4, -1.4, 0.2])
SPAWN_HIGH = np.array([2.4, 1.4, 1.8])

if TYPE_CHECKING:
    from jax import Array

    from lsy_drone_racing.envs.race_core import EnvData


def target_gate(data: EnvData) -> tuple[Array, Array, Array, Array, Array]:
    """Pass index, center, orientation and pass axis (world frame) of each world's target gate."""
    n_pass = data.gate_sequence.shape[-1]
    n = data.n_gates_passed.shape[0]
    idx = jp.clip(data.n_gates_passed[:, 0], 0, n_pass - 1)
    gate_id = jp.broadcast_to(data.gate_sequence, (n, n_pass))[jp.arange(n), idx]
    direction = jp.broadcast_to(data.gate_sequence_direction, (n, n_pass))[jp.arange(n), idx]
    gate = data.gates_pos[jp.arange(n), gate_id]
    gate_quat = data.gates_quat[jp.arange(n), gate_id]
    axis = quat2mat(gate_quat)[..., 0] * direction[:, None]
    return idx, gate, gate_quat, axis


def in_front_of(p: Array, gate: Array, axis: Array) -> Array:
    """Inside a 45 deg cone around the pass axis on the approach side, or in front of the opening."""
    rel = p - gate
    along = jp.sum(rel * axis, axis=-1)  # Negative on the approach side
    lateral = jp.linalg.norm(rel - along[:, None] * axis, axis=-1)
    return (along < 0.0) & (lateral < jp.maximum(GATE_HALF_OPENING, -along))


def via_pending(data: EnvData, via_pass_dist: tuple[float, ...]) -> Array:
    """Whether the current target pass still requires its via point (not already in front of it)."""
    idx, gate, _, axis = target_gate(data)
    has_via = jp.asarray(via_pass_dist)[idx] > 0 if via_pass_dist else False
    return has_via & ~in_front_of(data.sim_data.states.pos[:, 0], gate, axis)


@partial(
    jax.jit,
    static_argnames=(
        "progress_coef",
        "height_weight",
        "approach_dist",
        "via_pass_dist",
        "via_radius",
        "via_bonus",
        "wrong_way_crash",
        "wall_crash",
        "unrevealed_cap_step",
        "rate_coef",
        "crash_penalty",
        "gate_bonus",
        "finish_bonus",
    ),
)
def racer_reward(
    prev: EnvData,
    data: EnvData,
    via_todo: Array,
    progress_coef: float,
    height_weight: float,
    approach_dist: float,
    via_pass_dist: tuple[float, ...],
    via_radius: float,
    via_bonus: float,
    wrong_way_crash: bool,
    wall_crash: bool,
    unrevealed_cap_step: float,
    rate_coef: float,
    crash_penalty: float,
    gate_bonus: float,
    finish_bonus: float,
) -> tuple[Array, dict[str, Array], Array]:
    """Reward, episode flags and the next via state for the transition prev -> data.

    via_todo marks worlds whose target gate still requires its via point (see via_pending).
    """
    n_pass = prev.gate_sequence.shape[-1]
    n_prev = prev.n_gates_passed[:, 0]
    n_now = data.n_gates_passed[:, 0]
    # Target gate before the step, also on the step in which it is passed
    idx, gate, gate_quat, axis = target_gate(prev)
    direction = jp.sign(jp.sum(axis * quat2mat(gate_quat)[..., 0], axis=-1))
    p_prev = prev.sim_data.states.pos[:, 0]
    p = data.sim_data.states.pos[:, 0]
    # Target point: the via point while pending, else the gate center from the front and the
    # approach point in front of the gate otherwise
    in_front = in_front_of(p_prev, gate, axis)
    target = jp.where(in_front[:, None], gate, gate - approach_dist * axis)
    via_dist = jp.asarray(via_pass_dist)[idx] if via_pass_dist else jp.zeros(idx.shape)
    via = gate - via_dist[:, None] * axis
    target = jp.where(via_todo[:, None], via, target)
    w = jp.array([1.0, 1.0, height_weight])
    d_prev = jp.sqrt(jp.sum(w * (target - p_prev) ** 2, axis=-1))
    progress = d_prev - jp.sqrt(jp.sum(w * (target - p) ** 2, axis=-1))
    if unrevealed_cap_step > 0:  # Speed cap: no extra progress while the target is not revealed
        n_pass_seq = prev.gate_sequence.shape[-1]
        gate_id = jp.broadcast_to(prev.gate_sequence, (idx.shape[0], n_pass_seq))[
            jp.arange(idx.shape[0]), idx
        ]
        revealed = prev.gates_visited[jp.arange(idx.shape[0]), 0, gate_id]
        progress = jp.where(revealed, progress, jp.minimum(progress, unrevealed_cap_step))
    rate_pen = rate_coef * jp.linalg.norm(data.sim_data.states.ang_vel[:, 0], axis=-1)
    via_reached = via_todo & (jp.linalg.norm(p - via, axis=-1) < via_radius)

    just_finished = (n_prev < n_pass) & (n_now >= n_pass)
    after_finish = n_prev >= n_pass
    crashed = data.disabled_drones[:, 0] & ~after_finish & ~just_finished
    passed = (n_now > n_prev) & ~after_finish
    # Crossing the target gate's opening against the pass direction
    wrong_way = gate_passed(
        p[:, None], p_prev[:, None], gate[:, None], gate_quat[:, None], (direction > 0)[:, None],
        (0.45, 0.45),
    )[:, 0]
    wrong_way = wrong_way & ~crashed & ~after_finish & wrong_way_crash
    # Invisible wall in the target gate's plane: getting from its approach side to its far side
    # without passing the gate counts as a crash. Back to front is allowed (gate 0 sits in gate 1's
    # plane, so every drone crosses it that way right after gate 0).
    behind_prev = jp.sum((p_prev - gate) * axis, axis=-1) >= 0
    behind_now = jp.sum((p - gate) * axis, axis=-1) >= 0
    wall = ~behind_prev & behind_now & ~passed & ~crashed & ~after_finish & wall_crash
    reward = progress_coef * progress - rate_pen + gate_bonus * passed + via_bonus * via_reached
    reward = reward + finish_bonus * just_finished
    reward = jp.where(crashed | wrong_way | wall, -crash_penalty, reward)
    reward = jp.where(after_finish, 0.0, reward)
    valid = ~prev.marked_for_reset
    # New target (gate passed) or new episode (auto-reset): recompute; else keep until reached
    new_target = passed | ~valid
    via_todo = jp.where(new_target, via_pending(data, via_pass_dist), via_todo & ~via_reached)
    info = {
        "valid": valid,
        "passed": passed,
        "finished": just_finished,
        "crashed": crashed,
        "wrong_way": wrong_way,
        "wall": wall,
        "via_reached": via_reached,
        "gates_passed": n_now,
        "progress": progress,
    }
    return reward, info, via_todo


@partial(jax.jit, static_argnames=("stall_steps", "penalty"))
def stall_cutoff(
    data: EnvData,
    since_pass: Array,
    reward: Array,
    terminated: Array,
    info: dict[str, Array],
    stall_steps: int,
    penalty: float,
) -> tuple[EnvData, Array, Array, Array, dict[str, Array]]:
    """End episodes without a gate pass for stall_steps steps (reward -penalty), wrong-way passes and
    gate-wall hits.

    The drone is marked disabled and for reset, so the env resets it on the next step exactly like
    after a crash (that step is then invalid). Wrong-way passes and wall hits already carry their
    reward.
    """
    since_pass = jp.where(~info["valid"] | info["passed"], 0, since_pass + 1)
    rule_crash = info["wrong_way"] | info["wall"]
    stalled = (since_pass >= stall_steps) & info["valid"] & ~terminated & (stall_steps > 0)
    stalled = stalled & ~rule_crash
    end = stalled | (rule_crash & ~terminated)
    data = data.replace(
        disabled_drones=data.disabled_drones | end[:, None],
        marked_for_reset=data.marked_for_reset | end,
    )
    reward = jp.where(stalled, -penalty, reward)
    return data, since_pass, reward, terminated | end, info | {"stalled": stalled}


class RacerEnv(VecDroneRaceEnv):
    """Vectorized race env taking network actions in [-1, 1]^3 and returning (N, 51) observations."""

    def __init__(
        self,
        *args: object,
        progress_coef: float = 1.0,
        height_weight: float = 1.0,
        approach_dist: float = 0.0,
        via_pass_dist: tuple[float, ...] = (),
        via_radius: float = 0.25,
        via_bonus: float = 2.0,
        wrong_way_crash: bool = False,
        wall_crash: bool = False,
        unrevealed_speed_cap: float = 0.0,
        rate_coef: float = 0.01,
        crash_penalty: float = 10.0,
        gate_bonus: float = 0.0,
        finish_bonus: float = 10.0,
        air_start_frac: float = 0.5,
        air_start_sigma: float = GATE_DIAGONAL / 2,
        front_start_frac: float = 0.0,
        stall_time: float = 0.0,
        stall_penalty: float = 10.0,
        c_offset: float = C_OFFSET,
        c_scale: float = C_SCALE,
        **kwargs: object,
    ):
        """Create the race env in attitude mode. Remaining arguments go to VecDroneRaceEnv."""
        # Needed by build_reset_fn, which the parent constructor calls
        self.air_start_frac = air_start_frac
        self.air_start_sigma = air_start_sigma
        self.front_start_frac = front_start_frac
        super().__init__(*args, control_mode="attitude", **kwargs)
        action_map = ActionMap(self.sim.drone, self.sim.dynamics, c_offset, c_scale)
        self._action_map = jax.jit(action_map.__call__)
        # Mass input: the true (randomized) mass of each world, scaled so that the whole
        # randomization range spans [0, 1] around the nominal mass at 0.5
        mass_rand = (kwargs.get("randomizations") or {}).get("drone_mass")
        half_range = 1.0
        if mass_rand is not None:
            lim = mass_rand["kwargs"]
            half_range = max(abs(float(lim["minval"])), abs(float(lim["maxval"]))) or 1.0
        nominal = float(load_dynamics_params(self.sim.dynamics, self.sim.drone)["mass"])
        self._obs_fn = jax.jit(
            lambda obs, mass: build_obs(obs, mass_input(mass, nominal, half_range))
        )
        # Hover cutoff: steps without a gate pass before the episode ends (0 disables it)
        stall_steps = int(round(stall_time * self.settings.freq))
        self._stall = partial(stall_cutoff, stall_steps=stall_steps, penalty=stall_penalty)
        self._since_pass = jp.zeros(self.num_envs, dtype=jp.int32)
        via_pass_dist = tuple(float(d) for d in via_pass_dist)
        self._via_pending = jax.jit(partial(via_pending, via_pass_dist=via_pass_dist))
        self._via_todo = self._via_pending(self.data)
        self._reward = partial(
            racer_reward,
            progress_coef=progress_coef,
            height_weight=height_weight,
            approach_dist=approach_dist,
            via_pass_dist=tuple(float(d) for d in via_pass_dist),
            via_radius=via_radius,
            via_bonus=via_bonus,
            wrong_way_crash=wrong_way_crash,
            wall_crash=wall_crash,
            unrevealed_cap_step=unrevealed_speed_cap / self.settings.freq,
            rate_coef=rate_coef,
            crash_penalty=crash_penalty,
            gate_bonus=gate_bonus,
            finish_bonus=finish_bonus,
        )
        self.single_action_space = spaces.Box(-1.0, 1.0, shape=(3,), dtype=np.float32)
        self.action_space = batch_space(self.single_action_space, self.num_envs)
        self.single_observation_space = spaces.Box(-np.inf, np.inf, shape=(OBS_DIM,))
        self.observation_space = batch_space(self.single_observation_space, self.num_envs)

    def build_reset_fn(self):  # noqa: ANN201
        """Wrap the race env reset with mid-air starts along the nominal route.

        The step function auto-resets through this function as well.
        """
        base_reset = super().build_reset_fn()
        start = jp.asarray(self.track.drones[0]["pos"], dtype=jp.float32)
        route = jp.concatenate([start[None], self.data.nominal_gates_pos[0, self.data.gate_sequence]])
        leg_a, leg_b, n_legs = route[:-1], route[1:], route.shape[0] - 1
        # Rotor speed whose thrust carries the nominal mass: rpm2thrust = [c0, c1, c2] in c0+c1*w+c2*w^2
        params = load_dynamics_params(self.sim.dynamics, self.sim.drone)
        c0, c1, c2 = (float(c) for c in params["rpm2thrust"])
        f = float(params["mass"]) * 9.81 / 4
        hover_rotor = (-c1 + np.sqrt(c1**2 - 4 * c2 * (c0 - f))) / (2 * c2)
        frac, sigma, front_frac = self.air_start_frac, self.air_start_sigma, self.front_start_frac
        seq, seq_dir = self.data.gate_sequence, self.data.gate_sequence_direction
        low, high = jp.asarray(SPAWN_LOW), jp.asarray(SPAWN_HIGH)
        n_candidates = 8

        def clear(pos: Array, data: EnvData) -> Array:
            """Candidates (n, K, 3) at least ~0.1 m away from all gate frames and poles."""
            rot = quat2mat(data.gates_quat)  # (n, G, 3, 3)
            local = jp.einsum("ngji,nkgj->nkgi", rot, pos[:, :, None] - data.gates_pos[:, None])
            ring = jp.maximum(jp.abs(local[..., 1]), jp.abs(local[..., 2]))
            # Frame occupies 0.2 m (opening) to 0.36 m (outer edge) around the center, plus margin
            in_frame = (jp.abs(local[..., 0]) < 0.12) & (ring > 0.12) & (ring < 0.48)
            d_pole = jp.linalg.norm(pos[:, :, None, :2] - data.obstacles_pos[:, None, :, :2], axis=-1)
            return ~in_frame.any(-1) & (d_pole > 0.12).all(-1)

        def air_start(data: EnvData, mask: Array) -> EnvData:
            n = data.steps.shape[0]
            keys = jax.random.split(data.sim_data.core.rng_key, 9)
            key, k_air, k_leg, k_u, k_noise, k_front, k_fleg, k_fd, k_fnoise = keys
            rows = jp.arange(n)
            shape = (n, n_candidates)
            # Route starts: point on a leg of the nominal route plus noise
            leg = jax.random.randint(k_leg, shape, 0, n_legs)
            u = jax.random.uniform(k_u, (*shape, 1))
            cand = leg_a[leg] + u * (leg_b[leg] - leg_a[leg])
            cand = cand + sigma * jax.random.normal(k_noise, cand.shape)
            # Front starts: on the axis in front of the target gate (approach side of the pass)
            fleg = jax.random.randint(k_fleg, shape, 0, n_legs)
            gid = seq[fleg]
            axis = quat2mat(data.gates_quat)[rows[:, None], gid][..., 0] * seq_dir[fleg][..., None]
            dist = jax.random.uniform(k_fd, (*shape, 1), minval=0.3, maxval=1.0)
            fcand = data.gates_pos[rows[:, None], gid] - dist * axis
            fcand = fcand + 0.05 * jax.random.normal(k_fnoise, fcand.shape)
            front = jax.random.uniform(k_front, (n,)) < front_frac
            cand = jp.clip(jp.where(front[:, None, None], fcand, cand), low, high)
            leg = jp.where(front[:, None], fleg, leg)
            ok = clear(cand, data)
            pick = jp.argmax(ok, axis=1)  # First clear candidate
            leg, pos = leg[rows, pick], cand[rows, pick][:, None]
            # Worlds without any clear candidate keep their ground start
            air = mask & (jax.random.uniform(k_air, (n,)) < frac) & ok[rows, pick]
            a = air[:, None, None]
            states = data.sim_data.states
            states = states.replace(
                pos=jp.where(a, pos, states.pos),
                vel=jp.where(a, 0.0, states.vel),
                ang_vel=jp.where(a, 0.0, states.ang_vel),
                rotor_vel=jp.where(a, hover_rotor, states.rotor_vel),
            )
            p = states.pos
            core = data.sim_data.core.replace(rng_key=key)
            # Sensor reveal flags as seen from the new position
            d_gates = jp.linalg.norm(p[..., None, :2] - data.gates_pos[:, None, :, :2], axis=-1)
            d_obst = jp.linalg.norm(p[..., None, :2] - data.obstacles_pos[:, None, :, :2], axis=-1)
            return data.replace(
                sim_data=data.sim_data.replace(states=states, core=core),
                n_gates_passed=jp.where(air[:, None], leg[:, None], data.n_gates_passed),
                last_drone_pos=jp.where(a, p, data.last_drone_pos),
                takeoff_pos=jp.where(a, p, data.takeoff_pos),
                gates_visited=jp.where(a, d_gates < data.sensor_range, data.gates_visited),
                obstacles_visited=jp.where(a, d_obst < data.sensor_range, data.obstacles_visited),
            )

        @jax.jit
        def reset(
            data: EnvData, seed: int | None = None, mask: Array | None = None
        ) -> tuple[EnvData, tuple[dict[str, Array], dict]]:
            data, _ = base_reset(data, seed, mask)
            mask = jp.ones(data.steps.shape, dtype=bool) if mask is None else mask
            data = air_start(data, mask)
            return data, (race_obs(data), {})

        return reset

    def _build_obs(self, obs: dict[str, Array]) -> Array:
        """Network observations, with the mass input of each world's current (randomized) mass."""
        return self._obs_fn(obs, self.data.sim_data.params.mass[:, 0, 0])

    def reset(self, seed: int | None = None, options: dict | None = None) -> tuple[Array, dict]:
        """Reset all worlds and return network observations."""
        obs, info = super().reset(seed=seed, options=options)
        self._via_todo = self._via_pending(self.data)
        self._since_pass = jp.zeros(self.num_envs, dtype=jp.int32)
        return self._build_obs(obs), info

    def step(self, action: Array) -> tuple[Array, Array, Array, Array, dict]:
        """Step all worlds with network actions (N, 3)."""
        prev = self.data
        obs, _, terminated, truncated, _ = super().step(self._action_map(action))
        reward, info, self._via_todo = self._reward(prev, self.data, self._via_todo)
        self.data, self._since_pass, reward, terminated, info = self._stall(
            self.data, self._since_pass, reward, terminated, info
        )
        return self._build_obs(obs), reward, terminated, truncated, info

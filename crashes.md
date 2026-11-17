# MPCC++ crashes at ~10 s laps

Controller: `lsy_drone_racing/control/mpccpp.py` (branch `mpcc++`, commit `b0df425` plus uncommitted changes: `obstacle_clearance` 0.4 → 0.25, `tunnel_margin` 0.0374 → 0.01, the shifted tunnel, the reveal recovery, the smaller area assumed for undetected poles, the inside route after gate 2 (`route_gate23=4`, now the default) and no recovery within 0.2 m of a gate, described below), `config/level2.toml`, overrides `reference_speed=1.6`, `max_speed=2.2`, `unobserved_speed=1.6`. With the current version: new seeds 3170–3189 20/20 (mean lap 8.96 s), and seed 3155 finishes (8.66 s). Earlier sets with the inside route but before the near-gate fix: 3000–3019 20/20 (9.28 s), 3130–3149 20/20 (9.16 s), 3150–3169 19/20 (9.74 s). Seeds 3020–3039 have not been run with the inside route.

The ~20 s preset (`reference_speed=0.7`, `max_speed=1.0`, `unobserved_speed=0.7`) is saved as `config/level2_mpccpp_20s.toml`.

Run the commands from the repository root. Each one opens the viewer and plays the race at 0.5x real time (`--speed` changes it, `--headless` runs without the viewer). It prints every track rebuild (when a gate or pole is revealed) and the outcome. Results are deterministic per seed. Viewer keys: space = pause/resume, right arrow = one step.

Overlays: green = centerline, red lines = tunnel walls over the MPC horizon (lateral free extent of the drone center, bright red low to whitish red high; `--full-walls` draws them along the whole track), orange = MPC prediction, white = flown trail, balls on poles = pole positions by pole ID 0–3 (deep blue, light blue, light yellow, deep yellow), balls at gate centers = assumed gate positions (white nominal, red detected).

Headless version that also saves race data: `LD_LIBRARY_PATH=acados/lib .pixi/envs/default/bin/python .mpcc_dev/slow_runs.py '{"reference_speed":1.6,"max_speed":2.2,"unobserved_speed":1.6}' <seed>:<seed+1> .mpcc_dev/runs/crash_<seed>.json 1`

No open crashes. Seed 3155, the last one, is fixed (see below); it now finishes in 8.66 s.

Crash time is simulated time from the start of the episode, alive is from takeoff (first tick 2 cm above the start height) until the crash. Gate and pole numbers are 0-based IDs. No solver failures. Recoveries = recovery routes built before revealed gates (see below).

## Fixed: recovery triggered at the gate sends the drone back

In seed 3155 a reveal recovery triggered at 4.96 s with the drone only ~0.05 m in front of gate 2's plane (the threshold `hold_tol + hold_slope × distance` shrinks to ~0.05 m there). The recovery's sideways point is at least 0.2 m in front of the gate, i.e. behind the drone, so the rebuilt route led back to it and progress froze. The drone passed the gate on momentum (5.02 s), turned back as the route demanded, and hit gate 2's frame at 5.42 s (56° tilt), which looked like a problem with the steep turn after gate 2. `_update_hold` now skips the recovery when the drone is less than 0.2 m from the gate plane: it is committed to the gate there. Seed 3155 now finishes in 8.66 s with no recovery.

## Fixed: outside route around pole 3 (inside route after gate 2)

The old route (`route_gate23=0`) swung south of pole 3 and entered gate 3 at 35° from the south-west. Seeds 3012 and 3021 crashed into gate 3's frame after reveal recoveries (see below). The new default (`route_gate23=4`) turns steeply after gate 2: south past the side of its frame while climbing, then north-east past pole 3 on the inside (north, 0.29 m from its nominal axis) and into gate 3 at 35° from the north-west. On seeds 3000–3019 it finished 20/20 (9.28 s) against 19/20 (9.08 s).

## Open: recoveries at gate 3 too sharp at 1.6 m/s (old route)

With the old route, both crashes (3012, 3021) hit gate 3's frame after one or two reveal recoveries (32–40° tilt, 2.1–2.3 m/s, against 1.6 m/s reference). The recovery route starts at the drone's position and heads sideways onto the gate's center line, ignoring its velocity. At 1.6 m/s with the planned tilt limited to 0.73 rad the drone cannot turn tighter than ~0.3 m radius, so the MPC prediction swings wide of the new path. Measured on seed 3008 (earlier version): solver status 0 every tick, and 10 instead of 2 RTI iterations gave the same prediction, so the solver is not lagging; the new path is not flyable from the current state. Candidate fixes: build the recovery route tangent to the current velocity, raise the contour weight during a recovery, or trigger the recovery at the reveal itself.

## Fixed: reveal at an angled approach (reveal recovery)

An angled approach turns a gate shift along its normal into a sideways error. In seed 3012 at 0.7 m/s, gate 3 moved 0.145 m towards the drone and turned 11°, leaving it 0.36 m from the gate plane and 0.59 m to the side; it swerved into the frame. A more perpendicular approach (route variants `route_gate23=1–3`, 30–20°) and lower slack penalties did not help.

`MPCCPlusPlus._update_hold` now checks, on the final approach to a revealed gate, whether the drone is further from the centerline than `hold_tol + hold_slope × distance to the gate plane`. If so, it rebuilds the leg from the drone sideways onto the gate's center line, then straight through, and ramps the progress speed down to `hold_speed` until the gate is passed. Bugs found on the way:

- The window used the distance to the extended gate plane, so drones far from or beside a gate triggered recoveries and detours (seed 3103: 3.5 m loop; seed 3019 at 1.4 m/s). It now requires the drone within `hold_window` of the gate both along the path and directly.
- The progress speed cap stepped down to `hold_speed` in one stage, infeasible above ~1 m/s, so the solver failed after every recovery at 1.6 m/s. It now ramps down at 0.8 × `max_progress_acc`.
- Progress is re-projected after every track rebuild instead of keeping the larger old value.

## Fixed: free space blocked behind gates by undetected poles

An undetected pole was assumed to be anywhere within a 0.212 m radius of its nominal position (the diagonal of its ±0.15 m randomization range), so the drone center had to stay 0.337 m from it. Pole 2 stands about 0.5 m behind gate 2 on its exit line, so the free space behind the gate was blocked from 0.1 to 0.6 m (seed 3008 at 1.6 m/s). The uncertainty is now the randomization box instead of the circle around it, and only half of it (±0.075 m) is assumed: `_obstacle_uncertainty` in `MPCCPlusPlus.__init__`, used by `_pole_distance`. The drone center now keeps 0.2 m from the nominal axis along x and y until the pole is detected at 0.7 m. A pole further than 0.075 m off its nominal position can therefore be closer than the tunnel assumes until it is detected.

## Fixed: tunnel collapsing around a blocked centerline

`Track._tunnel` cast its rays from the centerline. Where the centerline itself was blocked, every ray started inside an obstacle and the tunnel collapsed to `tunnel_min` (0.02 m) on all sides, pinning the drone to the blocked line. This happened when a pole sits near a gate's fixed entry or exit point (where `Track._push_from_obstacles` is faded out), or when a pole has not been observed yet and is inflated by its position uncertainty (0.212 m), more than the 0.25 m `obstacle_clearance` the centerline keeps. A blocked cross section is now centered on the nearest free point along the four tunnel directions, with signed extents, so the tunnel no longer has to contain the centerline.

## Fixed: pole push shoves the centerline into a gate frame

`Track._push_from_obstacles` pushes the centerline to `obstacle_clearance` from every pole but ignores gate frames. Where the path passed between a pole and a gate, the push moved it into the frame (seeds 3005, 3024, 3028, 3034). Lowering `obstacle_clearance` from 0.4 to 0.25 fixed all four; the push still ignores gate frames.

## Results

~20 s laps (0.7 m/s):

| Change | Seeds | Finished | Mean lap (s) |
| ------ | ----- | -------: | -----------: |
| `obstacle_clearance` 0.40, `tunnel_margin` 0.0374 (commit `b0df425`) | 3000–3039 | 28/40 | 19.6 |
| `obstacle_clearance` 0.25 | 3000–3039 | 33/40 | 18.9 |
| + `tunnel_margin` 0.01 | 3000–3039 | 33/40 | 18.85 |
| + shifted tunnel | 3000–3079 | 77/80 | 18.73 |
| + reveal recovery | 3000–3129 | 130/130 | 19.06 |

~10 s laps (1.6 m/s), seeds 3000–3019:

| Change | Finished | Mean lap (s) |
| ------ | -------: | -----------: |
| reveal recovery as at 0.7 m/s | 14/20 | 9.93 |
| + recovery only on the final approach | 17/20 | 9.42 |
| + ramped speed cap | 18/20 | 9.42 |
| + undetected pole as box instead of circle | 18/20 | 9.38 |
| + half the box | 19/20 | 9.08 |
| + inside route after gate 2 | 20/20 | 9.28 |

Other seed sets:

| Version | Seeds | Finished | Mean lap (s) |
| ------- | ----- | -------: | -----------: |
| half the box, old route | 3020–3039 | 19/20 | 9.28 |
| inside route | 3130–3149 | 20/20 | 9.16 |
| inside route | 3150–3169 | 19/20 | 9.74 |
| **+ no recovery within 0.2 m of a gate (current)** | **3170–3189** | **20/20** | **8.96** |
| current, every earlier 1.6 m/s crash | 3004, 3005, 3006, 3008, 3010, 3011, 3012, 3013, 3019, 3021, 3155 | 11/11 | 8.84 |

The 130/130 at 0.7 m/s was measured before the two recovery fixes; only seed 3103 has been rerun since (19.02 s, no detour).

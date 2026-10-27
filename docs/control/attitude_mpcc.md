# control.attitude_mpcc

`AttitudeMPCC` uses the same identified drone dynamics and `[roll, pitch, yaw, thrust]`
commands as `AttitudeMPC`. It follows a geometric spline with an optimized virtual
progress state, rather than a reference indexed by elapsed time.

Run the supplied nominal-track configuration:

```bash
pixi run python scripts/sim.py --config attitude_mpcc.toml
```

For Level 2, including mass/inertia, starting-pose, gate, and obstacle randomization:

```bash
pixi run python scripts/sim.py --config attitude_mpcc_level2.toml
```

Use `--render=False` to measure controller performance without GUI/rendering overhead.

To use another track configuration, set these entries:

```toml
[controller]
file = "attitude_mpcc.py"

[env]
control_mode = "attitude"
```

Optional settings (shown with their defaults):

```toml
[controller.mpcc]
horizon_steps = 40
reference_speed = 1.3  # Preferred progress speed, approximately m/s
max_speed = 1.8        # Upper bound on virtual progress speed
contour_weight = 400.0
lag_weight = 400.0
progress_weight = 12.0
max_angle = 0.6        # Attitude state and command bound, radians
attitude_rate_weight = 0.1
attitude_slew_weight = 0.02
thrust_slew_weight = 0.1
terminal_weight = 0.2
adaptation_rate = 2.0  # Thrust-gain estimator bandwidth, 1/s; 0 disables estimation
obstacle_clearance = 0.26  # Desired path-to-pole distance, meters (not a hard constraint)
# waypoints = [[...], [...]]  # Path after the automatically prepended start position
```

The objective penalizes perpendicular contour error and tangential lag error,
and rewards progress with quadratic speed regularization. It also penalizes
changes between consecutive attitude/thrust commands throughout the horizon,
including the change from the last issued command. This reduces alternating
commands when the fitted attitude dynamics differ from the real inner loop.
The previous command is an additional discrete state; RK4 integrates the drone
dynamics and SQP-RTI updates the solution twice per control step. Bulk acados
state/input transfers reduce Python overhead. The smaller terminal weight and
angular-rate weight reduce unnecessary braking at the end of the short horizon.

Increasing `reference_speed` or `progress_weight` favors faster progress. Increase
`attitude_slew_weight` to reduce abrupt roll/pitch/yaw commands, or
`thrust_slew_weight` to smooth vertical control. For example, try `0.04` and `0.2`
respectively if commands still chatter; stronger smoothing also slows reactions
to turns and newly observed objects. `max_speed` bounds virtual progress rather
than physical drone velocity. The path starts approximately parameterized by
arc length; local corrections can change that parameterization's metric scale.

The online estimator compares acceleration from successive velocity observations
with acceleration predicted from the previously issued thrust and observed
orientation. A bounded, filtered gain accounts for effective inverse mass and
thrust calibration. It adjusts the prediction and hover reference, excludes
ground contact and large thrust transients, and resets between episodes. It does
not read hidden simulator mass/inertia or identify the full inertia tensor.
Slew penalties and receding-horizon feedback reduce sensitivity to inertia-driven
changes in attitude response; they do not provide formal robustness guarantees.

The default route is based on the example MPC's nominal-course waypoints. Its
ordered crossings are corrected locally to observed gate centers and orientations,
with entry/exit points aligned to the gate normal. Local pole repulsion preserves
these anchors, and a departure clearance adjustment keeps the immediate climb
from intersecting a shifted gate frame. Only observed object poses are used;
objects outside sensor range retain their nominal poses. Path corrections retain
the same progress coordinates instead of resetting or jumping to another branch.

These are local adjustments to a fixed route, not a general planner. Different
gate order or track layouts may require custom `waypoints`; custom paths bypass
automatic gate/pole corrections. There are no hard obstacle/gate/tunnel constraints
or MPCC++ terminal-set guarantees. Test multiple Level 2 seeds before increasing
speed. A failed or nonfinite solve freezes progress, clears the warm start, and
returns upright hover thrust using the estimated thrust gain. Hover is a fallback
command, not an emergency braking policy.

Validation on the first-principles simulator at 50 Hz used seeds `1337`, `42`,
and `7`. With randomized mass/inertia and starting pose but nominal objects, all
three races completed in 9.74–9.82 seconds. With all Level 2 randomizations, two
of three completed in 9.70–9.84 seconds; seed `1337` still collided with gate 3's
frame after crossing it. These short checks do not establish a general success
rate. The local route correction remains the limitation in that case.

On those full Level 2 runs, roll/pitch command-change RMS fell from roughly
0.33 rad per control step with the original controller to 0.02–0.03 rad, and
median controller computation fell from roughly 9.8 ms to roughly 5 ms on the
test machine. These metrics include incomplete flights and are diagnostic
comparisons, not a matched successful-lap benchmark.

Green shows the reference path, blue the predicted flight, and red the virtual
progress point. Generated solver files live under `c_generated_code/attitude_mpcc`.
Construct a new controller for a new starting position or track; `reset()` resets
progress and solver state on the existing path.

::: lsy_drone_racing.control.attitude_mpcc

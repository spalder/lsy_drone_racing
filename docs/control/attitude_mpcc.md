# control.attitude_mpcc

`AttitudeMPCC` is the restored original end-of-stage-2 implementation. It uses
the identified attitude model from `AttitudeMPC` and issues the first optimized
`[roll, pitch, yaw, thrust]` input synchronously at each control tick. The
reference is a geometric spline with an optimized progress state and speed input.

The controller source matches archived SHA-256
`2033f45e88df6931b734155281b1cb3c80e71a10bb8358be754ff39ed8324b3c`.
The original stage-2 boundary was completed on October 27, 2026. The standalone
geometry and corridor modules belong to that implementation.

Run the randomized Level 2 configuration with an explicit reset seed:

```bash
SCIPY_ARRAY_API=1 pixi run python scripts/sim.py --config level2.toml --seed=7
```

`--render=False` disables graphical rendering. `attitude_mpcc.toml` selects the
nominal course; `attitude_mpcc_level2.toml` supplies the Level 2 randomizations.
The evaluated `level2.toml` uses first-principles physics at 500 Hz and a 50 Hz
environment/control loop, with attitude commands and a 0.7 m sensor range.

The actual evaluate entry point accepts explicit ordered seeds and an external
output directory. Without these arguments it retains its original 20-run default.
Run this command in Bash to reproduce the historical comparison set:

```bash
SCIPY_ARRAY_API=1 pixi run evaluate --seeds {1..50} 1337 --output-dir /tmp/stage2-evaluation
```

Evaluation writes `evaluation.csv` to the requested directory. Generated acados
solver files are relative to the process working directory, under
`c_generated_code/attitude_mpcc`. A new controller instance is constructed for
each episode. `--seed` on the simulator applies that explicit reset seed;
the evaluator passes its ordered list through `simulate(seeds=...)`.

## Controller behavior

The objective penalizes contour and lag error, rewards progress, and penalizes
attitude/thrust command changes. The previous physical command is a discrete
state. RK4 integrates the identified model, and two synchronous SQP-RTI passes
update the prediction each tick. A bounded online thrust-gain estimate uses
public velocity and orientation observations; it resets between episodes.

The default spline follows the nominal course. Local gate corrections align
approach, crossing and departure anchors with observed gate geometry. Pole
repulsion preserves those anchors. Corrections retain the existing progress
coordinates. Custom `waypoints` bypass automatic gate/pole path correction.
The correction procedure does not enforce a final joint clearance constraint.

`track_geometry` retains nominal poses, configured bounded uncertainties and
revealed poses separately. Public visited flags drive detection, including a
revelation whose position equals the nominal position. Revealed geometry persists
until `episode_reset()`. `reset()` clears optimizer progress and warm starts on
the existing path; a new starting position or track requires a new instance.

`plan_corridor(obs, tracking_margin, max_tilt=0.35)` is the original explicit
offline review API. It describes geometric regions and may report a certified
route, an observation request or search failure. It is not called by the racing
feedback loop and does not alter command ownership or constrain the optimizer.
Its results do not establish dynamic feasibility; bounded search failure does
not establish physical blockage.

A failed or nonfinite numerical solve freezes progress, clears the warm start
and returns the original upright-hover command. This behavior is part of the
archived implementation. The optimizer has no hard gate, pole, corridor or
terminal stopping constraints.

Optional settings and their defaults:

```toml
[controller.mpcc]
horizon_steps = 40
reference_speed = 1.3
max_speed = 1.8
contour_weight = 400.0
lag_weight = 400.0
progress_weight = 12.0
max_angle = 0.6
attitude_rate_weight = 0.1
attitude_slew_weight = 0.02
thrust_slew_weight = 0.1
terminal_weight = 0.2
adaptation_rate = 2.0
obstacle_clearance = 0.26
```

Progress speed is not a hard physical-speed bound. Local spline deformation can
change its metric. Desired pole clearance is not a hard collision constraint.
The MuJoCo 3.10 compatibility shim retains the upstream box-contact algorithm
while making the no-contact sentinel representable in float32.

## Verified baseline results

The matched historical loop reproduces 28 completions among seeds 1–50 plus
1337, with the same per-seed outcomes, step counts and command hashes as the
archived baseline. Successful laps have a 9.77 s median. Seeds 7 and 42 finish
in 9.86 s and 9.72 s; seed 1337 collides with gate ID 2 after three passages
at 6.98 s. There are no solver failures or timeouts in this comparison.

`sim.py` honors the completion callback and stops successful episodes one tick
earlier than the historical comparison harness, which waited for environment
termination. Its original `i / freq` log/CSV convention also reports the start
time of the final tick. Thus successful evaluate CSV times are 0.04 s below
the historical harness's completed-step times. This is a reporting/termination
convention difference, not a controller change.

Green shows the reference spline, blue the optimizer prediction, and red the
virtual progress point. These measurements describe the restored baseline on
the declared finite seed set. Holdout seeds 51–100 were not evaluated.

::: lsy_drone_racing.control.attitude_mpcc

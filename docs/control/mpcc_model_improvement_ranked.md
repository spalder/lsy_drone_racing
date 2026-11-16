# Ranked controller-model improvements

2026-11-04. Deeper source and archived-results investigation following
`mpcc_prediction_estimation_recommendation.md`. This ranking supersedes that
report's preliminary ordering of model improvements. No racing experiments ran.

**Recommendation: add a small drag model before implementing a general state
Kalman filter or online physical-inertia estimator.** Then calibrate the existing
attitude model if prediction residuals justify it. A scalar thrust-gain Kalman
filter is the lowest-complexity third choice, with a lower expected ceiling.

Numerical repair remains a prerequisite for promoting any candidate. It is not
counted as one of these three new model/estimation choices. Keep reference 3.0,
cap 3.2, max_angle .875, three RTI passes, pressure 12 for the numerical comparison.

| Rank | Choice | Implementation scope beyond experiment plumbing | Potential gain and confidence |
| --- | --- | --- | --- |
| 1 | Drag-aware prediction and consistent thrust adaptation | Existing solver dynamics plus gain-update method; one tuning scalar, no new state | Strongest source-level evidence of a missing force; racing benefit unmeasured |
| 2 | Calibrate roll/pitch response, initially with fixed multipliers | Existing model builder/solver; one or two calibration scalars, no estimator initially | Plausible effect on turn anticipation; actual response mismatch not yet measured |
| 3 | Scalar Kalman thrust-gain adaptation | Gain helper/core and reset; existing solver parameter unchanged | Cheap improvement to early adaptation; current EMA already handles much of this problem |

## Findings that change the ranking

The campaign controller is the research `MPCCBroadCore`, not the root config's
`attitude_mpcc_v1.py`. Its solver loads `Dynamics.so_rpy` and uses that model's
translational equation: gravity plus thrust along body z, scaled by the estimated
gain. There is no aerodynamic drag term.

The racing environment uses `first_principles`. Inspection of the installed
numeric dynamics confirms a body-frame linear drag force, transformed to the
world frame before integration. This is a real structural difference, not just
a guess based on generic drone behavior.

For the installed nominal cf21B_500 parameters:

- Mass is .0434 kg, randomized by +/-.005 kg: approximately +/-11.5%.
- Roll inertia is 25e-6 kg m² and pitch inertia 28e-6 kg m². Their configured
  +/-1e-6 randomization is approximately +/-4.0% and +/-3.6%.
- Drag force coefficients are .02164 horizontally and .02477 vertically in
  N/(m/s), corresponding to nominal damping of .499 and .571 per second.
- At 3 m/s, nominal near-level horizontal drag acceleration is 1.50 m/s².
- Nominal roll/pitch prediction coefficients imply a steady command gain of
  .894, natural frequency 12.50 rad/s, and damping ratio .652.

These values were calculated directly from installed TOML files and the model
equations, without reading any episode's hidden randomized parameters. They are
scales for prioritization, not measured residuals or performance improvements.

The latest 3.0/.875/RTI3 100-seed case failed 54 races: 38 while pursuing crossing
4 and 12 while pursuing crossing 1. Its final ten ticks in failed races had
commanded attitude near a bound 33.7% of the time and commanded thrust near a
bound 44.8% of the time. These are aggregate commanded-bound diagnostics, not
proof of inadequate physical authority or of any particular model error.

The archived observer retains position, speed magnitude, command and tracking
metrics, but not full actual attitude, velocity vector, angular rates, thrust
gain history, and one-step predictions. Consequently an honest retrospective
ranking cannot claim measured model-fit improvements from these archives.

## 1. Drag-aware prediction: best first implementation

Use the existing dynamics structure and add:

    acceleration = gravity + gain * nominal_thrust_acceleration + a_drag
    a_drag = -strength * R * diag(.499, .499, .571) * R.T * velocity

R maps body to world. `strength=0` reproduces the current model;
`strength=1` is a nominal physical starting hypothesis. Embed the constants in
the controller's model/settings; never query the randomized simulator parameters.
There are no additional states, optimization variables, or runtime dependencies.
The nominal coefficients need not be treated as exact for the randomized drone.

**Also correct the gain estimator.** Its acceleration observation must subtract
the modeled drag acceleration before projection onto expected thrust. Otherwise
the gain estimator can absorb some drag error while the predictor also explicitly
adds drag, producing inconsistent compensation. Use average endpoint velocity
and attitude over the observation interval where practical, preserving existing
sample acceptance and gain bounds. Keep drag separate from the empirical thrust
gain in the first experiment; gain is not guaranteed to equal pure inverse mass.

Why this can help: the present model predicts too little passive deceleration,
and may predict too much forward travel for an intended thrust/attitude sequence.
That can alter turn timing, braking, and gate alignment. Modeling drag does not
automatically reduce lap time: it can also reveal that more thrust is needed or
reduce optimistic progress. Closed-loop measurement is essential.

A simple scale calculation illustrates why one-step prediction alone can miss
this issue. For initial speed 3 m/s with drag-only deceleration at beta=.499/s,
the difference from constant-speed motion is .30 mm after .02 s, 2.90 cm after
.2 s, and 42.1 cm after .8 s. This is an open-loop illustration with no thrust
or feedback, not a prediction of racing error. Evaluate model accuracy over
100-200 ms as well as one step.

First screen: strengths 0, .5, 1.0, 1.5 on 30+ matched seeds, with all costs,
geometry, authority and speed fixed at the numerically repaired parent. Require
zero-strength action/model equivalence before interpreting comparisons. Record
gain trajectories to detect interaction with adaptation. Choose a single frozen
candidate for fresh 100+ confirmation only if racing gains justify it.

Implementation complexity is low to moderate: typically the solver's existing
acceleration expression, a small shared drag-expression/helper, and the core's
gain update. Verification must cover force sign/frame, zero-strength equivalence,
and gain-update consistency. Rebuild the generated solver once per configuration,
as already required by the harness. There is no extra optimization dimension;
runtime impact is expected to be small but must be measured.

## 2. Attitude-model calibration: fixed first, online only if needed

The current attitude model already has lag and damping. Its roll/pitch dynamics
are of the form:

    angle_ddot = c_angle*angle + c_rate*angle_rate + c_command*command

First measure how well these coefficients predict actual response, particularly
over 100-200 ms before turns. Its nominal steady command gain .894 means a
constant .875 rad command tends toward .782 rad in the isolated model. This is
a possible calibration issue, not evidence that the actual racing drone tends
toward .875 rad: its low-level controller, coupling, and saturation also matter.

Use a common bounded roll/pitch response-speed multiplier s initially:

    c_angle_new = s² * c_angle
    c_rate_new = s * c_rate
    c_command_new = s² * c_command

This changes response speed while preserving model steady gain and damping
ratio, and maintains continuous-time stability for positive s when the original
model is stable. Test .9, 1.0, 1.1 as development hypotheses if lag residuals
justify them. If the error is steady gain rather than lag, adjust c_command alone
in a separate comparison. Do not vary both simultaneously in the first screen.
Keep yaw unchanged initially.

Why fixed calibration precedes online identification: a systematic mismatch is
cheaper to correct once than to relearn during every five-second race. The modest
inertia randomization does not by itself justify a full parameter estimator.
If fixed calibration leaves clear episode-specific differences, then estimate
one bounded speed multiplier per roll/pitch axis from observed command response.
That extension requires excitation checks, update bounds, reset policy, and
confidence handling; it is materially more complex than the fixed experiment.

The gain ceiling could be useful because anticipation depends on how fast actual
attitude changes, especially near commanded bounds. However, where the requested
turn physically exceeds available thrust/torque, a better model cannot create
authority. Do not attribute these failures solely to inertia variation.

## 3. Scalar thrust-gain Kalman filter: smallest estimator change

Keep the existing gain observation and solver parameter. Replace only its EMA
update with a scalar covariance-based update. This does not require an EKF or a
physical mass/inertia state vector. Use the drag-corrected observation when
combined with choice 1, but test that interaction only after the individual cases.

There is a concrete potential startup limitation: adaptation_rate=2 gives an
update weight .0392 per accepted sample. It takes about 58 accepted updates to
remove 90% of an initial error: 1.15 s if every tick is accepted, approximately
2.30 s if half are accepted. That is significant within a roughly five-second
race, but initial error and accepted-sample rates have not been measured here.

Start with gain=1, P0=.0025, R=.01 and Q_step=.000016 at dt=.02 s, with bounded
covariance and the original acceptance/gain bounds. These are exploratory values,
not calibrated noise statistics. They give about .20 initial update weight and
approximately .039 steady weight for uninterrupted accepted samples: faster
startup, similar eventual smoothing. Predict covariance each tick and update
only on accepted observations. Reset per episode. Monitor early thrust transients
because a larger initial weight can learn a biased sample faster too.

Include adaptation_rate=4 as a cheaper EMA comparator. If the KF cannot outperform
that on matched racing outcomes, keep the EMA. Gain uncertainty is not a license
to relax numerical-health checks or assume independent Gaussian residuals.

This is the easiest estimator implementation, but ranks third because adaptation
already exists and cannot correct the missing speed-dependent force or erroneous
attitude response. Expecting large speed gains from the filter change alone would
be speculative.

## What I would defer

- Full state EKF / replacing the current state by a next-state forecast: duplicates
  existing MPC prediction without addressing an evidenced simulator delay.
- Full inertia-tensor estimation: unknown actual motor torque and short,
  feedback-controlled trajectories make physical identification difficult; the
  existing MPC consumes attitude-response coefficients, not that inertia tensor.
- General 3D bias observer: can chase random disturbances or absorb drag that
  changes direction in a turn. Try a structured known-form drag term first.
- Predicted gate-clearance constraints: worthwhile later, but require passage
  association, frame/envelope handling and added cost/constraint tuning. That is
  more implementation and solver interaction than the top choices.

## Minimal evidence needed before promoting any of the three

On a predetermined diagnostic subset, log pre-action state, the actual applied
command, gain/update acceptance, and predicted next state. Align these with the
next observation. For longer prediction scoring use recorded future applied
commands, or explicitly label results as plan-tracking rather than pure model
error. Also score 100-200 ms rollouts, not just .02 s.

Report velocity/attitude residuals by phase, gain convergence, numeric statuses,
crossing-specific outcomes, paired time on shared finishes, rescues/regressions,
completion and advisory latency. The existing observed >=40% completion and
unchanged numerical-health rules remain. None of these model changes has yet
demonstrated a racing gain, and the analytic calculations do not imply a lap-time
percentage. Use a numerically healthy fixed parent and do not retune costs during
the first model comparison.

All controller behavior can remain inside the controller directory. Diagnostic,
settings and audit integration are the only necessary harness changes. Preserve
the historical research checkout and add a new version for implementation.

Sources: installed Crazyflow `first_principles/dynamics.py`,
`first_principles/params.toml`, `so_rpy/dynamics.py`, `so_rpy/params.toml`; campaign
`mpcc_broad_core.py` and `mpcc_broad_solver.py`; batch-004 diagnostics summary and
the actual shared recorder. Analytic figures were independently calculated from
the installed TOML values without importing or running a racing environment.

- [Batch-004 diagnostics](../../logs/mpcc-campaign/departure-speed-20261104-v1/batch-004/analysis-v1/diagnostics-summary.json)
- [Campaign interpretation](../../logs/mpcc-campaign/departure-speed-20261104-v1/results-analysis-20261104-v1/analysis-v2-policy40.md)
- [Crazyflow identification](https://learnsyslab.github.io/crazyflow/user-guide/dynamics/system-identification/)
- [Crazyflow first-principles model](https://learnsyslab.github.io/crazyflow/api-reference/dynamics/first_principles/)
- [Recursive estimator algorithms](https://www.mathworks.com/help/ident/ug/algorithms-for-online-estimation.html)

# Prediction and online estimation for the fast MPCC

Follow-up: [deeper ranked recommendation](mpcc_model_improvement_ranked.md)
identifies omitted aerodynamic drag and supersedes this report's preliminary
ranking of model improvements.

Investigation: 2026-11-04. Source inspection and existing campaign evidence only;
no racing experiments, controller changes, or campaign resumption.

The useful opportunity is to improve predictions of the drone's response, rather
than estimate its already exposed current state. Keep numerical repair first.
After that, investigate prediction residuals, effective thrust gain, and attitude
response. A Kalman filter is one possible estimator, not an extra source of future
information by itself.

## What the current implementation already does

The latest campaign uses `MPCCBroadCore` in
`.local/mpcc-study/broad-20261103T152500Z-r2/checkout/lsy_drone_racing/control/`.
The root configuration still selects `attitude_mpcc_v1.py`; changing only that
file would not change the campaign controller. Preserve historical checkouts and
introduce any implementation in a new controller/research version.

The campaign core already predicts the state over a horizon, optimizes future
commands, applies the first command, and shifts the prediction for its next warm
start. At N=40 and dt=.02 s the horizon is .8 s. Its initial state uses observed
position, attitude, velocity, and angular rates. It also estimates a scalar thrust
effectiveness gain, used in predicted acceleration and the hover reference.

The official sandbox's `race_core.obs()` exposes simulator state directly. Its
step applies the newly computed action before advancing ten physics steps at
500 Hz. Computation is synchronous: extra wall-clock solve time does not advance
simulated time. There is no evidenced additional one-control-tick transport delay
to compensate in this setup. Attitude response and actuator dynamics can still
lag commands; those belong in the prediction model.

The real environment instead obtains states from ROS estimators. Its timing and
staleness must be measured separately. The onboard Crazyflie setup already selects
its Kalman estimator. Changing onboard settings is distinct from improving the
external MPCC predictor and would exceed the desired controller-local scope.

## Does a separate one-step predictor help?

With exact current state and the same dynamics model, it largely duplicates the
first step of the MPC rollout. Replacing x[k] by predicted x[k+1] while applying
the new action immediately would misalign the optimization with physical time.
Likewise, smoothing current state can introduce tracking error without removing
measurement noise in this simulator. One effective tick of lag corresponds to
6 cm of travel at 3 m/s; this illustrates sensitivity, not a measured filter lag.

Prediction becomes useful when it adds something missing:

1. Correct a measured sensor/transport delay by propagating a timestamped state
   to actuation time under the commands actually pending during that interval.
   Align path references, progress, and warm starts with the same time. This is
   a deployment option after delay measurement, not the next local experiment.
2. Improve the dynamics model using prediction errors. Accurate state measurement
   makes this easier: compare the prediction made at k with the observation at
   k+1, under the command applied over that interval.
3. Predict an impending gate miss, using the existing trajectory in the actual
   gate frame, early enough to change the optimized control problem.

## Estimating randomized mass and inertia

### Effective mass / thrust gain: small, plausible improvement

The existing gain estimator uses nominal thrust-induced acceleration b and
measured acceleration a=(v[k]-v[k-1])/dt-gravity, forming
z=(b dot a)/(b dot b), then exponentially smoothing z. It excludes near-ground
samples and large thrust changes, rejects raw gains outside (.6,1.5), and clips
the estimate to [.7,1.4]. Retain these safeguards in the first comparison.

At adaptation_rate=2 and dt=.02, its update gain is .03921 per accepted sample.
Its nominal time constant is .5 s with every sample accepted; rejected samples
extend adaptation in elapsed time. Establish whether slow convergence or rejected
samples actually precede difficult crossings before investing in a replacement.

If thrust calibration were exact and this scalar captured only inverse mass,
effective mass would be nominal_mass/gain. In this implementation it also absorbs
thrust calibration, actuator response, omitted forces, and disturbances. Treat
it as effective thrust-to-acceleration gain, not a separately identified physical
mass. Its lack of sensitivity to the true inertia tensor is not fixed by changing
the smoothing algorithm.

A scalar random-walk Kalman filter is the smallest useful filter experiment:

    P_prior = P + Q_rate * dt
    K = P_prior / (P_prior + R)
    gain = gain + K * (z - gain)
    P = (1 - K) * P_prior

Use the existing accepted z samples. Predict covariance each tick, correct only
on accepted samples; bound covariance so long rejection periods cannot cause an
uncontrolled subsequent update. Reset gain and covariance each episode. Retain
the original bounds, finite checks, fallback, and public-observation interface.

An illustrative starting point is gain0=1, P0=.01, R=.01,
Q_rate=.0008 gain-squared/second (Q_step approximately .000016 at 50 Hz).
R=.01 means a .10 standard deviation in the dimensionless raw gain observation,
not position or acceleration noise. These are uncalibrated hypotheses. This Q/R
approximately matches the present EMA's asymptotic gain while allowing stronger
startup updates: K is approximately .50 initially, .096 at update 10, and .041
at update 50 with uninterrupted accepted samples. Initial trust may be excessive
after takeoff, so compare P0=.0025 if the first samples are transient-biased.

Estimate R from accepted prediction residuals on development data, excluding
contact and separating transient from steady operation. Consecutive velocity
differences and model errors are correlated: textbook covariance does not imply
calibrated confidence here. Constant Q/R eventually produces an approximately
constant-gain smoother. Include a faster EMA comparison to establish whether
any benefit comes from covariance handling or simply faster adaptation.

### Inertia: estimate its observable effects first

Physical rotational dynamics satisfy I*omega_dot + omega cross (I*omega)=torque.
The public controller commands attitude and collective thrust; it does not observe
actual motor torques. Exact angular velocity alone does not establish separate
identifiability of inertia and torque/inner-loop dynamics from a short race.
Do not claim a reliable full inertia-tensor estimate from this interface.

The MPC actually uses an identified second-order attitude model:

    angle_ddot = c_angle*angle + c_rate*angle_dot + c_cmd*command_angle

Its coefficients describe the closed-loop command-to-attitude response. They are
the directly useful targets for capturing effects of inertia randomization.
Start with one bounded response-speed multiplier per roll/pitch axis, scaling
the existing model's coefficients consistently, before fitting all coefficients
or using a joint state/parameter EKF. Fit on discrete one-step prediction errors
to avoid unnecessarily differentiating angular velocity. Require excitation,
retain stable dynamics, and update slowly with confidence and hard bounds.
Freeze on contact, numerical fallback, and inadequately excited intervals.
Saturation should be logged and either modeled or excluded from the first fit.

First validate this as an offline or shadow predictor across held-out races.
Only then feed coefficients into MPC stage parameters. A Kalman filter or recursive
least squares can perform identification, but neither resolves missing excitation
or confounded physical quantities. Randomized parameters reset per episode, so
learning must occur early enough to help the same race; do not carry per-episode
estimates into another randomized drone without a separately justified prior.

## Independent ideas and relative priority

1. **Measure prediction quality before adding prediction machinery.** Log
   predicted-next versus actual-next position, velocity, attitude, and rates, plus
   command, gain, acceptance reason, saturation, geometry revision, and solver
   status. Use wrapped/quaternion attitude errors and consistent frames. Score
   one-step residuals and rolling multi-step predictions under recorded applied
   commands; do not compare a long plan against a trajectory whose future actions
   were subsequently changed. Stratify early flight, crossings 3/4, and pre-failure.
   This distinguishes model mismatch from accurate prediction of an infeasible
   route or a numerical failure. It is the highest-value estimation-related step.
2. **Bounded attitude-response calibration.** My strongest new model-improvement
   hypothesis if residuals show systematic attitude lag. It complements the
   speed-by-authority tests: more allowable command angle does not guarantee the
   actual drone reaches that angle in time. Benefits remain unmeasured.
3. **A small acceleration-bias observer.** If velocity prediction errors show a
   persistent component after thrust-gain adaptation, estimate a 3D disturbance
   from (v_actual_next-v_predicted_next)/dt and add a bounded, slowly varying bias
   to predicted acceleration. An EMA is a useful baseline; a random-walk KF can
   adapt trust. Use this instead of, or after, gain calibration initially: a bias
   and gain can explain the same error without sufficient thrust/attitude variation.
   White random disturbances cannot be predicted sample by sample; an aggressive
   observer would chase them. This needs core and solver parameter changes.
4. **Predict gate passage explicitly.** Check when predicted segments cross the
   required gate plane and their lateral/vertical clearance in its frame. Log the
   margin first; if it predicts failures, test a local stage-cost or constraint
   change near that crossing. Account for the vehicle envelope and between-node
   crossing interpolation. Existing contour error at virtual progress is not the
   same as a valid future passage. This directly addresses the fourth-crossing
   failure cluster, though it is more work than a scalar filter.
5. **Separate numerical recovery from smoother tracking.** Retain default versus
   classical Riccati and small LM tests before attributing health improvements to
   adaptation. Changing the trajectory through filtering can hide a triggering
   condition without fixing solver robustness. Validate prediction and input
   finiteness, preserve numerical-failure counts, and inspect status before reset.

## Recommended next testing sequence

Use reference 3.0, cap 3.2, angle .875, RTI passes 3, pressure 12 as the numerical
repair parent. Record effective Riccati and condensing options and LM values.
Do not confuse classical Riccati (`qp_solver_ric_alg=0`) with the separate
condensing flag (`qp_solver_cond_ric_alg`). A small LM value such as 1e-4 is an
experiment, not an established cure. Verify default-equivalence and runner
integration before running; the existing prepared adapter is not by itself an
executable campaign.

The current evidence is 46/100 completions and 10 numerical ticks in two races
for 3.0/.875/RTI3. Most other failures are ordinary racing failures. Numerical
repair can unlock the observed 40% criterion while leaving considerable tracking
work. The symbolic stage Hessian's reported rank deficiency makes factorization
a plausible target, not a proven cause of the observed NaNs.

Keep speed-by-authority next. Collect the prediction diagnostics on a predetermined
matched subset during these tests. If thrust/attitude residuals justify adaptation,
insert a separate 30+ matched-seed screen with repaired-parent/current EMA,
faster EMA (e.g. adaptation_rate 4), and scalar gain KF. Follow with bounded
attitude-response or bias estimation according to the residual signature, rather
than stacking all estimators. Freeze promising candidates before fresh 100+
matched-seed confirmation. Require >=40% observed completion, worthwhile paired
speed gains, unchanged numerical-health rules, and advisory local latency.

Report prediction accuracy separately from racing outcomes: a lower one-step
error alone does not establish a faster or more reliable controller. No population
completion guarantee follows from just exceeding the observed sample threshold.

All proposed estimator/model changes can live in controller helpers, core, and
solver files. Only diagnostic collection, experiment configuration, and audit
integration need touch the testing harness. No simulator, dynamics randomization,
track visibility, gate-pass semantics, or dependency changes are required. Use
only public observations and commands, never hidden randomized parameters.

## Evidence and references

- [Latest campaign interpretation](../../logs/mpcc-campaign/departure-speed-20261104-v1/results-analysis-20261104-v1/analysis-v2-policy40.md)
- [Campaign checkpoint](../../logs/mpcc-campaign/departure-speed-20261104-v1/campaign-summary.md)
- [Root MPCC thrust adaptation](../../lsy_drone_racing/control/attitude_mpcc_v1.py)
- [Root controller prediction model](../../lsy_drone_racing/control/attitude_mpc.py)
- [Acados solver option documentation](https://docs.acados.org/python_interface/index.html): Riccati positive-definiteness requirements and LM options; corroborated in installed source.
- [Crazyflow identification documentation](https://learnsyslab.github.io/crazyflow/user-guide/dynamics/system-identification/): fitting translational and rotational response coefficients; corroborated in installed symbolic second-order dynamics.
- [MPC disturbance/noise model documentation](https://www.mathworks.com/help/mpc/ug/adjusting-disturbance-and-noise-models.html): distinguish persistent prediction errors from white noise.

Scalar-filter gains above were checked by direct recurrence. No estimator benefit
or racing improvement was measured in this investigation.

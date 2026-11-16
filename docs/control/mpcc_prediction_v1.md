# Prediction/adaptation research v1

This is a testing implementation, not a production controller or a selected racing
winner. The paused departure-speed campaign and its frozen research checkout are
unchanged. Use the new runner below; changing the root `config/level2.toml` would
not select this implementation in the campaign.

## Implementation and import path

- `lsy_drone_racing/control/mpcc_prediction_core.py` is a new copy of the campaign
  `MPCCBroadCore`, with the gain helper replaced. Path policy, costs, progress,
  solve loop and fallback retain the Broad behavior.
- `mpcc_prediction_solver.py` copies the Broad OCP, adds body drag **outside** the
  thrust-gain multiplier before RK4 discretization, calibrates nominal roll/pitch
  coefficients, and accepts the existing proposed numerical options directly.
- `mpcc_prediction_model.py` holds the small configuration dictionaries, shared
  drag expression, fixed coefficient scaling, and EMA/scalar-KF gain update.
- `scripts/mpcc_prediction_research.py` explicitly loads these three modules from
  the root controller directory into the **frozen campaign package**. Other imports,
  including environment, geometry, base attitude model and config, use
  `.local/mpcc-study/broad-20261103T152500Z-r2/checkout`. It checks import origin and
  the constructed controller class, and runs the same synchronous episode loop.
  It requires that checkout and the installed campaign dependencies to remain
  available. It intentionally refuses a process that already imported another
  `lsy_drone_racing` package; invoke it as its own Python command.
- `scripts/mpcc_prediction_diagnostics.py` adds a bounded per-tick prediction
  sidecar only for preselected seed IDs. Shared logging-v5 compact geometry and
  per-tick numerical/timing/racing diagnostics remain available for every race.

The copies make this version replaceable without modifying historical sources or
depending on runtime patches to their controller methods. They are not a new
controller framework. No simulator physics, randomizations, observations, gate
rules, dependencies or simulated control timing were changed. The only config
change at execution is `sim.render=False`, as in the campaign worker.

## Settings

Each prepared case has complete `mpcc`, `mpcc_experiment`, `prediction`, and
`numerics` dictionaries. Unknown prediction/numerical keys and nonfinite values
are rejected. Requested and effective settings are exported in episode rows and
compact diagnostics. The analyzer also checks the actual generated OCP JSON for
numerical options. Existing Broad solver settings (RTI passes, horizon,
condensing length, QP iterations/tolerances, RK4 substeps) remain in `mpcc`.

Prediction defaults preserve the Broad model and EMA rate 2:

```json
{
  "drag_strength": 0.0,
  "attitude_response_scale": 1.0,
  "attitude_command_gain_scale": 1.0,
  "thrust_gain_mode": "ema",
  "initial_gain": 1.0,
  "initial_covariance": 0.0025,
  "measurement_variance": 0.01,
  "process_noise_rate": 0.0008,
  "covariance_max": 0.01
}
```

Nominal beta is `[0.4987013311, 0.4987013311, 0.5707692403] /s`, computed as
`-[diag(drag_matrix)] / .0434` from the installed **nominal** cf21B_500 TOML.
The controller embeds these fixed constants; it never looks up episode mass,
inertia, motors, hidden disturbances or applied actuator states. The gain sample
uses the command previously sent to `env.step`, endpoint-averaged thrust direction,
and the average of drag acceleration at both observed endpoints. With zero drag
it retains the existing Broad observation/update arithmetic exactly.

Roll/pitch coefficients scale by `s²`, `s`, `s²*g` for angle, rate and command;
yaw coefficients remain unchanged. This is fixed model calibration.

EMA retains `mpcc.adaptation_rate`. KF predicts `P += Q_rate * dt` every tick,
including the first and rejected ticks, caps it at `covariance_max`, then corrects
only accepted samples. Both modes retain strict raw-gain bounds `(0.6,1.5)`, gain
clipping `[0.7,1.4]`, altitude and thrust-change gates from the parent. Gain and
covariance reset per episode. Covariance settings are exploratory noise/weight
choices, not confidence calibration.

`config/research/mpcc_prediction_v1/parent-fast.json` is the complete
`S30_RTI3_A875` configuration from campaign batch-004, including reference 3.0,
cap 3.2, max angle .875, three RTI passes and pressure 12. Every other setting is
explicit, including gate offset .162, pole width .39375 and departure depth .25.
Supply another complete racing parent with `--parent /absolute/path/parent.json`;
it must have `mpcc` and `mpcc_experiment` sections, optionally `numerics`, with
adaptation rate 2. Cases inherit all racing/geometry settings from that parent.

`cases.json` contains ready-to-run deltas:

| Case | Change from its baseline |
| --- | --- |
| baseline | Unmodified model; EMA rate 2 |
| drag_05 / drag_10 / drag_15 | Drag strength .5 / 1 / 1.5 |
| attitude_09 / attitude_11 | Response scale .9 / 1.1 |
| attitude_gain_11 | Command-gain scale 1.1 only |
| ema_4 | EMA adaptation rate 4 only |
| scalar_kf | KF only, with the exploratory defaults above |
| combined_example | Drag 1, response 1.1, command gain 1.1, KF |

The combined case is illustrative. Every single-feature case differs in exactly
one setting. Edit/copy these definitions before preparing a new batch to try other
KF settings or combinations; never edit inputs after freezing a plan.

`numerics-default.json` selects condensing Riccati 1, solver Riccati 1 and LM 0.
`numerics-classical-lm.json` keeps condensing Riccati 1, selects solver Riccati 0
and LM 1e-4. These are separate flags. The latter is now executable in this
runner and can serve as a **numerical-repair hypothesis** for all matched cases.
It is not an established repaired parent. Omit `--numerics` to inherit a supplied
parent's numerical options, or the default options if absent. Hold the numerical
options fixed across model comparisons; assess numerical repair separately.

## Commands

For a testing-session handoff, copy the [screen dispatch prompt](mpcc_prediction_v1_screen_dispatch.md).

Run from `/home/askho/repos/lsy_drone_racing`. These exports reproduce the recorded
campaign activation without invoking an install/build setup script. Builds occur
only in each fresh case's generated directory.

```bash
export ACADOS_SOURCE_DIR="$PWD/acados"
export LD_LIBRARY_PATH="$PWD/acados/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SCIPY_ARRAY_API=1
export PYTHONDONTWRITEBYTECODE=1
export PATH="$PWD/.pixi/envs/default/bin:$PATH"
```

The matched 30-seed screen below prepares all ten cases (300 episodes) and
preselects three matched prediction-diagnostic seeds. The commands are provided
for later use; implementation verification does **not** run this screen.

```bash
python scripts/mpcc_prediction_research.py prepare \
  --output logs/mpcc-prediction-v1/screen-30-v1 \
  --stage screen --seed-start 1601000 --seed-count 30 \
  --parent config/research/mpcc_prediction_v1/parent-fast.json \
  --numerics config/research/mpcc_prediction_v1/numerics-classical-lm.json \
  --prediction-seeds 1601000,1601001,1601002
python scripts/mpcc_prediction_research.py run logs/mpcc-prediction-v1/screen-30-v1
python scripts/mpcc_prediction_research.py analyze logs/mpcc-prediction-v1/screen-30-v1
```

After reviewing paired gains and health, freeze **one** candidate for fresh
100-seed confirmation. This example names `drag_10` for command syntax only;
replace it with the candidate justified by the completed screen. The runner
requires an audited screen, an identical baseline/candidate pair and disjoint
seed cohorts. It also rejects reuse of the six completed campaign cohorts.

```bash
python scripts/mpcc_prediction_research.py prepare \
  --output logs/mpcc-prediction-v1/confirm-100-v1 \
  --stage confirmation --seed-start 1602000 --seed-count 100 \
  --screen logs/mpcc-prediction-v1/screen-30-v1 \
  --cases baseline,drag_10 \
  --parent config/research/mpcc_prediction_v1/parent-fast.json \
  --numerics config/research/mpcc_prediction_v1/numerics-classical-lm.json \
  --prediction-seeds 1602000,1602001,1602002
python scripts/mpcc_prediction_research.py run logs/mpcc-prediction-v1/confirm-100-v1
python scripts/mpcc_prediction_research.py analyze logs/mpcc-prediction-v1/confirm-100-v1
```

Use fresh paths for repeated work. `prepare`, `run`, and `analyze` refuse output
reuse. Plans pin new sources, parent/case definitions, the policy, shared observer,
audits, and the frozen runtime dependencies. The runner takes the existing
`logs/mpcc-tuning/.combination.lock` nonblockingly, and creates a fresh process
and code-generation directory per case. It never advances the old campaign.
Changing pinned files requires a fresh plan/output path.

## Diagnostics and interpretation

`run-v1/CASE/episodes.json` holds requested/effective settings, actual generated
solver options, complete timing arrays, outcomes and matched public initial
states. `episode-NNN/diagnostics.compact.json.gz` retains the logging-v5 schema
and numerical-health signal (`status != 0` or missing optimized inputs).

On `--prediction-seeds`, `prediction.json.gz` additionally retains pre-action
position/quaternion/world velocity/angular velocity, command, a physical 12-state
next-state prediction, the actual next observation, gain/raw sample/rejection
reason/covariance/update weight, and one-step residuals. The sample associated
with gain at tick k closes interval `[k-1,k]`; the prediction at k is compared
with observation k+1. The terminal observation is scored too. Attitude error is
the rotation distance in radians, independent of Euler wrapping/quaternion sign.
The predicted angular coordinates are Euler angles/rates, as in the OCP; observed
angular velocity remains available in its original public convention.

100/200 ms shadow scores use recorded future commands with gain frozen at the
rollout's starting value. No full horizons are dumped. Noise, unobserved action
disturbances, contact, and inner-loop/motor mismatch remain part of these errors.
They are not scores against the old MPC plan under subsequently changed commands.
Sidecar work, geometry capture and rollout scoring are outside the compute timer.

`analysis-v1` contains an independent shared compact diagnostic audit, completion
intervals, failure occurrence counts, all status/fallback/timing metrics, paired
shared-finish deltas with bootstrap intervals/rescues/regressions, and prediction
summaries. It checks hashes, settings, generated options, matched initial
observations, per-tick command/prediction alignment and residual arithmetic.

The retained policy is **observed completion >=40%, worthwhile paired speed
improvement, zero numerical-status/fallback ticks and finite commands**. Local
latency is reported as advisory, with the simulated .02 s control interval
unchanged. The analyzer labels only the completion/numerical floor; it does not
select a winner or invent a minimum worthwhile speed gain. A smoke result never
qualifies. A lower prediction residual alone is not racing evidence. The fast
parent's prior adverse numerical results remain relevant; a healthy tiny cohort
does not erase them or establish repair.

## Verification

```bash
python -m pytest -q -p no:cacheprovider tests/unit/control/test_mpcc_prediction.py
```

Focused checks cover exact default-model and real-solver action/prediction replay
equality with frozen Broad, nominal damping sign/frame, consistent drag-corrected
gain observations, fixed roll/pitch coefficients/yaw preservation, shared sample
acceptance, KF rejected/nonfinite samples/covariance/gain bounds/reset, single
case differences, numerical option application and combined construction.

Implementation smoke results and limitations are recorded separately under
`logs/mpcc-prediction-v1/`; no 30/100-seed study or production promotion is part
of this implementation task.

The completed check is [smoke-v3](../../logs/mpcc-prediction-v1/smoke-v3/analysis-v1/audit.json):
two matched seeds, baseline versus combined example, four episodes, prediction
diagnostics on seed 1600010 only, classical solver Riccati plus LM 1e-4. The audit
passed and both cases had zero numerical/fallback ticks. Baseline finished 2/2;
the combination finished 1/2. These counts do not support performance selection
or numerical-repair claims. All eight focused tests passed, including a real
generated-solver default replay and recorded-command rollout/terminal-alignment
checks. See the [verification receipt](../../logs/mpcc-prediction-v1/implementation-verification.json).

Intermediate smoke-v1 and smoke-v2 outputs are retained: v1 stopped before
simulation on a config-loader `Path` conversion error; v2 ran one baseline episode
then stopped on list/array conversion during rollout export. Both issues were
fixed, with the latter covered by the rollout regression test. Those incomplete
attempts are not study results, and their old source pins precede the fixes.

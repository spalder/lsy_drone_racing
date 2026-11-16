**MPCC tuning options without large-scale changes — 2026-11-03**

Use the current fixed MPCC v1 as the main reference. The most useful next work is
to confirm that reference in the official simulator, refine recentering × contour
weight, then revisit speed, lift and preview around the resulting configuration.
There are still several weights and local geometry constants worth testing before
changing the optimizer formulation or adding a planner.

This is an inventory for future work, not a record of new experiments. No tuning
episodes were run to produce it. The supplied identifier did not identify a unique
local session; the user confirmed using the recent MPCC tuning work instead.
The inventory includes the later 100-seed validation and v1 packaging work, which
supersede the shortlist in the earlier 700-episode autonomous summary.

“Without large-scale changes” means retaining the attitude command interface,
identified dynamics family, spline route, virtual progress formulation, existing
state/input dimensions and SQP-RTI solver structure. Existing parameter changes
come first. Local constants and small behavioral extensions are listed separately
because their implementation and validation effort is greater. Proposed values
are starting grids, not measured improvements or certified operating limits.

**Current reference and evidence**

The current [Level 2 configuration](../../config/level2.toml) selects
[attitude_mpcc_v1.py](../../lsy_drone_racing/control/attitude_mpcc_v1.py).
Its embedded effective settings are:

| Setting | Current v1 value |
| --- | ---: |
| `reference_speed` | 2.3 |
| `max_speed` | 2.6 |
| `horizon_steps` | 40 |
| `contour_weight` | 800 |
| `lag_weight` | 400 |
| `progress_weight` | 12 |
| `max_angle` | 0.70 rad |
| `attitude_rate_weight` | 0.1 |
| `attitude_slew_weight` | 0.02 |
| `thrust_slew_weight` | 0.1 |
| `terminal_weight` | 0.2 |
| `adaptation_rate` | 2.0 |
| `obstacle_clearance` | 0.26 m |
| `gate_center_snap` | 0.75 |
| `over_gate_lift` | 0.15 m |
| `observed_obstacle_clearance` | `None` |

The [latest independent comparison](mpcc_speed_snap_contour_validation.md) used
100 matched fresh seeds, 15592–15691, at reference/cap 2.3/2.6:

| Recentring / contour | Finishes | Paired lap-time change vs 0.50/600 | Interpretation |
| --- | ---: | ---: | --- |
| 0.50 / 600 | 63/100 | Reference | Earlier speed option |
| 0.75 / 600 | 67/100 | +0.00323 s, about +0.06% | Lower time-cost alternative |
| 0.75 / 800 | 70/100 | +0.05000 s, about +0.86% | Current v1; highest observed completion |

Both time contrasts use 62 shared successful seeds. The direct 800-vs-600
comparison at snap 0.75 gained three net finishes and cost 0.04636 s on 66 shared
finishes; its completion advantage remains uncertain. The current candidate's
completion 95% interval is approximately 60.0–78.8%, so 70/100 does not establish
a population completion rate of at least 65%.

These 100-seed results came from the historical simulator with its compatibility
patch. The [packaging handoff](../../logs/mpcc-compliance-20261103/HANDOFF.md)
records two successful smoke episodes in the unmodified official environment,
on previously used seeds 15592 and 15593. That verifies bounded execution, not a
new reliability cohort. One command hash differed despite matching step counts.
Treat historical performance as provisional until a matched official-environment
comparison is completed.

For a slower reliability reference, retain the old 1.3/1.8 configuration with
snap 0, lift 0.05, contour 400 and angle 0.6. It finished 557/725 in the
[overnight holdout](mpcc_overnight_results.md). That is a separate cohort and
cannot be compared directly with 70/100 to estimate the speed/reliability tradeoff.

**All existing tuning parameters: 16 options**

These names already exist in the research controller. Optimizer options live in
`controller.mpcc`; the three experimental geometry options live in
`controller.mpcc_experiment`. The fixed v1 controller embeds the same settings
and explicitly rejects nonempty research tuning sections. For future research,
use a separate configurable candidate or explicit copies of the embedded settings.
Adding TOML overrides to v1 will raise an error.

“Earlier regime” below means the parameter was screened around slower settings;
its effect has not thereby been established around the current 2.3/2.6 candidate.
Priorities reflect the reviewed evidence and implementation cost.

| ID / parameter | What can be tried next | Evidence and priority |
| --- | --- | --- |
| E01 `gate_center_snap` | Refine around 0.75: 0.50, 0.625, 0.75, 0.875, 1.00, first holding contour fixed. | **High.** Recentring helped in the recent fast regime. At the older slow regime, zero recentering won; the preferred value depends on other settings. Zero retains a projected/clipped previous crossing; one requests full centering. |
| E02 `contour_weight` | 600, 700, 800, 900, 1000; then pair finalists with recentering. | **High.** 800 gave the highest recent validation finish count with a small time cost. Its advantage over 600 is uncertain; 700 and 900 are useful local interpolation tests. |
| E03 `reference_speed` | 2.1, 2.2, 2.3, 2.4 with cap initially fixed at 2.6. Consider 2.5 only after the faster branch preserves the chosen completion criterion. | **High.** This changes the preferred virtual progress speed and has produced substantial lap-time changes. Re-evaluate with current geometry rather than carrying forward the old speed ladder's ranking. |
| E04 `over_gate_lift` | Refine 0.125, 0.15, 0.175 m; retain 0.10 and 0.20 as diagnostic outer references if needed. | **High/medium.** 0.15 became the fast-regime reference. At 2.2/2.5, 0.10 lost finishes; 0.20 did not add finishes and cost time. It is a smooth bump between the third and fourth crossings, not a uniform gate-height offset. |
| E05 `max_angle` | 0.65, 0.70, 0.75 rad, paired with speed and contour finalists. | **Medium.** 0.70 previously improved both speed and observed finishes over 0.60. The scalar bounds all three Euler command components and attitude states, including yaw; it is not solely a roll/pitch tilt limit. |
| E06 `horizon_steps` | 35, 40, 45, 50; reserve 60 for a specific preview hypothesis. | **Medium.** At 50 Hz these are 0.70, 0.80, 0.90, 1.00 s of preview. Horizon 50 gave a small isolated completion gain, but did not add finishes at the leading combination in autonomous batch001. Longer horizons cost compute and sometimes lap time. |
| E07 `lag_weight` | 200, 300, 400, 600, 800; prioritize contour × lag comparisons. | **Medium.** Screened in the earlier regime, without establishing a current-regime optimum. Changes the penalty on along-path mismatch; its balance with contour and progress matters. |
| E08 `progress_weight` | 6, 9, 12, 18, 24 while holding speed fixed. | **Medium.** Weights the squared deviation from `reference_speed`. Raising it strengthens speed preference; it does not independently raise the preferred speed. Earlier screening is not a substitute for testing the present geometry. |
| E09 `attitude_rate_weight` | 0.05, 0.075, 0.10, 0.15, initially keeping slew 0.02. | **Medium/low.** Less angular-rate penalty can improve responsiveness. The old joint reduction of rate and slew was faster but lost holdout finishes; test this factor independently. |
| E10 `attitude_slew_weight` | Local 0.015, 0.02, 0.025, 0.03; use 0.01/0.04 only to revisit a diagnosed issue. | **Medium/low.** The fast one-factor study had seven numerical-failure ticks at 0.01; 0.04 lost a finish and added time. 0.02 remains the useful reference. |
| E11 `thrust_slew_weight` | 0.05, 0.075, 0.10, 0.15, 0.20, especially with lift and adaptation. | **Medium.** Already screened in the slower regime. Controls vertical-command responsiveness versus smoothness; the changed climb and speed can change its effect. |
| E12 `terminal_weight` | 0.10, 0.20, 0.30, 0.40, preferably with horizon 40/50. | **Medium/low.** Already screened earlier. Multiplies the whole terminal cost; there is no terminal stopping or collision constraint. It also scales terminal velocity and attitude penalties. |
| E13 `obstacle_clearance` | Small global changes: 0.24, 0.26, 0.28, 0.30 m; test smaller requests only with measured pole-clearance diagnostics. | **Low until pole failures are identified.** Increasing global clearance to 0.30 did not improve the recent 16-seed safety cohort. This is distance requested from the pole axis, not a guaranteed body/swept clearance. |
| E14 `observed_obstacle_clearance` | `None`, 0.26, 0.28, 0.30 m, as a separate factor from global clearance. | **Low until pole failures are identified.** Earlier isolated rescues did not translate into a consistent combination benefit. Applies to detected poles on replans; initial planning and unrevealed poles use global clearance. |
| E15 `adaptation_rate` | 0, 1, 2, 4 s⁻¹; compare gain convergence and vertical tracking. | **Medium; underexplored.** Fixed at 2.0 in the reviewed broad optimizer studies. Zero is supported and disables gain updates. At 50 Hz, rate 2 gives a filter coefficient of about 0.0392 per accepted sample. |
| E16 `max_speed` | Measure cap saturation first. If binding, test 2.4, 2.6, 2.8 at fixed reference 2.3 and inspect numerical behavior. | **Low unless binding.** A previous cap-only sweep 2.1/2.4/2.8/3.2 produced identical outcomes and successful times on its 16 matched seeds. This bounds virtual progress speed, not physical drone speed; raising it alone need not speed up flight. |

Most research settings must be positive and finite. `horizon_steps` must be an
integer; `adaptation_rate=0` is permitted. Snap is in [0,1], lift is nonnegative,
and an observed clearance is either `None` or positive. Some runners enforce
narrower experiment bounds than the controller. In particular,
`mpcc_adaptive_batch.config_for` does not currently allow adaptation-rate changes;
E15 requires a small runner extension or a new research driver.

**Local geometry constants: 12 additional options**

These require small edits to the experimental path correction or a separate
research copy of v1. They keep the same optimizer. Their proposed effects are
mechanistic hypotheses; the reviewed studies did not validate these edits.
Measure achieved path/body clearance because gate correction and pole repulsion
can interfere with each other.

| ID / location and present value | What can be tried | Purpose / practical limit |
| --- | --- | --- |
| G01 gate approach/departure offsets, ±0.18 m | Symmetric 0.14/0.18/0.22 m; then asymmetric approach/departure distances. | Change alignment and departure timing around the gate plane. Rebuild the anchor basis for every changed offset. |
| G02 gate warp width, 0.4 in progress coordinates | 0.30/0.40/0.50. | Trade a local sharp correction against a broader smoother deformation; monitor basis conditioning and tracking error. |
| G03 extra opening erosion, vehicle radius +0.02 m | Extra 0.01/0.02/0.03 m while preserving the physical radius bound. | Change the permitted off-center crossing. More erosion reduces freedom; it does not itself guarantee a safe trajectory. |
| G04 single snap fraction for all gates | Per-gate/per-occurrence snap values, starting with one problematic crossing. | Avoid forcing every crossing to share a compromise. The repeated second gate can have different needs on its two passages. |
| G05 common lateral and vertical recentering fraction | Separate lateral/vertical fractions. | Test whether retaining a lateral crossing while centering vertically, or the reverse, addresses the measured failure. |
| G06 lift bump endpoints, `_anchors[9:11]` | Move start/end slightly or change bump width/peak location, holding peak lift at 0.15. | Raise or delay the climb at the return segment without moving gate crossings. Distinguish this from changing lift amplitude. |
| G07 pole-repulsion Gaussian width, 0.35 | 0.25/0.35/0.45 in progress coordinates. | Spread a pole detour differently; a wider detour may reduce abrupt curvature but affect neighboring gates. |
| G08 pole-correction passes, 8 | 4/8/12, checking residual distance and replan latency. | Determine whether more correction converges to a useful result; fixed anchors can prevent the requested clearance regardless of pass count. |
| G09 pole vertical bypass, pole height +0.1 m | Local buffer 0.10/0.15/0.20 m. | Test whether the point-path criterion skips repulsion too early during overflight. Include the vehicle envelope in interpreting clearance. |
| G10 gate departure depth, 0.25 m | 0.20/0.25/0.30 m, initially at fixed rise scale. | Change how far the departure correction pushes the path through the gate before the climb. |
| G11 departure-depth rise scale, 0.18 | 0.14/0.18/0.22 in progress coordinates. | Change how quickly the extra departure depth is requested after crossing; pair with G10 only after isolated checks. |
| G12 departure influence: 1.2 extent, 0.2 taper, 0.60 lateral/vertical extent, 0.12 taper | Small isolated changes, e.g. ±10–20%, one quantity at a time. | Adjust where frame-departure protection acts. Larger influence can deform unrelated segments; inspect the full rebuilt spline. |

Small changes to the nominal spline's existing turn and climb waypoints are also
possible. This is a **conditional extension**, not an ordinary supported override:
research `waypoints` bypass automatic gate/pole correction, and ExperimentalMPCC
rejects custom waypoints. Edit a research copy of the default waypoint array and
verify ordered gate crossings/anchor construction, or explicitly preserve that
construction in a new helper. Preserve the route and gate order. Changing course
geometry in `env.track` would change the task instead of tuning the controller.

Path sampling densities (200 samples per original spline interval; 3000 samples
for gate-anchor search) can be adjusted for resolution/performance diagnostics.
They are lower-priority numerical implementation choices: more samples are not
evidence of better racing, and changed anchors can change the controller behavior.

**Cost and identified-model constants: seven options**

These need small solver/controller edits and a fresh generated solver. The
existing exposed scalar weights above should be tested first.

| ID / present implementation | Local extension | Why it might help |
| --- | --- | --- |
| C01 one contour weight for all three components | Separate horizontal/vertical contour penalties. | More vertical tracking around the climb without equally stiff lateral tracking. Existing contour components are in world coordinates; a gate-frame cost would be an additional change. |
| C02 attitude-state stage weights `[1,1,1]` | Separate roll/pitch/yaw weights. | Test the yaw-versus-translational-response compromise without changing the dynamics. |
| C03 command stage weights `[1,1,1,50]` | Expose command attitude penalties and thrust deviation penalty, initially ±25% around baseline. | These are fixed effort costs independent of the existing rate and slew weights. |
| C04 terminal attitude weight 1 and velocity weight 0.1 before overall scaling | Tune terminal velocity separately from terminal contour/lag. | Longer preview may slow the drone because terminal motion is penalized; isolate that effect before discarding more preview. |
| C05 shared angle bound and shared angular penalties | Separate yaw bound, roll/pitch bounds, angular-rate weights or attitude slew weights. | `max_angle` currently couples yaw freedom to roll/pitch freedom. Split only the component supported by measured behavior. |
| C06 adaptation acceptance: altitude >0.15 m; thrust change <0.04; accepted raw gain (0.6,1.5); clipped estimate [0.7,1.4] | Tune one acceptance threshold/bound, or use a short acceleration-estimate filter. | Improve gain estimation when few samples pass or noise dominates. Log accepted/rejected samples and estimated gain; preserve exclusion of ground-contact data. |
| C07 nominal identified model loaded from `Dynamics.so_rpy` | Small controller-local multipliers on identified attitude-response or thrust-calibration coefficients, based on public observed prediction residuals. | Test model mismatch using the same model family. Do not alter simulator parameters or read hidden randomized mass/inertia. This is calibration work and lower priority than E15. |

**Solver and warm-start details: five options**

| ID / current value | What can be tried | Interpretation |
| --- | --- | --- |
| N01 two path-linearization/RTI passes per tick | 1/2/3 passes. | Trade solve consistency on a curved/rebuilt path against latency; measure behavior and calls that include replanning. |
| N02 partial-condensing horizon `min(10,N)` | Condensing lengths 5/10/20 when compatible with N. | Primarily a runtime/numerical comparison. Equal trajectories with lower compute can be useful even without a lap-time gain. |
| N03 QP iteration maximum 50 and tolerance 1e-4 | Modest comparisons such as 30/50/80 iterations and 1e-3/1e-4/1e-5 tolerance. | Only useful if stopping criteria or residuals matter; record statuses/residuals and preserve behavior under difficult cases. The NLP is SQP_RTI: increasing `nlp_solver_max_iter=20` alone is not a substitute for adding RTI passes. |
| N04 shifted previous state/input prediction; repeat final row | Compare baseline shift with extrapolated final state or progress reinitialization after a large path update. | May improve the next solve after revelation. Needs explicit handling of path bounds and the previous-command state. |
| N05 one RK4 step per control interval | Two RK4 substeps with the same control interval and model. | Small integration-accuracy experiment; adds generated-model work. Keep the actual 50 Hz control interval fixed. |

Changing solver family, replacing SQP_RTI with full SQP, adding states or hard
collision constraints would expand beyond this inventory's intended scope.

**Small behavioral extensions: six options with more validation effort**

These change the control policy rather than just a constant. They remain local
experiments, but should follow diagnosis of the remaining failures. None is an
already-supported setting or a demonstrated improvement in the reviewed results.

| ID | Extension | Minimum useful scope |
| --- | --- | --- |
| B01 | Short speed reduction approaching an unrevealed gate or immediately after a geometry revision. | One bounded speed multiplier plus a recovery duration/distance, driven only by public observations. Update the solver's per-stage speed references consistently. |
| B02 | Slower virtual speed in the tight climb/return, faster on open segments. | A small progress-dependent schedule with a few parameters; test against a matched constant-speed case. Local path deformation changes the progress metric, so validate segment boundaries. |
| B03 | Curvature/tracking-error-based speed attenuation. | One smooth bounded multiplier, optionally previewed along the horizon. Verify that attenuation improves completion rather than merely slowing every race. |
| B04 | Bounded progress correction when virtual progress gets ahead of the drone. | Project onto a local window of the current route, respecting the next required gate occurrence. An unconstrained nearest point can jump between nearby route branches. |
| B05 | Blend a newly rebuilt path over a short interval instead of applying it immediately. | A small transition duration after geometry revelation; verify every intermediate path near the observed gate and account for warm-start consistency. Delayed corrections can also hurt at 0.7 m sensor range. |
| B06 | Alternative response to a failed solve. | Compare current upright hover/reset with a bounded brief reuse of the last feasible input/prediction. Low priority while the reference has zero observed numerical-failure ticks; test actual failure cases and repeated failures separately. |

**Interactions worth testing explicitly**

Single-parameter gains cannot be added. The earlier studies include both
complementary rescues and regressions introduced by combinations. Start with
small matched factorials, retaining the constituent references:

| Priority | Interaction | Question it resolves |
| --- | --- | --- |
| 1 | Snap × contour | Does the current 0.75/800 tradeoff persist, and do nearby values improve it? |
| 2 | Reference speed × snap/contour finalist | Does the preferred geometry change at 2.2 versus 2.3/2.4? |
| 3 | Lift × reference speed | Is the current 0.15 m climb still appropriate after speed changes? |
| 4 | Horizon × terminal weight | Can more preview help without an unnecessary terminal-motion penalty? |
| 5 | Contour × lag × progress weight, in small stages | Is the controller trading path error against virtual progress effectively? |
| 6 | Max angle × contour or reference speed | Does greater command freedom improve tracking at the selected speed? |
| 7 | Adaptation rate × thrust slew × lift, in small stages | Is vertical error due to gain estimation, thrust responsiveness or path shape? |
| 8 | Global × observed-only pole clearance | Is a reveal-specific detour useful once pole failures are actually identified? |
| 9 | Rate weight × attitude slew | Can modest responsiveness changes work without repeating the aggressive smoothing reduction's finish loss? |

**Approaches already tested that deserve lower priority**

- **Raising the cap alone:** the cap-only 16-seed sweep had unchanged completion
  and successful times. Inspect saturation before repeating it. The earlier
  overnight study also skipped a cap branch under its saturation rule.
- **Aggressive smoothing reduction:** the overnight challenger, rate 0.05 plus
  attitude slew 0.005, was about 1.37% faster on shared finishes but finished
  543/725 versus 557/725, with 21 regressions and seven rescues. It did not meet
  completion preservation. That does not rule out modest isolated changes at
  the new speed, but it gives a concrete reason to avoid making this the default.
- **Increasing all clearances:** the 0.30 m safety singles did not improve the
  recent 16-seed cohort. In the older 100-seed geometry factorial, adding the
  observed-pole override to snap 0/lift 0.05 reduced finishes 77→76 and added
  26.9 ms on shared finishes. More requested clearance is not always better.
- **Always using zero recentering:** good at the older slow reference, worse
  than modest/stronger recentering in several fast-regime comparisons. Its old
  ranking should not determine the current value.
- **Always increasing lift or horizon:** 0.20 lift and horizon 60 did not add
  finishes in the fast one-factor study. Revisit them only with a specific
  path/preview hypothesis or a relevant interaction.
- **Very fine low-speed geometry sweeps:** snap 0.025/lift 0.07 tied the old
  snap 0/lift 0.05 incumbent at 151/200 independent finishes, exchanging two
  rescues for two regressions with negligible paired time difference. Further
  refinement there has less immediate value than testing the current reference.
- **Blind escalation beyond reference speed 2.4:** an older screen reached
  about 5.27 s at reference 2.6 but only 3/16 finishes. The current geometry may
  change that frontier; it still needs staged evidence rather than assumed gains.

These are deprioritized repeats, not proof that an entire parameter direction
can never help.

**Useful diagnostics before selecting more knobs**

Record gate occurrence, next required gate, contact object/primitive if exposed
by the environment, cross-track/lag/vertical error, physical velocity, virtual
speed and cap saturation, commanded angles/thrust and bound saturation, gain
estimate/accepted samples, geometry revisions, solver status and replan-call
latency. A failure after three gates is a location/stage observation, not proof
of a particular gate-frame or pole contact. Measure actual clearance where the
available geometry allows it; the current spline has no hard gate or collision
constraints. Offline corridor parameters do not affect racing because
`plan_corridor` is not called by the feedback loop and is absent from v1.

The first practical experiment should be a matched official-environment
comparison of 0.50/600, 0.75/600 and 0.75/800 with all other current settings
fixed. Then screen a small snap/contour neighborhood, freeze finalists, and use
a fresh independent cohort. Follow with speed/lift or the failure-specific
parameters identified above. This order is a proposal, not a scheduled run.

For future comparisons:

1. Freeze the objective first. Use the recent completion aim and approximately
   2% paired lap-time cost ceiling as historical context; state the next study's
   actual acceptance rule before outcomes. Keep speed/reliability alternatives
   when neither dominates.
2. Use identical ordered seeds for every configuration in a cohort. Inventory
   all earlier used **and reserved** seeds before allocating a new holdout;
   the next unused seed cannot be inferred from the latest report alone.
3. Keep failure-enriched diagnostic sets separate from population validation.
   A holdout used to choose another setting becomes tuning evidence; allocate
   new independent seeds for the next confirmation.
4. Report completion counts/intervals, paired rescues/regressions, shared-success
   time differences with their sample sizes, and all-seed time with a fixed 30 s
   failure penalty. Successful-only means use different subsets. Historical
   study time is steps/50; official reporting uses (steps−1)/50. Record the
   convention and compare like with like.
5. Preserve numerical and latency criteria separately from race outcomes.
   Historical eligibility was every episode p99 ≤20 ms and aggregate >20 ms
   fraction ≤1%. Include replanning in measured controller calls; p99 does not
   guarantee that every full control-loop tick meets its deadline.
6. Generate/run each optimizer configuration in a fresh subprocess, serially
   under the shared acados lock. Loaded generated libraries previously retained
   old configurations even when Python settings changed. Save effective values,
   source/runtime hashes and episode checkpoints.
7. Start a new manifest/output directory. The old prepared runs bind earlier
   sources/configuration and must reject the current changed tree; do not weaken
   their fingerprints to resume new research. Keep the fixed v1 and historical
   evidence available as references.

Keep physics, mass/inertia randomization, disturbances, sensor range, gate order,
assets, collision behavior, control frequency and scoring fixed when judging
controller improvement. Changing these can be a separate diagnostic study, but
would not demonstrate a better controller on the original task. A new global
planner, corridor-constrained MPC, added obstacle constraints, learned controller,
full online identification or a replacement dynamics model are larger projects.

**Source map**

| Source | What it supports |
| --- | --- |
| [Latest snap/contour validation](mpcc_speed_snap_contour_validation.md) | Current primary reference, lower-cost alternative, uncertainty and 100-seed outcomes |
| [Official-environment packaging handoff](../../logs/mpcc-compliance-20261103/HANDOFF.md) | Fixed v1 settings/interface, official smoke, simulator caveat and preserved historical manifests |
| [Autonomous 700-episode summary](mpcc_autonomous_summary.md) | Earlier angle/contour/horizon combinations and 2.2/2.3 Pareto alternatives |
| [Fast one-factor robustness study](mpcc_robustness_results.md) | Angle, contour, horizon, lift and slew evidence, including numerical failures |
| [Revised speed/safety study](mpcc_speed_safety_revised_results.md) | Cap-only nonresponse, speed changes, safety singles and validation |
| [Overnight optimizer results](mpcc_overnight_results.md), [plan](mpcc_overnight_plan.md) | Earlier weight screening, smoothing holdout loss, saturation policy and measurement rules |
| [Fresh fast-regime recentering](mpcc_recenter_fresh_results.md), [geometry feasibility](mpcc_speed_geometry_feasibility.md) | Speed-dependent geometry and failure-enriched diagnostic limitations |
| [Older combination study](mpcc_combination_study.md), [local holdout](mpcc_local_tuning_study.md) | Clearance interactions and lack of gain from fine slow-regime refinement |
| [Fixed controller](../../lsy_drone_racing/control/attitude_mpcc_v1.py), [solver](../../lsy_drone_racing/control/mpcc_v1_solver.py) | Actual embedded parameters, geometry/adaptation/progress constants and optimizer costs |
| [Experimental controller](../../lsy_drone_racing/control/attitude_mpcc_experimental.py), [base controller](../../lsy_drone_racing/control/attitude_mpcc.py) | Existing configurable research interface and custom-waypoint behavior |
| [Adaptive runner](../../scripts/mpcc_adaptive_batch.py), [overnight runner](../../scripts/overnight_mpcc.py) | Runner bounds, missing adaptation override, process isolation and provenance behavior |

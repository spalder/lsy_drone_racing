Prepare an autonomous MPCC **optimizer** study around the current geometry. The
harness is [overnight_mpcc.py](../../scripts/overnight_mpcc.py); its independent
arithmetic/statistical auditor is
[overnight_mpcc_analysis.py](../../scripts/overnight_mpcc_analysis.py).
Preparation and execution are separate commands. Preparation does not launch screening.

The machine-readable plan and source/runtime manifest in the preparation directory
are authoritative. See [the handoff](mpcc_overnight_handoff.md) for the exact directory,
preflight results and commands. Controller algorithms, defaults, existing runners,
track, physics, randomizations and sensors are unchanged.

The incumbent uses `attitude_mpcc_experimental.py`, recentering **0**, height
**0.05 m**, no observed-pole override, and global clearance **0.26 m**. These
geometry settings stay fixed. All optimizer settings are explicit in every case:

```toml
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

The earlier [local geometry study](mpcc_local_tuning_study.md) ran 1,000 episodes
in 94.6 minutes. Its challenger tied the incumbent at 151/200 independent finishes
and did not justify replacing it. Its data remain separate from this new study.

Stages and bounded adaptation:

| Stage | Matched fresh seeds | Configurations and decision |
| --- | ---: | --- |
| Screening | 40 | All 23 distinct isolated cases below; incumbent deduplicated; 920 episodes. Matrix is never truncated. |
| Refinement | 60 | Up to eight new values and five references. Rank isolated intervals, try neighboring midpoints; permit a modest outward half-step only for an eligible, faster boundary value, within fixed bounds. Retain neighbors because 40-seed results are noisy. |
| Combinations | 80 | Up to 12 total. Build speed × progress-weight core with incumbent and constituent references, then paired isolated/core additions in smoothing, horizon and angle priority order. Tracking alternatives remain available in challenges. |
| Challenges | 80 | Up to ten total, including incumbent and unchanged leader. Revisit stronger preview/contour/smoothing or alternate lag/angle/rate/terminal values in the faster regime. Raise progress cap to 2.0/2.2 only if the preceding leader spends at least 1% of valid ticks at >=98% of the current cap. |
| Confirmation | 150 | Incumbent plus at most two finalists. Re-evaluate all on identical fresh seeds and select exactly one distinct challenger. |
| Validation | 300–1,500 | Exactly incumbent and frozen challenger. Size is a prefix of a reserved unused block, chosen using remaining time **before** any validation outcomes. Minimum 600 episodes total. No tuning after this stage. |

Initial grids:

| Parameter | Values |
| --- | --- |
| reference_speed | 1.2, 1.3, 1.4, 1.5, 1.6 |
| progress_weight | 6, 12, 24 |
| attitude_slew_weight | 0.01, 0.02, 0.04 |
| thrust_slew_weight | 0.05, 0.1, 0.2 |
| max_angle | 0.6, 0.65, 0.7 |
| horizon_steps | 30, 40, 60 |
| contour_weight | 200, 400, 800 |
| lag_weight | 200, 400, 800 |
| attitude_rate_weight | 0.05, 0.1, 0.2 |
| terminal_weight | 0.1, 0.2, 0.4 |

Refinement limits are saved in `plan.json`: speed 1.1–1.7, progress weight 3–36,
attitude slew 0.005–0.06, thrust slew 0.025–0.3, angle 0.55–0.75,
horizon 20–70 integer steps, contour/lag 100–1,200, attitude-rate 0.025–0.3,
and terminal weight 0.05–0.6. Adaptation remains 2.0. Geometry is never refined.

Ranking and evidence:

- Eligible candidates finish at least as many matched seeds as the incumbent,
  have no more numerical-failure ticks, and pass latency criteria. Require at
  least one shared finish for a speed ranking.
- Rank by mean candidate-minus-incumbent time on shared successful seeds,
  then completion count descending, normalized L1 departure ascending, then name.
  Normalization scales are fixed in `plan.json` and the runner before execution.
- If none qualifies, the incumbent remains the reference/recommendation. Choose a
  distinct comparison challenger by latency eligibility, fewer numerical ticks,
  more finishes, paired time, distance and name. Record this as a fallback.
- Earlier cohorts guide proposals; comparisons and confirmation always use
  matched seeds within their own cohort. Cross-cohort ranks are exploratory
  proposal heuristics, not direct measured comparisons or pooled evidence.
- Save each stage decision, parent-report hashes, budget check and ordered cases
  before that stage runs. Validation selection and seed count are frozen before
  any holdout episode.
- The final recommendation additionally requires at least **1% paired speed gain**
  and an upper paired bootstrap bound below zero, while preserving observed
  completion/numerical/latency eligibility. Otherwise retain the incumbent.
  This is an observed selection rule, not proof of reliability noninferiority.

Failure scoring and timing:

The registered Gym TimeLimit and internal environment limit are both **1,500
steps at 50 Hz = 30 s**. Every unsuccessful episode receives a fixed 30 s score;
never reward an early termination as a fast lap. Also retain actual elapsed time,
outcome, gate stage and solver failure ticks.

Race time is completed steps / 50 Hz through the existing completion callback.
Per-episode resolution is 20 ms. Save successful means descriptively and compare
paired means/medians/p90/p95, shared-success counts, common-success means across
all cases in each cohort, and all-episode penalized differences.

The diagnostic subclass calls the original controller and returns its exact
command. It reads current optimized progress speed and attitude command after
successful solves, and times the whole parent computation plus diagnostic reads,
including geometry replanning. It records p99/max, >20 ms ticks and replan calls.
Eligibility requires **every episode's p99 <=20 ms** and **aggregate >20 ms tick
fraction <=1%**. Existing probe p50/p95 also time the outer controller call.
These measures exclude initialization, environment stepping and callbacks;
they do not certify a complete 20 ms control-loop deadline. Constructor and
solver-generation time are instead included in episode wall-time throughput.

Process isolation and recovery:

The real preflight found acados shared-library caching across different optimizer
configurations. Even serial execution in one Python process can retain old solver
dimensions. Therefore each configuration runs in a **fresh subprocess**, serially
under the same existing acados generation lock. It reuses its environment within
that one configuration and creates a fresh controller for each episode. The parent
atomically checkpoints a result before acknowledging the next worker episode.
Native/compiler/solver chatter goes to the cohort diagnostic log; a dedicated
pipe carries structured episode results. The unchanged shared probe episode loop
controls race semantics; no archived-baseline extra run or isolated tune reset occurs.

Fingerprints bind preparation and execution to full configuration, fixed plan,
controller/package/config/acados sources, new runner and auditor, runtime versions
and relevant environment variables. A mismatch refuses resume. Completed stages
are immutable. Infrastructure exceptions are separate from race/numerical outcomes;
interrupted/uncommitted episodes are retried only under the matching provenance.
A required source fix needs explicit new preparation or reviewed migration, never
silent mixing. Preserve earlier failed attempts and their manifests.

Budget:

Execution starts its clock only at `run`, with persistent absolute **9 h target**
and **10 h hard deadline**. Resuming does not reset either; downtime counts.
Forecasts use observed episode wall time, horizon scaling, historical 5.7 s/episode
floor at horizon 40, and 35% exploration margin. Worker startup is additional
fixed overhead; observed configuration wall time is saved for reviewing forecasts.
Reserve 15 minutes for audits/reporting, the minimum final 300-seed pair, and a
150-seed confirmation pair before optional work. Optional stages accept only a
prefix that fits, or are skipped explicitly. Screening stays complete or is not
started. Confirmation/validation require at least two configurations.

Spare target time increases the independent validation prefix up to 1,500 seeds
per case using measured throughput and 10% margin, rather than adding new tuning
branches. Its size never changes after outcomes are observed. Stop scheduling
at hard deadline minus the reporting reserve, finish the current episode and
report incomplete work honestly if necessary. Do not pad runtime with redundant
runs: 8–9 hours is an estimate, not a minimum. Realized failures and horizon choices
can shorten or lengthen the study.

Statistics and reporting:

The independent auditor recalculates counts, fixed settings, matching seeds,
means, penalties, latency eligibility, CSVs and source hashes. It saves every
incumbent comparison and regression episode. Exact paired completion tests use
SciPy binomial tests on discordant pairs. Completion-difference intervals subtract
Bonferroni simultaneous Clopper–Pearson rescue/regression bounds, giving
conservative >=95% coverage, including zero-discordance cases.

Final speed and penalized-time intervals use 10,000 paired-seed bootstrap
resamples with fixed RNG seed 20261102. Speed conditions on shared successful
seeds; the penalty interval uses all matched seeds. Screening is exploratory.
An observed completion tie/gain does not establish equivalence/noninferiority.
One course and finite cohorts do not establish an optimum or deployment readiness.

Preparation stops after focused tests, eight real smoke episodes and one action
equivalence replay. It saves a handoff with exact launch/resume/audit commands.
No defaults are changed and nothing is deployed.

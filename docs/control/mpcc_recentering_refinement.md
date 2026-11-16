Recommend retaining **`gate_center_snap = 0.00` with `over_gate_lift = 0.05` m**.
Keep **`observed_obstacle_clearance = None`** and **`controller.mpcc.obstacle_clearance = 0.26` m**.
Zero recentering had the highest completion count, **80/100**, in this six-value
refinement on fresh seeds 201–300. No higher recentering value improved completion.
The small paired speed improvements at 0.05–0.20 do not offset their lost finishes
under the completion-first objective.

This refines the [earlier combined-parameter study](mpcc_combination_study.md).
All earlier reports, source files and recommendations are preserved. Its 101–200
cohort is kept separate: comparing its completion percentage directly with this
201–300 cohort would confound parameter changes with seed selection.

| Recentring | Completion | Newly finished / regressed vs 0.00 | Mean paired time change vs 0.00, ms (shared finishes) | Mean successful race time, s |
| --- | ---: | ---: | ---: | ---: |
| 0.00 | 80/100 (80%) | reference | reference | 9.779000 |
| 0.05 | 79/100 (79%) | 0 / 1 | -5.063 (79) | 9.775190 |
| 0.10 | 78/100 (78%) | 1 / 3 | -5.714 (77) | 9.772821 |
| 0.15 | 76/100 (76%) | 1 / 5 | -5.067 (75) | 9.772632 |
| 0.20 | 77/100 (77%) | 2 / 5 | -2.400 (75) | 9.775065 |
| 0.25 | 76/100 (76%) | 2 / 6 | +0.811 (74) | 9.777632 |

Negative paired differences mean faster. Successful-run means in the last column
use different successful seed subsets and are retained for reporting consistency;
they are not direct speed comparisons. Individual race times have 20 ms resolution
at 50 Hz, while paired averages summarize many seeds.

The completion changes against zero recentering were:

- **0.05:** no rescues; regressed **277**. Its 79 shared finishes averaged 5.1 ms faster.
- **0.10:** rescued **278**; regressed **222, 224 and 277**. Its 77 shared finishes averaged 5.7 ms faster.
- **0.15:** rescued **278**; regressed **213, 218, 222, 224 and 277**. Its 75 shared finishes averaged 5.1 ms faster.
- **0.20:** rescued **278 and 296**; regressed **213, 218, 222, 224 and 277**. Its 75 shared finishes averaged 2.4 ms faster.
- **0.25:** rescued **278 and 296**; regressed **213, 218, 222, 224, 277 and 299**. Its 74 shared finishes averaged 0.8 ms slower.

The response is not strictly monotonic. Increasing 0.15 to 0.20 recovered seed 296
without losing a finish, but added 2.6 ms on their 76 shared successful seeds.
Increasing 0.20 to 0.25 lost seed 299 with no rescue and was also 2.6 ms slower on
76 shared successful seeds. Increasing 0.10 to 0.15 lost seeds 213 and 218 with no
rescue and was 0.5 ms slower on their 76 shared finishes. All fifteen pairwise
comparisons, including adjacent values, are retained in the linked analysis.

Across the entire sweep, **74 seeds finished with every value**, **18 finished with
none**, and **eight changed completion outcome**:

| Seed | 0.00 | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 |
| ---: | --- | --- | --- | --- | --- | --- |
| 213 | finish | finish | finish | fail | fail | fail |
| 218 | finish | finish | finish | fail | fail | fail |
| 222 | finish | finish | fail | fail | fail | fail |
| 224 | finish | finish | fail | fail | fail | fail |
| 277 | finish | fail | fail | fail | fail | fail |
| 278 | fail | fail | finish | finish | finish | finish |
| 296 | fail | fail | fail | fail | finish | finish |
| 299 | finish | finish | finish | finish | finish | fail |

Every regression against zero recentering terminated after **three gates**.
None had numerical-failure ticks. The experiment records the termination stage,
not a specific collision cause; a gate-frame or pole-collision explanation would
require additional instrumentation. Seeds 278 and 296 show that zero recentering
does not contain every other value's successful seed set, despite winning on total
completion count. No tested value completed the union of all 82 successful seeds.

The exact paired completion tests are exploratory. All fifteen unadjusted
p values were at least **0.21875**; the sample does not establish a definitive
population ranking. The recommendation retains the highest measured completion
count and avoids a parameter change with no observed net completion benefit.
There is no independent post-selection validation cohort, and these results do
not establish an optimum between grid points, outside 0–0.25, or on other courses.

Execution and validation:

- **600 real simulation episodes:** six recentering values `0.00, 0.05, 0.10, 0.15, 0.20, 0.25`, each on the identical ordered 100 fresh seeds 201–300.
- Height fixed at **0.05 m**, no observed-pole override, pole clearance **0.26 m**. All other controller, optimizer, physics and environment settings held at baseline. Full configurations and effective optimizer settings are saved for every case.
- A new controller per episode, serial execution, shared environment reset with each saved seed. No automatic archived-baseline episode or isolated-tuning reset was used. Controllers and existing runners were not modified.
- A timestamped directory, atomic JSON checkpoint after every episode, and simulator/compiler/solver output redirected to `simulation.log`. Race failures remain measured outcomes. **Zero episode infrastructure errors and zero numerical-failure ticks** occurred.
- The auditor checked ordered seeds, settings, source hashes, counts, rates, successful means, JSON/CSV agreement, every paired completion set, every per-seed paired time, medians and exact completion p values. The paired p values were cross-checked against SciPy's independent binomial-test implementation.
- Completed-run resume was executed and skipped all 600 episodes. Focused tests covered interrupted resume, settings/source mismatch rejection, freshness overlap rejection, CSV tampering, exact paired statistics, clean-process CLI startup and existing experimental geometry. **Nine tests and lint checks passed**.
- One CLI import-order issue was caught and fixed before any episodes started. It is recorded separately in `preflight.json`; it was never counted as a race failure.

Race time is completed environment steps divided by `env.freq`, stopping on the
completion callback. Pairwise differences are candidate minus reference on shared
successful seeds. Controller p50/p95 fields measure wall-clock `compute_control`
calls, excluding initialization, environment stepping and callbacks; those fields
are not used as race-speed comparisons. The construction seed is 201, and each
episode explicitly resets the environment with its own saved seed.

Results:

- [Complete execution report and source manifest](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/report.json)
- [All fifteen paired comparisons](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/analysis.md)
- [Structured audit and regression episode details](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/analysis.json)
- [Structured recommendation](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/recommendation.json)
- [Summary CSV](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/summary.csv)
- [Comparison CSV](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/comparisons.csv)
- [600 individual episode records](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/episodes.csv)
- [100-seed sensitivity matrix](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/seed_sensitivity.csv)
- [Simulator/compiler/solver log](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/simulation.log)
- [Preflight checks and resolved startup issue](../../logs/mpcc-tuning/recentering-20261102T181158356104Z/preflight.json)

Run the fixed study from the repository root:

```sh
pixi run python -m scripts.refine_mpcc_recentering
```

Resume this study without mixing changed code, settings, runtime or seeds:

```sh
pixi run python -m scripts.refine_mpcc_recentering --resume \
  --output-dir logs/mpcc-tuning/recentering-20261102T181158356104Z
```

Rebuild the audit without running episodes:

```sh
pixi run python -m scripts.refine_mpcc_recentering --audit-only \
  --output-dir logs/mpcc-tuning/recentering-20261102T181158356104Z
```

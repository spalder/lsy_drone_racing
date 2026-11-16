# Overnight MPCC tuning results

Retain the incumbent. The frozen challenger was faster on shared successful seeds but completed fewer independent validation races, failing the prespecified observed-completion requirement. No production defaults or controller code were changed.

Execution used the prepared runner and original preparation `overnight-prep-20261102T212955383826Z`. It ran from 2026-11-02T22:02:36.077644+00:00 to 2026-11-03T06:29:24.594116+00:00: 8.447 hours, within the 8–9 hour target and ten-hour maximum. All six stages completed without skips: **5,280 episodes**.

| Stage | Configurations | Matched seeds | Episodes |
| --- | ---: | ---: | ---: |
| Screening | 23 | 40 | 920 |
| Refinement | 13 | 60 | 780 |
| Combinations | 12 | 80 | 960 |
| Challenges | 9 | 80 | 720 |
| Confirmation | 3 | 150 | 450 |
| Independent validation | 2 | 725 | 1,450 |

Screening was exploratory: higher reference speeds reduced successful lap times but lost finishes. Refinement and combinations led to reduced attitude smoothing. Challenges evaluated nine configurations; the progress-cap branch was skipped under the saved saturation rule. Confirmation produced no eligible distinct challenger: incumbent 117/150, faster finalist 114/150, and selected comparison challenger 115/150. The deterministic fallback therefore selected `opt_a758e8cb3e87` for comparison, without endorsing replacement.

The frozen challenger changes only `attitude_rate_weight` from 0.1 to 0.05 and `attitude_slew_weight` from 0.02 to 0.005. The validation prefix of 725 seeds (12412–13136) was frozen before any holdout outcomes; the unused reserved suffix remains reserved. No tuning followed validation.

| Independent validation | Incumbent | Challenger |
| --- | ---: | ---: |
| Finishes | 557/725 (76.83%) | 543/725 (74.90%) |
| Successful mean (different subsets), s | 9.76309 | 9.62998 |
| All-episode mean with 30 s failure score, s | 14.45247 | 14.74356 |
| Numerical failure ticks | 0 | 0 |
| Maximum episode p99 controller latency, ms | 8.414 | 8.448 |
| Calls exceeding 20 ms | 0 | 0 |

Across 536 shared successful seeds, challenger-minus-incumbent mean time was −0.133806 s (about 1.37% faster); paired bootstrap 95% interval [−0.135597, −0.131978] s. Median difference was −0.140 s, p90 −0.100 s, and p95 −0.100 s. This meets the speed rule but fails observed completion preservation: 21 regressions versus 7 rescues, a −1.93 percentage-point completion difference. The exact paired completion p-value was 0.01254; the conservative simultaneous Clopper–Pearson difference interval was [−4.287, +0.466] percentage points. These use different inferential constructions and need not agree on exclusion of zero.

The all-seed penalized difference was **+0.291090 s**, bootstrap 95% interval [+0.011281, +0.574601] s, favoring the incumbent. Both bootstrap intervals used 10,000 paired resamples and RNG seed 20261102. Successful-only speed is conditional on both configurations finishing and does not account for failures.

Startup verified the saved full source/runtime/config/plan fingerprint, preparation artifact and documentation hashes, smoke audit, action-equivalence replay and completed-resume proof. The prescribed 15 focused tests and lint passed again. The fingerprint still matched after execution. The final independent audit passed all six stages, checking settings, matching seeds, arithmetic, exports, provenance and frozen decisions. There were no study infrastructure errors. Five numerical-failure ticks occurred in the exploratory angle challenger `opt_1d32ceafca44`; none occurred in confirmation or holdout. All reported configurations passed the latency rule; controller timing excludes initialization, stepping and callbacks and does not certify a complete control-loop deadline.

Geometry remained `gate_center_snap=0.0`, `over_gate_lift=0.05`, `observed_obstacle_clearance=None`, and `obstacle_clearance=0.26`. Controller algorithms/defaults, track, physics, randomizations, sensor range and control frequency were unchanged. No harness fixes, migrations or measured-episode resumes were needed. Existing work and historical reports were preserved.

Monitoring polled the runner every 55 seconds through normal exit and captured stage summaries and audits. An auxiliary progress counter used unavailable bare `python` and repeatedly failed; this affected progress display only. The prepared runner used Pixi Python throughout and completed normally. This execution-side monitoring defect is recorded explicitly in the validation record.

One course and finite cohorts do not establish an optimum, reliability equivalence, or deployment readiness. This was simulation testing only.

Artifacts: [study and frozen decisions](../../logs/mpcc-tuning/overnight-20261102T212955383826Z/study.json), [independent recommendation](../../logs/mpcc-tuning/overnight-20261102T212955383826Z/recommendation.json), [complete analysis](../../logs/mpcc-tuning/overnight-20261102T212955383826Z/analysis.md), [combined summaries](../../logs/mpcc-tuning/overnight-20261102T212955383826Z/summary.csv), and [execution validation record](../../logs/mpcc-tuning/overnight-20261102T212955383826Z/execution-validation.json). Each stage also retains report, independent audit, episode/settings CSVs and simulation log.

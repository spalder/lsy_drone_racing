# Autonomous MPCC tuning — stopped after batch 004

User requested completing the active test set and stopping. Batch 004 completed and passed audit; no batch 005 was created or launched. All worker processes exited normally.

**700 episodes across four matched, fresh-seed batches**. About 62.4 minutes of batch execution, plus orchestration, testing and reporting. No tuning/validation cohorts were pooled. All configuration settings and seeds were frozen before measurement.

## Stages

| Batch | Purpose | Cases × seeds | Main outcome |
| --- | --- | --- | --- |
| 001 | Full angle × contour × horizon factorial | 8 × 20 | Reference 13/20; angle 0.70 + contour 600 reached 15/20 at +0.0215 s paired time. Horizon 50 added lap time without further finishes at the leading combination. |
| 002 | Independent validation of angle-only and angle+contour | 3 × 50 | Original reference 22/50; angle-only 24/50; angle+contour 27/50. Combination rescued five with no regressions and +0.0218 s on 22 shared finishes. Provisionally adopted as reference under frozen robustness rule. |
| 003 | Speed × recentering × lift factorial | 12 × 20 | Reference 8/20; recentering 0.50 at speed 2.2 reached 10/20; speed 2.3 with recentering 0.50 reached 9/20. Lift 0.20 added time without more finishes for recentering 0.50. |
| 004 | Independent validation of recentering and faster speed | 3 × 50 | Recentring 0.50 at 2.2 reached 29/50, versus reference 27/50; speed 2.3 reached 27/50 with faster laps. |

Full batch tables include successful means, paired/shared counts, rescue/regression seeds, penalties, numerical ticks, p99 latency and overruns: [001](../../logs/mpcc-tuning/autonomous-20261103/batch001/report.md), [002](../../logs/mpcc-tuning/autonomous-20261103/batch002/report.md), [003](../../logs/mpcc-tuning/autonomous-20261103/batch003/report.md), [004](../../logs/mpcc-tuning/autonomous-20261103/batch004/report.md).

## Final independent cohort — speed/robustness shortlist

All three use max_angle=0.70, contour_weight=600, horizon_steps=40, over_gate_lift=0.15, obstacle_clearance=0.26, observed_obstacle_clearance=None, attitude_slew_weight=0.02. All other optimizer settings retain the original values. Only speed and recentering differ in this final comparison.

| Setting (reference/max speed; recenter) | Finishes | Successful mean, s | Paired Δ vs batch-004 reference (shared n), s | Rescues / regressions | Penalized mean, s | Completion exact 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| 2.2/2.5; 0.25 | 27/50 (54%) | 6.0637 | +0.0000 (27) | 0 / 0 | 17.0744 | 39.3%–68.2% |
| 2.2/2.5; 0.5 | 29/50 (58%) | 6.0628 | +0.0008 (25) | 4 / 2 | 16.1164 | 43.2%–71.8% |
| 2.3/2.6; 0.5 | 27/50 (54%) | 5.8311 | -0.2280 (25) | 2 / 2 | 16.9488 | 39.3%–68.2% |

**Robustness option:** reference_speed=2.2, max_speed=2.5, recentering=0.50. It rescued four and regressed two compared with recentering 0.25. Paired time change +0.0008 s, bootstrap 95% interval [−0.0032, +0.0048] s; 25 shared finishes. Its finish improvement is uncertain: exact paired p=0.6875 and conservative paired completion-difference interval [−13.5, +20.6] percentage points. Its all-episode penalized change was −0.958 s, bootstrap interval [−3.3548, +1.4384] s.

**Speed option:** reference_speed=2.3, max_speed=2.6, recentering=0.50. Against the batch-004 reference it tied finishes at 27/50, rescuing two and regressing two, while gaining 0.228 s (about 3.8%) on 25 shared finishes; paired bootstrap interval [−0.2336, −0.2224] s. Against the robustness option it lost two net finishes (27 vs 29) while gaining 0.2269 s on 26 shared finishes. Its penalized mean is 0.8324 s worse than that robustness option, because failures cost 30 s. Keep both as observed Pareto alternatives.

No independent validation reached the 65% completion aim. The final observed 54% and 58% exceed 50%, but their exact intervals cross 50%; neither establishes population reliability above 50%. The screening 70–75% results did not persist on harder independent cohorts. The original configuration had 13/20 in batch001 and 22/50 in batch002; the promoted combination had 8/20 in batch003 and 27/50 in batch004. This cohort variation is why comparisons remain paired within each batch and are not pooled.

Successful means condition on each configuration finishing and use different subsets. Paired comparisons use only common successful seeds, and bootstrap speed intervals are conditional on those successes. Independent validation uses exact completion intervals, paired binomial tests and 10,000 paired-seed bootstrap resamples, RNG seed 20261102. Tests are exploratory/unadjusted; small gains do not establish certainty.

## Validation and artifacts

Across 700 episodes: **0 numerical-failure ticks**, **4 >20 ms calls** over 168154 controller ticks (aggregate fraction 0.002379%), maximum episode p99 **9.484 ms**. Every configuration in all four batches passed the <=20 ms episode p99 / <=1% aggregate-overrun criteria. Zero infrastructure errors occurred. Controller-call timing excludes initialization, stepping and callbacks; individual long calls can occur while the p99 criterion passes.

Each completed batch was independently re-read and audited for effective/full settings, unchanged environment, ordered matched seeds, outcomes, gate/time semantics, successful averages, fixed penalties, numerical counts, latency arithmetic, source/runtime and driver hashes. Five configuration-boundary tests and lint passed before execution. Every configuration ran in a fresh subprocess under the shared lock, and every episode was atomically committed before worker acknowledgement. Fresh seeds excluded all prior used/reserved reports and plans. Driver code did not change during measured episodes.

Persistent state and exact full shortlist configs: [state.json](../../logs/mpcc-tuning/autonomous-20261103/state.json). Decision journal: [journal.md](../../logs/mpcc-tuning/autonomous-20261103/journal.md). Each batch preserves request, plan/provenance, report, independent audit, all constituent comparisons, summary/episode/comparison CSVs, and native simulation log. The final user stop request is recorded in the journal. All historical artifacts and existing work were preserved.

No controller algorithms, track, physics, randomizations, sensor range or control frequency changed. No production defaults were changed and nothing was deployed. The current shortlist is for future simulation work only.

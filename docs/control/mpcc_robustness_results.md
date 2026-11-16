# MPCC one-factor robustness study

**Exploratory: 20 fresh matched seeds per configuration; no combinations.**
220 episodes completed in 19.72 minutes from runner startup through simulation; seeds 14813–14832.
Fixed speed 2.2/2.5, recentering 0.25, obstacle clearance 0.26, observed override None. Baseline lift 0.15; every variant changes exactly one requested parameter.
Successful means use each configuration's own successful subset; paired differences condition on shared finishes. Negative differences mean faster. Do not pool these means.
Every unsuccessful race receives a fixed 30 s score. Numerical failures and latency are separate from completion; infrastructure errors are never converted into races.

## contour_weight

| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 400 | 7/20 (35%) | 6.0543 | +0.0000 (7) | [] | [] | 0 | 8.554 | True | 21.6190 |
| 600 | 8/20 (40%) | 6.1225 | +0.0600 (7) | [14821] | [] | 0 | 8.461 | True | 20.4490 |
| 800 | 8/20 (40%) | 6.1625 | +0.1000 (6) | [14816, 14821] | [14818] | 0 | 8.467 | True | 20.4650 |

Most promising eligible value: **600**. Improved **completion** relative to baseline; finish-count change +1/20. Selection prioritizes more finishes then smaller paired time cost.
Tradeoff/uncertainty: paired-speed bootstrap 95% interval [0.051428571428571344, 0.0685714285714285]; only 7 shared finishes. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.

## horizon_steps

| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 40 | 7/20 (35%) | 6.0543 | +0.0000 (7) | [] | [] | 0 | 8.554 | True | 21.6190 |
| 50 | 8/20 (40%) | 6.1350 | +0.0767 (6) | [14817, 14831] | [14823] | 0 | 9.024 | True | 20.4540 |
| 60 | 7/20 (35%) | 6.2743 | +0.2233 (6) | [14817] | [14823] | 0 | 9.665 | True | 21.6960 |

Most promising eligible value: **50**. Improved **completion** relative to baseline; finish-count change +1/20. Selection prioritizes more finishes then smaller paired time cost.
Tradeoff/uncertainty: paired-speed bootstrap 95% interval [0.06666666666666643, 0.08666666666666689]; only 6 shared finishes. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.

## over_gate_lift

| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 4/20 (20%) | 6.0150 | -0.0150 (4) | [] | [14815, 14823, 14825] | 0 | 9.201 | True | 25.2030 |
| 0.15 | 7/20 (35%) | 6.0543 | +0.0000 (7) | [] | [] | 0 | 8.554 | True | 21.6190 |
| 0.2 | 7/20 (35%) | 6.0657 | +0.0114 (7) | [] | [] | 0 | 8.590 | True | 21.6230 |

Most promising eligible value: **0.15**. Improved **neither** relative to baseline; finish-count change +0/20. Selection prioritizes more finishes then smaller paired time cost.
Tradeoff/uncertainty: the selected value is the unchanged baseline; its [0, 0] self-comparison interval is an identity, not evidence of certainty about performance. Only seven baseline successes were observed. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.

## attitude_slew_weight

| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.01 | 7/20 (35%) | 6.0629 | +0.0086 (7) | [] | [] | 7 | 8.402 | True | 21.6220 |
| 0.02 | 7/20 (35%) | 6.0543 | +0.0000 (7) | [] | [] | 0 | 8.554 | True | 21.6190 |
| 0.04 | 6/20 (30%) | 6.0800 | +0.0233 (6) | [] | [14825] | 0 | 9.038 | True | 22.8240 |

Most promising eligible value: **0.02**. Improved **neither** relative to baseline; finish-count change +0/20. Selection prioritizes more finishes then smaller paired time cost.
Tradeoff/uncertainty: the selected value is the unchanged baseline; its [0, 0] self-comparison interval is an identity, not evidence of certainty about performance. Only seven baseline successes were observed. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.

## max_angle

| Value | Finishes | Successful mean, s | Paired Δ, s (shared n) | Rescued seeds | Regressed seeds | Numerical ticks | Max episode p99, ms | Latency eligible | 30 s penalized mean, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.6 | 7/20 (35%) | 6.0543 | +0.0000 (7) | [] | [] | 0 | 8.554 | True | 21.6190 |
| 0.65 | 7/20 (35%) | 6.0314 | -0.0229 (7) | [] | [] | 0 | 9.625 | True | 21.6110 |
| 0.7 | 8/20 (40%) | 6.0075 | -0.0429 (7) | [14827] | [] | 0 | 8.492 | True | 20.4030 |

Most promising eligible value: **0.7**. Improved **both** relative to baseline; finish-count change +1/20. Selection prioritizes more finishes then smaller paired time cost.
Tradeoff/uncertainty: paired-speed bootstrap 95% interval [-0.04857142857142881, -0.040000000000000036]; only 7 shared finishes. Small count differences are exploratory; successful subsets differ. No statistical certainty or independent holdout confirmation is claimed.

## Recommendation for later work

The nominated values above are candidates for a later combination study only. Interactions are untested; no combinations were executed, no defaults changed, and nothing deployed.
Bootstrap intervals use 10,000 paired-seed resamples with RNG seed 20261102. Completion tests in comparisons.json are exploratory and unadjusted. Whole-call controller timing excludes initialization, environment stepping and callbacks.
Data: plan.json contains frozen exact configs, cohort and provenance; report.json contains committed episodes; summary.csv, episodes.csv and comparisons.json/csv contain the comparison evidence. simulation.log retains native diagnostics. audit.json records validation.

## Practical interpretation and next combination candidates

This cohort was difficult: baseline 7/20 (35%) and best variants 8/20 (40%). **No tested configuration exceeded the earlier 50% finish-rate objective on this cohort.** The earlier 31/50 result is separate evidence; it is not pooled here. No variant establishes reliable improvement from one additional finish.

- **Contour weight: prefer 600 for later testing.** Completion improved by one finish without losing a baseline success, at a paired +0.060 s cost (about 1%). Weight 800 tied the count but had a larger +0.100 s cost and swapped one baseline success for two rescues. The single extra finish is weak evidence.
- **Horizon: 50 is the promising alternative.** It gained one net finish, rescuing two while losing one, at +0.0767 s on six shared successes (about 1.3%). Horizon 60 provided no net completion improvement and cost +0.2233 s. Longer-horizon latency remained eligible, but its extra compute and lap-time cost make it lower priority.
- **Lift: retain 0.15 m.** Neither tested alternative improved completion over baseline. Lift 0.10 lost three finishes for a small conditional speed gain; 0.20 finished the same seven seeds and was slightly slower. The unchanged baseline is preferred, rather than claiming a new improvement.
- **Attitude slew: retain 0.02.** Neither alternative improved completion or speed on shared finishes. Weight 0.01 introduced seven failed-solve ticks, despite passing latency and tying the finish count. Weight 0.04 lost a finish and was slower. Numerical and timing eligibility are separate observations.
- **Max angle: 0.70 is the strongest candidate.** It rescued one failure with no regressions and gained 0.0429 s on seven shared successes (about 0.7%). Angle 0.65 improved speed slightly without changing finishes. These are small conditional gains; a larger independent cohort is needed.

For a later combination study, first prioritize **max_angle=0.70**, then test whether adding **contour_weight=600** retains the rescue gains at acceptable speed cost. Treat **horizon_steps=50** as a separate additional branch because it exchanges successes and has a larger time cost. Keep lift 0.15 and slew 0.02 as reference settings. These suggestions are untested combinations, not measured combined improvements.

Independent validation passed for all 220 episodes and original source hashes. Zero infrastructure errors occurred. All 11 configurations passed the <=20 ms maximum episode p99 / <=1% aggregate overrun criteria; all measured overrun fractions were zero. Maximum p99 across configurations was 9.665 ms. The seven failed-solve ticks occurred only at slew 0.01. The shared simulation harness, algorithms, course, randomizations, sensors and frequency remained unchanged.

Artifacts: [frozen exact configs, seed inventory and provenance](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/plan.json), [complete episodes](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/report.json), [paired comparisons](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/comparisons.json), [episode CSV](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/episodes.csv), [summary CSV](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/summary.csv), [independent audit](../../logs/mpcc-tuning/robustness-2p2-onefactor-20261103/audit.json). Exact settings were frozen before the first episode; a fresh subprocess was used for every configuration. Historical artifacts were preserved. No combinations, production-default changes or deployment were performed.

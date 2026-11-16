# Larger independent validation: recentering 0.75, contour 600/800

**Recommend recentering 0.75 with contour weight 800 as the provisional robustness candidate.** It finished 70/100 versus baseline 63/100 at about 0.86% paired lap-time cost. Recentring 0.75 with contour 600 remains the lower-time-cost alternative at 67/100. The difference between the two candidates is uncertain. No production defaults changed.

## Design and provenance

Exactly three configurations on the same **100 fresh ordered seeds (15592–15691)**: baseline snap0.50/contour600, snap0.75/contour600 and snap0.75/contour800. This cohort was frozen before any outcomes and is independent of the prior 25-seed screening cohort. No historical measurements were pooled. Original used/reserved seeds were checked recursively. All cases retained reference_speed=2.3, max_speed=2.6, max_angle=0.70, horizon_steps=40, over_gate_lift=0.15, obstacle_clearance=0.26, observed_obstacle_clearance=None; all remaining settings were copied exactly from the recorded speed option.

The startup provenance gate refused execution because the Linux kernel changed from 7.0.0-38-generic to 7.0.0-42-generic. The mismatch was platform-only: controller/package/config/acados/runner sources, full plan and package versions were unchanged. Zero episodes had run. A separate preparation manifest and explicit platform-migration wrapper were created; all original preparation and runners were preserved. Fifteen relevant tests and wrapper lint passed before execution. The new platform applies equally to all three current configurations. Latency comparisons across historical platforms should not be treated as identical runtime conditions.

The batch completed **300 episodes in 26.27 minutes** of execution, plus startup migration/preflight and reporting. Conservative forecast: 33 minutes execution within a 38-minute budget. Every configuration used an isolated fresh solver subprocess; checkpoints were committed before acknowledging another episode.

## Matched-cohort results

Paired Δ is candidate minus baseline on shared successful seeds; percent cost uses the same baseline shared subset. Successful means condition on each configuration finishing and use different subsets. Every unsuccessful race receives a fixed 30 s score.

| Snap / contour | Finishes | Exact completion 95% CI | Successful mean, s | Paired Δ / cost (shared n) | Rescued seeds | Regressed seeds | Penalized mean, s | Numerical ticks | Max episode p99, ms | >20 ms fraction | Latency eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.5 / 600 | 63/100 (63%) | 52.8%–72.4% | 5.84571 | +0.00000 s / +0.00% (63) | [] | [] | 14.7828 | 0 | 9.623 | 0.000000% | True |
| 0.75 / 600 | 67/100 (67%) | 56.9%–76.1% | 5.84955 | +0.00323 s / +0.06% (62) | [15592, 15613, 15656, 15672, 15673] | [15679] | 13.8192 | 0 | 9.608 | 0.000000% | True |
| 0.75 / 800 | 70/100 (70%) | 60.0%–78.8% | 5.89943 | +0.05000 s / +0.86% (62) | [15592, 15600, 15602, 15613, 15656, 15672, 15673, 15674] | [15676] | 13.1296 | 0 | 9.084 | 0.000000% | True |

All measured paired lap-time costs are within the preferred ~2% ceiling. Both candidates exceeded 65% completion in this sample; their exact intervals include rates below 65%, so neither establishes population completion >=65%.

## Candidate assessments

- **Snap0.75 / contour600:** five rescues and one regression, a net +4 finishes versus baseline; +0.00323 s on 62 shared finishes (about 0.06%). Paired time bootstrap 95% interval [approximately 0, +0.00645] s. Penalized mean improved by 0.9636 s; bootstrap interval [−2.1712, +0.0042] s. Exact paired completion p=0.21875, with conservative difference interval [−4.84, +12.26] percentage points. Its apparent improvement remains uncertain.
- **Snap0.75 / contour800:** eight rescues and one regression, a net +7 finishes versus baseline; +0.0500 s on 62 shared finishes (about 0.86%). Paired time bootstrap interval [+0.04645, +0.05355] s. Penalized mean improved by 1.6532 s, bootstrap interval [−3.1012, −0.4432] s. Exact paired completion p=0.03906, unadjusted; the conservative difference interval [−3.12, +16.24] percentage points includes zero. The exact test would not pass a Bonferroni 0.025 threshold for two baseline comparisons. This is useful observed evidence, not a certainty claim.

## Direct comparison and recommendation

Against snap0.75/contour600, contour800 rescued seeds **15600, 15602, 15674, 15679** and regressed **15676**. It gained three net finishes and added **0.04636 s** on **66 shared finishes**. The paired completion p-value is 0.375; the conservative completion-difference interval is [−5.32, +10.86] percentage points. Its 30 s penalized mean was 0.6896 s lower. The extra three finishes are insufficient to establish that contour800 is more reliable than600.

The direct paired-time bootstrap 95% interval is [0.04333333333333335, 0.049393939393939434] s; the penalized-mean interval is [-1.8923999999999999, 0.27739999999999987] s.

The prior screen tied these candidates at18/25 and favored contour600 on speed. This larger independent cohort instead gives contour800 the higher observed completion. Selection after small samples can be unstable; the two cohorts remain separate. The best observed robustness/time tradeoff here is **0.75/800**, while **0.75/600** retains almost baseline lap time. A reference change in simulation is provisional; this task did not alter defaults or deploy either candidate.

## Audit and saved evidence

Final re-audit passed for full/effective configs, ordered matched seeds, outcome/gate/time semantics, summary arithmetic, unsuccessful-race penalties, numerical ticks, p99/overrun eligibility and source/runtime/driver fingerprints. All three cases had zero numerical-failure ticks, zero >20 ms controller calls and passing latency eligibility (every episode p99 <=20 ms; aggregate overrun <=1%). No infrastructure errors occurred during measured execution. Controller-call timings exclude initialization, stepping and callbacks. The earlier fingerprint refusal is recorded as a startup/provenance event, not a failed race.

Completion intervals are exact Clopper–Pearson; paired completion tests are exact discordant-pair binomial tests; paired completion-difference bounds use the conservative simultaneous construction in the existing auditor. Time intervals use 10,000 paired-seed bootstrap resamples with RNG seed20261102. Speed intervals condition on shared successful seeds. Tests are unadjusted unless explicitly noted above.

Artifacts: [frozen request](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/migrated-request.json), [exact configs, seed order and provenance](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/plan.json), [episode data](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/report.json), [independent audit and comparisons](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/audit.json), [direct candidate comparison with intervals](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/candidate-direct-comparison.json), [episode CSV](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/episodes.csv), [summary CSV](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/batch/summary.csv), [startup resolution](../../logs/mpcc-tuning/speed-snap-contour-validation-20261103/startup-resolution.json), [platform-only migration](../../logs/mpcc-tuning/platform-prep-kernel42-20261103/migration.json).

All historical artifacts, algorithms, track, physics, randomizations, sensor range and control frequency were preserved. No further tuning was run after this independent comparison.

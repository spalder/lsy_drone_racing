Recommend **recentring 0.000 with 5 cm extra height** based on the independent validation comparison.
Keep no observed-pole override and global pole clearance 0.26 m; all optimizer, physics and environment settings remain at baseline. Controller defaults were not modified.

The [prespecified plan](mpcc_local_tuning_plan.md) was completed: **1,000 serial simulation episodes in 94.6 minutes** (including the audit and selection transition between cohorts). The prior 600-episode study predicted about 95 minutes. Existing studies and controller sources are preserved.

Screening used identical ordered fresh seeds **301–400** for six local configurations. Challenger selection ranked completion first, paired successful time second, then grid distance and name. Selection was frozen before validation started.

| Recentring | Extra height | Screening completion | Rescues / regressions vs current best | Paired time Δ vs current best, ms (shared finishes) | Mean successful time, s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.000 | 3 cm | 73/100 | 0 / 1 | +1.644 (73) | 9.766301 |
| 0.000 | 5 cm | 74/100 | 0 / 0 | +0.000 (74) | 9.764865 |
| 0.000 | 7 cm | 76/100 | 2 / 0 | +0.270 (74) | 9.769211 |
| 0.025 | 3 cm | 75/100 | 2 / 1 | +2.192 (73) | 9.765867 |
| 0.025 | 5 cm | 76/100 | 2 / 0 | +1.081 (74) | 9.765000 |
| 0.025 | 7 cm | 77/100 | 3 / 0 | +1.081 (74) | 9.769610 |

The screening gains overlap: increasing height to 7 cm at zero recentering rescued seeds **341 and 366**, while recentering 0.025 at 5 cm rescued **341 and 349**. Their combination rescued the union **341, 349 and 366**, with no additional rescue beyond that union. Seed 341 is shared, so the two isolated gains cannot be added. Both 3 cm cases lost seed **377** relative to their 5 cm counterpart.

The selected challenger was **snap_0.025_height_0.07**, with 77/100 screening finishes. The holdout compared that frozen challenger with the incumbent on **200 untouched seeds, 401–600**, giving 400 more episodes. Screening counts are not pooled with validation to justify selection.

| Configuration | Independent validation completion | Mean successful race time, s | Numerical failure ticks |
| --- | ---: | ---: | ---: |
| snap_0.000_height_0.05 | 151/200 (75.5%) | 9.778013 | 0 |
| snap_0.025_height_0.07 | 151/200 (75.5%) | 9.773907 | 0 |

Against the incumbent, the challenger newly finished **[450, 472]** and regressed **[437, 568]**. The net completion change was **+0.0 percentage points**. The approximate paired normal 95% interval is **[-1.96, +1.96] percentage points**; the exact two-sided paired completion p value is **1**.

On **149 shared successful seeds**, mean challenger-minus-incumbent race time was **-0.134 ms** and median was **+0.000 ms**. There were 24 faster, 28 slower and 97 unchanged shared finishes. Successful-run averages over different seed subsets are retained above but do not provide a direct speed comparison.

Validation regression and rescue episodes were inspected:

| Change | Seed | Incumbent outcome / gates / time, s | Challenger outcome / gates / time, s |
| --- | ---: | --- | --- |
| regressions | 437 | success / 5 / 9.74 | terminated / 3 / 7.40 |
| regressions | 568 | success / 5 / 10.08 | terminated / 3 / 7.66 |
| rescues | 450 | terminated / 3 / 7.26 | success / 5 / 9.66 |
| rescues | 472 | terminated / 3 / 7.24 | success / 5 / 9.56 |

These stages describe where termination occurred; they do not establish a specific collision cause.

The completion-first rule recommends **snap_0.000_height_0.05**. The screening gains did not justify replacing the incumbent under the independent validation rule.
The paired test gives p = 1.0 and the interval spans zero: there is no demonstrated completion benefit. The 0.13 ms paired speed difference is negligible. Retain the incumbent because the challenger trades two finishes for two losses without improving total completion. This does not establish equivalence or an optimum.

All **1000 episodes** completed, with **0 numerical-failure ticks** and **0 infrastructure errors**. Each episode used a fresh controller and a seeded environment reset. Execution was serial because acados generation shares files. Python/native simulator, compiler and solver chatter was captured in per-cohort simulation logs.

Completed-run resume was executed and preserved all 1,000 episode records without rerunning episodes. Atomic per-episode checkpoints and strict source/runtime/settings/seed manifests support resume. Independent audits checked ordered seeds, settings, optimizer invariance, source hashes, counts, rates, successful-time means, numerical ticks, JSON/CSV agreement, paired seed sets, every paired time and exact completion tests against SciPy. All fifteen screening comparisons and the single validation comparison are saved. Ten focused tests and lint passed before execution; tests include infrastructure interruption/resume, mismatch rejection, output capture, freshness, statistics, cold CLI startup, selection integrity and holdout regressions.

Race time is completed environment steps divided by 50 Hz through the completion callback, with 20 ms resolution per episode. Paired differences use shared successful seeds only; controller wall-clock timing fields are not race speed. The screening construction seed is 301 and validation construction seed is 401; each actual episode explicitly resets its own saved seed.

Limitations: one nominal course, two local geometry parameters, six tested grid points, and 200 independent validation seeds. Screening comparisons are exploratory and unadjusted. The paired completion interval uses a normal approximation. The study does not establish an optimum between grid points, generalization to other courses, or deployment readiness. No additional search followed holdout inspection.

Artifacts:

- [Study index](../../logs/mpcc-tuning/local-20261102T192015449578Z/study_report.json)
- [Combined summary CSV](../../logs/mpcc-tuning/local-20261102T192015449578Z/summary.csv)
- [Screening report](../../logs/mpcc-tuning/local-20261102T192015449578Z/screening/report.json)
- [Screening comparisons](../../logs/mpcc-tuning/local-20261102T192015449578Z/screening/analysis.md)
- [Frozen selection](../../logs/mpcc-tuning/local-20261102T192015449578Z/selection.json)
- [Validation report](../../logs/mpcc-tuning/local-20261102T192015449578Z/validation/report.json)
- [Validation comparisons and seed sets](../../logs/mpcc-tuning/local-20261102T192015449578Z/validation/analysis.md)
- [Validation audit and regression records](../../logs/mpcc-tuning/local-20261102T192015449578Z/validation/analysis.json)
- [Structured recommendation](../../logs/mpcc-tuning/local-20261102T192015449578Z/recommendation.json)
- [Seed freshness evidence](../../logs/mpcc-tuning/local-20261102T192015449578Z/freshness.json)
- [Completed-run resume proof](../../logs/mpcc-tuning/local-20261102T192015449578Z/resume-check.json)
- [Preflight checks](../../logs/mpcc-tuning/local-20261102T192015449578Z/preflight.json)

Reproduce or resume from the repository root:

```sh
pixi run python -m scripts.local_mpcc_study
pixi run python -m scripts.local_mpcc_study --resume \
  --output-dir logs/mpcc-tuning/local-20261102T192015449578Z
pixi run python -m scripts.local_mpcc_study --audit-only \
  --output-dir logs/mpcc-tuning/local-20261102T192015449578Z
```

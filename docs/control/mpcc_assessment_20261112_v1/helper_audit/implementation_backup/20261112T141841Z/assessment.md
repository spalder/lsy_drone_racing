# Reproducible assessment of retained MPCC tests — 2026-11-12

Assessed **596 configuration/cohort records** and **420 distinct configuration/environment identities** (382 resolved; 38 explicitly unresolved). **95 resolved configurations** have primary n ≥10 and observed completion ≥70%; **11** also have a two-sided exact 95% interval lower endpoint strictly above 70%. Including unresolved identities, 107 records meet the observed count/rate threshold. No 9-second cutoff is applied.

This is an assessment of retained evidence, not a new experiment. Completion/uncertainty refer to each original seed cohort, not a guarantee for a competition distribution. No simulations, tuning, controller/config edits, dependency installation or Git publication were performed.

## Reusable data and regeneration

[Configuration metrics](configuration_metrics.csv), [cohort metrics](cohort_metrics.csv), [paired comparisons](paired_comparisons.csv), [all validation changes](validation_comparisons.csv), [data dictionary](data_dictionary.md), [manual complexity registry](complexity_assessments.json), [checks](checks.json), [source inventory and exclusions](source_inventory.json). Full normalized input evidence is in [cohort_evidence.jsonl.gz](cohort_evidence.jsonl.gz).

From `/home/askho/repos/lsy_drone_racing`:

```bash
.pixi/envs/default/bin/python docs/control/mpcc_assessment_20261112_v1/analyze.py
# Optional original-artifact rescan (USB must be mounted):
python3 docs/control/mpcc_assessment_20261112_v1/discover.py
.pixi/envs/default/bin/python docs/control/mpcc_assessment_20261112_v1/analyze.py
```

The first command regenerates the CSVs, checks and this Markdown from the evidence snapshot. The discovery command reads original sources and refreshes that snapshot. Both are read-only outside this report directory.

## Source coverage and identity

Searched `logs`, retained `.local/mpcc-study` cohorts, plans/manifests, frozen controller sources, reports and detailed episode records in the main worktree; selected-controller evidence and evaluation CSV in the V3 worktree; retained `research/*.tar.zst`; and `/media/askho/Ask-USB/mpcc-study`. Earlier conversational CSV exports are not the source of truth. Generic documentation, solver build products and synthetic report fixtures are not treated as experiments.

The USB scan inspected **117 episode JSON files** without opening bulk horizon/warm-start/path arrays. Archive episode members were streamed without extracting large datasets. Exact USB/archive copies are recorded against their local originals in the exclusion inventory. There are **188 explicit copy/aggregate/fixture exclusions** and **0 source-discovery issues**. These counts are files/records, not additional independent tests.

Configuration identity hashes normalized complete recorded settings, the relevant pinned implementation source bundle, and environment config/source pins. Numeric `1` and `1.0` normalize identically; names never define identity. Missing implementation/environment information remains unresolved with a source-local scope, preventing unsupported merges. Source paths and hashes, full settings, implementation families/pins and environment metadata are retained in CSVs. Missing source dependencies and provisional family boundaries are limitations, not assumed equivalences.

Exact duplicate JSON cohorts, analysis-view copies and parent CSV aggregate exports are excluded. Genuine reruns retain separate cohorts even if outcomes are identical. The known 3+27 episode frozen bound-repair continuation is combined only after checking disjoint seeds; all other cohorts stay separate.

Primary selection happens **before performance filtering**: select the largest screening/independent-validation cohort for each configuration/environment; break equal-n ties by latest actual execution timestamp where available, otherwise the recorded result-file timestamp. A copied archive export time is not a new test. Smoke-only/diagnostic-only configurations remain in datasets but are ineligible for general reliability ranking. Full other-cohort history remains available.

## Metrics and ranking rule

- Completion is finishes/n. Both limits are **two-sided 95% exact binomial Clopper–Pearson** bounds, used throughout. Higher completion is preferable; the lower endpoint measures evidential caution, not an additional independent performance objective.
- Ranking race times use **completed control steps / frequency**. Recorded study/elapsed/completed-step values take priority; frozen 50 Hz driver semantics are identified explicitly when used. Original official means are retained separately: verified final zero-based official times are 0.02 s lower at 50 Hz. No blanket subtraction is applied.
- Mean and p90 race time condition on successful episodes; lower is preferable. P90 uses NumPy linear quantiles, h=(successful_n−1)×0.9. Estimates with fewer than 30 successes are provisional.
- Penalized mean assigns each failed race **30 s**. This is a chosen scoring convention, not observed failure duration. It is correlated with completion and is not a second robustness vote. Zero finishes gives 30 s.
- Numerical health is the percentage of episodes with any failed solve/fallback, taking their union. Separate solve/fallback episode counts and ticks are retained where present; absent fallback counters are labeled. Infrastructure exceptions are retained separately, not converted to race failures.
- Mean compute time weights every timed control step equally, across successes and failures. It uses whole `compute_control()` calls only, excluding construction and simulator stepping. A finite full-test mean requires complete per-call timings; missing/partial data yields literal `nan` in CSV and **N/A** here. Coverage and scope stay visible; missing timing does not disqualify a candidate.
- Controller p99 is calculated from pooled per-call samples only. If unavailable, a separately labeled maximum episode p99 is shown; it is never an average or claimed pooled p99. Calls >20 ms are reported at the measured 50 Hz period; other periods are retained explicitly. Research-instrumented and plain whole-call timings must not be interpreted as interchangeable.
- Complexity is a manually justified 0–4 relative scale, with source files and provisional flags in `complexity_assessments.json`. Parameter changes alone never raise the family score.

**Transparent lexicographic ordering:** among resolved configurations with primary n ≥10 and observed completion ≥70%, prefer (1) provenance-supported independent-validation evidence; (2) higher five-percentage-point bands of the exact lower confidence endpoint; (3) lower implementation complexity within a band; (4) larger primary n; then (5) faster mean successful time. Stable ID breaks exact ties. Completion, CI and penalized mean are not added into a weighted score. Health/runtime concerns are displayed and reviewed in recommendations, not hidden by this ordering.

## Ranked shortlist: observed completion ≥70%

The threshold label **observed ≥70%** is distinct from **95% lower endpoint >70%**. Screening-only results are explicitly labeled. IDs link the following tables and the CSVs.

| Rank / ID | Configuration | n | Finishes | Completion % | 95% lower % | 95% upper % | Evidence | Lower >70% |
|---|---|---|---|---|---|---|---|---|
| 1 / c76e14c8 | opt_a758e8cb3e87 | 725 | 543 | 74.9 | 71.6 | 78.0 | independent validation present | yes |
| 2 / aa3179ce | incumbent | 725 | 557 | 76.8 | 73.6 | 79.9 | independent validation present | yes |
| 3 / 26f37062 | snap_0.025_height_0.07 | 200 | 151 | 75.5 | 68.9 | 81.3 | independent validation present | no |
| 4 / 0db03072 | opt_1b995c29c9b2 | 150 | 114 | 76.0 | 68.4 | 82.6 | independent validation present | no |
| 5 / 6682535c | combined | 100 | 70 | 70.0 | 60.0 | 78.8 | independent validation present | no |
| 6 / 4aa6b53a | 7bd4beef8c15 | 50 | 37 | 74.0 | 59.7 | 85.4 | independent validation present | no |
| 7 / 2470aab0 | F1_2 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 8 / a460142e | F1 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 9 / 3742dfc4 | G07_pole_width_0p4375 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 10 / ef1845c7 | opt_f02e58da8c0d | 80 | 65 | 81.2 | 71.0 | 89.1 | screening only | yes |
| 11 / 7d3f7626 | opt_8c03fe3e18b8 | 80 | 65 | 81.2 | 71.0 | 89.1 | screening only | yes |
| 12 / eb8c8ee3 | opt_c752cd5c15d5 | 80 | 66 | 82.5 | 72.4 | 90.1 | screening only | yes |
| 13 / 0a0e7f44 | opt_a94d57fa56d0 | 80 | 66 | 82.5 | 72.4 | 90.1 | screening only | yes |
| 14 / 191b83e2 | opt_6e237808dff9 | 80 | 66 | 82.5 | 72.4 | 90.1 | screening only | yes |
| 15 / a44ebb26 | opt_35681df3cc94 | 80 | 65 | 81.2 | 71.0 | 89.1 | screening only | yes |
| 16 / 9b5f60a0 | snap_0.025_height_0.05 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 17 / b53679a3 | snap_0.025_height_0.03 | 100 | 75 | 75.0 | 65.3 | 83.1 | screening only | no |
| 18 / 0ca3c052 | snap_0.000_height_0.07 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 19 / 86cc362b | recenter_0.15 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 20 / ce6ca967 | recenter_0.10 | 100 | 78 | 78.0 | 68.6 | 85.7 | screening only | no |
| 21 / 5799eb5b | recenter_0.20 | 100 | 77 | 77.0 | 67.5 | 84.8 | screening only | no |
| 22 / 1b2cb184 | recenter_0.05 | 100 | 79 | 79.0 | 69.7 | 86.5 | screening only | no |
| 23 / ba8bc310 | recenter_0.25 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 24 / 91af55fc | all_three | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 25 / 9860eee7 | height_and_observed_poles | 100 | 75 | 75.0 | 65.3 | 83.1 | screening only | no |

### Conditional race time, numerical health and complexity

| Rank / ID | Mean successful s | P90 successful s | Successful n | P90 status | 30 s penalty mean s | Numerical/fallback episodes % | Complexity |
|---|---|---|---|---|---|---|---|
| 1 / c76e14c8 | 9.630 | 9.740 | 543 | ≥30 successes | 14.744 | 0.00 | 1 provisional |
| 2 / aa3179ce | 9.763 | 9.900 | 557 | ≥30 successes | 14.452 | 0.00 | 1 provisional |
| 3 / 26f37062 | 9.774 | 9.900 | 151 | ≥30 successes | 14.729 | 0.00 | 1 provisional |
| 4 / 0db03072 | 9.601 | 9.714 | 114 | ≥30 successes | 14.497 | 0.00 | 1 provisional |
| 5 / 6682535c | 5.899 | 6.000 | 70 | ≥30 successes | 13.130 | 0.00 | 1 provisional |
| 6 / 4aa6b53a | 7.202 | 7.320 | 37 | ≥30 successes | 13.130 | 0.00 | 1 provisional |
| 7 / 2470aab0 | 5.920 | 6.060 | 84 | ≥30 successes | 9.773 | 0.00 | 2 provisional |
| 8 / a460142e | 5.928 | 6.074 | 84 | ≥30 successes | 9.779 | 0.00 | 2 provisional |
| 9 / 3742dfc4 | 5.935 | 6.082 | 84 | ≥30 successes | 9.785 | 3.00 | 2 provisional |
| 10 / ef1845c7 | 9.771 | 9.912 | 65 | ≥30 successes | 13.564 | 0.00 | 1 provisional |
| 11 / 7d3f7626 | 10.555 | 10.720 | 65 | ≥30 successes | 14.201 | 0.00 | 1 provisional |
| 12 / eb8c8ee3 | 11.115 | 11.380 | 66 | ≥30 successes | 14.419 | 0.00 | 1 provisional |
| 13 / 0a0e7f44 | 11.123 | 11.380 | 66 | ≥30 successes | 14.426 | 0.00 | 1 provisional |
| 14 / 191b83e2 | 11.123 | 11.380 | 66 | ≥30 successes | 14.426 | 0.00 | 1 provisional |
| 15 / a44ebb26 | 11.130 | 11.380 | 65 | ≥30 successes | 14.668 | 0.00 | 1 provisional |
| 16 / 9b5f60a0 | 9.765 | 9.880 | 76 | ≥30 successes | 14.621 | 0.00 | 1 provisional |
| 17 / b53679a3 | 9.766 | 9.900 | 75 | ≥30 successes | 14.824 | 0.00 | 1 provisional |
| 18 / 0ca3c052 | 9.769 | 9.890 | 76 | ≥30 successes | 14.625 | 0.00 | 1 provisional |
| 19 / 86cc362b | 9.773 | 9.900 | 76 | ≥30 successes | 14.627 | 0.00 | 1 provisional |
| 20 / ce6ca967 | 9.773 | 9.886 | 78 | ≥30 successes | 14.223 | 0.00 | 1 provisional |
| 21 / 5799eb5b | 9.775 | 9.900 | 77 | ≥30 successes | 14.427 | 0.00 | 1 provisional |
| 22 / 1b2cb184 | 9.775 | 9.880 | 79 | ≥30 successes | 14.022 | 0.00 | 1 provisional |
| 23 / ba8bc310 | 9.778 | 9.920 | 76 | ≥30 successes | 14.631 | 0.00 | 1 provisional |
| 24 / 91af55fc | 9.804 | 9.960 | 76 | ≥30 successes | 14.651 | 0.00 | 1 provisional |
| 25 / 9860eee7 | 9.813 | 9.960 | 75 | ≥30 successes | 14.860 | 0.00 | 1 provisional |

### Whole-call compute and runtime feasibility

| Rank / ID | Mean call ms | Timed / expected calls | Coverage % | Pooled p99 ms | Max episode p99 ms (substitute) | Calls >20 ms % | Timing scope |
|---|---|---|---|---|---|---|---|
| 1 / c76e14c8 | N/A | 0 / 322916 | 0.0 | N/A | 8.448 | 0.0000 | whole_compute_control |
| 2 / aa3179ce | N/A | 0 / 328836 | 0.0 | N/A | 8.414 | 0.0000 | whole_compute_control |
| 3 / 26f37062 | N/A | 0 / 90197 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 4 / 0db03072 | N/A | 0 / 66054 | 0.0 | N/A | 8.297 | 0.0000 | whole_compute_control |
| 5 / 6682535c | N/A | 0 / 25954 | 0.0 | N/A | 9.084 | 0.0000 | whole_compute_control |
| 6 / 4aa6b53a | N/A | 0 / 15722 | 0.0 | N/A | 8.495 | 0.0000 | whole_compute_control |
| 7 / 2470aab0 | 2.187 | 27563 / 27563 | 100.0 | 7.868 | 8.441 | 0.0036 | whole_compute_control |
| 8 / a460142e | 2.191 | 27756 / 27756 | 100.0 | 7.860 | 8.498 | 0.0036 | whole_compute_control |
| 9 / 3742dfc4 | 2.210 | 28316 / 28316 | 100.0 | 7.926 | 8.344 | 0.0035 | whole_compute_control |
| 10 / ef1845c7 | N/A | 0 / 37104 | 0.0 | N/A | 8.262 | 0.0000 | whole_compute_control |
| 11 / 7d3f7626 | N/A | 0 / 40079 | 0.0 | N/A | 8.223 | 0.0000 | whole_compute_control |
| 12 / eb8c8ee3 | N/A | 0 / 42364 | 0.0 | N/A | 8.164 | 0.0000 | whole_compute_control |
| 13 / 0a0e7f44 | N/A | 0 / 42397 | 0.0 | N/A | 8.102 | 0.0000 | whole_compute_control |
| 14 / 191b83e2 | N/A | 0 / 42397 | 0.0 | N/A | 8.150 | 0.0000 | whole_compute_control |
| 15 / a44ebb26 | N/A | 0 / 42342 | 0.0 | N/A | 8.866 | 0.0024 | whole_compute_control |
| 16 / 9b5f60a0 | N/A | 0 / 45043 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 17 / b53679a3 | N/A | 0 / 44899 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 18 / 0ca3c052 | N/A | 0 / 45071 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 19 / 86cc362b | N/A | 0 / 45506 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 20 / ce6ca967 | N/A | 0 / 45733 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 21 / 5799eb5b | N/A | 0 / 45572 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 22 / 1b2cb184 | N/A | 0 / 45981 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 23 / ba8bc310 | N/A | 0 / 45434 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 24 / 91af55fc | N/A | 0 / 45314 | 0.0 | N/A | N/A | N/A | whole_compute_control |
| 25 / 9860eee7 | N/A | 0 / 44219 | 0.0 | N/A | N/A | N/A | whole_compute_control |

## Availability across tests

| Tests | Cohorts | Complete compute mean | Partial timings; mean N/A | No timings; mean N/A | Successful p90 available | Health available | Pooled p99 available |
|---|---|---|---|---|---|---|---|
| All cohorts | 596 | 355 | 0 | 241 | 559 | 464 | 355 |
| Cohorts with n ≥10 | 400 | 180 | 0 | 220 | 396 | 309 | 180 |

These are cohort availability counts; smoke/diagnostic cohorts are included in “all tests” and labeled in the datasets. Hardware/software/environment metadata are carried in the runtime context fields. Missing hardware details prevent attributing runtime differences to controller changes alone.

## Independent validation and changes across cohorts

Found **70 supportable validation-versus-earlier-screen comparisons** for matching configuration/environment identities with disjoint seeds. Every comparison is retained in `validation_comparisons.csv`, including unfavorable ones. A new seed cohort by itself is not labeled independent validation; an explicit plan/handoff must support that role.

| Config ID | Screen cohort (n, finishes) | Validation cohort (n, finishes) | Validation − screen pp |
|---|---|---|---|
| 33c8fa48 | cohort_47fb6f656e1c0b73 (20, 14) | cohort_284e9b3f9242f667 (50, 24) | -22.0 |
| d6d52934 | cohort_80553aa24ade2eb3 (20, 13) | cohort_33300ec64a12d9de (50, 22) | -21.0 |
| daebdfc3 | cohort_5f17a50649a89834 (20, 15) | cohort_68a7390e1b189ba5 (50, 27) | -21.0 |
| daebdfc3 | cohort_5f17a50649a89834 (20, 15) | cohort_5f83423b0962fe48 (50, 27) | -21.0 |
| f96eb206 | cohort_4b5678434c28d267 (40, 21) | cohort_04dc74af2fe2f5f2 (100, 35) | -17.5 |
| 5d3fa079 | cohort_7e65dd7ae4687e21 (30, 23) | cohort_c19d33cd8ec5f3ed (100, 62) | -14.7 |
| 1a497c26 | cohort_f619458d1c6bf341 (30, 23) | cohort_62bfa5bdea925e0c (100, 62) | -14.7 |
| 34c5d203 | cohort_f9da31402d2f2672 (40, 27) | cohort_31a9017a41509305 (100, 55) | -12.5 |
| d6d52934 | cohort_4c5e37eb4f175186 (16, 9) | cohort_33300ec64a12d9de (50, 22) | -12.2 |
| e16a0f06 | cohort_934e1e88e55b61d6 (20, 9) | cohort_cba26122de87507d (100, 33) | -12.0 |
| adcb486e | cohort_86a4ebdb801ddf7a (40, 23) | cohort_a698d0f0cfa8fd62 (100, 46) | -11.5 |
| 5875cec7 | cohort_8151083eca1f04a8 (30, 22) | cohort_902027d5a2ff9122 (100, 62) | -11.3 |

The table shows the largest declines, not a selection of favorable confirmations. Inspect all rows for the same configuration before drawing conclusions. A primary result can therefore be worse than a smaller earlier screen. Paired comparisons preserve their explicit reference, matched-seed n, rescues/regressions and shared-success time n; they are descriptive when source identity is unresolved.

## Recommended foundations

- **F1 (a460142e)**: primary 84/100 (84.0%; exact 95% 75.3–90.6%), mean 5.928 s; numerical/fallback-affected 0.00%; mean call 2.191 ms. Complexity 2, provisional. Evidence remains exploratory screening; no independent confirmation claim. Meets observed 70% preference.
- **G07_pole_width_0p4375 (3742dfc4)**: primary 84/100 (84.0%; exact 95% 75.3–90.6%), mean 5.935 s; numerical/fallback-affected 3.00%; mean call 2.210 ms. Complexity 2, provisional. Evidence remains exploratory screening; no independent confirmation claim. Meets observed 70% preference.
- **F1_2 (2470aab0)**: primary 84/100 (84.0%; exact 95% 75.3–90.6%), mean 5.920 s; numerical/fallback-affected 0.00%; mean call 2.187 ms. Complexity 2, provisional. Evidence remains exploratory screening; no independent confirmation claim. Meets observed 70% preference.
- **departure_rise_lower (1a497c26)**: primary 62/100 (62.0%; exact 95% 51.7–71.5%), mean 5.337 s; numerical/fallback-affected N/A%; mean call 2.241 ms. Complexity 2, provisional. Independent validation is present; inspect all validation changes. Below the observed 70% preference; a comparison foundation, not a qualifying shortlist entry.
- **opt_a758e8cb3e87 (c76e14c8)**: primary 543/725 (74.9%; exact 95% 71.6–78.0%), mean 9.630 s; numerical/fallback-affected 0.00%; mean call N/A ms. Complexity 1, provisional. Independent validation is present; inspect all validation changes. Meets observed 70% preference.
- **incumbent (aa3179ce)**: primary 557/725 (76.8%; exact 95% 73.6–79.9%), mean 9.763 s; numerical/fallback-affected 0.00%; mean call N/A ms. Complexity 1, provisional. Independent validation is present; inspect all validation changes. Meets observed 70% preference.
- **snap_0.025_height_0.07 (26f37062)**: primary 151/200 (75.5%; exact 95% 68.9–81.3%), mean 9.774 s; numerical/fallback-affected 0.00%; mean call N/A ms. Complexity 1, provisional. Independent validation is present; inspect all validation changes. Meets observed 70% preference.

Start with the best-supported broad/experimental foundations whose numerical health and whole-call runtime are acceptable, before adding V3 prediction/soft-constraint machinery. Favor a simpler option within the same reliability band when speed is comparable. A fast successful mean does not compensate automatically for a substantial completion decline. No automatic controller promotion is made.

## Relevant alternatives below 70%

| ID | Configuration | n | Finishes | Completion % | 95% lower % | 95% upper % | Mean successful s | Mean call ms | Complexity |
|---|---|---|---|---|---|---|---|---|---|
| e2fb227b | snap075 | 100 | 67 | 67.0 | 56.9 | 76.1 | 5.850 | N/A | 1 |
| e1fc4e29 | near_tie_cap26 | 100 | 64 | 64.0 | 53.8 | 73.4 | 5.344 | 2.335 | 2 |
| d7f78294 | reference | 100 | 63 | 63.0 | 52.8 | 72.4 | 5.846 | N/A | 1 |
| 5875cec7 | departure_depth_lower | 100 | 62 | 62.0 | 51.7 | 71.5 | 5.337 | 2.250 | 2 |
| 1a497c26 | departure_rise_lower | 100 | 62 | 62.0 | 51.7 | 71.5 | 5.337 | 2.241 | 2 |
| 5d3fa079 | baseline | 100 | 62 | 62.0 | 51.7 | 71.5 | 5.338 | 2.234 | 2 |
| 8bcbe6b2 | progress_7p5 | 100 | 59 | 59.0 | 48.7 | 68.7 | 4.959 | 5.248 | 3 |
| 34c5d203 | progress_7p5_contour_500 | 100 | 55 | 55.0 | 44.7 | 65.0 | 4.876 | 5.325 | 3 |
| 256332d6 | opt_c54375503085 | 60 | 39 | 65.0 | 51.6 | 76.9 | 7.999 | N/A | 1 |
| 37f25f5c | opt_3f643d1be620 | 60 | 31 | 51.7 | 38.4 | 64.8 | 7.157 | N/A | 1 |

These alternatives remain outside the qualifying shortlist; larger/independent cohorts or a simpler implementation can make them more informative than a small favorable screen.

## Checks, unresolved evidence and limitations

Automated count/rate/CI, primary-selection, unique-identity, timing-coverage and paired-environment checks **passed**. Markdown numbers are formatted directly from the written CSVs. Saved-report checks: 429 attached scalar summaries; 0 discrepancies (details in `checks.json`).

- Exact 95% intervals describe binomial uncertainty within a cohort; they do not adjust for selecting among many configurations. The shortlist is exploratory and subject to winner’s bias.
- Seed difficulty varies substantially. Do not pool arbitrary cohorts, compare conditional successful means as though they shared successful seeds, or treat repeated seeds as independent replication.
- Different environment IDs and implementation source bundles remain separate. Unresolved identities are retained in CSVs and excluded from the ranked shortlist, even if their observed completion is high. Source-local unresolved IDs may split configurations that later provenance work could merge.
- Classification of implementation complexity is a manual review aid, not an objective line-count score. Provisional scores and conservative source-bundle boundaries are explicit.
- Original selected-controller evaluation CSVs are overwrite-only summaries and do not retain controller identity, episode records, seeds or run history. They are listed in the inventory rather than attached to the currently selected controller or retroactively reconstructed from conversational claims.
- File timestamps are not execution timestamps. Equal-n selection using file times is explicitly labeled; copied exports are not genuine reruns.
- Research instrumentation, hardware load, dependency/runtime versions and timing scope can differ. Full-test compute means are never inferred from percentiles or wall time.
- Smoke tests and targeted failing-seed replays are not estimates of general completion probability. Stopped studies retain completed episodes and separate infrastructure evidence; unfinished/unattempted cells are not race failures.
- USB/archive copies do not add sample size. Only scalar/tick evidence needed for these metrics was read; bulk solver arrays were not re-audited.


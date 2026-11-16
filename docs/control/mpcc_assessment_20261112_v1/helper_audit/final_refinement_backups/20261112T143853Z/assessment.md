# Reproducible assessment of retained MPCC tests — 2026-11-12

> **PROVISIONAL — regenerated report; independent integrity checks still required.**
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

**Transparent within-group lexicographic ordering:** among resolved primary n ≥10, observed completion ≥70% candidates within the SAME recorded race-core provenance group, prioritize independent validation; then higher five-percentage-point bands of exact lower confidence bounds; then lower complexity; then larger primary n; then faster successful mean. A stable identity breaks ties. No completion probability from patched versus retained-official-core environments is treated as directly comparable. Full datasets retain all candidates, even when excluded from the 25-row primary display.

## Environment provenance and comparability

The retained historical official reference is a **source snapshot**, not proof of complete runtime/physics equivalence. A difference in `env.control_mode` (state versus attitude) is a control interface difference, not evidence on its own of altered physics. Other recorded configuration differences, incomplete package pins, and instrumentation scopes remain visible in the CSVs.

| Recorded race-core evidence | Environments | Configurations | Cohorts | Observed ≥70% eligible |
|---|---|---|---|---|
| retained_official_core_match | 4 | 259 | 354 | 28 |
| unverified_core_source | 9 | 31 | 35 | 0 |
| verified_modified_core_source | 6 | 130 | 207 | 67 |

- **Retained official core match:** pinned `race_core.py` equals the historical official snapshot. Other simulator dependencies may remain unverified; this label is deliberately narrower than “official-equivalent”.
- **Verified modified core source:** pinned `race_core.py` differs. The recovered historical modification installs an MJX box-box collision compatibility function for MuJoCo 3.10.0; collision behavior may change. No experimental magnitude has been established.
- **Unverified core source:** recorded `race_core.py` pin absent. Unknown is not equivalent or different.
- Main shortlist display is limited to source-matched candidates; modified-core results have their own table below. Historical completion rates are NOT pooled or ranked as if under the same physical environment.

## Ranked shortlist: retained official race-core match, observed completion ≥70%

This **display filter** requires a pinned `race_core.py` matching the retained official snapshot, resolved identity, primary n ≥10, and observed completion ≥70%. Up to 25 within-group ranked configurations are shown; all other configurations remain in CSVs, including qualifying patched-core candidates. A matching core alone does NOT prove full simulator equivalence. “Observed ≥70%” differs from “95% lower endpoint >70%”. Screening-only cases are labeled.

| Rank / ID | Env / core | Configuration | n | Finishes | Completion % | 95% lower % | 95% upper % | Evidence | Lower >70% |
|---|---|---|---|---|---|---|---|---|---|
| 1 / 2470aab0 | 404376cd / core match | F1_2 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 2 / a460142e | 404376cd / core match | F1 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 3 / 3742dfc4 | 404376cd / core match | G07_pole_width_0p4375 | 100 | 84 | 84.0 | 75.3 | 90.6 | screening only | yes |
| 4 / c38f523f | 404376cd / core match | E09_attitude_rate_weight_0p05 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 5 / e5d615f4 | 404376cd / core match | E09_attitude_rate_weight_0p075 | 100 | 76 | 76.0 | 66.4 | 84.0 | screening only | no |
| 6 / ed7e53a4 | 404376cd / core match | RECHECK_R24 | 60 | 47 | 78.3 | 65.8 | 87.9 | screening only | no |
| 7 / 607b4d45 | 404376cd / core match | F1_2_3 | 100 | 73 | 73.0 | 63.2 | 81.4 | screening only | no |
| 8 / 9afcd036 | 404376cd / core match | F1_3 | 100 | 73 | 73.0 | 63.2 | 81.4 | screening only | no |
| 9 / 33360774 | 404376cd / core match | E02_contour_weight_700 | 100 | 73 | 73.0 | 63.2 | 81.4 | screening only | no |
| 10 / dd387f08 | 404376cd / core match | G01_gate_offset_0p144 | 100 | 74 | 74.0 | 64.3 | 82.3 | screening only | no |
| 11 / 4f870307 | 404376cd / core match | F2 | 100 | 73 | 73.0 | 63.2 | 81.4 | screening only | no |
| 12 / 040437a7 | 404376cd / core match | REF | 100 | 73 | 73.0 | 63.2 | 81.4 | screening only | no |
| 13 / 019517bc | 404376cd / core match | vertical_taper_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 14 / 45711bf0 | 404376cd / core match | influence_extent_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 15 / 01789e0f | 404376cd / core match | influence_taper_lower | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 16 / 21667dec | 404376cd / core match | lateral_taper_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 17 / 37882a8c | 404376cd / core match | lateral_extent_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 18 / 4942d94c | 404376cd / core match | departure_rise_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 19 / d9778431 | 404376cd / core match | lateral_extent_lower | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 20 / e2a0acd0 | 404376cd / core match | lateral_taper_lower | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 21 / fc5048d7 | 404376cd / core match | influence_taper_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 22 / 0f1bfc9b | 404376cd / core match | vertical_taper_lower | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 23 / 541f580d | 404376cd / core match | departure_depth_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 24 / 71c38410 | 404376cd / core match | vertical_extent_higher | 30 | 23 | 76.7 | 57.7 | 90.1 | screening only | no |
| 25 / fa4dcdf7 | 404376cd / core match | S28_D20_P9 | 30 | 22 | 73.3 | 54.1 | 87.7 | screening only | no |

### Conditional race time, numerical health and complexity

| Rank / ID | Mean successful s | P90 successful s | Successful n | P90 status | 30 s penalty mean s | Numerical/fallback episodes % | Complexity |
|---|---|---|---|---|---|---|---|
| 1 / 2470aab0 | 5.920 | 6.060 | 84 | ≥30 successes | 9.773 | 0.00 | 2 provisional |
| 2 / a460142e | 5.928 | 6.074 | 84 | ≥30 successes | 9.779 | 0.00 | 2 provisional |
| 3 / 3742dfc4 | 5.935 | 6.082 | 84 | ≥30 successes | 9.785 | 3.00 | 2 provisional |
| 4 / c38f523f | 5.838 | 5.960 | 76 | ≥30 successes | 11.637 | 0.00 | 2 provisional |
| 5 / e5d615f4 | 5.857 | 5.970 | 76 | ≥30 successes | 11.651 | 0.00 | 2 provisional |
| 6 / ed7e53a4 | 5.729 | 5.860 | 47 | ≥30 successes | 10.988 | 0.00 | 2 provisional |
| 7 / 607b4d45 | 5.525 | 5.660 | 73 | ≥30 successes | 12.133 | 0.00 | 2 provisional |
| 8 / 9afcd036 | 5.529 | 5.680 | 73 | ≥30 successes | 12.136 | 0.00 | 2 provisional |
| 9 / 33360774 | 5.853 | 5.960 | 73 | ≥30 successes | 12.373 | 0.00 | 2 provisional |
| 10 / dd387f08 | 5.867 | 5.980 | 74 | ≥30 successes | 12.142 | 0.00 | 2 provisional |
| 11 / 4f870307 | 5.897 | 6.020 | 73 | ≥30 successes | 12.405 | 0.00 | 2 provisional |
| 12 / 040437a7 | 5.904 | 6.036 | 73 | ≥30 successes | 12.410 | 0.00 | 2 provisional |
| 13 / 019517bc | 5.336 | 5.480 | 23 | provisional | 11.091 | N/A | 2 provisional |
| 14 / 45711bf0 | 5.337 | 5.496 | 23 | provisional | 11.092 | N/A | 2 provisional |
| 15 / 01789e0f | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 16 / 21667dec | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 17 / 37882a8c | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 18 / 4942d94c | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 19 / d9778431 | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 20 / e2a0acd0 | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 21 / fc5048d7 | 5.338 | 5.496 | 23 | provisional | 11.093 | N/A | 2 provisional |
| 22 / 0f1bfc9b | 5.343 | 5.496 | 23 | provisional | 11.096 | N/A | 2 provisional |
| 23 / 541f580d | 5.345 | 5.512 | 23 | provisional | 11.098 | N/A | 2 provisional |
| 24 / 71c38410 | 5.354 | 5.480 | 23 | provisional | 11.105 | N/A | 2 provisional |
| 25 / fa4dcdf7 | 5.182 | 5.300 | 22 | provisional | 11.800 | N/A | 2 provisional |

### Whole-call compute and runtime feasibility

| Rank / ID | Mean call ms | Timed / expected calls | Coverage % | Pooled p99 ms | Max episode p99 ms (substitute) | Calls >20 ms % | Timing scope |
|---|---|---|---|---|---|---|---|
| 1 / 2470aab0 | 2.187 | 27563 / 27563 | 100.0 | 7.868 | 8.441 | 0.0036 | whole_compute_control |
| 2 / a460142e | 2.191 | 27756 / 27756 | 100.0 | 7.860 | 8.498 | 0.0036 | whole_compute_control |
| 3 / 3742dfc4 | 2.210 | 28316 / 28316 | 100.0 | 7.926 | 8.344 | 0.0035 | whole_compute_control |
| 4 / c38f523f | 2.202 | 27249 / 27249 | 100.0 | 7.891 | 8.610 | 0.0037 | whole_compute_control |
| 5 / e5d615f4 | 2.204 | 27384 / 27384 | 100.0 | 7.951 | 8.657 | 0.0037 | whole_compute_control |
| 6 / ed7e53a4 | 2.275 | 15788 / 15788 | 100.0 | 8.202 | 8.661 | 0.0000 | whole_compute_control |
| 7 / 607b4d45 | 2.236 | 24683 / 24683 | 100.0 | 8.000 | 10.525 | 0.0041 | whole_compute_control |
| 8 / 9afcd036 | 2.269 | 24707 / 24707 | 100.0 | 7.975 | 9.864 | 0.0040 | whole_compute_control |
| 9 / 33360774 | 2.178 | 26589 / 26589 | 100.0 | 7.833 | 8.523 | 0.0038 | whole_compute_control |
| 10 / dd387f08 | 2.184 | 27279 / 27279 | 100.0 | 7.882 | 8.485 | 0.0037 | whole_compute_control |
| 11 / 4f870307 | 2.174 | 26400 / 26400 | 100.0 | 7.900 | 9.528 | 0.0000 | whole_compute_control |
| 12 / 040437a7 | 2.190 | 26405 / 26405 | 100.0 | 7.889 | 8.608 | 0.0038 | whole_compute_control |
| 13 / 019517bc | 2.255 | 7068 / 7068 | 100.0 | 8.222 | N/A | 0.0000 | whole_compute_control |
| 14 / 45711bf0 | 2.225 | 7071 / 7071 | 100.0 | 8.134 | N/A | 0.0000 | whole_compute_control |
| 15 / 01789e0f | 2.238 | 7072 / 7072 | 100.0 | 8.210 | N/A | 0.0000 | whole_compute_control |
| 16 / 21667dec | 2.248 | 7072 / 7072 | 100.0 | 8.157 | N/A | 0.0000 | whole_compute_control |
| 17 / 37882a8c | 2.243 | 7072 / 7072 | 100.0 | 8.187 | N/A | 0.0000 | whole_compute_control |
| 18 / 4942d94c | 2.240 | 7072 / 7072 | 100.0 | 8.124 | N/A | 0.0000 | whole_compute_control |
| 19 / d9778431 | 2.258 | 7072 / 7072 | 100.0 | 8.167 | N/A | 0.0000 | whole_compute_control |
| 20 / e2a0acd0 | 2.253 | 7072 / 7072 | 100.0 | 8.198 | N/A | 0.0000 | whole_compute_control |
| 21 / fc5048d7 | 2.243 | 7072 / 7072 | 100.0 | 8.139 | N/A | 0.0000 | whole_compute_control |
| 22 / 0f1bfc9b | 2.233 | 7080 / 7080 | 100.0 | 8.097 | N/A | 0.0000 | whole_compute_control |
| 23 / 541f580d | 2.244 | 7082 / 7082 | 100.0 | 8.136 | N/A | 0.0000 | whole_compute_control |
| 24 / 71c38410 | 2.249 | 7093 / 7093 | 100.0 | 8.150 | N/A | 0.0000 | whole_compute_control |
| 25 / fa4dcdf7 | 2.220 | 6814 / 6814 | 100.0 | 8.074 | N/A | 0.0000 | whole_compute_control |

## Historical modified-core foundations (not directly comparable)

These candidates met the same observed completion and sample-size eligibility rules, but their pinned race-core source differs. This is a separate display table (up to 12), not a continuation of the main shortlist.

| Within-group rank / ID | Configuration | Env ID | n | Finishes | Completion % | Exact 95% CI (fraction) | Successful mean s | P90 s (provisional if <30 finishes) | 30 s penalized s | Solver/fallback affected % | Pooled p99 ms | Mean compute ms | Complexity | Independent validation? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 / c76e14c8 | opt_a758e8cb3e87 | env_752b4b1bdb019cc1 | 725 | 543 | 74.9 | 0.716–0.780 | 9.630 | 9.740 | 14.744 | 0.00 | N/A | N/A | 1 | yes |
| 2 / aa3179ce | incumbent | env_752b4b1bdb019cc1 | 725 | 557 | 76.8 | 0.736–0.799 | 9.763 | 9.900 | 14.452 | 0.00 | N/A | N/A | 1 | yes |
| 3 / 26f37062 | snap_0.025_height_0.07 | env_752b4b1bdb019cc1 | 200 | 151 | 75.5 | 0.689–0.813 | 9.774 | 9.900 | 14.729 | 0.00 | N/A | N/A | 1 | yes |
| 4 / 0db03072 | opt_1b995c29c9b2 | env_752b4b1bdb019cc1 | 150 | 114 | 76.0 | 0.684–0.826 | 9.601 | 9.714 | 14.497 | 0.00 | N/A | N/A | 1 | yes |
| 5 / 6682535c | combined | env_752b4b1bdb019cc1 | 100 | 70 | 70.0 | 0.600–0.788 | 5.899 | 6.000 | 13.130 | 0.00 | N/A | N/A | 1 | yes |
| 6 / 4aa6b53a | 7bd4beef8c15 | env_752b4b1bdb019cc1 | 50 | 37 | 74.0 | 0.597–0.854 | 7.202 | 7.320 | 13.130 | 0.00 | N/A | N/A | 1 | yes |
| 7 / ef1845c7 | opt_f02e58da8c0d | env_752b4b1bdb019cc1 | 80 | 65 | 81.2 | 0.710–0.891 | 9.771 | 9.912 | 13.564 | 0.00 | N/A | N/A | 1 | screening only |
| 8 / 7d3f7626 | opt_8c03fe3e18b8 | env_752b4b1bdb019cc1 | 80 | 65 | 81.2 | 0.710–0.891 | 10.555 | 10.720 | 14.201 | 0.00 | N/A | N/A | 1 | screening only |
| 9 / eb8c8ee3 | opt_c752cd5c15d5 | env_752b4b1bdb019cc1 | 80 | 66 | 82.5 | 0.724–0.901 | 11.115 | 11.380 | 14.419 | 0.00 | N/A | N/A | 1 | screening only |
| 10 / 0a0e7f44 | opt_a94d57fa56d0 | env_752b4b1bdb019cc1 | 80 | 66 | 82.5 | 0.724–0.901 | 11.123 | 11.380 | 14.426 | 0.00 | N/A | N/A | 1 | screening only |
| 11 / 191b83e2 | opt_6e237808dff9 | env_752b4b1bdb019cc1 | 80 | 66 | 82.5 | 0.724–0.901 | 11.123 | 11.380 | 14.426 | 0.00 | N/A | N/A | 1 | screening only |
| 12 / a44ebb26 | opt_35681df3cc94 | env_752b4b1bdb019cc1 | 80 | 65 | 81.2 | 0.710–0.891 | 11.130 | 11.380 | 14.668 | 0.00 | N/A | N/A | 1 | screening only |

Full historical configuration identities, numeric exact CI endpoints, timing scope and source pins are retained in `configuration_metrics.csv`. Numerical health and timing gaps must not be silently interpreted as zero.

## Availability across tests

| Tests | Cohorts | Complete compute mean | Partial timings; mean N/A | No timings; mean N/A | Successful p90 available | Health available | Pooled p99 available |
|---|---|---|---|---|---|---|---|
| All cohorts | 596 | 355 | 0 | 241 | 559 | 464 | 355 |
| Cohorts with n ≥10 | 400 | 180 | 0 | 220 | 396 | 309 | 180 |

These are cohort availability counts; smoke/diagnostic cohorts are included in “all tests” and labeled in the datasets. Hardware/software/environment metadata are carried in the runtime context fields. Missing hardware details prevent attributing runtime differences to controller changes alone.

## Direct F1 versus F1_2 comparison

F1: **84/100**, successful mean 5.9279 s. F1_2: **84/100**, successful mean 5.9198 s. Both used the same source-matched environment/implementation group, and differ in the recorded `mpcc.gate_offset` setting (F1 0.180, F1_2 0.162).

Direct seed intersection: **100**; F1_2 rescues **2**, regresses **2**; paired completion gain **0.00 pp**. On **82** common successful seeds, F1_2 minus F1 successful time is **-0.00561 s** (negative = F1_2 faster).

**Evidence limitation:** same cohort group/implementation/environment and seeds; initial states missing for 100 matched pairs. The compared episodes have matching explicit seeds and recorded study conditions but lack independently recorded initial-state vectors for 100 pairs. This is exploratory matched-seed evidence, NOT independent validation.

Phase 4 found an exploratory direct McNemar exact p=1.0, with 2 rescues and 2 regressions each way. The approximately 5.6 ms time difference is tiny in practical terms; neither controller establishes a completion-reliability advantage. F1 is a provisional comparison foundation; F1_2 remains a near-equivalent faster alternative.

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

## Recommended foundations — separate source environments

The following are **provisional research foundations**, not independently validated competition-ready winners. Completion evidence, solver/fallback health, timing scope, complexity and sampling uncertainty should be read together; penalized time is correlated with completion and is not a separate robustness score.

- **F1 (config_a460142e3d)**: 84/100 (84.0%); exact 95% CI 0.753–0.906 (fractions); successful mean 5.928 s; p90 6.074 s; solver/fallback affected 0.00%; call mean 2.191 ms; complexity 2. A source-matched, 84/100 focused screening candidate with no recorded failed solver ticks; selected as a practical baseline for further paired testing, not because it statistically beats F1_2.
- **F1_2 (config_2470aab065)**: 84/100 (84.0%); exact 95% CI 0.753–0.906 (fractions); successful mean 5.920 s; p90 6.060 s; solver/fallback affected 0.00%; call mean 2.187 ms; complexity 2. Same observed 84/100 screening completion and implementation complexity; slightly faster on shared successful seeds, but no established robustness advantage.
- **G07 comparison (config_3742dfc435)**: 84/100 finishes, 5.935 s mean successful time; 13.0 recorded failed solver ticks. Similar observed completion should not conceal worse solver-health evidence.
- **Historical modified-core foundation (opt_a758e8cb3e87, config_c76e14c844)**: 543/725, exact 95% CI 0.716–0.780 (fractions), mean successful 9.630 s. Useful within its own environment; not an apples-to-apples competition comparison.

The source-matched F1/F1_2 cohorts are **screening**, not post-selection independent validation. Reconsider a foundation if independent validation or a stricter runtime/solver-health audit changes the ordering. Remaining unverified-source environments are retained in the datasets, not presumed equivalent.

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


# Speed-threshold configurations: 100 fresh episodes each

All six configurations received 100 new matched episodes, selected before testing because their table cohorts had fewer than 100 episodes and observed completion at least 40%. Duplicate table appearances were tested once. No tuning or outcome-dependent stopping. New rates below stand separately from historical screening.

| Configuration | New completion (exact 95% CI) | New successful mean / p90 | 30 s penalized mean | Failed / fallback ticks | Original screening | Original successful mean |
|---|---|---|---|---|---|---|
| vertical_taper_higher | 68/100 (68.0%; 57.9–77.0%) | 5.322 / 5.440 s | 13.219 s | 0 / 0 | 23/30 | 5.336 s |
| S28_D20_P9 | 67/100 (67.0%; 56.9–76.1%) | 5.179 / 5.308 s | 13.370 s | 0 / 0 | 22/30 | 5.182 s |
| reference_speed_2p8 | 66/100 (66.0%; 55.8–75.2%) | 4.966 / 5.090 s | 13.478 s | 0 / 0 | 13/20 | 4.932 s |
| depth_0p35 | 57/100 (57.0%; 46.7–66.9%) | 4.819 / 4.948 s | 15.647 s | 2 / 2 | 24/40 | 4.770 s |
| drag_10 | 45/100 (45.0%; 35.0–55.3%) | 4.734 / 4.860 s | 18.630 s | 76 / 76 | 18/30 | 4.651 s |
| speed33_combined | 40/100 (40.0%; 30.3–50.3%) | 4.604 / 4.724 s | 19.842 s | 23 / 23 | 12/30 | 4.525 s |

## Methods and provenance

Fresh seed lists, full settings and source hashes were frozen before measured validation. The same physical environment/config/source pins apply to all six controllers; each paired reset is verified using a full EnvData hash and saved NumPy arrays. Source packages and the V3 naming-only adapter were recovered from the retained records. V3 soft constraints and progress-bound repair are preserved. speed33_combined uses its original soft-attitude formulation; drag_10 remains hard-bound. No official physics or active project configuration was changed.

Broad/prediction build caches are per configuration, with path-length bounds refreshed. V3 retains unique fresh builds and its embedded progress-bound restoration. Technical smoke and cached/rebuilt action comparisons are excluded from reported performance. Every compute_control call is timed; construction, callbacks, simulation and diagnostics are outside that boundary. Candidate order rotates across seeds; candidates run serially. Ordinary background desktop load remains a timing limitation. Timing summaries are in metrics.csv.

Race times use completed steps / 50 Hz, matching the retained assessment convention. Original zero-based official times, 0.02 s lower, are separately retained. Average times condition on successful completion. Failed races score 30 s. Explicit hover fallback and nonzero solver status are recorded separately; absent events are observed zeros, not missing telemetry.

Individual completion intervals are exact Clopper–Pearson 95%. All 15 paired comparisons are in paired_comparisons.csv: exact McNemar tests with Holm correction within this confirmation, conservative paired completion intervals, and 10,000 deterministic paired bootstrap intervals for penalized time and joint-success time. Time intervals are pointwise. A small successful-time gain does not compensate for a large completion loss.

Historical implementation/environment identities and source evidence are retained in manifest.json and source_verification.json. V3 evidence listed both installed CasADi solver-library copies and acados libraries; the original runtime used LD_LIBRARY_PATH=acados/lib. This run pins that same acados library path and verifies loaded runtime maps. Historical screening and new validation are not pooled. The known MuJoCo 3.10 initialization collision-sentinel warning is retained without installing the historical modified-core contact fix.


## Reproduction

From the repository root:
```bash
export LD_LIBRARY_PATH="$PWD/acados/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.pixi/envs/default/bin/python docs/control/mpcc_speed_confirmation_20261116_v1/run.py --stage validation --cache
.pixi/envs/default/bin/python docs/control/mpcc_speed_confirmation_20261116_v1/analyze.py
.pixi/envs/default/bin/python docs/control/mpcc_speed_confirmation_20261116_v1/audit.py
```
Completed episode files are skipped on resume; source, settings and runner fingerprints must match. For an independent rerun, copy the preparation/source/scripts to a new sibling directory and start with empty smoke/validation directories; retain the fixed seeds when reproducing this exact dataset.

## Interpretation

The top three observed completion rates are vertical_taper_higher 68/100, S28_D20_P9 67/100 and V3 reference_speed_2p8 66/100. No pair among these establishes a completion advantage after Holm correction (all adjusted p=1); that does not prove equivalence. The V3 configuration is the most promising of these tested candidates for a sub-5-second successful average: 4.966 s, with zero observed failed solver/fallback ticks. On jointly successful seeds it was 0.207 s faster than S28_D20_P9 and 0.356 s faster than vertical_taper_higher.

drag_10 fell from 18/30 (60%) screening completion to 45/100, with 76 failed/fallback ticks across 13 episodes. speed33_combined remained at 40% completion, but its successful mean increased to 4.604 s, missing the former under-4.6-second cutoff. depth_0p35 averaged 4.819 s, missing its former under-4.8-second cutoff. Historical screening and this independent confirmation are shown separately; observed changes alone are not causal evidence of an implementation or environment effect.

The updated 0.1-second threshold table uses the new results for these six configurations and retains other existing evidence. Newly appearing screening leaders remain unconfirmed; no additional simulations were run for them. See updated_threshold_table.md and updated_threshold_table.csv.

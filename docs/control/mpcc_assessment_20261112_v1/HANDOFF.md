# PAUSED at user request — 2026-11-12 13:10 Europe/Oslo

This assessment is unfinished. Do not use the current Markdown/CSV ranking as a final recommendation.
No simulation, tuning, controller/config modification, installation, staging, commit or push was performed. No assessment process remains running.

## Scope and locations

User requested a reproducible assessment of ALL retained MPCC configurations, prioritizing robustness somewhat over speed, observed completion >=70%, evidence/sample size, simplicity, both exact 95% confidence limits, full compute-call means with coverage (literal nan when incomplete), primary largest eligible cohort before filters, no arbitrary pooling, matching-seed comparisons, explicit unresolved records, datasets BEFORE generated Markdown. Full requirements are in the conversation.
Sources: /home/askho/repos/lsy_drone_racing, sibling lsy_drone_racing-mpcc-v3, retained research archives, and added USB /media/askho/Ask-USB/mpcc-study.

## Completed

- Original source discovery across logs, .local/mpcc-study, V3 selected-validation, retained tar.zst and ZIP dossiers, and USB.
- Latest discover.py finished successfully: 596 candidate configuration/cohort records, 188 explicit copy/aggregate/fixture exclusions, zero archive/native disagreement issues, 117 USB episode records.
- USB has v3-departure-envelope-n100-v1/v2, and its 117 episode JSON records are exact copies of local aggregates. Archive/ZIP datasets also reconciled. No bulk horizon/warmstart/path arrays extracted or read.
- Scripts discover.py, analyze.py and report.py created in this directory, with complexity_assessments.json and additional_user_evidence.json.
- discover.py only reads original files. analyze.py uses existing repository .pixi Python/NumPy/SciPy; it imports no controllers and launches no simulations.
- Latest compact input snapshot cohort_evidence.jsonl.gz and source_inventory.json were refreshed around 13:09.
- Earlier analysis at 13:06 wrote all required CSVs and Markdown and passed invariant checks. Its 429 attached scalar summaries all agreed with recomputed counts/means. BUT THESE CSVs/Markdown ARE STALE relative to latest scripts/input snapshot.
- Earlier intermediate counts were 596 cohorts / 418 configurations / 82 resolved observed>=70 qualifiers / 465 paired comparisons / 67 validation comparisons. These ARE NOT final: identity normalization has since improved.

## Important discovered issues / latest code fixes

1. Runtime/geometry behavior must be part of identity, not just effective_settings. Native departure-envelope fixed_envelope and attitude_envelope have IDENTICAL effective settings and controller class, but manifest case mode/scheduling + geometry_v1.py change executed behavior. Latest discover.py includes active_behavior in implementation identity, helper hash and provisional family v3_envelope complexity=4. Hard/soft solver formulations from plan.formulations and active instrumentation helper hashes also distinguish otherwise equal parameter sets.
2. Resumed bound-repair cohort: 3 initial baseline episodes + disjoint 27 frozen continuation episodes are combined; request points sideways to screen/plan.json. Latest context() follows a hash-checked referenced plan rather than losing solver/environment provenance.
3. Broad/focused plans lack an embedded full environment but explicitly pin frozen checkout config/level2.toml. Latest code verifies that file hash before reading it. This resolved much missing identity.
4. Broad and focused had been spuriously separated by missing-vs-present package VERSION labels, despite byte-identical pinned code. Latest identity uses a digest of recorded simulator package source/library closure instead; version labels retained as metadata. Relevant source pins are normalized relative to the LAST lsy_drone_racing component, avoiding artificial source-root differences.
5. Legacy defaults are reconstructed ONLY when the old baseline source hash 2033f45e88df6931b734155281b1cb3c80e71a10bb8358be754ff39ed8324b3c is pinned; AST verification against retained historical source confirms the default dictionary. No imports or controller construction.
6. Paired comparisons for native per-case JSONs need the shared run directory as cohort_group. Latest discover.py corrects the previous per-case directory grouping.
7. Focused100 studies are SCREENING, not independent validation: focused/report.md explicitly says higher-n tuning and selected-factor combinations, not post-selection independent validation. Departure batch002 is explicit fresh confirmation; batch004 incumbent/S30_RTI3 likewise, but new A875 repair remains screening. Roles captured in ROLE_RULES.
8. V3 raw compute_durations_ms includes research instrumentation/getters. controller_compute_ms is an overhead-adjusted quantity and is deliberately NOT used as whole-call mean. Label scopes distinctly. Do not confuse saved report's adjusted p99 with pooled raw whole-call p99.
9. Full per-call timing data mostly survives broad/prediction/V3; legacy experimental reports usually retain only percentiles, so mean is nan. No estimation from wall time/medians/p99.
10. Source-only evaluation.csv does not retain historical controller identity, seeds, n or per-episode data. Latest analyze.py adds unresolved_records.csv with raw summary records and additional user excerpts, without retroactively attaching them to the current selector. User-supplied G07 excerpt explicitly says n20,18 finishes; departure/R23 excerpts omit explicit n so leave those blank. Supplemental evidence source is a saved user-message record, not an actual evaluation transcript. These summaries are not extra independent cohorts.

## Critical remaining work before finalizing

A. Re-run analyze.py against the LATEST snapshot. It has been edited since last run, including unresolved_records output; check for errors.
   .pixi/envs/default/bin/python docs/control/mpcc_assessment_20261112_v1/analyze.py

B. MAJOR interpretation correction: historical high-n experimental studies used a DIFFERENT environment implementation from the unmodified official sandbox. Confirmed: largest overnight incumbent cohort n725,557 finishes has a pinned envs/race_core.py hash DIFFERENT from logs/mpcc-compliance-20261103/official/main/lsy_drone_racing/envs/race_core.py. G07 focused100 matches official environment sources.
   - Environment IDs are already separate, but current generated ranking globally mixes them and recommendations do not adequately distinguish this.
   - Add explicit environment compatibility labels by comparing relevant PINNED environment hashes against retained official source hashes, and full normalized physical env/sim config where possible. Keep evidence, missingness and reference source explicit.
   - Carry environment label/ID into report shortlist tables. Do not let high-n historical patched data masquerade as competition validation.
   - Decide/document transparent ranking within comparable environments, or prioritize verified unmodified official environments in the main shortlist and put historical modified-environment foundations in a clearly separate table. State any additional DISPLAY filter explicitly, retaining ALL data and no 9-second filter. Do not equate different env completion probabilities.

C. Inspect latest identity merges and primary selections: G07 pole0.4375, pole0.39375/F1/RECHECK_R23 aliases; departure_rise_lower30 vs confirmation100; V3 fixed/attitude envelopes MUST remain distinct. Verify active formulations and no exact implementation/settings/env duplicates.
D. Saved-summary checks cover early report summaries, broad configuration-summary/summary CSV, and native .local report tables (official means compared to original official convention). Recheck latest discrepancy list, explain any real differences.
E. Review and improve recommendations: small set of actual foundations, explicit tradeoffs on completion, n, lower/upper CI, complexity, numerical health and runtime. Original selected G07 has13 failed solve ticks over3 episodes in its100 cohort, unlike R23/F1; do not hide that. Explain validation declines, meaningful matched-seed differences and V3 confirmation results (e.g. progress7.5 59/100 vs original46/100) without promoting below70 candidates into shortlist.
F. Add/check data dictionary definitions for new fields active_behavior_json, simulator_package_versions_json, environment compatibility, unresolved_records, user evidence. Clarify known saved max-episode p99 may be adjusted/instrumented and should not substitute across timing scopes.
G. Automated checks: add explicit generated-Markdown-vs-CSV verification, deterministic rerun checks (hash outputs before/after analyze), duplicate seed checks, primary latest equal-n checks, resumed provenance check beyond disjoint seeds, and check source integrity/nonmodification of controller/config files relative to initial state. No broad software tests/simulations needed.
H. Review source discovery completeness: source_inventory has all surfaced archives, native logs and .local. Some smoke/health records stay unresolved. Keep them visible, and retain missing provenance limitations rather than guessing. Manual complexity scores are family-level and provisional where active equivalence needs deeper review.
I. Update report header/remove DRAFT only after completion. Add convenient README/reproduction instructions if useful. Final response must link assessment.md, three required CSVs, dictionary, reproduction scripts; give final cohort/config/70% counts plus key unresolved limits and USB dedup result. Do not cite intermediate counts as final.

## Files and process notes

- /tmp/mpcc-assessment-discovery.log: latest successful discovery output.
- /tmp/mpcc-assessment-analysis.log: previous 13:06 analysis result.
- No background processes remain.
- Report source reproducibility: analyze.py writes CSVs/checks FIRST, then imports report.generate(), which reads the CSVs rather than recomputing numerical cells.
- No work beyond this report directory was edited. Initial main worktree was already very dirty (config/level2.toml modified and many untracked controllers/scripts/docs); preserve all existing changes.

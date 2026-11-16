# Decision checklist for ChatGPT — not a final assessment

- Total cohorts in CSV: **596**; configurations: **420**; original ≥70% qualifiers: **95**.
- Independent validation comparison rows: **70**; matched-seed comparison rows: **474**.
- Selected detailed dossier: **40 configurations**; full qualifying list retained separately.
- Configs in dossier with nonzero recorded failed-solve ticks: **3**.
- Configs in dossier with recorded health missingness: **7**.
- Configs in dossier without a matching pinned `race_core.py`: **22**.

## Decisions that still require scientific judgment

1. Which field-level environment differences alter physics, observations, race termination, scoring or seed distribution?
2. Can any run be considered comparable to the official reference *beyond* a matching `race_core.py`? Which simulator/runtime pins are absent?
3. Should the main recommendation be limited to a verified official environment (and if no such cohort exists, explicitly abstain)?
4. Which ≥70% candidates have independent confirmation, and how far did their completion rate fall between screening and validation?
5. How do lower AND upper 95% completion bounds, sample size, speed and implementation complexity trade off?
6. Are the solver-failure, fallback and control-call latency measurements actually complete and compatible across families?
7. Should modified-environment configurations appear only as separate research foundations, not official-equivalent performance evidence?

## High-priority source files

- `environment_comparison.csv`: one row per environment, separate config and pinned-code statuses.
- `environment_field_differences.csv`: exact differing official vs recorded config fields.
- `environment_source_hashes.csv`: recorded vs retained official source hashes.
- `all_qualifying_candidates.csv`: every qualifying candidate; not a recommendation order.
- `candidate_dossier.json`: complete available settings, numerical health and links to paired/validation evidence for selected candidates.
- `validation_evidence.csv`: ALL valid screening-to-independent-validation comparisons.
- `matched_seed_evidence.csv`: all paired results touching selected configurations.

**Do not label any environment fully equivalent solely on the basis of these files.**

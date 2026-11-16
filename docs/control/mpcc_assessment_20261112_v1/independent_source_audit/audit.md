# Independent MPCC original-source audit

Status: **partial_verification**; PASS **106**, FAIL **0**, NOT_VERIFIED **33**.

Checks read original experiment CSV/JSON files. Normalized `cohort_evidence.jsonl.gz` and assessment analysis functions are not used to compute metrics.

## Findings
- No observed metric disagreement among independently verified checks.

## Limitations
- Missing source fields are `NOT_VERIFIED`, never assumed zero.
- Exact confidence intervals use SciPy beta quantiles; p90 uses linear order-statistic interpolation.
- An original source checksum match establishes file integrity, not simulation-environment equivalence.
- Identical seeds do not prove identical initial states when those states are not recorded.
- Missing per-call timings cannot establish that no complete timing exists elsewhere.
- F1/F1_2 paired initial states: {"excluded_different_initial_states": 0, "unknown_initial_state_pairs": 100}

All metric-level comparisons and original paths are in `results.csv`.

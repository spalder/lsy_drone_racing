# Validation provenance review

## Verdict: NOT_VERIFIED

The assessment row for the requested 15/20 versus 27/50 comparison is configuration `config_daebdfc31b8b3c48`, screening cohort `cohort_5f17a50649a89834` (batch001), and validation cohort `cohort_68a7390e1b189ba5` (batch002). Indexed records are `docs/control/mpcc_assessment_20261112_v1/validation_comparisons.csv` and `cohort_metrics.csv`. Their original source paths are `logs/mpcc-tuning/autonomous-20261103/batch001/report.json` and `batch002/report.json`; indexed episode counts and finishes agree with 20/15 and 50/27.

| Claim | Finding | Evidence |
|---|---|---|
| Validation seeds disjoint from screening | VERIFIED | `batch001/plan.json` lists seeds 14932–14951; `batch002/plan.json` lists 15051–15100. These do not overlap. |
| Disjoint from all relevant selection data | NOT_VERIFIED | The batch001 factorial plan is selection data and has seed 14932 in its request, but the indexed validation comparison names only the chosen cohort. No complete seed inventory for all configuration-selection data is established by the reviewed records. |
| Seeds and settings frozen before outcomes | NOT_VERIFIED | `batch002/plan.json` and `batch002-request.json` document the 50-seed independent-validation design and the chosen case. `logs/mpcc-tuning/autonomous-20261103/journal.md` says “Batch 002 frozen” before reporting results. However, no independently timestamped pre-outcome journal/commit or immutable plan chronology establishes when the frozen artifacts were created relative to observation. |
| Settings and environment equivalent | VERIFIED | Indexed settings and environment for both exact cohorts match; both original plans specify the same `a0.7_c600_n40` controller parameters and experiment parameters. Plans also carry matching source pins/runtime/environment. Paths: `batch001/plan.json`, `batch002/plan.json`. |
| Validation not used to select validated configuration | NOT_VERIFIED | The journal describes batch002 as validation, and says the combo was promoted after batch002 outcomes. This supports post-outcome promotion, but does not establish that the configuration was selected independently before batch002: batch001 itself is a factorial screen that includes this configuration, and no dated pre-validation selection decision or frozen rule artifact was located. |

The journal (`logs/mpcc-tuning/autonomous-20261103/journal.md`) records batch001's 15/20 result, then says batch002 was frozen and later reports its 27/50 outcome and promotion. This is evidence of the intended order, not sufficient independent chronology. The summary (`docs/control/mpcc_autonomous_summary.md`) likewise states settings and seeds were frozen before measurement, but is a retrospective assessment-generated summary, not original timestamp evidence.

Accordingly, the comparison has fresh, disjoint validation seeds and matching indexed settings/environment, but the evidence reviewed does not prove pre-outcome freezing or independence from configuration selection. It cannot be classified as genuinely independent validation on this provenance record alone.

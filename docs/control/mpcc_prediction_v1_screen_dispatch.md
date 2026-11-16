# Dispatch prompt: prediction/adaptation v1 screening

Copy the text below into the testing session.

---

Run the prediction/adaptation v1 **matched 30-seed screen** in
`/home/askho/repos/lsy_drone_racing`. Work autonomously through execution,
auditing and reporting; do not stop at a plan or request routine confirmation.
This authorizes the new 300-episode screen described below. It does not resume
the paused departure-speed campaign. Stop after reporting the screen; leave
100-seed confirmation and production promotion for a separate decision.

Read before execution:

- `docs/control/mpcc_prediction_v1.md`
- `logs/mpcc-campaign/departure-speed-20261104-v1/campaign-summary.md`
- `logs/mpcc-campaign/departure-speed-20261104-v1/logging-v5/README.md`
- `logs/mpcc-campaign/departure-speed-20261104-v1/research-policy-20261104-v2.json`
- `logs/mpcc-prediction-v1/implementation-verification.json`
- The parent, case definitions and numerical settings under
  `config/research/mpcc_prediction_v1/`.

Inspect the new runner's import, validation and effective-setting checks before
running. Use `scripts/mpcc_prediction_research.py`, which explicitly loads
`MPCCPredictionCore` from the root controller directory into the frozen campaign
package. The old campaign used `MPCCBroadCore` in a research checkout; the root
`config/level2.toml` selects a different controller. Changing that config or
invoking the old runner will not execute this experiment correctly.

Keep the complete racing parent fixed: reference 3.0, cap 3.2, max angle .875,
three solver passes, pressure 12, with every other racing/geometry setting from
`parent-fast.json`. Hold numerical options fixed across all cases:
`qp_solver_cond_ric_alg=1`, `qp_solver_ric_alg=0`, `levenberg_marquardt=1e-4`.
These settings are an executable **numerical-repair hypothesis**, not an
established repaired parent. Do not retune the parent, costs or numerical options
during this screen, and do not attribute trajectory-dependent health changes to
numerical repair.

Run all ten cases in the declared order on the same 30 seeds:

1. `baseline`: unmodified model, EMA rate 2.
2. `drag_05`: drag strength .5 only.
3. `drag_10`: drag strength 1 only.
4. `drag_15`: drag strength 1.5 only.
5. `attitude_09`: attitude response scale .9 only.
6. `attitude_11`: attitude response scale 1.1 only.
7. `attitude_gain_11`: attitude command-gain scale 1.1 only.
8. `ema_4`: EMA rate 4 only.
9. `scalar_kf`: KF only, using the exploratory defaults.
10. `combined_example`: drag 1, response 1.1, command gain 1.1 and KF.

Verify that each individual case differs from baseline in exactly its intended
setting. The combined case is illustrative, not a preselected winner. All other
settings, including numerical options, must match baseline.

Use fresh outputs and seeds 1601000–1601029. Before freezing the plan, check that
these seeds have not already been used by another prediction screen or relevant
historical evaluation. If the path or seeds are already used, select a fresh
output version and disjoint consecutive 30-seed block, and record the substitution
before execution. Never overwrite or silently resume existing results. Preselect
the first three seed IDs for prediction diagnostics, identically across cases.

Run from the repository root:

```bash
export ACADOS_SOURCE_DIR="$PWD/acados"
export LD_LIBRARY_PATH="$PWD/acados/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SCIPY_ARRAY_API=1
export PYTHONDONTWRITEBYTECODE=1
export PATH="$PWD/.pixi/envs/default/bin:$PATH"

python -m pytest -q -p no:cacheprovider tests/unit/control/test_mpcc_prediction.py

python scripts/mpcc_prediction_research.py prepare \
  --output logs/mpcc-prediction-v1/screen-30-v1 \
  --stage screen --seed-start 1601000 --seed-count 30 \
  --parent config/research/mpcc_prediction_v1/parent-fast.json \
  --numerics config/research/mpcc_prediction_v1/numerics-classical-lm.json \
  --prediction-seeds 1601000,1601001,1601002

python scripts/mpcc_prediction_research.py run logs/mpcc-prediction-v1/screen-30-v1
python scripts/mpcc_prediction_research.py analyze logs/mpcc-prediction-v1/screen-30-v1
```

Freeze and inspect the prepared complete cases, seed cohort, diagnostic subset
and fingerprints before `run`. Do not edit pinned inputs afterward. The runner
uses the existing `logs/mpcc-tuning/.combination.lock` and fresh worker/generated
directories. If another simulation holds the lock, leave it undisturbed and retry
when the lock becomes available. Monitor progress and available storage. Preserve
historical sources/results and existing user changes. Keep the simulator physics,
randomizations, visibility, gate passage rules and .02 s simulated interval fixed.
Use only public observations and commands; never inspect episode-specific hidden
mass, inertia, motors or disturbances. Keep compact logging and the preselected
prediction subset; do not enable full geometry or horizon dumps.

The implementation check passed eight focused tests and a four-episode smoke
audit with zero numerical/fallback ticks. Baseline finished 2/2 and the combination
1/2. This is plumbing evidence only. The earlier incomplete smoke attempts and
the fast parent's historical numerical failures remain documented; do not erase
them or count smoke seeds as screening evidence.

Complete the entire declared screen and retain failures. Do not replace seeds,
drop adverse cases or stop a case because its performance looks poor. If an
execution or integrity failure prevents completion, retain the partial outputs
and report the cause; never present an incomplete cohort as a completed screen.
Any necessary plumbing fix must be verified and frozen into a fresh plan/output
before a new comparable run, rather than changing an in-progress experiment.

Require the analyzer audit to pass. Check requested/effective controller and
generated solver settings, matched initial observations, all 30 results per case,
diagnostic subset selection, next-observation alignment including terminal steps,
and numerical status/fallback accounting. Numerical failures are outcomes to
report even when the artifact/integrity audit passes.

Write `screening-report.md` in the new batch directory and report:

- Per-case completion count/rate and exact interval, conditional successful mean,
  paired time delta versus baseline with shared-finish count/bootstrap interval,
  and rescue/regression seeds. Include failure crossing occurrences.
- Numerical tick/status/fallback counts and effective Riccati/LM options. Report
  latency p99/max/overrun fraction as advisory.
- One-step and 100/200 ms velocity/attitude prediction summaries on the fixed
  diagnostic subset, plus gain acceptance/rejection and EMA/KF behavior where
  useful. Keep model-fit evidence separate from racing outcomes.
- A reasoned recommendation for whether any **single frozen candidate** merits
  fresh 100+ seed confirmation, or that none does. Do not launch confirmation.

Retain the evaluation policy: **observed completion >=40%, worthwhile paired
speed gains, zero nonzero-status or missing-input/prediction fallback ticks, and
finite commands**. Local latency is advisory. Do not invent a fixed worthwhile
gain cutoff, relax numerical-health rules, treat a completion interval as a
population guarantee, or select solely on successful means/prediction residuals.
Screening is provisional; no candidate is confirmed and no numerical repair is
established by a favorable small cohort. If the fixed parent remains numerically
unhealthy, say so and distinguish exploratory model results from a qualified
candidate.

Return the report/audit paths, completed episode counts, concise comparisons and
the confirmation recommendation. Preserve the frozen screen configuration so a
later fresh confirmation can use exactly the same baseline and chosen candidate.

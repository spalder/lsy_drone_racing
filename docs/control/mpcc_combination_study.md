Recommend **zero recentering plus 5 cm over-gate height**, with **no observed-pole
clearance override**. It completed 77/100 fresh seeds, the highest count in the
requested eight-case matrix. Adding the pole override completed 76/100 and was
26.9 ms slower on 75 shared successful seeds.

This completes the study proposed in [the earlier recommendation](mpcc_combination_recommendation.md).
That proposal and all earlier reports are preserved. The archived and experimental
controllers and existing runners were left unchanged; the new harness reuses
`run_episode`, environment creation, native/Python output suppression and atomic JSON reporting.

The selected controller configuration is:

```json
{
  "file": "attitude_mpcc_experimental.py",
  "mpcc": {"obstacle_clearance": 0.26},
  "mpcc_experiment": {
    "gate_center_snap": 0.0,
    "over_gate_lift": 0.05,
    "observed_obstacle_clearance": null
  }
}
```

All optimizer, physics and environment settings otherwise match baseline.
The pole override, wherever tested, applied only to revealed poles on replans;
initial planning and unrevealed poles retained 0.26 m. Exact full configurations,
effective optimizer defaults, package versions and source hashes are in the report.
These settings are recommended for simulation; the study does not change controller defaults.

| Configuration | Selected diagnostic cohort | Fresh seeds 101–200 | Fresh mean successful time (s) |
| --- | ---: | ---: | ---: |
| `baseline` | 0/12 | 68/100 (68%) | 9.793 |
| `recenter_only` | 5/12 | 68/100 (68%) | 9.779 |
| `height_only` | 5/12 | 74/100 (74%) | 9.785 |
| `observed_poles_only` | 2/12 | 70/100 (70%) | 9.825 |
| `recenter_and_height` | 7/12 | 77/100 (77%) | 9.777 |
| `recenter_and_observed_poles` | 5/12 | 68/100 (68%) | 9.808 |
| `height_and_observed_poles` | 6/12 | 75/100 (75%) | 9.813 |
| `all_three` | 7/12 | 76/100 (76%) | 9.804 |

The diagnostic cohort contains the 12 requested known-failure seeds and is kept
separate from the 100 fresh seeds. Successful-run averages above use different
seed subsets; use the paired comparisons below to assess speed.

The fresh results show interactions rather than independent isolated gains:

- Recentring alone stayed at 68/100: seven rescues and seven regressions. Height
  alone reached 74/100: six rescues and no regressions.
- Recentring plus height reached 77/100: 12 rescues and three regressions against
  baseline, with a 23.4 ms speed improvement on 65 shared successful seeds.
  Against recentering alone it added nine finishes, lost none and was 6.2 ms faster
  on all 68 shared finishes. Against height alone it added eight, lost five and
  was 15.9 ms faster on 69 shared finishes.
- Seeds 136 and 193 finished with recentering plus height although neither
  constituent isolated configuration finished them. Conversely, the combination
  lost seeds 114, 115, 163, 181 and 183 from the union of the isolated completion
  sets. Completion gains cannot be added as independent effects.
- Recentring plus poles stayed at 68/100. Against recentering alone, pole clearance
  rescued 114, 152 and 183 but regressed 164, 168 and 189; shared finishes were
  27.1 ms slower. Against poles alone it gained six and lost eight.
- Height plus poles reached 75/100. Against height alone it rescued 193 and 199,
  regressed 168 and was 26.6 ms slower on 73 shared finishes. Against poles alone
  it added five finishes with no regressions.
- Adding poles to recentering plus height rescued **114** but regressed **168 and
  189**, reducing completion from **77% to 76%**. It was **26.9 ms slower** on the
  75 shared finishes. The override therefore offers no net benefit beyond the
  primary combination in this cohort.

The primary combination's baseline regressions were inspected:

| Seed | Outcome | Gates passed | Race time (s) | Numerical failure ticks |
| --- | --- | ---: | ---: | ---: |
| 114 | terminated | 3 | 7.36 | 0 |
| 115 | terminated | 0 | 2.10 | 0 |
| 181 | terminated | 3 | 7.48 | 0 |

Height alone completed all three of these seeds. It remains the alternative if
preserving every observed baseline completion takes priority over the highest
completion count. The recommendation follows the requested completion-count-first
priority and does not claim that recentering plus height dominates on every seed.
Termination stages do not establish a specific collision cause.

On the diagnostic cohort, recentering plus height and all three changes completed
exactly the same seven seeds. Pole clearance added 31.4 ms on those shared
finishes. The combination retained all five recentering-only finishes and added
72 and 76, but lost height-only finishes 80 and 1337. These selected examples are
not pooled with the fresh cohort.

All **896 episodes** completed: 96 diagnostic and 800 fresh, with eight configurations
per cohort, identical ordered seeds, a new controller per episode and serial
execution. There were **zero numerical-failure ticks and zero infrastructure errors**.
An independent audit recalculated counts, settings, seed identities, summary means,
CSV contents and all 28 cohort-specific paired comparisons. All 36 diagnostic
episodes with matching earlier settings/seeds reproduced outcomes, gate counts,
step counts and command hashes exactly. Completed-run resume was executed and
skipped all episodes; interrupted-episode resume and changed-setting rejection
were also covered by focused tests. Eleven focused tests passed across the harness,
existing tuning and experimental geometry tests.

Race time is completed environment steps divided by 50 Hz, stopping at the
completion callback. Individual race times have 20 ms resolution. Paired differences
are candidate minus reference on shared successful seeds. Controller p50/p95 timings
measure wall-clock `compute_control` calls and exclude construction, environment
steps and callbacks; those machine-dependent timings are not race-time comparisons.
`config.env.seed=6` seeds initial environment construction; every actual episode
uses its saved seed through `env.reset(seed=...)`.

The evidence covers one nominal course and 100 fresh level-2 simulation seeds.
The diagnostic seeds were selected from known failures. The fresh cohort was used
to compare and select candidates, so it is not independent post-selection validation.
No further configurations or height values were simulated.

Results:

- [Complete report and execution manifest](../../logs/mpcc-tuning/combined-20261102T160058720196Z/report.json)
- [All paired comparisons and interaction sets](../../logs/mpcc-tuning/combined-20261102T160058720196Z/analysis.md)
- [Independent structured audit](../../logs/mpcc-tuning/combined-20261102T160058720196Z/analysis.json)
- [Structured recommendation](../../logs/mpcc-tuning/combined-20261102T160058720196Z/recommendation.json)
- [Summary CSV](../../logs/mpcc-tuning/combined-20261102T160058720196Z/summary.csv)
- [896 individual episode records](../../logs/mpcc-tuning/combined-20261102T160058720196Z/episodes.csv)
- [Historical replay checks](../../logs/mpcc-tuning/combined-20261102T160058720196Z/historical-replay-check.json)
- [Simulator/compiler/solver diagnostic log](../../logs/mpcc-tuning/combined-20261102T160058720196Z/simulation.log)

Run the fixed study from the repository root:

```sh
pixi run python -m scripts.compare_mpcc
```

Resume this study, requiring matching code, settings, seeds and runtime fingerprints:

```sh
pixi run python -m scripts.compare_mpcc --resume \
  --output-dir logs/mpcc-tuning/combined-20261102T160058720196Z
```

Rebuild the independent analysis without running episodes:

```sh
pixi run python -m scripts.analyze_mpcc_combinations \
  logs/mpcc-tuning/combined-20261102T160058720196Z
```

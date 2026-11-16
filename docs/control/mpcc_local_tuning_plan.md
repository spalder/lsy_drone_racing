Further local MPCC tuning will use 1,000 serial simulation episodes. The previous
600-episode study took 56.9 minutes, giving a projected simulation runtime of
94.8 minutes, plus focused checks and analysis. Runtime is an estimate rather
than a stop condition; complete the planned matrix and independent validation.

The incumbent is recentering 0.000, extra height 0.05 m, no observed-pole override,
with global pole clearance 0.26 m. Controllers and optimizer settings are unchanged.

1. Screen the Cartesian product of recentering {0.000, 0.025} and extra height
   {0.03, 0.05, 0.07} m on identical ordered fresh seeds 301–400: 600 episodes.
   This brackets the best height locally and examines the interval below the
   previously tested 0.05 recentering increment. It does not repeat 10–20 cm heights.
2. Select one challenger from the five non-incumbents by highest screening
   completion count, then lowest paired mean race-time difference against the
   incumbent on shared finishes (missing paired means rank last), then smallest
   distance from the incumbent in the tested grid, then configuration name.
   Always select a distinct challenger, even if none beats the incumbent in screening.
3. Validate the incumbent and selected challenger on identical untouched fresh
   seeds 401–600: 400 episodes. Freeze the choice before reading any validation
   outcomes. Do not combine screening and validation rates to justify selection.

Prioritize independent validation completion count, inspect all regression seeds
and gate stages, then assess paired successful race times. Retain the incumbent
on a completion tie unless there are no completion regressions and paired times
improve. Report exact paired completion tests and a paired completion-difference
confidence interval; do not claim a definitive improvement on weak evidence.
The interval is an approximate paired normal 95% interval, clipped to [-1, 1].

Every episode gets a fresh controller, runs serially, and checkpoints atomically.
Completed episodes can resume only under identical source/runtime/settings/seeds.
Native and Python chatter goes to a diagnostic log. Ordinary race and numerical
failures remain outcomes; infrastructure errors are recorded separately and retried
through resume after a fix. Save exact settings, source hashes, seed freshness,
JSON, summary and episode CSVs, all paired comparisons, and independent audits.
Validate counts, matching seeds, settings, arithmetic, CSVs and hashes. Print one
summary per completed configuration/cohort and absolute report paths. No further
adaptive searches are part of this plan.

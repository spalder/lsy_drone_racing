# F1, F1_2, G07 targeted evidence

This summarizes recorded evidence, not a new performance claim.

## Named configurations

- **F1**: ID `config_a460142e3d70aa79`; environment `env_404376cdd03e85f3`; 84/100 finishes; 95% CI [0.7532124025891377–0.9056897100260538]; failed solver ticks 0.0; primary role `screening`.
- **F1_2**: ID `config_2470aab06585d4ce`; environment `env_404376cdd03e85f3`; 84/100 finishes; 95% CI [0.7532124025891377–0.9056897100260538]; failed solver ticks 0.0; primary role `screening`.
- **G07_pole_width_0p4375**: ID `config_3742dfc435fa9211`; environment `env_404376cdd03e85f3`; 84/100 finishes; 95% CI [0.7532124025891377–0.9056897100260538]; failed solver ticks 13.0; primary role `screening`.

## Effective settings difference: F1 vs F1_2

- `mpcc`: F1={"adapt_altitude": 0.15, "adapt_clip_high": 1.4, "adapt_clip_low": 0.7, "adapt_raw_high": 1.5, "adapt_raw_low": 0.6, "adapt_thrust_change": 0.04, "adaptation_rate": 2.0, "attitude_; F1_2={"adapt_altitude": 0.15, "adapt_clip_high": 1.4, "adapt_clip_low": 0.7, "adapt_raw_high": 1.5, "adapt_raw_low": 0.6, "adapt_thrust_change": 0.04, "adaptation_rate": 2.0, "attitude_

## Direct same-seed comparisons

**No direct F1/F1_2 matching-seed comparison found.** Equal 84/100 rates do not prove equivalent outcomes or paired speed advantage.

Additional comparison records touching a target: **6**.
All such records are saved in `f1_related_pairs.csv` (not just selected summaries).

## Limits

- Screening cohorts must not be called independent post-selection validation.
- A matching `race_core.py` hash does not establish full environment equivalence.
- Source-level changes require inspection; a diff alone does not establish changed race physics.

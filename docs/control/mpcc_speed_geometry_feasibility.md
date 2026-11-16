# Fast MPCC geometry feasibility check

Promising first-round candidate: **gate_center_snap=0.25, over_gate_lift=0.10 m**, with reference_speed=1.8 and max_speed=2.1. It rescued two previously failed seeds and retained all four successful controls. No defaults were changed.

Completed 96 episodes (eight configurations × 12 matched seeds) in 8.82 minutes of execution, plus brief preparation/reporting, within the 15-minute work budget.

The seed set deliberately contains eight historical failures (four with zero gates passed, three at gate stage 3, one at stage 1) and the first four historical successes. All come from the existing 1.8/2.1 holdout. This is a failure-enriched diagnostic cohort: 6/12 is not an estimate of the overall completion rate and must not be compared directly with the prior 31/60 result. Reusing these seeds for tuning means they are no longer independent holdout evidence.

| Recentring | Lift, m | Finishes / 12 | Rescued failures | Lost controls |
| ---: | ---: | ---: | --- | ---: |
| 0.00 | 0.05 | 4 | — | 0 |
| 0.10 | 0.05 | 4 | — | 0 |
| 0.25 | 0.05 | 5 | 14055 | 0 |
| 0.00 | 0.10 | 5 | 14053 | 0 |
| 0.00 | 0.15 | 5 | 14053 | 0 |
| 0.10 | 0.10 | 5 | 14053 | 0 |
| 0.25 | 0.10 | 6 | 14055, 14053 | 0 |
| 0.10 | 0.15 | 5 | 14053 | 0 |

Recentring 0.25 rescued seed **14055** (previously zero gates passed). Lift 0.10 rescued seed **14053** (previously three gates passed). Their combination rescued both, with no lost control finishes. Recentring 0.10 alone did not help; lift 0.15 did not rescue additional seeds. The combined setting added only **0.010 s** on average across the four shared successful controls (20 ms episode resolution). Its successful-only mean was 7.200 s, but that includes two newly rescued seeds and uses a different subset from baseline. Six selected failures remain unresolved.

The existing lift parameter raises the smooth path between gates; it does not simply add a fixed vertical offset to every gate crossing. Recentring blends crossing points toward gate centers. This test changes those existing geometry parameters only; optimizer settings, obstacle clearance 0.26, algorithms, track, physics, sensors, randomizations and frequency remain fixed.

Validation: the rerun baseline exactly matched historical outcome, gate count, step count, numerical ticks and command hash on all 12 seeds. Effective settings were checked for every episode, and recorded finish/rescue/regression counts were recalculated. All configurations had zero numerical-failure ticks, zero >20 ms controller calls and maximum episode p99 below 8.5 ms. Driver and original source hashes matched, lint passed, and all artifacts remain separate from earlier studies.

Conclusion: combining modest recentering and additional lift is feasible and warrants testing on a broader cohort. These 12 selected seeds support a mechanism-level improvement, not a reliable population completion-rate claim. No additional tuning or simulations were run after this comparison.

Artifacts: [frozen plan](../../logs/mpcc-tuning/speed-geometry-20261103T082313Z/plan.json), [episode report](../../logs/mpcc-tuning/speed-geometry-20261103T082313Z/report.json), [validation and rescued seeds](../../logs/mpcc-tuning/speed-geometry-20261103T082313Z/audit.json).

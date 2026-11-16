# MPCC speed-first targeted tests

The fastest setting that exceeded the observed 50% finish threshold on fresh holdout seeds was **reference_speed=1.8, max_speed=2.1**. It finished **31/60 (51.7%)**, with successful laps averaging **7.157 s**. This narrowly meets the first-round sample criterion; its exact 95% finish-rate interval is **38.4–64.8%**, so the study does not establish a population finish probability above 50%.

| Fresh holdout setting | Finishes | Mean successful lap | Paired time gain vs incumbent |
| --- | ---: | ---: | ---: |
| Incumbent: reference 1.3, cap 1.8 | 46/60 (76.7%) | 9.762 s | — |
| Reference 1.6, cap 1.9 | 39/60 (65.0%) | 7.999 s | 1.741 s |
| Reference 1.8, cap 2.1 | 31/60 (51.7%) | 7.157 s | 2.572 s |

Successful averages use different seed subsets; paired gains compare only shared finishes. The fastest candidate's paired bootstrap 95% interval is −2.589 to −2.554 s (candidate minus incumbent). It is about 26% faster on shared finishes. With every failed race assigned 30 s, its all-episode mean is 18.198 s versus incumbent 14.484 s: the speed comes at a substantial finish-rate cost, accepted under the revised objective.

The 1.6 setting provides more observed finish-rate margin, at roughly 18% paired speed improvement. Neither is an established optimum. No defaults were changed.

The separate experiment reused the prepared serial subprocess harness and independent auditor. It completed **452 episodes in 41.3 minutes**: 112 screening, 160 targeted, 180 holdout. Fresh seeds were reserved after the historical inventory's maximum, excluding all earlier used and reserved seeds. Decisions and parent report hashes were frozen before every stage. The two holdout finalists were selected before outcomes; no tuning followed holdout.

Screening tried reference speeds 1.6, 1.8, 2.0, 2.2, 2.4 and 2.6 m/s with progress-speed caps of reference+0.3 (minimum 1.8). Finish counts were 11, 9, 7, 7, 5 and 3 out of 16, respectively; the incumbent finished 11/16. The fastest runs averaged 5.27 s at reference 2.6, but only 3/16 finished, far below the requested threshold.

Targeted testing used 20 new matched seeds, probing reference 1.7/1.9 around 1.8 plus increased progress weight, increased angle, reduced contour weight, and reduced attitude-rate/slew penalties. It was a harder cohort: incumbent 11/20; every targeted challenger finished at most 10/20. Under the frozen fallback, the two eligible screen leaders (1.8 and 1.6) advanced to the 60-seed holdout. Cross-cohort finish percentages are not pooled or treated as matched evidence.

All three holdout configurations had zero numerical-failure ticks and passed the saved latency criteria. Fixed geometry was gate_center_snap=0.0, over_gate_lift=0.05, observed_obstacle_clearance=None, obstacle_clearance=0.26. Controller algorithms/defaults, track, physics, randomizations, sensor range and control frequency were unchanged. Only this separate driver's optimizer validation bounds expanded beyond the overnight search; original runner/auditor/controller files and historical artifacts were preserved. Final independent stage audits and driver/source hashes passed; lint passed.

An initial driver startup failed before any simulation or output directory creation because importing SciPy before the simulation package violated its initialization order. The import order was corrected before this measured run. No measured episodes used the failed version, and no measured run was resumed under changed code.

Artifacts: [plan and provenance](../../logs/mpcc-tuning/speed-first-20261103T073311Z/plan.json), [result and exact settings](../../logs/mpcc-tuning/speed-first-20261103T073311Z/result.json), [holdout audit](../../logs/mpcc-tuning/speed-first-20261103T073311Z/holdout/analysis.json). All stages retain episode/settings CSVs, immutable decisions and simulation logs. Driver: [mpcc_speed_first_round.py](../../scripts/mpcc_speed_first_round.py).

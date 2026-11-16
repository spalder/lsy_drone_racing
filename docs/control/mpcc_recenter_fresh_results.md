# Fresh-seed recentering comparison at 1.8/2.1

Prefer **gate_center_snap=0.25**, with **over_gate_lift=0.10 m**, for the next speed-first experiments. It tied 0.5 at 35/50 finishes and preserved every finish achieved at 0.0. This is a simulation recommendation; production defaults remain unchanged.

All three configurations ran the same 50 fresh seeds (14206–14255), totaling 150 episodes in 13.51 minutes. Speed reference stayed at 1.8 and progress-speed cap at 2.1. Every other optimizer setting stayed at incumbent values.

| Recentring | Finishes | Successful mean, s | Failure-penalized mean, s | Numerical failure ticks |
| ---: | ---: | ---: | ---: | ---: |
| 0.0 | 29/50 (58%) | 7.22207 | 16.78880 | 0 |
| 0.25 | 35/50 (70%) | 7.22286 | 14.05600 | 0 |
| 0.5 | 35/50 (70%) | 7.22857 | 14.06000 | 0 |

Compared with 0.0, recentering 0.25 rescued six seeds (14207, 14218, 14222, 14223, 14227, 14255) and lost none: **+12 percentage points**. On 29 shared successful seeds, mean lap-time difference was +0.00345 s, paired bootstrap 95% interval [−0.00690, +0.01172] s. There is no meaningful observed speed penalty at the 20 ms per-episode resolution.

Recentring 0.5 rescued seven baseline failures but lost seed 14216, also yielding +12 percentage points. Against 0.25 it rescued seed 14208 and lost 14216; on 34 shared finishes it averaged +0.00294 s, bootstrap interval [−0.00235, +0.00765] s. The finish-rate tie and negligible speed difference provide no reason here to prefer stronger recentering.

Unadjusted exact paired completion p-values are 0.03125 (0.0 vs 0.25), 0.07031 (0.0 vs 0.5), and 1.0 (0.25 vs 0.5). These are exploratory comparisons without multiplicity adjustment. The saved conservative completion-difference interval for 0.25 vs 0.0 is [−4.51, +26.15] percentage points; finite samples do not establish the size or certainty of a population gain. Paired bootstrap intervals use 10,000 resamples and fixed RNG seed 20261102. Successful means use different subsets; paired comparisons condition on shared successful seeds. All unsuccessful episodes receive a fixed 30 s penalty.

The prior failure-enriched feasibility cohort was not pooled into this evidence. A recursive historical inventory was checked before reserving the new seeds; exact configs, ordered seeds, source/runtime manifest and driver hash were frozen before simulation. Each configuration used the existing isolated solver subprocess harness, serially under the shared simulation lock; each episode was checkpointed before worker acknowledgement.

Validation passed for all 150 episodes: matched ordered seeds, effective settings, finish counts, gate/time semantics, source/driver hashes, summary calculations and all three paired comparisons. Lint passed. All cases had zero numerical-failure ticks, zero controller calls over 20 ms, and maximum episode p99 under 8.4 ms. These controller timings exclude initialization and environment stepping. No controller algorithms/defaults, track, physics, randomizations, sensors, frequency or obstacle clearance were changed. No infrastructure errors occurred.

Artifacts: [frozen plan and settings](../../logs/mpcc-tuning/recenter-fresh-20261103T083618Z/plan.json), [complete episode report](../../logs/mpcc-tuning/recenter-fresh-20261103T083618Z/report.json), [audit and paired comparisons](../../logs/mpcc-tuning/recenter-fresh-20261103T083618Z/audit.json), [summary CSV](../../logs/mpcc-tuning/recenter-fresh-20261103T083618Z/summary.csv), [episode CSV](../../logs/mpcc-tuning/recenter-fresh-20261103T083618Z/episodes.csv).

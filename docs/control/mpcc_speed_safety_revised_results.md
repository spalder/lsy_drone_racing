# Adaptive speed and safety study — revised execution

Recommended first-round simulation configuration: **reference_speed=2.2, max_speed=2.5, gate_center_snap=0.25, over_gate_lift=0.15 m, obstacle_clearance=0.26, observed_obstacle_clearance=None**. Other optimizer settings remain at incumbent values. No production defaults changed.

| Fresh 50-seed validation | Finishes | Successful mean | Latency eligible |
| --- | ---: | ---: | --- |
| Baseline 1.8/2.1, recenter 0.25, lift 0.10 | 37/50 (74%) | 7.202 s | Yes |
| **2.2/2.5, recenter 0.25, lift 0.15** | **31/50 (62%)** | **6.055 s** | **Yes** |
| 2.2/2.5, recenter 0.50, lift 0.10 | 28/50 (56%) | 6.050 s | No |

The selected candidate was **15.91% faster** on 30 shared successful seeds: candidate-minus-baseline paired mean −1.146 s, 95% paired bootstrap interval [−1.1573, −1.1347] s. Its finish-rate exact 95% interval is **47.2–75.3%**; 62% exceeds the observed floor, but does not establish a population rate above 50%. It rescued 1 baseline failures and lost 7 baseline finishes. The paired completion p-value is 0.0703 (exploratory, unadjusted). Completion preservation was not required by this revised objective.

All-episode means with every failed race scored at 30 s were baseline 13.1296 s, selected candidate 15.1544 s: speed comes at a finish-rate cost. Successful-only means use different subsets and should not be treated as all-seed performance. Bootstrap uses 10,000 paired resamples, RNG seed 20261102.

## Audited scope change

The user first authorized execution of the max-speed-only plan, then explicitly requested reference-speed increases after observing unchanged lap times. The cap-only run is preserved at `logs/mpcc-tuning/max-speed-safety-20261103T0920`, with a resolution record. Its completed 64-episode cap cohort produced identical 12/16 finishes and 7.19333 s successful means for caps 2.1, 2.4, 2.8, 3.2. Its next cohort committed 16 baseline episodes before intentional interruption; an uncommitted partial worker episode, if any, is not counted. The generic handler recorded KeyboardInterrupt as infrastructure_error; its cause was this user-directed stop, not a solver error.

A distinct driver, revised machine plan, new output directory and new reserved seeds were used. No measurements were pooled or resumed under changed code. The **original absolute clock** was retained; both phases plus revision/preflight and final validation finished in about **44.3 minutes**, leaving time for reporting within one hour. Revised run: **358 episodes** (64 speed screening, 96 safety singles, 48 combination/neighbor tests, 150 validation). With the earlier 80 committed episodes, execution totaled **438 committed episodes**.

## Adaptive path

The revised screen varied reference speed 1.8/2.0/2.2/2.4 with caps 2.1/2.3/2.5/2.7. Completion counts were 10/16, 10/16, 8/16, 4/16; successful means about 7.236, 6.594, 6.058, 5.645 s. The first two configurations failed strict latency eligibility (episode p99 over 20 ms), so reference 2.2 was selected as the recoverable faster frontier. This is measured latency behavior; no unverified cause is assigned to it.

At 2.2/2.5, recenter 0.5 increased exploratory completion from 8/16 to 10/16. Lift 0.15 reached 9/16. Global clearance 0.30, observed-only 0.30, and both together each remained at 8/16. No obstacle-clearance increase improved completion in that cohort. Only recentering met the planned repair-advancement rule; the combination stage therefore tested recenter 0.75 as a bounded neighbor, rather than stacking an unqualified lift change. On that new cohort the unchanged geometry finished 7/16 and recenter 0.5/0.75 each 8/16. Since recovery did not clear the >50% floor there, further escalation and second recovery were skipped. This avoided raising speed from an unconfirmed repair.

The frozen final comparison nominated the fastest eligible exploratory candidate and a nearby completion alternative. Fresh validation favored increased lift at recenter 0.25. The recenter-0.5 finalist exceeded 50% finishes but failed latency eligibility (maximum episode p99 26.108 ms); it was excluded. The selected lift candidate had maximum episode p99 8.949 ms and no >20 ms calls. Every validation configuration had zero failed-solve ticks.

No tuning followed validation. Track, physics, randomizations, sensor range, frequency, optimizer weights and controller algorithms remained unchanged. The original prepared source/runtime fingerprint matched before launch. New driver/plan hashes and independent episode/settings/count/penalty/latency audits passed after execution. Tests passed without simulations before launch: 14 original/adaptive tests, then six tests covering the revised ladder and shared adaptive rules. Lint passed.

Artifacts: [revised frozen machine plan](mpcc_speed_safety_revised_plan.json), [state and absolute deadlines](../../logs/mpcc-tuning/speed-safety-revised-20261103/study.json), [recommendation and exact settings](../../logs/mpcc-tuning/speed-safety-revised-20261103/recommendation.json), [validation audit and all paired comparisons](../../logs/mpcc-tuning/speed-safety-revised-20261103/fresh_validation/audit.json), [validation summary CSV](../../logs/mpcc-tuning/speed-safety-revised-20261103/fresh_validation/summary.csv). Every stage retains full configs, frozen decisions, parent hashes, ordered seeds, episode CSV and simulation log. Original runner: `scripts/mpcc_max_speed_safety.py`; separate revised runner: `scripts/mpcc_speed_safety_revised.py`.

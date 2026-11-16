# Dynamic max-speed and safety study — planned, not started

Run only after the user explicitly authorizes execution. This document and its
[machine-readable plan](mpcc_max_speed_safety_plan.json) define a separate study.
No simulations, solver generation, seed reservations or background runs are part
of this planning task. The adaptive driver remains to be implemented before launch;
the existing isolated episode harness will be reused.

## Objective and starting point

Find a faster configuration by raising **`controller.mpcc.max_speed` only**, then
recovering completion through existing geometry and obstacle-clearance parameters.
**`reference_speed` stays exactly 1.8 throughout**, including fallback branches.
The speed setting being tuned caps optimized path-progress speed; it is not a hard
limit on the drone's physical velocity.

Start from the recent 70%-completion configuration:

```toml
[controller.mpcc]
reference_speed = 1.8
max_speed = 2.1
obstacle_clearance = 0.26
# Other optimizer settings retain the incumbent values in the JSON baseline.

[controller.mpcc_experiment]
gate_center_snap = 0.25
over_gate_lift = 0.10
# observed_obstacle_clearance remains None initially.
```

The 70% result was 35/50 on seeds 14206–14255, at about 7.223 s per successful
lap. It guides this plan but is not pooled with the new experiment. Track,
physics, disturbances/randomizations, sensors, frequency, controller algorithms
and all other optimizer settings stay fixed. No production defaults change.

Important limitation: the current configuration spent only **0.195% of valid
ticks at >=98% of the 2.1 progress cap**. A higher cap may not materially shorten
laps while the preferred speed stays 1.8. Test this rather than assuming that a
higher configured maximum makes the drone faster. Never compensate by raising
reference speed or progress weight in this study.

## One-hour envelope

Target 50–55 minutes, hard maximum 60 minutes including implementation/preflight,
simulation, auditing and reporting. Start the persistent budget clock when the
authorized work begins, not after preparation. Reserve the last five minutes for
reporting; stop scheduling episodes by minute 55. Downtime counts on resume.

Recent measured throughput was about 5.33 s/episode. Forecast at **6.5 s/episode**
plus 10 s per new configuration worker, replacing that rate with the larger of
6.5 s and 1.2 times observed mean wall time as data accumulate. Include startup,
compilation and audit time when checking available budget. The full ceiling is
470 episodes, roughly 51 minutes of episode time plus startup and reporting, so
not every optional stage is expected to fit. No padding if evidence is exhausted.

Before every stage freeze its ordered configurations, fresh seeds, parent hashes,
decision reason and time forecast. Protect the final 50-seed validation cohort:
150 episodes if three configurations are selected, 100 if only baseline plus one
distinct finalist. Skip second recovery first, then shorten/skip other optional
exploration by whole configurations. Never truncate a matched seed cohort or
trade away validation to complete the exploration matrix. If preparation consumes
too much time, cut optional exploration explicitly. Report unfinished work honestly.

## Stages

| Stage | Fresh matched seeds | Cases, maximum | Purpose |
| --- | ---: | ---: | --- |
| 1. Cap probe | 16 | 4 | Hold starting geometry; test caps 2.1, 2.4, 2.8, 3.2 |
| 2. Safety singles | 16 | 6 | Recover finishes at the selected higher cap |
| 3. Combine repairs | 16 | 3 | Verify promising safety interactions at that cap |
| 4. Raise cap again | 16 | 3 | Keep recovered safety, test up to two higher caps |
| 5. Second recovery | 16 | 4, optional | Repair the next finish-rate loss if budget permits |
| 6. Frozen validation | 50 | 3 | Original baseline and up to two distinct finalists |

All stages use mutually disjoint seeds, fresh relative to all existing used and
reserved blocks. Allocate and reserve the blocks under the shared simulation lock
after a recursive historical inventory when execution is authorized. Every case
within a stage uses the exact same ordered seeds. Evaluate the reference first;
no stopping individual configurations early based on poor outcomes.

### 1. Increase the cap and identify a useful frontier

Evaluate the four fixed caps with recentering 0.25, lift 0.10, global clearance
0.26 and no observed-pole override. Always compare measured paired lap times,
finish counts, progress-cap saturation and actual maximum optimized progress.

A configuration is numerically/latency eligible only with zero failed-solve ticks,
every episode's whole-call p99 <=20 ms and aggregate >20 ms fraction <=1%.
For a speed comparison require at least five shared successful seeds. An eligible
speed increase must improve shared-success mean lap time by at least 1% against
the lower-cap reference on this same cohort. If fewer than five shared successes
exist, record insufficient speed evidence rather than ranking that comparison.

Select the highest tested cap with a useful speed gain and >50% observed finishes.
If its next higher tested cap has useful speed gain but drops completion below
65%, or by >=10 percentage points relative to the same-cohort reference, use that
next cap as the recovery frontier. A candidate at exactly 50% does not meet the
user's finish floor, but may be a recovery target. Caps with fewer than 25%
finishes are not advanced in this short study; step back to the preceding cap.

If no raised cap gives a useful gain, keep 2.1 as the frontier and allow one safety
recovery pass there. Do not force an escalation cycle unsupported by lap times.
Once geometry changes, one higher-cap recheck is allowed because cap usage may
change. Stop cap escalation after that recheck if it still gives <1% gain; do not
expand beyond the saved ladder merely because the cap is rarely active.

### 2. Recover completion with isolated safety changes

At the selected frontier cap compare these six cases, all against unchanged
frontier safety on the new matched cohort:

1. Unchanged frontier safety.
2. Recentring 0.50, other settings unchanged.
3. Lift 0.15 m, other settings unchanged.
4. Global obstacle clearance 0.30 m, observed override unchanged.
5. Observed-pole clearance 0.30 m, global clearance unchanged.
6. Global and observed-pole clearance both 0.30 m.

At the first pass, "unchanged" means recentering 0.25/lift 0.10/global 0.26/observed
None. In subsequent stages it means the frozen current parent, not reset defaults.

The recovery target is **>=65% observed finishes** (at least 11/16), giving some
margin above 50%. This is a planning heuristic, not a confidence guarantee. A repair
may also advance with >50% finishes and at least two extra finishes over the
unchanged frontier. Require numerical/latency eligibility and no more than a 5%
shared-success lap-time increase. Keep the faster unrepaired case available as a
finalist if it exceeds 50%; a repair's speed cost must not erase the useful cap gain.

Rank advancing repairs by finish count descending, paired successful time ascending,
normalized departure from the current parent ascending, then canonical name.
Distance scales: cap 0.3, recentering 0.25, lift 0.05 m, global clearance 0.04 m;
observed override costs 1 for None/non-None switching, otherwise difference/0.04 m.

### 3. Combine complementary repairs

Compare the unchanged frontier, best advancing single repair, and the combination
of the best two independently improving families. A family is recentering, lift,
or obstacle clearance (global/observed variants belong to the same family).
Combine only settings actually tested in stage 2. Deduplicate exact configs.

If there is no pair of improving families, replace the combination with a single
stronger neighbor of the best family: recentering 0.75, lift 0.20 m, or clearance
0.34 m applied to the same global/observed fields as its parent. Stay within bounds.
If no family improved completion, skip combinations and retain the prior parent.
Do not stack changes based only on calling them safer.

Choose the recovered parent by the same completion-first recovery ranking, always
against the unchanged frontier measured in this cohort. If recovery does not meet
the floor or target, step back to the last useful eligible lower cap; do not increase
the cap from a failed recovery.

### 4–5. Increase again, then repair only if warranted

With recovered safety fixed, compare its current cap with the next two ascending
values in [2.1, 2.4, 2.8, 3.2, 3.5]. Never exceed 3.5. If already at 3.2, test 3.5
only. Include the unchanged recovered parent, deduplicate, and skip previously
ineffective **identical full configurations**. A previously tested cap with newly
recovered safety is a new configuration and may be tested. With no higher value,
go to validation. Apply stage 1's useful-gain and completion-drop rules.

If a higher cap is meaningfully faster but loses finishes, stage 5 may compare its
unchanged parent and up to three targeted repairs. Propose in this deterministic
order: another improving recentering neighbor, another improving lift neighbor,
then an obstacle-clearance neighbor. Increase only one field/family per proposal,
using the next saved value; omit exhausted fields. Prioritize lift over recentering
only if the newly lost finishes are mostly at gate stage 3; prioritize obstacle
clearance only with logged pole-proximity evidence. Gate count alone cannot identify
an obstacle collision. Save the reason. Use the recovery criteria above.

If it cannot recover, retain the earlier lower-cap candidate. Permit at most these
two cap rounds and two repair rounds; no open-ended branching within the hour.

## Parameter meanings and bounds

| Parameter | Permitted values |
| --- | --- |
| `max_speed` | 2.1, 2.4, 2.8, 3.2, 3.5 |
| `gate_center_snap` | 0.0, 0.25, 0.50, 0.75 |
| `over_gate_lift` | 0.05, 0.10, 0.15, 0.20 m |
| `obstacle_clearance` | 0.26, 0.30, 0.34 m |
| `observed_obstacle_clearance` | None, 0.30, 0.34 m |

Recentring blends crossing targets toward the gate center. Lift is a smooth vertical
bump on the nominal return segment after the third crossing; it does **not** raise
every gate target or guarantee clearance above every gate. Global obstacle clearance
sets the path's desired horizontal distance from pole axes. The observed override
applies to detected poles on replans; it does not change the initial path correction.
Larger values may increase curvature or create harder approaches, so improvement
must be measured. No collision-avoidance algorithm changes are allowed.

## Final validation and recommendation

Freeze baseline and at most two distinct finalists before looking at any final-seed
outcomes. Provisional finalists: fastest eligible >50% candidate, plus the strongest
completion candidate within 5% of that candidate's exploratory successful lap time.
If unavailable, use the next fastest eligible distinct candidate. Earlier cohorts
guide nominations only: never pool them or interpret cross-cohort ranking as a
matched comparison. If no challenger exceeds 50%, compare the least-bad distinct
candidate but mark it a fallback, not a recommendation.

Run all frozen configs on the same 50 untouched seeds. Do not change validation
size based on outcomes. Report exact finish-rate intervals, all paired completion
rescues/regressions and exact tests, 10,000 paired-seed bootstrap time intervals,
shared-success counts, numerical ticks, latency and 30 s failure-penalized means.
Separate conditional successful speed from all-episode results. Comparisons are
exploratory; identify unadjusted p-values and finite-sample uncertainty.

For a speed recommendation require >50% observed validation finishes (>=26/50),
numerical/latency eligibility, >=5 shared finishes with baseline, and >=1% paired
speed gain. Rank by paired speed gain against the same validation baseline, then
completion descending, departure ascending and name; report the different shared
subsets. A useful gain is still provisional if its bootstrap interval spans zero.
If no challenger qualifies, retain baseline if eligible and above 50%; otherwise
report that no tested configuration met the requirement. Also name the highest
observed completion option as a tradeoff. No tuning follows validation.

## Execution preparation and artifacts

On authorization, implement a separate driver reusing `configuration_episodes`,
`measured_episode` and the existing paired auditor. Existing overnight `case` bounds
and fixed-geometry assertions do not accept this matrix; do not edit them or
silently use the overnight executor. Apply full explicit per-case configs in the
new driver, with independent geometry/optimizer checks.

Use a fresh subprocess for every configuration under `.combination.lock`, preserve
parent acknowledgement after each checkpoint, and monitor through normal exit.
Read-only instrumentation may record physical-velocity summaries alongside existing
optimized-progress/cap diagnostics; any new instrumentation must be fingerprinted
and checked before measured episodes, with no controller algorithm changes.

Before launch verify original preparation source/runtime fingerprint, validate
candidate generation and budget/state transitions without simulations, and freeze
the new source/runtime/config/plan manifest. Save a new output directory, plan,
full settings, seed-inventory evidence, stage decisions and parent hashes, episode
reports/CSVs, simulation logs, independent arithmetic/settings audit, deadline log
and concise recommendation. Preserve every historical run and report. A required
measured-code fix needs a separate run or explicit audited migration, never silent
mixing. This plan changes no defaults and authorizes no deployment.

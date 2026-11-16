Preparation is **ready**. No overnight study or broad screening has been launched.
Read [the plan](mpcc_overnight_plan.md) before executing. Work from
`/home/askho/repos/lsy_drone_racing` with Pixi Python. Do not run another simulation
concurrently; all study commands use the shared `.combination.lock`.

Authoritative preparation directory:

`/home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-prep-20261102T212955383826Z`

The prepared runner and independent auditor are:

- [overnight_mpcc.py](../../scripts/overnight_mpcc.py)
- [overnight_mpcc_analysis.py](../../scripts/overnight_mpcc_analysis.py)
- [Focused tests](../../tests/unit/control/test_overnight_mpcc.py)

Evidence and artifacts:

- [Machine-readable plan](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/plan.json): exact incumbent, geometry, grids, limits, normalization, seeds, ranking, final recommendation policy and budgets.
- [Source/runtime manifest](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/manifest.json): package/controller/config/acados sources plus runner/auditor SHA-256, runtime versions and relevant environment variables. Execution recomputes and checks it.
- [Preflight](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/preflight.json): 15 focused tests and lint passed; test source and preparation hashes.
- [Test log](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/preflight-tests.log) and [lint log](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/preflight-lint.log).
- [Smoke report](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/report.json), [independent audit](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/analysis.json), [episode CSV](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/episodes.csv), [summary CSV](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/summary.csv), [exact settings CSV](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/settings.csv), and [diagnostic log](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/smoke/simulation.log).
- [Action-equivalence replay](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/replay.json): command hash, outcome, gates, steps, elapsed time and numerical ticks exactly matched the instrumented incumbent.
- [Completed-resume proof](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/resume-check.json): all eight smoke records preserved, report hash unchanged, zero additional episodes.
- [Measured calibration](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/calibration.json) and [initial budget forecast](../../logs/mpcc-tuning/overnight-prep-20261102T212955383826Z/initial-forecast.json).

Real preparation work completed:

| Case | Seeds | Completions | Mean successful time | Maximum episode p99 call latency |
| --- | --- | ---: | ---: | ---: |
| Incumbent, horizon 40, speed 1.3 | 12000, 12001 | 2/2 | 9.840 s | 7.66 ms |
| Horizon 30 | 12000, 12001 | 2/2 | 9.880 s | 7.37 ms |
| Horizon 60 | 12000, 12001 | 2/2 | 9.870 s | 8.36 ms |
| Reference speed 1.5 | 12000, 12001 | 2/2 | 8.620 s | 7.68 ms |

This successful attempt contains **eight smoke episodes plus one real replay**.
There were zero numerical-failure ticks, zero >20 ms controller calls and zero
infrastructure errors in this attempt. The higher-speed result is a two-seed
startup check, not selection evidence; screening starts from the saved initial grids.
Warm episode wall times used for calibration were approximately 5.90 s at horizon
40, 5.74 s at 30, and 6.28 s at 60. Startup/generation costs are additionally
visible in per-configuration wall time and report timestamps. The conservative
initial forecast accepts the full 920-episode screening matrix at about **2.43 h**,
while reserving about **3.48 h** for minimum confirmation, validation and reporting.
These are conservative scheduling estimates, not promised actual runtime.

A prior preparation attempt is preserved at
`logs/mpcc-tuning/overnight-prep-20261102T212704977265Z/`.
It completed two ordinary failed races on seeds 10000–10001, then encountered a
harness infrastructure error changing from horizon 40 to 30: acados reused the
loaded 40-step shared library. The repair isolates **every optimizer configuration
in a fresh subprocess**, even when dimensions match, while retaining serial
execution and per-episode parent checkpoint acknowledgements. The replacement
used a new plan/manifest and fresh seeds; no results were mixed. See its
[resolution record](../../logs/mpcc-tuning/overnight-prep-20261102T212704977265Z/resolution.json).
Thus total preparation has 11 completed real episodes across separate attempts,
plus one uncommitted infrastructure-failed partial attempt. Earlier reserved seeds
are also excluded by the inventory. Do not resume the superseded attempt.

Seed allocation for overnight execution:

| Stage | Reserved seeds | Usage |
| --- | --- | --- |
| Screening | 12002–12041 | 40 matched seeds, 23 configurations |
| Refinement | 12042–12101 | 60 matched seeds |
| Combinations | 12102–12181 | 80 matched seeds |
| Challenges | 12182–12261 | 80 matched seeds |
| Confirmation | 12262–12411 | 150 matched seeds |
| Validation | 12412–13911 | Reserve 1,500; freeze a prefix of 300–1,500 before outcomes |

The two smoke seeds are excluded from every overnight cohort. The inventory checks
prior reports and reserved plans, and launch checks again for new overlaps.
Unused reserved validation suffixes remain reserved rather than being silently reused.

Policies to preserve:

- Geometry: recentering 0, height 5 cm, no observed override, global clearance 0.26 m.
- Failure score: **30 seconds**, from the actual 1,500-step / 50 Hz timeout.
- Exploratory eligibility: no loss of completion count against matched incumbent,
  no numerical-tick increase, every episode p99 call <=20 ms and aggregate >20 ms
  fraction <=1%; paired successful time must exist.
- Eligible ranking: paired mean, completion descending, normalized L1 distance,
  canonical name. Scales are saved in `plan.json`.
- Fallback challenger: latency eligible first, numerical ticks ascending, completion
  descending, paired mean, distance, name. A fallback does not replace the incumbent
  merely by being chosen for comparison.
- Independent recommendation: eligible, >=1% paired speed improvement, bootstrap
  upper bound below zero. Otherwise retain incumbent. Observed completion
  preservation is not a noninferiority claim.
- Progressive budget: nine-hour target, ten-hour hard maximum, downtime counts on
  resume, 15-minute reporting reserve, minimum 300-seed validation pair protected.
  Optional prefixes/stages may shrink or skip. Spare time expands the holdout
  before any validation outcomes. No post-holdout tuning.

Launch the overnight study in the new execution session:

```sh
cd /home/askho/repos/lsy_drone_racing
pixi run python -m scripts.overnight_mpcc run \
  --prepared /home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-prep-20261102T212955383826Z \
  --output-dir /home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-20261102T212955383826Z
```

This output directory does not exist yet. Its timestamp identifies the preparation;
the actual execution start and persistent deadlines are written at launch.
There is no background process to attach to.

Resume that exact study, preserving its deadline and completed episodes:

```sh
cd /home/askho/repos/lsy_drone_racing
pixi run python -m scripts.overnight_mpcc run \
  --prepared /home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-prep-20261102T212955383826Z \
  --output-dir /home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-20261102T212955383826Z \
  --resume
```

Audit the overnight study without running episodes:

```sh
cd /home/askho/repos/lsy_drone_racing
pixi run python -m scripts.overnight_mpcc audit \
  --output-dir /home/askho/repos/lsy_drone_racing/logs/mpcc-tuning/overnight-20261102T212955383826Z
```

Recheck preparation without simulations:

```sh
pixi run python -c 'from pathlib import Path; from scripts.overnight_mpcc import load_prepared; load_prepared(Path("logs/mpcc-tuning/overnight-prep-20261102T212955383826Z")); print("Preparation fingerprint matches")'
pixi run pytest -q tests/unit/control/test_overnight_mpcc.py tests/unit/control/test_mpcc_experimental.py
pixi run ruff check scripts/overnight_mpcc.py scripts/overnight_mpcc_analysis.py tests/unit/control/test_overnight_mpcc.py
```

Pending work: **all six overnight stages**, independent final analysis and a concise
human recommendation. The runner writes `study.json`, stage reports/audits/CSVs,
`recommendation.json`, combined `summary.csv`, and `analysis.md`. Adaptive decisions
and parent hashes live in `study.json`; exact effective settings are repeated in
each episode. The execution agent should also write a concise narrative results
document from these artifacts, clearly separating screening and holdout evidence.

Treat infrastructure failures as such, preserve artifacts, and use a reviewed new
preparation/migration if code changes are required. Do not edit fingerprinted
sources and silently resume. Do not change production defaults or deploy anything.

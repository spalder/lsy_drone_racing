These are small, testable controller changes. A minimal prototype now lives in
`lsy_drone_racing/control/attitude_mpcc_experimental.py`: it inherits the existing
optimizer and copies only the local spline correction method. The archived
controller, race configuration, and competition evaluator are unchanged.

| Parameter | Implementation and limits |
| --- | --- |
| `controller.mpcc_experiment.gate_center_snap` | `1` preserves baseline centering; `0` projects the previous crossing into the new gate plane and clips it to the usable opening. Intermediate values request partial recentering. The opening is eroded by the vehicle's bounding radius plus 2 cm. Approach/departure anchors follow the chosen crossing. This approximates retaining the previous path; it does not search for its exact intersection with the new plane. |
| `controller.mpcc_experiment.over_gate_lift` | Extra height in meters, applied as a smooth bump between the third gate's departure anchor and the fourth gate's approach anchor. It preserves crossing targets and retains the existing departure correction. This is a nominal-course experiment, not automatic body-aware clearance planning. |
| `controller.mpcc.obstacle_clearance` | Already supported; default `0.26` m from the pole axis. Larger values request more separation, but fixed anchors and the subsequent gate correction can still prevent it. Requested clearance is not achieved clearance. |
| `controller.mpcc_experiment.observed_obstacle_clearance` | Optional clearance override for observed poles during replanning only. Initial path correction and unrevealed poles keep `obstacle_clearance`. Revealed poles retain the override on later replans. |

All three reuse the existing spline and correction passes. They add no optimizer
states, constraints, horizon steps, or planner. Additional work is a small
calculation per gate and a vectorized height bump, only when track geometry
changes. No separate timing study of geometry rebuilds was performed.

`scripts/probe_mpcc.py` runs the original controller and a parameter grid on the
same ordered seeds, with a fresh controller each episode. It saves the source
configuration, grid settings, and per-episode CSV rows: outcome, gates passed,
completed steps/time, numerical failure ticks, control timing, and command hash.
For example, from the repository root:

```bash
SCIPY_ARRAY_API=1 pixi run python scripts/probe_mpcc.py \
  --seeds 7 1337 --snap 1 0 --output-dir /tmp/mpcc-centering
SCIPY_ARRAY_API=1 pixi run python scripts/probe_mpcc.py \
  --seeds 7 1337 --snap 1 --lift 0.1 --output-dir /tmp/mpcc-height
SCIPY_ARRAY_API=1 pixi run python scripts/probe_mpcc.py \
  --seeds 7 1337 --snap 1 --clearance 0.26 --observed-clearance 0.30 0.34 \
  --output-dir /tmp/mpcc-observed-poles
```

The pole command isolates increased clearance after observation, with baseline
centering and height. Omit `--observed-clearance` to retain the previous behavior;
use `--clearance` alone to change both initial planning and replanning.

Use a new output directory for each run. Multiple values form a Cartesian grid;
start with one parameter at a time. Run serially because generated acados files
share a working-directory path.

Ten smoke-test episodes covered two distinct seeds:

| Variant | Seed 7 | Seed 1337 |
| --- | --- | --- |
| Original | Finished, 9.84 s | Failed after 3/5 gates, 6.98 s |
| Experimental defaults | Finished, 9.84 s | Failed after 3/5 gates, 6.98 s |
| No centering (`snap=0`) | Finished, 9.80 s | Failed after 3/5 gates, 7.00 s |
| Extra height (`lift=0.1`, `snap=1`) | Finished, 9.76 s | Finished, 9.84 s |

Defaults matched the original command hashes exactly on both seeds. No numerical
failure ticks occurred. Three geometry tests passed: baseline equivalence after
revelation, retained crossing bounds/stability, and added height with preserved
gate targets. Lint and formatting checks passed. Times count completed control
steps and stop on the completion callback; existing evaluation CSVs use a different
time convention.

The height result warrants broader testing, but two seeds establish no general
improvement. Next compare centering and height separately on seeds 1–50 plus 1337,
then evaluate selected settings on untouched seeds 51–100. Compare paired wins,
regressions, completion rate, and lap times on jointly successful seeds. Test larger
pole offsets after checking their interaction with gate anchors. This harness
does not identify contact pairs or measure swept body clearance, so it cannot
prove which collision mechanism changed.

For a full isolated tuning study, run:

```bash
SCIPY_ARRAY_API=1 pixi run python scripts/tune_mpcc.py
```

Defaults evaluate the same seeds 1–20 for every value, serially: four parameters,
five values each, twenty runs per value (400 episodes). Every candidate starts
from baseline settings; no parameter combinations are tested.

| Parameter | Five default values |
| --- | --- |
| Observed pole clearance, replanning only (m) | 0.26, 0.28, 0.30, 0.32, 0.34 |
| Gate recentering fraction | 1, 0.75, 0.5, 0.25, 0 |
| Extra over-gate height (m) | 0, 0.05, 0.10, 0.15, 0.20 |
| Pole clearance, initial planning and replanning (m) | 0.26, 0.28, 0.30, 0.32, 0.34 |

The console prints one summary per completed twenty-run evaluation and the
absolute report path. `report.json` includes completion rate, average successful
time (null when no runs finish), exact controller settings, seeds, source hashes,
and per-seed outcomes for later combination studies. `summary.csv` provides one
row per value; `episodes.csv` preserves individual results. Simulation and solver
output goes to `simulation.log`. The JSON report is checkpointed after every
evaluation and marked completed, failed, or interrupted when the process exits.
Average times use successful episodes only, so compare completion rate alongside
time; different values may complete different subsets of seeds.

Results default to a new timestamped directory under `logs/mpcc-tuning/`, or set
`--output-dir` to a new directory explicitly. `--parameters` selects individual
studies; `--observed-clearance`, `--snap`, `--lift`, and `--clearance` each accept
one or more distinct values (five by default). `--seeds` overrides the common seed list.

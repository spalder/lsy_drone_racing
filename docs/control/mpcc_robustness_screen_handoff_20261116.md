Copy the prompt below into a new session in `/home/askho/repos/lsy_drone_racing`.

---

Execute only the prepared exploratory robustness screen. This prompt authorizes its 440 episodes and final screening report. Do not tune, combine changes, run additional smoke episodes, validate, deploy, modify the baseline controller, or resume any other campaign. Do not ask for routine confirmation.

Use `.pixi/envs/default/bin/python` throughout. The frozen executable is `docs/control/mpcc_robustness_screen_20261116_v1/screen.py`; its adjacent `manifest.json` is authoritative. Sources, environment, dependencies, seeds and settings are already prepared and fingerprinted. Do not rerun preparation or change frozen files.

Plan:

- A = F1_2 (`config_2470aab06585d4ce`), B = G07_pole_width_0p4375 (`config_3742dfc435fa9211`). A00 and B00 are unchanged controls. Preserve each parent's full settings, including its distinct gate offset and pole width.
- Each row below defines TWO independent screens, Axx and Bxx. Apply only that row's override relative to its parent; the launcher already does this. Everything else remains inherited.

| xx | Setting | Parent → trial | Hypothesis |
|---|---|---|---|
| 01 | `mpcc.reference_speed` | 2.3 → 2.2 m/s | More recovery time |
| 02 | `mpcc.contour_weight` | 800 → 900 | Stronger tracking |
| 03 | `mpcc.lag_weight` | 400 → 300 | Less along-path pressure |
| 04 | `mpcc.horizon_steps` | 40 → 50 | Preview 0.8 → 1.0 s |
| 05 | `mpcc_experiment.gate_center_snap` | 1.0 → 0.875 | Gentler recentering |
| 06 | `mpcc_experiment.over_gate_lift` | 0.15 → 0.175 m | More climb clearance |
| 07 | `mpcc.thrust_slew_weight` | 0.10 → 0.075 | Faster vertical correction |
| 08 | `mpcc.adaptation_rate` | 2.0 → 1.0 s⁻¹ | Smoother gain estimation |
| 09 | `mpcc.opening_margin` | 0.02 → 0.03 m | Greater gate-frame margin |
| 10 | `mpcc.pole_vertical_buffer` | 0.10 → 0.15 m | Retain avoidance during climb |

- Every configuration uses the SAME 20 seeds frozen in the manifest (proposed range 1611160000–1611160019; preparation checked local records and selected the first unused block). All cases retain the same environment/randomization distributions and 30 s simulated timeout. The launcher rotates configuration order by seed and checks exact initial-state fingerprints.
- Workload: 10 changes × 2 parents × 20 seeds = 400 variant episodes; 2 controls × 20 seeds = 40 control episodes; TOTAL = 440. Maximum simulated time = 13,200 s. No extra episodes are included or authorized.
- Rank each parent's cases by finishes descending, solver/fallback-affected episodes ascending, penalized mean time ascending, then controller-call p99 ascending. Failure penalty is 30 s; successful time is `(steps−1)/50`. Report rescues/regressions and paired time differences with shared-finish counts. Across parents, rank changes by minimum paired net finish gain, combined net gain, then health, mean penalized time and worst-parent call p99. Label improvements confined to one parent. Treat all findings as exploratory.

Execution:

1. Briefly state that you are starting the prepared screen. Run the following preflight; it validates files, dependencies and all settings without constructing an environment or solver:

   ```bash
   .pixi/envs/default/bin/python docs/control/mpcc_robustness_screen_20261116_v1/screen.py check
   ```

2. Run the full screen. Use the execution tool's persistent session support (`yield_time_ms: 1000`), retain its session ID, and keep the task active until the process exits:

   ```bash
   .pixi/envs/default/bin/python -u docs/control/mpcc_robustness_screen_20261116_v1/screen.py run
   ```

   The launcher runs serially under the shared acados lock, one fresh worker process per episode. It builds each configuration once and reuses its isolated cache with refreshed per-seed path bounds. Episode receipts are atomic and resumable; worker output goes to per-case logs. Do not launch another copy concurrently.

3. During collection, provide timer-based user updates EVERY FIVE MINUTES, containing ONLY `X/440`. The launcher emits an initial count, a count every 300 monotonic seconds (including unchanged counts), and a final count. Poll the running tool session at intervals no longer than 60 seconds; relay each timed count as commentary. If a tool returns immediately, use a clock wait of at most 60 seconds before polling again. Do not busy-poll. Do not end your turn while collection is active. Do not inspect outcomes, analyze, browse, edit code, spawn agents, or perform unrelated work while waiting. If resuming after a context loss, use the existing session when available; otherwise check for a live launcher before restarting. Obtain a count only when needed with:

   ```bash
   .pixi/envs/default/bin/python docs/control/mpcc_robustness_screen_20261116_v1/screen.py status
   ```

4. If interrupted, rerun the SAME `run` command; it verifies and skips complete receipts. Racing failures and solver/fallback ticks remain in the results. Do not delete a result, replace a seed or alter a setting. An infrastructure error stops collection. Inspect only the named case log; report the blocker if it cannot be resolved without changing frozen sources/dependencies/settings. A lock-busy error means another campaign is using the solver: wait for it without terminating that campaign. No analysis of partial results.

5. After the process exits successfully at 440/440, run exactly one analysis command:

   ```bash
   .pixi/envs/default/bin/python docs/control/mpcc_robustness_screen_20261116_v1/screen.py analyze
   ```

6. Read `docs/control/mpcc_robustness_screen_20261116_v1/report.md`. Give a concise final answer linking that report and `ranking.csv`, state 440/440 completed, and summarize the leading observed changes and any parent-specific tradeoff. Do not claim validation or population reliability. Stop; no follow-up experiments.

Preparation verification already performed: complete settings validation and synthetic orchestration/ranking tests. No simulator episodes were run during preparation. No real solver build or end-to-end episode has yet been exercised for this new launcher; its first scheduled case will exercise that path. If that fails, retain the logs and incomplete status.

# Run 20261125-073432

Run 16: from run 15a (final, iteration 190; 92.1% at 5.41 s on level 2). Combines both run-15 variants: crash penalty -30 + hover cutoff (5 s, -30) from 15a, plus the 15b speed cap (progress counts at most 1.5 m/s while the target gate is unrevealed). Goal: keep 15a's success rate while getting closer to 15b's lap time (5.12 s).

- Started: 2026-11-25 07:34
- Resumed from: runs/racer/20261124-232115
- Config: level2.toml
- Settings changed on the command line: resume=runs/racer/20261124-232115, config=level2.toml, air_start_frac=0.8, crash_penalty=30, stall_time=5, stall_penalty=30, unrevealed_speed_cap=1.5

## Result (2026-11-25)
Level 2, ground start, 1024 courses (eval_racer.py seeds 0-3), final checkpoint (iteration 190):
93.9% finished, median lap 5.32 s, best 4.94 s. Failures: pass 1 (gate 1) 25, pass 3 (gate 3) 24, pass 4 13, pass 2 1.
Snapshots: actor_it50.npz (92.8% at 5.47 s), actor_it100.npz (93.0% at 5.45 s); the lap time only dropped after iteration 100.

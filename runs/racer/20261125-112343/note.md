# Run 20261125-112343

Run 17b: from run 16 (final, iteration 190; 93.9% at 5.32 s on level 2). Parallel to run 17 (runs/racer/20261125-111428): same plain L2 progress distance (height_weight 4 -> 1), but the unrevealed speed cap is removed (1.5 m/s -> off). Crash -30 and hover cutoff (5 s at -30) stay and should be enough to discourage reckless flight. Motivation: the drone flies almost flat between gates 2 and 3, where the cap covers nearly the whole ~1.1 m leg. Goal: faster laps, especially on the gate 2 -> 3 leg.

- Started: 2026-11-25 11:23
- Resumed from: runs/racer/20261125-073432
- Config: level2.toml
- Settings changed on the command line: resume=runs/racer/20261125-073432, config=level2.toml, air_start_frac=0.8, crash_penalty=30, stall_time=5, stall_penalty=30, height_weight=1

## Result (2026-11-25)
Level 2, ground start, 1024 courses (eval_racer.py seeds 0-3), final checkpoint (iteration 190, 80 min):
96.0% finished, median lap 5.08 s, best 4.68 s. Failures: pass 0: 2, pass 1: 13, pass 2: 1, pass 3: 16, pass 4: 9.
Snapshots (512 courses, seeds 0-1): actor_it50.npz 92.4% at 5.12 s, actor_it100.npz 91.2% at 5.25 s, actor_it150.npz 94.9% at 5.08 s.
Per-leg on the fixed track (it150): 4.97 s vs run 13's 3.87 s; the gap is takeoff (+0.28 s), gate 1->2 (+0.30 s) and gate 2->3 (+0.40 s, 26 deg avg tilt vs 46 deg). Thrust at max only 21% of the time.

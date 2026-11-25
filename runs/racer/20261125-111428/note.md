# Run 20261125-111428

Run 17: from run 16 (final, iteration 190; 93.9% at 5.32 s on level 2). Only change: progress distance uses the plain L2 norm, height_weight 4 -> 1, so vertical offset counts the same as horizontal (sqrt(dx^2 + dy^2 + dz^2)). Everything else as run 16 (crash -30, hover cutoff 5 s at -30, 1.5 m/s unrevealed speed cap). Goal: faster laps, since the policy no longer gets extra progress for fixing height first.

- Started: 2026-11-25 11:14
- Resumed from: runs/racer/20261125-073432
- Config: level2.toml
- Settings changed on the command line: resume=runs/racer/20261125-073432, config=level2.toml, air_start_frac=0.8, crash_penalty=30, stall_time=5, stall_penalty=30, unrevealed_speed_cap=1.5, height_weight=1

## Stopped (2026-11-25)
Stopped at iteration 75 in favor of run 17b (runs/racer/20261125-112343, same change without the speed cap). Level-2 test at iteration 50 (512 courses, seeds 0-1, ground start): 89.6% at 5.32 s median, against 17b's 92.4% at 5.12 s. Last checkpoint (iteration 70) also saved as checkpoint_last.pt / actor_last.npz.

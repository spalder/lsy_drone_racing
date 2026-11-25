# Run 20261125-132421

Run 18 (mass input): from run 17b (final, iteration 190; 96.0% at 5.08 s on level 2). Only change: the true (randomized) drone mass is a new, 51st network input, scaled so the whole randomization range (nominal 0.0434 kg +- 0.005 kg) spans [0, 1] with the nominal mass at 0.5. The new input starts with zero weights (policy unchanged at the start); its obs statistics start at mean 0.5, var 1/12. Reward and all other settings as 17b. Goal: better thrust use (heavier/lighter drones) -> faster laps. Caveat: in deployment (racer_rl.py) the true mass is unknown and the input is fixed at 0.5 (nominal).

- Started: 2026-11-25 13:24
- Resumed from: runs/racer/20261125-112343
- Config: level2.toml
- Settings changed on the command line: resume=runs/racer/20261125-112343, config=level2.toml, air_start_frac=0.8, crash_penalty=30, stall_time=5, stall_penalty=30, height_weight=1

## Result (2026-11-25)
Level 2, ground start, 1024 courses (seeds 0-3), final checkpoint (iteration 190, 82 min):
- true mass input: 91.3% finished, median 4.91 s, best 4.46 s. Failures: pass 0: 2, 1: 16, 2: 16, 3: 41, 4: 14.
- mass input fixed at 0.5 (as racer_rl.py in deployment): 91.9% finished, median 4.92 s.
The mass input has no measurable effect (also at it50 and it100); the policy compensates for +-11.5% mass with feedback.
Compared with 17b (96.0% at 5.08 s): 0.17 s faster, ~5 points less success, from training longer, not from the mass.
Snapshots (512 courses, seeds 0-1, true mass): actor_it50.npz 91.2% at 4.99 s, actor_it100.npz 88.9% at 4.93 s.

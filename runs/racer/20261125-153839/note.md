# Run 20261125-153839

Run 18b: from run 17b (final, iteration 190; 96.0% at 5.08 s on level 2). Low-noise fine-tune: action noise std halved at the start (0.75/0.17/0.17 -> 0.38/0.09/0.09), entropy bonus off (ent_coef 0.01 -> 0) so the noise is not pushed back up, learning rate 3e-4 -> 1e-4. Reward as 17b (crash -30, hover cutoff -30). Idea: training noise (~16 deg random tilt per step) teaches safety margins the noise-free deployed policy does not need; less noise -> tighter, faster lines. Parallel to 18a (crash penalty -15).

- Started: 2026-11-25 15:38
- Resumed from: runs/racer/20261125-112343
- Config: level2.toml
- Settings changed on the command line: resume=runs/racer/20261125-112343, config=level2.toml, air_start_frac=0.8, stall_time=5, height_weight=1, crash_penalty=30, stall_penalty=30, sigma_scale=0.5, ent_coef=0, learning_rate=0.0001

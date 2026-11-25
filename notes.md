#details
network: 2x128
input: 50
output: 3

#legend
v: Velocity[[3]]
R: attitude[[9]]
g_t: positions of inner corners of target gate [[12]]
t_f: target gate unrevealed flag[[1]]
g_n: positions of inner corners of next gate [[12]]
n_f: next gate unrevealed flag[[1]]
poles: 4 poles' x,y, unrevealed flag [[12]]

c: mass normalized thrust 
roll, pitch: attitude setpoints

input vector: [[v, R, g_t, t_f, g_n, n_f, poles]]

output vector: [[c, roll, pitch]]

action mapping (network output a in [-1, 1]^3, a = 0 is near hover):
c = 9.81 + 9.0 * a_c, linear, past the range [1.97, 18.4] m/s^2 (env thrust 0.085-0.8 N / 0.0434 kg)
  a_c = 0 is hover at the nominal mass
  the ends are clipped: max thrust at a_c ~ 0.96 (tanh never outputs exactly 1), min thrust at a_c ~ -0.87
  checkpoints store c_offset / c_scale; runs before this change used 10.19 + 8.6 * a_c
thrust [N] = c * 0.0434 (nominal mass)
roll, pitch = pi/2 * a (full env range, needed to lead setpoints)
yaw = 0 (fixed)
env action: [roll, pitch, 0, thrust]



# RL racer: summary of runs (as of 2026-11-25)

## Goal and setup
PPO racer after Song et al. 2023 (literature/Song2023.pdf), trained on the level-2 track, deployed as a
numpy controller (lsy_drone_racing/control/racer_rl.py). Target: beat MPCC++ (~70% finished at 5.33 s on
level 2) and get the lap under 4 s.
- Code: control/racer_core.py (obs + action map), control/racer_env.py (reward, start states),
  control/train_racer.py (PPO), scripts/eval_racer.py (lap test), scripts/watch_racer.py.
- Train: `.pixi/envs/tests/bin/python lsy_drone_racing/control/train_racer.py --resume <run> --config level2.toml ... --note "..."`
  (`pixi run` does not work on this branch). One run uses ~5 of 10 cores, so two variants run in parallel.
- Runs live in runs/racer/<timestamp>/ (checkpoint.pt, actor.npz, progress.csv; note.md from run 15 on).
- Test = scripts/eval_racer.py on level2.toml, ground start, noise-free policy, 1024 courses (seeds 0-3).
  Training-log numbers (with exploration noise) say little: checkpoints with identical training stats
  differ by up to 0.17 s in the test. Always judge by the test.

## Reward (current, run 17b)
Per step at 50 Hz: r = 5 * progress - 0.01 * |omega|, +10 per gate pass, +10 extra at the finish.
progress = how much closer the drone got to the true center of the target gate (plain L2 distance).
Crash, out of bounds, invisible gate wall (crossing the target gate plane outside the opening) and the
hover cutoff (no gate pass for 5 s) all give -30 and end the episode. gamma = 0.99.
Note: nothing pays directly for a short lap; speed only pays through the discount.

## How we got here
1. Runs 1-12 (fixed track): finding a reward that does not hover or loop.
   - Pure progress at coef 1 -> hovering. Fixed with progress coef 5, height error weighted 4x, +10 per gate.
   - Mid-air starts (70% along the route with 0.28 m noise, 30% right in front of a gate) instead of only
     ground starts, so every leg gets trained.
   - Failed ideas: stall-only cutoff, approach points, wrong-way crash, via points (all led to hovering or
     to looping around the back of gate 1). The invisible gate wall fixed the looping instead.
2. Run 13 (fixed track, runs/racer/20261124-210945): 100% at 3.84 s, but only ~10% on randomized level 2.
   Lesson: the randomization has to be in training.
3. Run 14 (runs/racer/20261124-222045): level-2 randomization, 20% ground starts. ~44% at 4.7 s.
4. Run 15, two variants in parallel from run 14:
   - 15a (runs/racer/20261124-232115): crash -10 -> -30, plus the 5 s hover cutoff at -30 so that waiting is
     never safer than crashing. 92.1% at 5.41 s.
   - 15b (runs/racer/20261124-232118): progress capped at 1.5 m/s while the target gate is unrevealed
     (exact pose only known within 0.7 m). 87.8% at 5.12 s.
5. Run 16 (runs/racer/20261125-073432): 15a + the 15b speed cap. 93.9% at 5.32 s.
   (Lap time only dropped after iteration 100; don't stop runs early on training numbers.)
6. Run 17, two variants from run 16, both with plain L2 progress (height weight 4 -> 1):
   - 17 (runs/racer/20261125-111428): with the speed cap. Stopped at iteration 75 (89.6% at 5.32 s).
   - 17b (runs/racer/20261125-112343): speed cap removed; the -30 crash penalty alone keeps it careful.
     **96.0% at 5.08 s median, best 4.68 s. Current best policy.**

| Run | Change | Finished | Median lap |
|---|---|---|---|
| MPCC++ | reference | ~70% | 5.33 s |
| 14 | level-2 randomization | 44% | 4.7 s |
| 15a | crash -30 + hover cutoff | 92.1% | 5.41 s |
| 15b | speed cap 1.5 m/s | 87.8% | 5.12 s |
| 16 | 15a + speed cap | 93.9% | 5.32 s |
| 17b | plain L2, no speed cap | 96.0% | 5.08 s |

## Where the time goes (17b vs run 13 on the fixed track: 4.97 s vs 3.87 s)
- Lost on takeoff (+0.28 s), gate 1 -> 2 (+0.30 s) and gate 2 -> 3 (+0.40 s). Gate 2 -> 3 is flown almost
  flat (26 deg average tilt vs 46 deg in run 13), with the motors below hover for ~0.6 s.
- Not a thrust limit: averaged over the lap the motors run at 65% (hover 53%); a motor is at max in only
  ~2% of steps.
- Likely causes: the -30 crash penalty together with training noise (~15 deg random tilt per step) teaches
  wide safety margins, and the reward has no direct time pressure.
- Remaining failures: gate 3 (pole 3 sits on its approach axis) and gate 1.

## Next ideas (not run yet)
- 18a: crash penalty -30 -> -15 (trade some success for speed).
- 18b: low-noise fine-tune (ent_coef 0, action noise halved), so the policy trains for the noise-free flight
  it does at deployment.
- A time penalty per step for direct time pressure.
- Level 3 (randomized track layout): the policy crashes before gate 0. It only knows the level-2 layout;
  this needs training on randomized tracks.

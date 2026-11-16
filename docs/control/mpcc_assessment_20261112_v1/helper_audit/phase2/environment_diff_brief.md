# MPCC environment differences — preliminary evidence, NOT a selection decision

- Historical reference: `/home/askho/repos/lsy_drone_racing/logs/mpcc-compliance-20261103/official/main`.
- Reference config: available; official source files: 1.
- Environments: 19; unique cohorts: 596; configuration identities: 420.
- Current CSV identities agree with snapshot: **True**.
- Dataset normalization already excludes `env.seed` and `sim.render`; differences in those omitted fields CANNOT be evaluated here.
- Source SHA mismatch proves byte inequality, not a specific physical-model change.
- A matching `race_core.py` plus matching config cannot establish complete simulator/runtime equivalence.

## `race_core.py` provenance

- `match`: 4 environments
- `mismatch`: 6 environments
- `not_pinned`: 9 environments

## Per-environment review

| Environment | n cohorts | ≥70% configs | `race_core` | Config | Material/other changed fields |
|---|---:|---:|---|---|---:|
| `env_752b4b1bdb019cc1` | 191 | 59 | mismatch | different | 1 / 0 |
| `env_404376cdd03e85f3` | 287 | 28 | match | different | 1 / 0 |
| `env_143cf349695c0e2d` | 10 | 8 | mismatch | different | 1 / 0 |
| `env_6e464568817c697b` | 55 | 0 | match | different | 1 / 0 |
| `env_4508ff0ded365938` | 20 | 0 | not_pinned | different | 1 / 0 |
| `env_2b2f64b7027dd09d` | 11 | 0 | match | different | 1 / 0 |
| `env_e9021c7c69c7ff9a` | 5 | 0 | not_pinned | different | 1 / 0 |
| `env_43deaeb983f08ba7` | 3 | 0 | mismatch | recorded_config_missing | 0 / 0 |
| `env_bec9be4ed10f0747` | 3 | 0 | not_pinned | recorded_config_missing | 0 / 0 |
| `env_8d7c5e89d7daae2c` | 2 | 0 | not_pinned | different | 1 / 0 |
| `env_3b1649efc33ec7fa` | 1 | 0 | not_pinned | recorded_config_missing | 0 / 0 |
| `env_5605b3ef44e7b204` | 1 | 0 | not_pinned | recorded_config_missing | 0 / 0 |
| `env_5a2d01ae51d10ec1` | 1 | 0 | mismatch | recorded_config_missing | 0 / 0 |
| `env_605b42dafd054217` | 1 | 0 | not_pinned | recorded_config_missing | 0 / 0 |
| `env_6b4d949e990ea052` | 1 | 0 | mismatch | different | 1 / 0 |
| `env_9edc592edf4faef5` | 1 | 0 | not_pinned | different | 1 / 0 |
| `env_a68c049fdd4c2b45` | 1 | 0 | not_pinned | recorded_config_missing | 0 / 0 |
| `env_c8fa7d0521dec35f` | 1 | 0 | match | recorded_config_missing | 0 / 0 |
| `env_d9fe07842d13a590` | 1 | 0 | mismatch | recorded_config_missing | 0 / 0 |

## Interpretation guardrails

- Treat differences in dynamics, disturbances, randomization, drone parameters, control mode, track, sensors, frequency or episode rules as potentially material.
- Presentation-looking fields are **unverified**, not automatically harmless.
- Config difference labels depend on matching recorded keys. Missing configuration is an unknown, never a match.
- Use environment IDs to segregate non-equivalent studies; decide whether any near-equivalence is defensible only after reviewing concrete changes.
- The code-hash evidence includes only sources preserved in the reference; other dependencies remain unverified.

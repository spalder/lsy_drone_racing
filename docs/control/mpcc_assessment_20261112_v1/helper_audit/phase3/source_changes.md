# Source-level provenance review

Retained official file: `/home/askho/repos/lsy_drone_racing/logs/mpcc-compliance-20261103/official/main/lsy_drone_racing/envs/race_core.py`
Official SHA256: `06821466a5edb5fa67ed36cf7a5e3dc46640a44a6cd503e2b291787f10d82686`

**Caution:** Different hashes prove different bytes only. Matching one module is not full simulator equivalence.
Do not classify differences as physical or harmless without reading the affected logic.

## Historical versions

### `0a16409980429e8` (6 environment(s))

Environments: `env_143cf349695c0e2d;env_43deaeb983f08ba7;env_5a2d01ae51d10ec1;env_6b4d949e990ea052;env_752b4b1bdb019cc1;env_d9fe07842d13a590`

Located in `/home/askho/repos/lsy_drone_racing/lsy_drone_racing/envs/race_core.py`.

Diff lines: 18; changed lines containing relevant keywords: 1.

```diff
--- retained_official/race_core.py
+++ recorded_0a1640998042/race_core.py
@@ -40,6 +40,7 @@
 from gymnasium import spaces
 from scipy.spatial.transform import Rotation as R
 
+from lsy_drone_racing.envs.mjx_compat import install_box_contact_fix
 from lsy_drone_racing.envs.randomize import (
     build_full_track_randomization_fn,
     randomize_drone_inertia_fn,
@@ -363,6 +364,7 @@
             device: Device used for the environment and the simulation.
         """
         super().__init__()
+        install_box_contact_fix()
         # 1) Sanitize args
         if sim_config.freq % freq != 0:
             raise ValueError(f"({sim_config.freq=}) is no multiple of ({freq=})")
```

## Official attitude-mode evidence (static inspection only)

- Line 227: `control_mode: Literal["state", "attitude"], drone: Drone, dynamics: Dynamics`
- Line 232: `control_mode: The control mode to use. Either "state" for full-state control`
- Line 240: `if control_mode == "state":`
- Line 242: `if control_mode == "attitude":`
- Line 250: `raise ValueError(f"Invalid control mode: {control_mode}")`
- Line 341: `control_mode: Literal["state", "attitude"] = "state",`
- Line 356: `control_mode: Control mode for the drones. See `build_action_space` for details.`
- Line 386: `control=control_mode,`

Official configuration and controller deployment compliance require separate verification.
The retained official reference used `state` mode; attitude-mode source support alone does not demonstrate equivalence.

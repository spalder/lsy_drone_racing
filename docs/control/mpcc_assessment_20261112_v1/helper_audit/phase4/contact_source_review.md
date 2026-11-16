# Phase 4 contact-fix source comparison

Recorded SHA256 pins are authoritative for historical attribution.

# Source review: `lsy_drone_racing/envs/mjx_compat.py`

Exact recorded SHA256: `b2195f21c7183f9afc0d3d6d5edf96126503cd04ef497d635a9c6df48a97cfb2`
Source location: `/home/askho/repos/lsy_drone_racing/lsy_drone_racing/envs/mjx_compat.py`

Static inspection only. No functions below were called.

## Imports

- Line 20: `import jax.numpy as jp`
- Line 21: `import mujoco`
- Line 22: `from mujoco.mjx._src import collision_convex`
- Line 23: `from mujoco.mjx._src.collision_types import Collision, ConvexInfo`

## Entrypoint and local helpers

### `install_box_contact_fix` (lines 46–49)

**Call expressions:** 

**Assignment targets:** `collision_convex._box_box`

```python
  46  def install_box_contact_fix():
  47      """Patch only the tested affected release, before collision functions are traced."""
  48      if mujoco.__version__ == "3.10.0":
  49          collision_convex._box_box = _box_box
```

## Interpretation limits

- Hook presence plus matching module hashes identify a modified execution path, not its empirical effect.
- Monkeypatch/JAX/MJX changes can alter collision/contact physics; do not assume harmlessness.
- The official source is a retained reference, not proof of the full competition environment.


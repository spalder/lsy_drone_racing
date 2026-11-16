# Mechanistic interpretation of the frozen implementation

Source: `source/lsy_drone_racing/control/mpcc_broad_core.py`, especially `_update_gate_path()` and `compute_control()`; cost construction in `mpcc_broad_solver.py`.

G07 changes only `pole_width` from 0.39375 to 0.4375. This is the Gaussian width **along path progress** over which each pole-avoidance correction is spread, followed by projection that preserves gate anchors. It does not change the physical pole clearance threshold: `obstacle_clearance` remains 0.26 m. Wider support can change the bend and approach to a pole, but does not by itself prove a larger minimum physical separation. Paired rescue impacts and regressions are needed to assess the effect.

F1_2 changes only `gate_offset` from 0.180 to 0.162. This changes the approach/departure anchor positions and normal offsets around each gate; the center target remains unchanged with gate_center_snap=1.0. It changes local deformation geometry rather than moving the gate-center goal by 18 mm. A faster successful mean does not establish a robustness benefit.

The E09 0.05 and 0.075 candidates differ only in the attitude-rate cost from each other. Relative to F1 they also use pole_width=0.35, so E09-versus-F1 is not an isolated attitude-rate intervention. Their lower rate penalty permits less heavily penalized rotation rates, but any causal explanation based on that alone must remain a hypothesis. The direct E09 pair in Stage A isolates the weight within the same geometry.

All configurations use the same post-gate frame-clearance deformation, two RTI passes, state/control bounds and adaptation logic unless an explicit setting difference is recorded. Nonzero final solver status or non-finite predictions/inputs triggers the unique hover branch and solver reset. Status zero is not a guarantee of collision avoidance or globally optimal control.

Numerical status codes come from the pinned acados source `acados/utils/types.h`: ACADOS_QP_FAILURE=4. A log message giving underlying QP status=3 must not be mislabeled as acados status=3 (ACADOS_MINSTEP).

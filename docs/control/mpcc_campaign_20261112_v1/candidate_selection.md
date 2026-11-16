# Frozen candidate selection

Completion first; historical alpha rankings are contextual, correlated exploratory indicators. All ten suggested candidates retained to cover gate geometry, pole clearance, cost weighting, speed, and reference behavior. Equal E09 screening completion does not establish equivalence; both weights retained to expose state-specific rescues. F1/F1_2 is an explicit scientific question.

- **F1** `config_a460142e3d70aa79`: 84/100, exact lower 0.753; penalized 9.7794 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/combinations`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **F1_2** `config_2470aab06585d4ce`: 84/100, exact lower 0.753; penalized 9.7726 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/combinations`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **G07_pole_width_0p4375** `config_3742dfc435fa9211`: 84/100, exact lower 0.753; penalized 9.7854 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/isolated`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **E09_attitude_rate_weight_0p05** `config_c38f523f225d4537`: 76/100, exact lower 0.664; penalized 11.637 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/isolated`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **E09_attitude_rate_weight_0p075** `config_e5d615f48e78a5a5`: 76/100, exact lower 0.664; penalized 11.6512 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/isolated`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **G01_gate_offset_0p144** `config_dd387f0828a6f79d`: 74/100, exact lower 0.643; penalized 12.1418 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/isolated`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **E02_contour_weight_700** `config_333607745da71732`: 73/100, exact lower 0.632; penalized 12.3726 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/isolated`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **F2** `config_4f870307a460c27a`: 73/100, exact lower 0.632; penalized 12.405 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/combinations`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **REF** `config_040437a726eb52b8`: 73/100, exact lower 0.632; penalized 12.409600000000001 s; complexity 2. Source `logs/mpcc-tuning/focused-20261103T190200Z/combinations`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.
- **RECHECK_R24** `config_ed7e53a4a9e93552`: 47/60, exact lower 0.658; penalized 10.988 s; complexity 2. Source `logs/mpcc-tuning/speed-ladder-20261103T215400Z/step-07-RECHECK_R24`; common historical `env_404376cdd03e85f3`. Complete settings and verified implementation/library hashes in manifest.

Excluded: F1_2_3 and F1_3 (73/100, redundant multi-change relatives); small n geometry variants (less precision, redundant). Modified-core incumbent and opt_a758e8cb3e87 have substantial independent evidence but different legacy implementation and slower 9.6–9.8 s behavior; retain environment-specific evidence rather than replacing a more informative official-core candidate. No historical samples pooled. Missing timing is not zero. Original 106 PASS audit not repeated.

## Effective settings and trade-offs

All candidates use the same broad-core/solver/geometry implementation. Complete settings, not labels, define identity. Differences below are relative to F1; geometry settings are included.

### F1

Differences: `{}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.191422817444877; independent validation cohorts: 0.

### F1_2

Differences: `{"mpcc.gate_offset": {"F1": 0.18, "candidate": 0.162}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.1872140670826834; independent validation cohorts: 0.

### G07_pole_width_0p4375

Differences: `{"mpcc.pole_width": {"F1": 0.39375, "candidate": 0.4375}}`. Historical solver ticks: 13.0; fallback ticks: missing; mean call ms: 2.209641765750812; independent validation cohorts: 0.

### E09_attitude_rate_weight_0p05

Differences: `{"mpcc.attitude_rate_weight": {"F1": 0.1, "candidate": 0.05}, "mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.201951403501046; independent validation cohorts: 0.

### E09_attitude_rate_weight_0p075

Differences: `{"mpcc.attitude_rate_weight": {"F1": 0.1, "candidate": 0.075}, "mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.204399420574058; independent validation cohorts: 0.

### G01_gate_offset_0p144

Differences: `{"mpcc.gate_offset": {"F1": 0.18, "candidate": 0.144}, "mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.1836583585908573; independent validation cohorts: 0.

### E02_contour_weight_700

Differences: `{"mpcc.contour_weight": {"F1": 800, "candidate": 700}, "mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.177656476738501; independent validation cohorts: 0.

### F2

Differences: `{"mpcc.gate_offset": {"F1": 0.18, "candidate": 0.162}, "mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.1738602175757578; independent validation cohorts: 0.

### REF

Differences: `{"mpcc.pole_width": {"F1": 0.39375, "candidate": 0.35}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.1903566479833363; independent validation cohorts: 0.

### RECHECK_R24

Differences: `{"mpcc.reference_speed": {"F1": 2.3, "candidate": 2.4}}`. Historical solver ticks: 0.0; fallback ticks: missing; mean call ms: 2.274617432797061; independent validation cohorts: 0.

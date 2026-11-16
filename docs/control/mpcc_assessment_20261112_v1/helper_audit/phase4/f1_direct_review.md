# Direct F1 / F1_2 episode comparison

The reported completion fractions are not themselves direct paired evidence.
This script matches stored seed IDs within one cohort group/environment/implementation;
when initial states are missing it reports both provisional and strict subsets.

## Selected cohorts

- **F1**: config `config_a460142e3d70aa79`, cohort `cohort_ced5195525a73529`, 84/100, group `logs/mpcc-tuning/focused-20261103T190200Z/combinations`.
- **F1_2**: config `config_2470aab06585d4ce`, cohort `cohort_13b826dd1a54a917`, 84/100, group `logs/mpcc-tuning/focused-20261103T190200Z/combinations`.

## Full nested settings differences (1)

- `settings_json.mpcc.gate_offset`: F1 `0.18`, F1_2 `0.162`

## Direct statistics

### F1__vs__F1_2 — all_matching_seeds_excluding_known_mismatches

- Matching: n=100, unknown initial states=100, excluded different states=0.
- Right-side rescues=2; regressions=2; net gain=0.0 pp.
- Exact McNemar p=1.0; exploratory bootstrap CI for paired completion gain [-4.0, 4.0] pp.
- Both finished=82, comparable successful times=82; paired mean right-minus-left time=-0.005609756097560975 s.
- Status: `provisional_when_initial_states_missing`.

### F1__vs__F1_2 — strict_verified_states

- Matching: n=0, unknown initial states=0, excluded different states=0.
- Right-side rescues=0; regressions=0; net gain= pp.
- Exact McNemar p=; exploratory bootstrap CI for paired completion gain [, ] pp.
- Both finished=0, comparable successful times=0; paired mean right-minus-left time= s.
- Status: `fully_state_verified`.

### REF__vs__F1 — all_matching_seeds_excluding_known_mismatches

- Matching: n=100, unknown initial states=100, excluded different states=0.
- Right-side rescues=13; regressions=2; net gain=11.0 pp.
- Exact McNemar p=0.00738525390625; exploratory bootstrap CI for paired completion gain [4.0, 19.0] pp.
- Both finished=71, comparable successful times=71; paired mean right-minus-left time=0.026760563380281672 s.
- Status: `provisional_when_initial_states_missing`.

### REF__vs__F1 — strict_verified_states

- Matching: n=0, unknown initial states=0, excluded different states=0.
- Right-side rescues=0; regressions=0; net gain= pp.
- Exact McNemar p=; exploratory bootstrap CI for paired completion gain [, ] pp.
- Both finished=0, comparable successful times=0; paired mean right-minus-left time= s.
- Status: `fully_state_verified`.

### REF__vs__F1_2 — all_matching_seeds_excluding_known_mismatches

- Matching: n=100, unknown initial states=100, excluded different states=0.
- Right-side rescues=14; regressions=3; net gain=11.0 pp.
- Exact McNemar p=0.012725830078125; exploratory bootstrap CI for paired completion gain [3.0, 19.0] pp.
- Both finished=70, comparable successful times=70; paired mean right-minus-left time=0.021142857142857137 s.
- Status: `provisional_when_initial_states_missing`.

### REF__vs__F1_2 — strict_verified_states

- Matching: n=0, unknown initial states=0, excluded different states=0.
- Right-side rescues=0; regressions=0; net gain= pp.
- Exact McNemar p=; exploratory bootstrap CI for paired completion gain [, ] pp.
- Both finished=0, comparable successful times=0; paired mean right-minus-left time= s.
- Status: `fully_state_verified`.

## Cross-checks against existing paired_comparisons.csv

- `F1__vs__F1_2`: **no_preexisting_direct_pair**. 
- `REF__vs__F1`: **MATCH**. 
- `REF__vs__F1_2`: **MATCH**. 

## Limitations

- This does not constitute new independent validation.
- Matching only seed IDs does not establish identical initial states; missing states are labelled.
- Cross-cohort comparisons require identical recorded implementation, environment and cohort group.
- Clopper–Pearson intervals are in the source CSV; paired bootstrap intervals are exploratory and unadjusted.
- Saved adjusted/instrumented computation times cannot be directly compared with raw whole-call times.

Oldest → newest, ordered by saved episode-result timestamp (Oslo time). Repeated configuration tests are separate rows; diagnostic and smoke tests are included. Average is simulated race time among successful episodes; — means no finishes. Completion is successful episodes / tested episodes. Copied analysis datasets and aggregate reports are excluded; the frozen 3+27 episode continuation is combined.

| # | Test set | Config | Avg time (s) | Completion | Finished / episodes |
|---:|---|---|---:|---:|---:|
| 1 | Departure B3 | S30_A75 | 4.938 | 36.7% | 11/30 |
| 2 | Departure B3 | S28_P9 | 5.188 | 70.0% | 21/30 |
| 3 | Departure B3 | S28_D20 | 5.029 | 60.0% | 18/30 |
| 4 | Departure B3 | S28_D20_P9 | 5.182 | 73.3% | 22/30 |
| 5 | Departure B3 | S28_CAP28 | 5.035 | 56.7% | 17/30 |
| 6 | Departure B3 | S32_AMBITIOUS | 4.789 | 36.7% | 11/30 |
| 7 | Departure B3 | S30_RTI3 | 4.844 | 50.0% | 15/30 |
| 8 | Departure B4 | incumbent_S28_D20 | 5.022 | 53.0% | 53/100 |
| 9 | Departure B4 | S30_RTI3 | 4.859 | 46.0% | 46/100 |
| 10 | Departure B4 | S30_RTI3_A875 | 4.815 | 46.0% | 46/100 |
| 11 | Departure B5 | incumbent_S28_D20 | 5.032 | 44.0% | 44/100 |
| 12 | Departure B5 | S30_A875_P9 | 4.936 | 44.0% | 44/100 |
| 13 | Departure B6 | incumbent_S28_D20 | 5.049 | 56.7% | 17/30 |
| 14 | Departure B6 | S30_P9_POLE44 | 5.019 | 56.7% | 17/30 |
| 15 | Departure B6 | S30_P9_H45 | 5.034 | 43.3% | 13/30 |
| 16 | Prediction smoke | baseline | 4.740 | 100.0% | 2/2 |
| 17 | Prediction smoke | combined_example | 4.700 | 50.0% | 1/2 |
| 18 | Speed32 | default | 4.852 | 33.3% | 10/30 |
| 19 | Speed32 | classical | 4.852 | 33.3% | 10/30 |
| 20 | Speed32 | LM1e4 | 4.852 | 33.3% | 10/30 |
| 21 | Numerics triage | default | 4.771 | 45.0% | 9/20 |
| 22 | Numerics triage | classical | 4.771 | 45.0% | 9/20 |
| 23 | Numerics triage | LM1e4 | 4.771 | 45.0% | 9/20 |
| 24 | Numerics triage | classical_LM1e4 | 4.771 | 45.0% | 9/20 |
| 25 | Selected numerics | default | — | 0.0% | 0/2 |
| 26 | Selected numerics | classical | — | 0.0% | 0/2 |
| 27 | Selected numerics | LM1e4 | — | 0.0% | 0/2 |
| 28 | Selected numerics | classical_LM1e4 | — | 0.0% | 0/2 |
| 29 | QP snapshots | default | — | 0.0% | 0/2 |
| 30 | Soft attitude | parent | 4.851 | 43.3% | 13/30 |
| 31 | Soft attitude | soft | 4.849 | 43.3% | 13/30 |
| 32 | Autonomous smoke | baseline | 4.900 | 100.0% | 1/1 |
| 33 | Autonomous smoke | combined_example | 4.800 | 100.0% | 1/1 |
| 34 | Autonomous screen | baseline | 4.789 | 50.0% | 15/30 |
| 35 | Autonomous screen | drag_05 | 4.716 | 50.0% | 15/30 |
| 36 | Autonomous screen | drag_10 | 4.651 | 60.0% | 18/30 |
| 37 | Autonomous screen | drag_15 | 4.630 | 40.0% | 12/30 |
| 38 | Autonomous screen | attitude_09 | 4.819 | 46.7% | 14/30 |
| 39 | Autonomous screen | attitude_11 | 4.776 | 50.0% | 15/30 |
| 40 | Autonomous screen | attitude_gain_11 | 4.827 | 56.7% | 17/30 |
| 41 | Autonomous screen | ema_4 | 4.801 | 46.7% | 14/30 |
| 42 | Autonomous screen | scalar_kf | 4.794 | 46.7% | 14/30 |
| 43 | Autonomous screen | combined_example | 4.707 | 53.3% | 16/30 |
| 44 | Covariance smoke | baseline | — | 0.0% | 0/1 |
| 45 | Covariance smoke | scalar_kf | — | 0.0% | 0/1 |
| 46 | Covariance smoke | drag_005 | — | 0.0% | 0/1 |
| 47 | Covariance screen | baseline | 4.917 | 46.7% | 14/30 |
| 48 | Covariance screen | scalar_kf | 4.911 | 46.7% | 14/30 |
| 49 | Covariance screen | kf_p0_0001 | 4.923 | 46.7% | 14/30 |
| 50 | Covariance screen | kf_p0_0005 | 4.909 | 46.7% | 14/30 |
| 51 | Covariance screen | kf_p0_0100 | 4.923 | 50.0% | 15/30 |
| 52 | Covariance screen | kf_q_00008 | 4.858 | 40.0% | 12/30 |
| 53 | Covariance screen | kf_q_008 | 4.949 | 43.3% | 13/30 |
| 54 | Covariance screen | kf_r_0025 | 4.916 | 46.7% | 14/30 |
| 55 | Covariance screen | kf_r_0400 | 4.874 | 43.3% | 13/30 |
| 56 | Covariance screen | drag_005 | 4.875 | 50.0% | 15/30 |
| 57 | Covariance screen | drag_015 | 4.860 | 50.0% | 15/30 |
| 58 | Covariance screen | drag_030 | 4.830 | 53.3% | 16/30 |
| 59 | Replay 00 | baseline | 5.120 | 100.0% | 1/1 |
| 60 | Replay 00 | drag_015 | — | 0.0% | 0/1 |
| 61 | Replay 00 | drag_030 | — | 0.0% | 0/1 |
| 62 | Replay 01 | baseline | — | 0.0% | 0/1 |
| 63 | Replay 01 | drag_05 | — | 0.0% | 0/1 |
| 64 | Replay 01 | drag_10 | — | 0.0% | 0/1 |
| 65 | Replay 02 | baseline | 4.840 | 100.0% | 1/1 |
| 66 | Replay 02 | drag_030 | 4.780 | 100.0% | 1/1 |
| 67 | QP capture baseline | case-00-baseline | 5.120 | 100.0% | 1/1 |
| 68 | QP capture drag030 | case-01-drag_030 | — | 0.0% | 0/1 |
| 69 | QP capture drag10 | case-02-drag_10 | — | 0.0% | 0/1 |
| 70 | QP repair screen | baseline | 4.857 | 53.3% | 16/30 |
| 71 | QP repair screen | drag_030 | 4.805 | 56.7% | 17/30 |
| 72 | QP repair screen | repaired_drag_030 | 4.806 | 56.7% | 17/30 |
| 73 | QP diagnosis drag030 | drag_030 | — | 0.0% | 0/1 |
| 74 | QP diagnosis repaired | repaired_drag_030 | — | 0.0% | 0/1 |
| 75 | Pitch diagnostic | diagnostic_cap10 | — | 0.0% | 0/1 |
| 76 | Pitch diagnostic | diagnostic_expanded | — | 0.0% | 0/1 |
| 77 | Pitch calibration | baseline_hard | — | 0.0% | 0/1 |
| 78 | Pitch calibration | soft_reference | — | 0.0% | 0/1 |
| 79 | Pitch calibration | speed33_combined | — | 0.0% | 0/1 |
| 80 | Pitch screen | baseline_hard | 4.840 | 46.7% | 14/30 |
| 81 | Pitch screen | soft_reference | 4.839 | 46.7% | 14/30 |
| 82 | Pitch screen | speed_33 | 4.648 | 33.3% | 10/30 |
| 83 | Pitch screen | speed_36 | 4.420 | 23.3% | 7/30 |
| 84 | Pitch screen | drag_030 | 4.760 | 53.3% | 16/30 |
| 85 | Pitch screen | speed33_drag | 4.516 | 36.7% | 11/30 |
| 86 | Pitch screen | speed36_drag | 4.392 | 16.7% | 5/30 |
| 87 | Pitch screen | attitude11 | 4.797 | 50.0% | 15/30 |
| 88 | Pitch screen | speed33_attitude | 4.644 | 30.0% | 9/30 |
| 89 | Pitch screen | speed33_combined | 4.525 | 40.0% | 12/30 |
| 90 | Pitch screen | speed33_tracking | 4.440 | 13.3% | 4/30 |
| 91 | Pitch screen | speed33_thrust | 4.538 | 33.3% | 10/30 |
| 92 | Bound repair diagnostic | baseline_hard | 4.770 | 100.0% | 2/2 |
| 93 | Bound repair diagnostic | drag_030 | 4.720 | 100.0% | 2/2 |
| 94 | Bound repair screen | baseline_hard | 4.784 | 36.7% | 11/30 |
| 95 | Bound repair screen | soft_reference | 4.782 | 36.7% | 11/30 |
| 96 | Bound repair screen | drag_030 | 4.740 | 40.0% | 12/30 |
| 97 | Robustness diagnostic | drag_030_parent | — | 0.0% | 0/2 |
| 98 | Robustness diagnostic | drag030_slew_003 | — | 0.0% | 0/2 |
| 99 | Robustness screen | drag_030_parent | 4.784 | 36.7% | 11/30 |
| 100 | Robustness screen | drag030_slew_003 | 4.792 | 33.3% | 10/30 |

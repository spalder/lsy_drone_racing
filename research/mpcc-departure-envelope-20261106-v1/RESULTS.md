# Departure-envelope comparison: retained compact results

Racing was stopped at the user’s request after115/200 episodes. The full saved-array audit completed successfully for all115 episodes, with zero errors. The original aborted v1 study is separate and is not pooled.

| Candidate | Finishes / completed | Exact95% completion interval | Numerical/fallback ticks | Constraint violations | Median/p99 latency ms | >20ms ticks |
|---|---|---|---|---:|---|---|
| fixed_envelope | 16/58 | 16.7%–40.9% | 2/2 | 0 | 109.26/238.10 | 10028/10028 |
| attitude_envelope | 16/57 | 17.0%–41.5% | 2/2 | 0 | 109.14/237.90 | 9975/9975 |

Paired successful official times: {"shared_successes": 16, "seeds": [1611010102, 1611010105, 1611010106, 1611010109, 1611010114, 1611010115, 1611010122, 1611010124, 1611010130, 1611010133, 1611010134, 1611010141, 1611010144, 1611010151, 1611010154, 1611010155], "attitude_minus_fixed_s": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "mean_s": 0.0, "median_s": 0.0, "mean_bootstrap95_ci_s": [0.0, 0.0], "interpretation": "Paired official lap times on shared successful seeds only; no failure-time speed ranking; exploratory percentile bootstrap, not a reliability or superiority claim"}

Both implementations are far above the20ms control budget. These are incomplete, stopped-study results; no candidate is promoted. Native V3 settings remained unchanged. V2 repaired terminal departure release; the original v1 failure and all v1 records remain separate.

The archive retains per-episode outcomes, configurations, credited crossings, contacts, measured observations, commands, numerical/fallback evidence, passive solver statistics, controller/diagnostic timings, frozen source snapshots, provenance and audit reports. Full horizon, warm-start and path arrays are omitted from this compact export; their originals remain on Ask-USB. Failure/partial evidence is retained. The compact package is sufficient to inspect outcomes and telemetry, but full solver-iterate re-analysis requires the USB originals.

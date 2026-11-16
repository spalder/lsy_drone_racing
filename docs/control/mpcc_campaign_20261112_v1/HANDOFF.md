# Completed campaign

All frozen simulations and final deliverables are complete: Stage A 10×100, Stage B 5×200, Stage C 3×500; 3,500 measured episodes. Smoke and diagnostic replays are separate. See final_report.md, final_rankings.csv, recommended_configuration.json and audit.json. Historical pause.json and resume.json remain as execution provenance.

To regenerate and validate derived artifacts from the repository root:
```bash
LD_LIBRARY_PATH="$PWD/acados/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" .pixi/envs/default/bin/python docs/control/mpcc_campaign_20261112_v1/finalize.py
```

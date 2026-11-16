"""Regenerate and validate all derived deliverables after frozen simulations finish."""
import pathlib,subprocess,sys,json,hashlib,datetime,csv
D=pathlib.Path(__file__).resolve().parent
assert (D/'COMPLETE').exists(),'Complete orchestrate.py first'
for name in ['analyze.py','audit.py','diagnostics.py','technical_findings.py','health_inference.py','diagnose_warning.py','replay_numerics.py','replay_cached_numerics.py','report.py']:
 with (D/(name+'.log')).open('w') as f:subprocess.run([sys.executable,str(D/name)],stdout=f,stderr=subprocess.STDOUT,check=True)
(D/'FINALIZED').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')
(D/'HANDOFF.md').write_text('# Completed campaign\n\nAll frozen simulations and final deliverables are complete: Stage A 10×100, Stage B 5×200, Stage C 3×500; 3,500 measured episodes. Smoke and diagnostic replays are separate. See final_report.md, final_rankings.csv, recommended_configuration.json and audit.json. Historical pause.json and resume.json remain as execution provenance.\n\nTo regenerate and validate derived artifacts from the repository root:\n```bash\nLD_LIBRARY_PATH="$PWD/acados/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" .pixi/envs/default/bin/python docs/control/mpcc_campaign_20261112_v1/finalize.py\n```\n')
files=[]
for p in sorted(D.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name not in ['artifact_inventory.csv'] and not p.name.endswith('.tmp'):
  files.append(dict(path=str(p.relative_to(D)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
with (D/'artifact_inventory.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['path','bytes','sha256']);w.writeheader();w.writerows(files)
print('Finalized',len(files),'artifacts')

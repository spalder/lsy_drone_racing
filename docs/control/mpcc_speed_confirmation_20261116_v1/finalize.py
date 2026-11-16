"""Produce and verify follow-up artifacts after all 600 measured episodes."""
import pathlib,subprocess,sys,csv,json,hashlib,datetime
D=pathlib.Path(__file__).resolve().parent
for name in ['analyze.py','audit.py']:
 with (D/(name+'.log')).open('w') as f:subprocess.run([sys.executable,str(D/name)],stdout=f,stderr=subprocess.STDOUT,check=True)
rows=list(csv.DictReader((D/'metrics.csv').open()));assert len(rows)==6 and all(int(r['n'])==100 for r in rows)
# Update the user's threshold table without retesting or changing any parameters.
R=D.parents[2];hist=list(csv.DictReader((R/'docs/control/mpcc_assessment_20261112_v1/configuration_metrics.csv').open()))
allrows={r['configuration_id']:dict(candidate=r['case_name'],n=int(r['episodes']),finishes=int(r['finishes']),completion=float(r['completion_rate']),mean_success_time_s=float(r['mean_success_time_s']),evidence=r['cohort_role']) for r in hist if r['identity_status']=='resolved' and r['primary_eligible']=='1' and r['environment_provenance_group']=='retained_official_core_match' and int(r['episodes'])>=5 and r['mean_success_time_s']}
for r in csv.DictReader((R/'docs/control/mpcc_campaign_20261112_v1/final_rankings.csv').open()):
 key=r['historical_configuration_id']
 if key not in allrows or int(r['n'])>=allrows[key]['n']:allrows[key]=dict(candidate=r['candidate'],n=int(r['n']),finishes=int(r['finishes']),completion=float(r['completion']),mean_success_time_s=float(r['successful_mean_s']),evidence=r['validation_status'])
for r in rows:
 allrows[r['historical_configuration_id']]=dict(candidate=r['candidate'],n=100,finishes=int(r['finishes']),completion=float(r['completion']),mean_success_time_s=float(r['mean_success_time_s']),evidence='new 100-episode confirmation')
thresholds=[]
for tick in range(60,42,-1):
 t=tick/10;xs=sorted((r for r in allrows.values() if r['mean_success_time_s']<t),key=lambda r:(-r['completion'],-r['n'],r['mean_success_time_s']))
 thresholds.append(dict(limit_s=t,**xs[0]) if xs else dict(limit_s=t,candidate='none',n='',finishes='',completion='',mean_success_time_s='',evidence=''))
with (D/'updated_threshold_table.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(thresholds[0]));w.writeheader();w.writerows(thresholds)
lines=['# Updated 0.1-second threshold table','', 'Minimum five episodes; largest eligible cohort per configuration, new confirmation superseding its historical screening. Times condition on successful races. Results from different exact historical environments are not a common-environment comparison.','', '| Under average time | Configuration | Completion | Successful mean | Evidence |','|---|---|---|---|---|']
for r in thresholds:
 if r['candidate']=='none':lines.append(f"| {r['limit_s']:.1f} s | None | — | — | — |")
 else:lines.append(f"| {r['limit_s']:.1f} s | {r['candidate']} | {100*r['completion']:.1f}% ({r['finishes']}/{r['n']}) | {r['mean_success_time_s']:.3f} s | {r['evidence']} |")
lines+=['', 'Small screening leaders newly appearing in this updated table remain unconfirmed. This follow-up tested the six configurations selected from the previous table; it does not automatically validate every newly appearing leader.']
(D/'updated_threshold_table.md').write_text('\n'.join(lines)+'\n')
# Check deterministic regeneration of the primary summaries.
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=['metrics.csv','episodes.csv','paired_comparisons.csv'];before={p:sha(D/p) for p in files}
subprocess.run([sys.executable,str(D/'analyze.py')],stdout=subprocess.DEVNULL,check=True);assert before=={p:sha(D/p) for p in files}
(D/'regeneration_check.json').write_text(json.dumps(dict(status='PASS',sha256=before),indent=2))
(D/'COMPLETE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat()+'\n')
(D/'HANDOFF.md').write_text('# Completed speed confirmation\n\nAll six configurations completed exactly 100 new matched episodes (600 total), with technical smoke excluded. Source/formulation, exact initial-state pairing and episode/metric audits passed. See report.md, metrics.csv, paired_comparisons.csv, updated_threshold_table.csv and audit.json.\n\nRegenerate with `.pixi/envs/default/bin/python docs/control/mpcc_speed_confirmation_20261116_v1/finalize.py`. Resume missing simulations with the frozen `run.py --stage validation --cache`.\n')
artifacts=[]
for p in sorted(D.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name!='artifact_inventory.csv' and not p.name.endswith('.tmp'):artifacts.append(dict(path=str(p.relative_to(D)),bytes=p.stat().st_size,sha256=sha(p)))
with (D/'artifact_inventory.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['path','bytes','sha256']);w.writeheader();w.writerows(artifacts)
print('Complete: 600 fresh episodes; all checks passed')

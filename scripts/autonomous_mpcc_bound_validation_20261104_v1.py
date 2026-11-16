"""Validate exact runtime roundtrip repair on every frozen case/seed without racing."""
import copy,subprocess,time
from pathlib import Path
import autonomous_expanded_pitch_bound_repair_20261104_v2 as base
ROOT=base.ROOT;OUT=base.OUT/'roundtrip-validation-v1';RUNNER=ROOT/'scripts/mpcc_prediction_research_expanded_pitch_bound_repair_20261104_v2.py'
SOURCES=[Path(__file__),RUNNER,ROOT/'scripts/mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v2.py',ROOT/'scripts/mpcc_bound_roundtrip_20261104_v1.py']
def main():
 OUT.mkdir(exist_ok=False);p=copy.deepcopy(base.read(base.OUT/'screen/plan.json'))
 p.update(stage='screen',construction_only=True,prediction_seeds=[])
 p['hashes'].update({str(f):base.sha(f) for f in SOURCES});base.write(OUT/'plan.json',p)
 with (OUT/'console.log').open('x') as log:
  rc=subprocess.call([str(base.PYTHON),str(RUNNER),'run',str(OUT)],cwd=ROOT,env=base.ENV,stdout=log,stderr=subprocess.STDOUT)
 status='BLOCKED';detail=[]
 if rc==0:
  import analyze_expanded_pitch_bound_repair_20261104_v1 as audit
  for case in p['case_order']:
   folder=OUT/'run-v1'/case;rows=base.read(folder/'constructions.json');assert [r['seed'] for r in rows]==p['seeds']
   assert len({r['runtime']['library'] for r in rows})==30
   for ep in rows:
    r=ep['runtime'];audit.audit_runtime(folder,ep,dict(runtime_initial=r,runtime_final=r,ticks=[]),p,case)
    assert all(x['ubx'][-1]==r['path_length'] for x in r['stages'][1:])
    repair=r['roundtrip_repair'];assert repair['getter_observable_state_preserved']
    detail.append(dict(case=case,seed=ep['seed'],path_length=r['path_length'],changed_stages=repair['changed_stages'],max_ulps=max(x['ulps'] for x in repair['rows']),construction_s=ep['construction_s'],library=r['library']))
  assert all(d['changed_stages']==0 for d in detail if d['case']=='baseline_hard' and d['seed'] in p['seeds'][:3])
  status='COMPLETED'
 base.write(OUT/'execution-summary.json',dict(status=status,rc=rc,constructions=len(detail),racing_episodes=0,details=detail,independent_runtime_audit=status=='COMPLETED',completed_episode_bounds_unchanged=status=='COMPLETED'))
if __name__=='__main__':main()

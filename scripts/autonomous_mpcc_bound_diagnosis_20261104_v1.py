"""Detached deterministic construction-only diagnosis; never races."""
import copy,json,subprocess,sys,time,hashlib
from pathlib import Path
import autonomous_expanded_pitch_bound_repair_20261104_v2 as base
ROOT=base.ROOT;OUT=base.OUT/'seed1603803-diagnosis-v1';RUNNER=ROOT/'scripts/mpcc_bound_capture_runner_20261104_v1.py'
def main():
 OUT.mkdir(exist_ok=False)
 p=copy.deepcopy(base.read(base.OUT/'screen/plan.json'));p.update(stage='smoke',construction_only=True,seeds=list(range(1603800,1603804)),prediction_seeds=[])
 p['hashes'].update({str(f):base.sha(f) for f in [Path(__file__),RUNNER,ROOT/'scripts/mpcc_bound_capture_20261104_v1.py']})
 base.write(OUT/'plan.json',p)
 with (OUT/'console.log').open('x') as log:
  rc=subprocess.call([str(base.PYTHON),str(RUNNER),'run',str(OUT)],cwd=ROOT,env=base.ENV,stdout=log,stderr=subprocess.STDOUT)
 captures=[]
 for f in sorted((OUT/'run-v1').glob('*/capture-seed-*.json')):
  d=base.read(f);bad=[r for r in d['rows'] if not r['exact']];captures.append(dict(case=f.parent.name,seed=d['seed'],original_passed=d['original_validation_passed'],differences=bad,getter_preserved=d['getter_observable_state_preserved'],library=d['library']))
 base.write(OUT/'execution-summary.json',dict(status='COMPLETED' if rc==0 and len(captures)==12 else 'BLOCKED',racing_episodes=0,rc=rc,captures=captures))
if __name__=='__main__':main()

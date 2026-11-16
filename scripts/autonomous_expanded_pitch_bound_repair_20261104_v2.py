#!/usr/bin/env python3
"""Versioned detached orchestrator: two diagnostics, three calibration episodes, conditional 360 screen."""
import copy,fcntl,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PYTHON=ROOT/'.pixi/envs/default/bin/python';OUT=ROOT/'logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1'
RUNNER=ROOT/'scripts/mpcc_prediction_research_expanded_pitch_bound_repair_20261104_v1.py';ANALYZER=ROOT/'scripts/analyze_expanded_pitch_bound_repair_20261104_v1.py';INSTRUMENT=ROOT/'scripts/mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v1.py'
PARENT=ROOT/'config/research/mpcc_prediction_v1/parent-fast.json';NUMERICS=ROOT/'config/research/mpcc_prediction_v1/numerics-classical-lm.json';DEFS=ROOT/'config/research/mpcc_prediction_v1/expanded-pitch-demand-20261104-v1/cases.json'
ENV=dict(os.environ,ACADOS_SOURCE_DIR=str(ROOT/'acados'),LD_LIBRARY_PATH=str(ROOT/'acados/lib'),SCIPY_ARRAY_API='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PATH=str(ROOT/'.pixi/envs/default/bin')+':'+os.environ.get('PATH',''))
ENV.pop('XLA_FLAGS',None)
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def used_seeds():
 used=set();files=[]
 def visit(d):
  if isinstance(d,dict):
   for k,v in d.items():
    if k in ['seeds','prediction_seeds'] and isinstance(v,list):used.update(s for s in v if type(s)is int)
    elif k in ['seed','seed_start','screen_seed_start','smoke_seed'] and type(v)is int:used.add(v)
    visit(v)
  elif isinstance(d,list):
   for v in d:visit(v)
 for p in (ROOT/'logs').rglob('*plan*.json'):
  if OUT in p.parents:continue
  try:visit(read(p));files.append(dict(path=str(p),sha256=sha(p)))
  except (ValueError,OSError):raise RuntimeError('Cannot inspect seed plan '+str(p))
 return used,files
def fresh_block(used,begin,count):
 while used.intersection(range(begin,begin+count)):begin+=100
 return list(range(begin,begin+count))
def command(args,timeout):
 start=time.monotonic()
 with (OUT/'orchestrator.log').open('a') as f:
  f.write('$ '+' '.join(map(str,args))+'\n');f.flush()
  child=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=ENV,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  write(OUT/'active-command.json',dict(pid=child.pid,args=list(map(str,args)),started_epoch=time.time()))
  try:rc=child.wait(timeout=max(1,timeout))
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
   rc=124
  return rc,time.monotonic()-start


OLD=ROOT/'logs/mpcc-prediction-v1/expanded-pitch-demand-20261104-v1'
NAMES=['baseline_hard','soft_reference','drag_030']
REUSED=[1603707,1603716]

def freeze_plan(path,names,seeds,rich,construction=False,stage='smoke'):
 import mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v1 as instrument
 p=copy.deepcopy(read(OLD/'screen/plan.json'))
 p.update(stage=stage,cases={k:p['cases'][k] for k in names},case_order=names,seeds=seeds,prediction_seeds=rich,construction_only=construction,
          formulations={k:instrument.formulation(k) for k in names},logging=instrument.LOGGING,analysis=instrument.ANALYSIS,eligibility=instrument.ELIGIBILITY,
          source_screen=str(OLD/'screen/plan.json'),source_screen_sha256=sha(OLD/'screen/plan.json'),
          runtime_bound_verification='Live NLP constraints_get/cost_get at all41 stages, initial equality and public reference parameters each RTI; loaded /proc/self/maps path; getter observable-state preservation. Absolute values, never SQP increments.',
          output=str(path),execution_order=[dict(case=c,seed=s) for c in names for s in seeds])
 p['hashes'].update({str(x):sha(x) for x in [Path(__file__),RUNNER,ANALYZER,INSTRUMENT,OLD/'screen/plan.json']})
 path.mkdir(exist_ok=False);write(path/'plan.json',p)
 return p

def call(args,timeout):
 rc,elapsed=command([PYTHON]+list(args),timeout)
 if rc:raise RuntimeError('Command failed rc='+str(rc)+' '+str(args))
 return elapsed

def construction():
 path=OUT/'construction'
 if not path.exists():freeze_plan(path,NAMES,[1603700,1603707,1603716],[],True)
 call([RUNNER,'run',path],900)
 rows={};libraries=[];handles=[]
 for case in NAMES:
  cc=read(path/'run-v1'/case/'constructions.json');assert [c['seed'] for c in cc]==[1603700,1603707,1603716]
  for c in cc:
   r=c['runtime'];assert c['requested_settings']==c['effective_settings']==read(path/'plan.json')['cases'][case]
   assert r['loaded_mapping_verified'] and r['getter_observable_state_preserved']
   assert all(s['ubx'][-1]==r['path_length'] for s in r['stages'][1:])
   libraries.append(r['library']);handles.append((case,r['handle']))
  assert len({c['runtime']['handle'] for c in cc})==3
  rows[case]=[dict(seed=c['seed'],path_length=c['runtime']['path_length'],library=c['runtime']['library'],construction_s=c['construction_s']) for c in cc]
 assert len(libraries)==len(set(libraries))==9
 # Compare all non-episode constants across sequential constructions in each case.
 for case in NAMES:
  cc=read(path/'run-v1'/case/'constructions.json');first=None
  for c in cc:
   d=copy.deepcopy(c['runtime']['stages'])
   for i,row in enumerate(d):
    if i==0:row.pop('lbx');row.pop('ubx')
    else:row['ubx'][-1]=0.
   if first is None:first=d
   else:assert d==first
 write(OUT/'construction-audit.json',dict(status='passed',constructions=9,racing_episodes=0,sequence=[1603700,1603707,1603716],retained_objects=True,unique_loaded_paths=True,distinct_live_handles_per_case=True,live_progress_matches_current_path=True,other_runtime_constants_unchanged=True,observable_getter_preservation=True,complete_effective_settings=True,rows=rows))
 return rows

def evidence():
 import numpy as np,gzip
 old=read(OLD/'screen/plan.json');assert old['seeds']==list(range(1603700,1603730))
 assert read(OLD/'execution-summary.json')['screen_episodes_retained']==360
 stats=read(OLD/'screen/independent-analysis-v1/statistics.json');pairs=read(OLD/'screen/independent-analysis-v1/paired.json')
 r=stats['drag_030'];assert r['finishes']==16 and r['numerical_ticks']==r['fallback_ticks']==r['invalid_command_ticks']==0 and r['constraint_violating_RTI_solves']>0
 p=pairs['drag_030-minus-soft_reference'];assert p['shared_n']==14 and len(p['rescues'])==2 and not p['regressions']
 failed=next((OLD/'screen/run-v1/speed33_combined/failed-QPs').glob('seed-1603706-*/qp-00.npz'))
 with np.load(failed) as z:
  loaded_ub=float((z['qp.ubx_01'][-1]+z['pre.x'].reshape(41,17)[1,12]).item())
 with gzip.open(OLD/'screen/run-v1/speed33_combined/episode-006/research.json.gz','rt') as f:current=json.load(f)
 # Previous receipts do not contain actual live bounds; reconstruct the saved QP's absolute upper bound.
 first=12.23148040639057;length=12.262160376532917
 assert abs(loaded_ub-first)<1e-10
 plateaus={}
 for seed in REUSED:
  v=[x[3] for x in stats['drag_030']['constraint_events'] if x[0]==seed];plateaus[str(seed)]=max(v)
 write(OUT/'historical-evidence.json',dict(screen_episodes=360,seeds=old['seeds'],drag_finishes=16,drag_health_constraint_failure=True,paired=p,saved_failed_QP=str(failed),saved_absolute_progress_upper=loaded_ub,first_seed_length=first,seed1603706_current_length=length,plateaus=plateaus,mechanism='Case-only shared library pathname reused while instrumentation closures retain prior solver/controller objects. dlopen may retain old loaded image; rebuilding identical pathname cannot prove reload. Unique model and absolute library/export path per episode eliminates this alias. Other defects remain subject to runtime and diagnostic gates.',old_audits='Generated artifacts and initial general rows verified, episode-specific loaded progress bounds not proved.'))

def final_report(status,reason,started,screen):
 count=0
 if screen and (screen/'run-v1').exists():
  count=sum(len(read(p)) for p in (screen/'run-v1').glob('*/episodes.json'))
 write(OUT/'execution-summary.json',dict(status=status,reason=reason,elapsed_s=time.time()-started,screen_episodes_retained=count,screen=str(screen) if screen else None,diagnostic=str(OUT/'diagnostic'),construction=str(OUT/'construction'),no_confirmation=True,no_promotion=True,remaining_authorized_batches=0))
 rc,_=command([PYTHON,ANALYZER,'report',OUT,status,reason],300)
 if rc:
  (OUT/'REPORT.md').write_text(status+'\n\n'+reason+'\nReport assembly failed; see orchestrator.log.\n')
  (OUT/'HANDOFF.md').write_text('No further execution authorized. See execution-summary.json and orchestrator.log.\n')
  write(OUT/'report-error.json',dict(rc=rc))

def main():
 started=time.time();deadline=started+7200;screen=None;status='BLOCKED';reason='Initialization incomplete'
 left=lambda:deadline-time.time()
 try:
  assert not (OUT/'frozen-orchestration.json').exists()
  evidence()
  frozen=dict(started_epoch=started,deadline_epoch=deadline,cases=NAMES,diagnostic_cases=['baseline_hard','drag_030'],diagnostic_seeds=REUSED,diagnostic_episodes=4,screen_episodes=90,screen_seeds_allocated_only_after_gate=True,construction_only_seeds=[1603700,1603707,1603716],headroom=1.3,audit_reserve_s=900,hashes={str(p):sha(p) for p in [Path(__file__),RUNNER,ANALYZER,INSTRUMENT]},authorization='Exactly four diagnostics after construction passes, and exactly one conditional 3x30 screen; no calibration racing, no additional batches, no promotion or confirmation.',environment={k:ENV.get(k) for k in ['ACADOS_SOURCE_DIR','LD_LIBRARY_PATH','SCIPY_ARRAY_API','PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','XLA_FLAGS']})
  write(OUT/'frozen-orchestration.json',frozen)
  if (OUT/'construction-audit.json').exists():
   assert read(OUT/'construction-audit.json')['status']=='passed'
   # Reverify all construction source hashes before relying on the receipt.
   for path,h in read(OUT/'construction/plan.json')['hashes'].items():assert sha(path)==h,path
   rows=read(OUT/'construction-audit.json')['rows']
  else:rows=construction()
  d=OUT/'diagnostic';freeze_plan(d,['baseline_hard','drag_030'],REUSED,REUSED)
  call([RUNNER,'run',d],min(1200,left()-900))
  call([RUNNER,'analyze',d],min(300,left()))
  rc,_=command([PYTHON,ANALYZER,'gate',d],min(300,left()))
  if rc==3:status='BLOCKED';reason='Four diagnostic episodes retained; frozen1e-5 numerical/command/predicted-constraint gate failed. No screen seeds allocated and no further tuning authorized.';return
  if rc:raise RuntimeError('Independent diagnostic audit failed rc='+str(rc))
  # Timing-only conservative estimate: historical worst full episode simulation and measured unique construction.
  oldtim=[]
  for c in NAMES:
   for e in read(OLD/'screen/run-v1'/c/'episodes.json'):
    rr=e['research_runtime'];oldtim.append(max(0.,rr['episode_s']-rr['construction_s']))
  unique=max(r['construction_s'] for rs in rows.values() for r in rs)
  diagnostic=[e['research_runtime'] for c in ['baseline_hard','drag_030'] for e in read(d/'run-v1'/c/'episodes.json')]
  simulation=max(oldtim+[r['episode_s']-r['construction_s'] for r in diagnostic])
  construction_cost=max([unique]+[r['construction_s'] for r in diagnostic])
  estimate=1.3*90*(simulation+construction_cost)+3*10+900
  write(OUT/'budget-receipt.json',dict(historical_max_simulation_s=max(oldtim),measured_max_simulation_s=simulation,unique_construction_s=construction_cost,estimate_s=estimate,remaining_s=left(),headroom=1.3,audit_reserve_s=900,selection='timings only; no calibration racing episodes'))
  if estimate>left():status='BLOCKED';reason=f'Diagnostic gate passed but complete90 plus30% headroom and15min audits estimated {estimate:.1f}s exceeds remaining {left():.1f}s; no screen seeds allocated.';return
  used,plans=used_seeds();seeds=fresh_block(used|set(REUSED)|{1603700},1603800,30)
  assert len(seeds)==30 and not used.intersection(seeds)
  write(OUT/'cohort-selection.json',dict(seeds=seeds,prediction_seeds=seeds[:2],checked_existing_plans=plans,case_order=NAMES,episodes=90,output_fresh=True,diagnostic_gate_passed=True))
  screen=OUT/'screen';freeze_plan(screen,NAMES,seeds,seeds[:2],stage='screen')
  call([RUNNER,'run',screen],max(1,left()-900))
  call([RUNNER,'analyze',screen],min(300,left()))
  call([ANALYZER,'analyze',screen],min(600,left()))
  assert read(screen/'analysis-v1/audit.json')['status']==read(screen/'independent-analysis-v1/audit.json')['status']=='passed'
  count=sum(len(read(p)) for p in (screen/'run-v1').glob('*/episodes.json'));assert count==90
  status='COMPLETED';reason='All nine construction-only checks and four diagnostic episodes passed; all90 fresh matched screen episodes retained; established and independent audits passed. Screen health and provisional eligibility are reported separately.'
 except Exception as e:
  status='PARTIAL' if screen and (screen/'run-v1').exists() else 'FAILED_INTEGRITY';reason=type(e).__name__+': '+str(e)
 finally:final_report(status,reason,started,screen)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='construction':
  try:construction()
  except Exception as e:
   final_report('BLOCKED','Construction-only runtime validation blocker: '+repr(e),time.time(),None);raise
 else:main()

#!/usr/bin/env python3
"""Versioned detached orchestrator: two diagnostics, three calibration episodes, conditional 360 screen."""
import copy,fcntl,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PYTHON=ROOT/'.pixi/envs/default/bin/python';OUT=ROOT/'logs/mpcc-prediction-v1/expanded-pitch-demand-20261104-v1'
RUNNER=ROOT/'scripts/mpcc_prediction_research_expanded_pitch_20261104_v1.py';ANALYZER=ROOT/'scripts/analyze_expanded_pitch_20261104_v1.py';INSTRUMENT=ROOT/'scripts/mpcc_expanded_pitch_instrumentation_20261104_v1.py'
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

def main():
 assert OUT.exists() and not (OUT/'frozen-orchestration.json').exists()
 started=read(OUT/'preparation-start.json')['epoch'];deadline=started+7500
 left=lambda:max(1.,deadline-time.time())
 used,plans=used_seeds();calib_seed=fresh_block(used,1603600,1)[0]
 cases=[k for k in read(DEFS) if not k.startswith('diagnostic_')];assert len(cases)==12
 write(OUT/'frozen-orchestration.json',dict(created_epoch=time.time(),deadline_epoch=deadline,screen_cases=cases,screen_seed_count=30,screen_episodes=360,diagnostic_seed=1603520,diagnostic_cases=['diagnostic_cap10','diagnostic_expanded'],calibration_seed=calib_seed,calibration_cases=['baseline_hard','soft_reference','speed33_combined'],runtime_only_selection=True,headroom_factor=1.3,audit_reserve_s=900,hashes={str(p):sha(p) for p in [Path(__file__),RUNNER,ANALYZER,INSTRUMENT,PARENT,NUMERICS,DEFS]},existing_seed_plan_fingerprints=plans,environment={k:ENV.get(k) for k in ['ACADOS_SOURCE_DIR','LD_LIBRARY_PATH','SCIPY_ARRAY_API','OMP_NUM_THREADS','XLA_FLAGS']}))
 status='BLOCKED';reason='Initialization incomplete';screen=None
 def execute(args,timeout=None):
  rc,elapsed=command([PYTHON]+args,min(left(),timeout) if timeout else left())
  if rc:raise RuntimeError('Command failed rc='+str(rc)+' '+str(args))
  return elapsed
 def prepare(path,names,seed,count,rich,stage):
  execute([RUNNER,'prepare','--output',path,'--stage',stage,'--seed-start',seed,'--seed-count',count,'--cases',','.join(names),'--prediction-seeds',','.join(map(str,rich)),'--parent',PARENT,'--numerics',NUMERICS],300)
 try:
  # Freeze diagnostic cases from exact audited screen settings; no extra baseline episode.
  sys.path.insert(0,str(ROOT/'scripts'));import mpcc_expanded_pitch_instrumentation_20261104_v1 as instrument
  old=ROOT/'logs/mpcc-prediction-v1/qp-capture-20261104-v2';p=copy.deepcopy(read(old/'screen-v1/plan.json'));d=OUT/'diagnostic';d.mkdir(exist_ok=False)
  settings=p['cases']['drag_030'];p.update(stage='smoke',diagnostic_only=True,seeds=[1603520],prediction_seeds=[1603520],cases={k:copy.deepcopy(settings) for k in ['diagnostic_cap10','diagnostic_expanded']},case_order=['diagnostic_cap10','diagnostic_expanded'],formulations={k:instrument.formulation(k) for k in ['diagnostic_cap10','diagnostic_expanded']},logging=instrument.LOGGING,segments=instrument.SEGMENTS,analysis=instrument.ANALYSIS,eligibility=instrument.ELIGIBILITY,source_screen=str(old/'screen-v1/plan.json'),source_screen_sha256=sha(old/'screen-v1/plan.json'))
  p['hashes'].update({str(x):sha(x) for x in [RUNNER,INSTRUMENT,ANALYZER,Path(__file__),DEFS,PARENT,NUMERICS,old/'screen-v1/plan.json',old/'screen-v1/independent-audit.json']});write(d/'plan.json',p)
  execute([RUNNER,'run',d],min(900,left()))
  rc,_=command([PYTHON,ANALYZER,'gate',d],min(300,left()))
  if rc==3:status='DIAGNOSTIC_GATE_FAILED';reason='Expanded-cap episode failed frozen numerical/command/predicted-constraint gate; no calibration/screen; no further bound widening.';return
  if rc:raise RuntimeError('Diagnostic independent audit failed rc='+str(rc))
  # Three separate runtime-only calibration episodes, with no rich QP retention.
  calibration=OUT/'calibration';prepare(calibration,['baseline_hard','soft_reference','speed33_combined'],calib_seed,1,[],'smoke')
  elapsed=execute([RUNNER,'run',calibration],min(900,left()))
  timing=[]
  for c in ['baseline_hard','soft_reference','speed33_combined']:
   ep=read(calibration/'run-v1'/c/'episodes.json')[0];r=ep['research_runtime'];steps=r['step_walls_s'];warmup=max(0.,sum(steps[:2])-2*float(sorted(steps)[len(steps)//2]));steady=max(.01,r['episode_s']-warmup)
   timing.append(dict(case=c,construction_s=r['construction_s'],episode_s=r['episode_s'],initialization_s=r['worker_to_first_episode_s'],first_two_step_extra_s=warmup,steady_episode_s=steady))
  # Include measured per-episode construction, simulation/observer cost, full process startup per case,
  # plus 30% simulation/construction headroom and 15min deterministic analysis reserve.
  per_episode=max(t['steady_episode_s'] for t in timing)
  startup=max(t['initialization_s']+t['first_two_step_extra_s'] for t in timing)
  estimate=1.3*360*per_episode+12*startup+900
  write(OUT/'calibration-receipt.json',dict(episodes=3,seed=calib_seed,total_run_s=elapsed,timing=timing,estimated_screen_plus_audit_s=estimate,remaining_budget_s=left(),selection_inputs='timings only; no success/status/lap-time outcome used',amortization='Per-case environment/JAX warmup cost separated from per-episode construction and subsequent simulation. Worst measured steady episode and startup across three cases; factor1.3 on360 episodes plus12 startups and900s audits.'))
  # Calibration integrity is audited but its performance never selects cases/cohort/configuration.
  execute([ANALYZER,'analyze',calibration],300)
  if estimate>left():status='BUDGET_BLOCKED';reason=f'Complete360 plus30% headroom and900s audits estimated {estimate:.1f}s, exceeding remaining {left():.1f}s. No screen seeds allocated.';return
  used,plans=used_seeds();seeds=fresh_block(used|{calib_seed,1603520},1603700,30)
  write(OUT/'cohort-selection.json',dict(seeds=seeds,prediction_seeds=seeds[:2],case_order=cases,episodes=360,estimated_s=estimate,timing_only=True,checked_prior_plans=plans))
  screen=OUT/'screen';prepare(screen,cases,seeds[0],30,seeds[:2],'screen')
  execute([RUNNER,'run',screen],max(1,left()-900))
  execute([RUNNER,'analyze',screen],max(300,left()))
  execute([ANALYZER,'analyze',screen],max(300,left()))
  assert read(screen/'analysis-v1/audit.json')['status']=='passed' and read(screen/'independent-analysis-v1/audit.json')['status']=='passed'
  status='COMPLETED';reason='Two diagnostic episodes passed gate; three disjoint calibration episodes; all360 matched screen episodes retained; original and independent deterministic audits passed.'
 except Exception as e:
  status='PARTIAL' if screen and (screen/'run-v1').exists() else 'FAILED_INTEGRITY';reason=str(e)
 finally:
  episodes=0
  if screen and (screen/'run-v1').exists():
   for path in (screen/'run-v1').glob('*/episodes.json'):episodes+=len(read(path))
  summary=dict(status=status,reason=reason,elapsed_s=time.time()-started,screen_episodes_retained=episodes,screen=str(screen) if screen else None,diagnostic=str(OUT/'diagnostic'),calibration=str(OUT/'calibration'),no_promotion=True,no_confirmation=True,remaining_authorized_batches=0)
  write(OUT/'execution-summary.json',summary)
  rc,_=command([PYTHON,ANALYZER,'report',OUT,status,reason],300)
  if rc:write(OUT/'report-error.json',dict(rc=rc));(OUT/'HANDOFF.md').write_text(status+'\n'+reason+'\nReport assembly failed; see orchestrator.log.\n')
if __name__=='__main__':main()

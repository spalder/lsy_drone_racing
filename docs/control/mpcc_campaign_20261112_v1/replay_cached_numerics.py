"""Post-campaign diagnostic replay of observed failures; never adds performance samples."""
import pathlib,json,os,sys,hashlib
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D))
import run as runner
import numpy as np,gymnasium
from scipy.spatial.transform import Rotation
from ml_collections import ConfigDict
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.control.mpcc_broad_core import MPCCBroadCore
from lsy_drone_racing.control import mpcc_broad_solver as bs
Original=bs.AcadosOcpSolver
def cached(ocp,**kwargs):
 cache=D/old['stage']/'build_cache'/hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()[:16]
 prior=os.getcwd();os.chdir(cache)
 try:
  sol=Original(ocp,**kwargs,generate=False,build=False)
  for k in range(1,int(ocp.solver_options.N_horizon)+1):sol.constraints_set(k,'ubx',ocp.constraints.ubx_e if k==int(ocp.solver_options.N_horizon) else ocp.constraints.ubx)
  return sol
 finally:os.chdir(prior)
bs.AcadosOcpSolver=cached
assert (D/'COMPLETE').exists(),'Do not contend with main timing measurements'
M=json.loads((D/'manifest.json').read_text());cfg=ConfigDict(M['environment']);cfg.sim.render=False;cfg.controller=ConfigDict({})
targets=[]
for st in ['A','B','C']:
 for p in (D/st).glob('*_*.json'):
  r=json.loads(p.read_text())
  if r['fallback_ticks'] or r['failed_solve_ticks']:targets.append(r)
out=D/'numerical_replays_cached';out.mkdir(exist_ok=True)
env=JaxToNumpy(gymnasium.make(cfg.env.id,freq=cfg.env.freq,sim_config=cfg.sim,sensor_range=cfg.env.sensor_range,control_mode=cfg.env.control_mode,track=cfg.env.track,disturbances=cfg.env.disturbances,randomizations=cfg.env.randomizations,seed=targets[0]['seed'] if targets else 1))
summary=[]
try:
 for old in targets:
  name,seed=old['candidate'],old['seed'];dest=out/f"{old['stage']}_{name}_{seed}.json"
  if dest.exists():summary.append(json.loads(dest.read_text())['summary']);continue
  work=out/f"build_{name}";work.mkdir(exist_ok=True);os.chdir(work)
  obs,info=env.reset(seed=seed);settings=M['candidates'][name]['settings'];c=MPCCBroadCore(obs,info,cfg,settings=settings['mpcc'],geometry=settings['mpcc_experiment'])
  solve=c._solver.solve;subsolves=[]
  def traced_solve(*args,**kwargs):
   status=solve(*args,**kwargs)
   subsolves.append(dict(status=int(status),qp_status=np.asarray(c._solver.get_stats('qp_stat')).tolist(),qp_iter=np.asarray(c._solver.get_stats('qp_iter')).tolist()))
   return status
  c._solver.solve=traced_solve
  records=[];actions=[]
  for tick in range(1500):
   before=dict(pos=np.asarray(obs['pos']).tolist(),vel=np.asarray(obs['vel']).tolist(),rpy=Rotation.from_quat(obs['quat']).as_euler('xyz').tolist(),gates_visited=np.asarray(obs['gates_visited']).tolist(),obstacles_visited=np.asarray(obs['obstacles_visited']).tolist(),gate_occurrences=int(obs['n_gates_passed']),progress=float(c._progress))
   subsolves=[];act=c.compute_control(obs,info);actions.append(np.asarray(act).tolist())
   records.append(dict(tick=tick,before=before,subsolves=subsolves,fallback=c._prediction is None,action=np.asarray(act).tolist(),thrust_gain=float(c._thrust_gain)))
   obs,reward,term,trunc,info=env.step(act);done=c.step_callback(act,obs,reward,term,trunc,info)
   if term or trunc or done:break
  equal=np.array_equal(np.asarray(actions,dtype=np.float32),np.asarray(old['actions'],dtype=np.float32))
  success=int(obs['n_gates_passed'])==5
  summary_row=dict(stage=old['stage'],candidate=name,seed=seed,steps=tick+1,success=success,float32_actions_equal=equal,original_fallback_ticks=old['fallback_ticks'],replayed_fallback_ticks=sum(r['fallback'] for r in records))
  summary_row['same_outcome']=success==old['success']
  summary_row['same_steps']=tick+1==old['steps']
  common=min(len(actions),len(old['actions']))
  aa=np.asarray(actions[:common],dtype=np.float32);bb=np.asarray(old['actions'][:common],dtype=np.float32)
  summary_row['max_absolute_float32_action_difference']=float(np.max(np.abs(aa-bb)))
  diff=np.flatnonzero(np.any(aa!=bb,axis=1));summary_row['first_different_tick']=int(diff[0]) if len(diff) else None
  events=[r['tick'] for r in records if r['fallback']]
  kept=[r for r in records if any(abs(r['tick']-e)<=5 for e in events)]
  runner.write(dest,dict(summary=summary_row,events=kept,all_actions=actions,role='targeted diagnostic only; excluded from completion estimates',action_sha256=hashlib.sha256(np.asarray(actions,dtype=np.float32).tobytes()).hexdigest()))
  assert equal and summary_row['same_outcome'] and summary_row['same_steps'],summary_row
  summary.append(summary_row);c.episode_callback();c.episode_reset();del c
finally:env.close()
runner.write(out/'summary.json',summary)
print(json.dumps(summary,indent=2))

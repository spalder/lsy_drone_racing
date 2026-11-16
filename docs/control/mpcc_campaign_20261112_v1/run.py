"""Serial checkpointed MPCC campaign. Run with --stage smoke/A/B/C; sources immutable."""
import os,sys,pathlib,json,hashlib,time,datetime,argparse,collections
D=pathlib.Path(__file__).resolve().parent;R=D.parents[2]
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',JAX_PLATFORMS='cpu',ACADOS_SOURCE_DIR=str(R/'acados'),LD_LIBRARY_PATH=str(R/'acados/lib'))
sys.path.insert(0,str(D/'source'))
import numpy as np
import jax,gymnasium,lsy_drone_racing
from ml_collections import ConfigDict
from gymnasium.wrappers.jax_to_numpy import JaxToNumpy
from lsy_drone_racing.control.mpcc_broad_core import MPCCBroadCore

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def conv(v):
 if isinstance(v,dict):return {str(k):conv(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [conv(x) for x in v]
 if isinstance(v,(str,bool,int,float)) or v is None:return v
 return np.asarray(v).tolist()
def write(p,v):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',required=True,choices=['smoke','A','B','C']);p.add_argument('--limit',type=int);p.add_argument('--cache',action='store_true');p.add_argument('--suffix',default='');a=p.parse_args()
 m=json.loads((D/'manifest.json').read_text());assert sha(D/'manifest.json')==(D/'manifest.sha256').read_text().strip()
 for f,h in {**m['source_hashes'],**m['libraries']}.items():assert sha(D/f)==h,f
 cfg=ConfigDict(m['environment']);cfg.sim.render=False;cfg.controller=ConfigDict({})
 stage=a.stage
 selection=json.loads((D/f'selection_{stage}.json').read_text()) if (D/f'selection_{stage}.json').exists() else list(m['candidates'])
 seeds=m['seeds'][stage]
 if (D/'runtime_design.json').exists():seeds=seeds[:json.loads((D/'runtime_design.json').read_text())['sizes'].get(stage,len(seeds))]
 if a.limit:seeds=seeds[:a.limit]
 out=D/(stage+a.suffix);out.mkdir(exist_ok=True);(out/'states').mkdir(exist_ok=True)
 plan=dict(stage=stage,candidates=selection,seeds=seeds,manifest_sha256=sha(D/'manifest.json'),runner_sha256=sha(pathlib.Path(__file__)))
 if (out/'plan.json').exists():assert json.loads((out/'plan.json').read_text())==plan
 else:write(out/'plan.json',plan);(out/'plan.sha256').write_text(sha(out/'plan.json'))
 import importlib.metadata,platform
 write(out/'runtime.json',dict(versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','jax','jaxlib','mujoco','crazyflow','gymnasium','casadi','acados-template']},python=sys.version,jax_devices=str(jax.devices()),started=datetime.datetime.now(datetime.timezone.utc).isoformat(),origins={k:v.__file__ for k,v in sys.modules.copy().items() if k.startswith('lsy_drone_racing') and getattr(v,'__file__',None)}))
 env=JaxToNumpy(gymnasium.make(cfg.env.id,freq=cfg.env.freq,sim_config=cfg.sim,sensor_range=cfg.env.sensor_range,control_mode=cfg.env.control_mode,track=cfg.env.track,disturbances=cfg.env.disturbances,randomizations=cfg.env.randomizations,seed=seeds[0]))
 # Read-only terminal collision diagnostic using the official sync/contact routine.
 from crazyflow.sim.sim import sync_sim2mjx
 import jax.numpy as jp
 core=env.unwrapped;sim=core.sim
 def contact_diag(data):
  mj=sim.mjx_data;gi,oi=core.mocap_ids
  mp=mj.mocap_pos.at[...,gi,:].set(data.gates_pos).at[...,oi,:].set(data.obstacles_pos)
  mq=mj.mocap_quat.at[...,gi,:].set(jp.roll(data.gates_quat,1,axis=-1))
  _,mj=sync_sim2mjx(data.sim_data,mj.replace(mocap_pos=mp,mocap_quat=mq),sim.mjx_model)
  ct=mj._impl.contact
  return ct.dist,ct.geom1,ct.geom2
 diagnostic=jax.jit(contact_diag)
 apply_action=core.build_apply_action_fn();sim_step=sim.build_step_fn()
 @jax.jit
 def prewarp(data,action):
  data=apply_action(action,data)
  return data.replace(sim_data=sim_step(data.sim_data,data.sim_data.core.freq//core.settings.freq))
 os.chdir(out)
 if a.cache:
  from lsy_drone_racing.control import mpcc_broad_solver as bs
  Original=bs.AcadosOcpSolver
  def cached(ocp,**kwargs):
   # Only path-length constraints vary within one frozen candidate.
   key=hashlib.sha256(json.dumps(active_settings,sort_keys=True).encode()).hexdigest()[:16]
   cache=out/'build_cache'/key;cache.mkdir(parents=True,exist_ok=True)
   prior=os.getcwd();os.chdir(cache)
   try:
    exists=(cache/'c_generated_code/attitude_mpcc_broad.json').exists()
    sol=Original(ocp,**kwargs,generate=not exists,build=not exists)
    if exists:
     for k in range(1,int(ocp.solver_options.N_horizon)+1):
      sol.constraints_set(k,'ubx',ocp.constraints.ubx_e if k==int(ocp.solver_options.N_horizon) else ocp.constraints.ubx)
    return sol
   finally:os.chdir(prior)
  bs.AcadosOcpSolver=cached
 try:
  for si,seed in enumerate(seeds):
   # Rotate execution order to distribute drift evenly; no concurrent workloads.
   order=selection[si%len(selection):]+selection[:si%len(selection)]
   for name in order:
    dest=out/f'{name}_{seed}.json'
    if dest.exists():continue
    start=time.time();obs,info=env.reset(seed=seed)
    leaves,treedef=jax.tree_util.tree_flatten(env.unwrapped.data)
    arrays={str(i):np.asarray(jax.random.key_data(x) if jax.dtypes.issubdtype(x.dtype,jax.dtypes.prng_key) else x) for i,x in enumerate(leaves)}
    h=hashlib.sha256(str(treedef).encode())
    for x in arrays.values():h.update(str((x.shape,str(x.dtype))).encode());h.update(x.tobytes())
    state_hash=h.hexdigest();state=out/'states'/f'{seed}.json'
    if state.exists():assert json.loads(state.read_text())['sha256']==state_hash,('initial state mismatch',seed,name)
    else:
     np.savez_compressed(out/'states'/f'{seed}.npz',**arrays)
     write(state,dict(sha256=state_hash,tree=str(treedef),observation=conv(obs),info=conv(info)))
    s=m['candidates'][name]['settings'];active_settings=s;c=MPCCBroadCore(obs,info,cfg,settings=s['mpcc'],geometry=s['mpcc_experiment'])
    assert c.settings==s['mpcc']
    durations=[];statuses=[];fallback=[];actions=[];cmd=hashlib.sha256()
    for tick in range(1500):
     t=time.perf_counter_ns();action=c.compute_control(obs,info);durations.append((time.perf_counter_ns()-t)/1e6)
     assert np.isfinite(action).all();actions.append(np.asarray(action).tolist())
     statuses.append(int(c.last_solver_status));fallback.append(c._prediction is None)
     cmd.update(np.asarray(action).tobytes())
     before_step=env.unwrapped.data
     obs,reward,terminated,truncated,info=env.step(action)
     done=c.step_callback(action,obs,reward,terminated,truncated,info)
     if terminated or truncated or done:break
    c.episode_callback();success=int(obs['n_gates_passed'])==len(obs['gate_sequence'])
    contacts=[];prewarp_position=None
    if not success:
     replay=prewarp(before_step,jp.asarray(action,dtype=jp.float32))
     prewarp_position=conv(replay.sim_data.states.pos)
     dist,g1,g2=map(np.asarray,diagnostic(replay))
     for dd,aa,bb in zip(dist.ravel(),g1.ravel(),g2.ravel()):
      if dd<0:
       contacts.append(dict(distance=float(dd),geom1=int(aa),geom2=int(bb),name1=sim.mj_model.geom(int(aa)).name,body1=sim.mj_model.body(int(sim.mj_model.geom_bodyid[int(aa)])).name,name2=sim.mj_model.geom(int(bb)).name,body2=sim.mj_model.body(int(sim.mj_model.geom_bodyid[int(bb)])).name))
    write(dest,dict(prewarp_position=prewarp_position,actions=actions,contacts=contacts,stage=stage,candidate=name,seed=seed,initial_state_sha256=state_hash,success=success,steps=tick+1,race_time_s=(tick+1)/50,official_time_s=tick/50,penalized_time_s=(tick+1)/50 if success else 30,terminated=terminated,truncated=truncated,solver_statuses=statuses,failed_solve_ticks=sum(x!=0 for x in statuses),fallback_ticks=sum(fallback),fallback_indices=[i for i,x in enumerate(fallback) if x],durations_ms=durations,total_control_calls=len(durations),terminal_observation=conv(obs),terminal_info=conv(info),command_sha256=cmd.hexdigest(),timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_s=time.time()-start,settings_sha256=hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()))
    c.episode_reset();del c
    print(stage,si+1,name,seed,success,round(time.time()-start,2),flush=True)
 finally:env.close()
if __name__=='__main__':main()

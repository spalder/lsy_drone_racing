"""Observational instrumentation and fixed expanded-pitch formulation for one study."""
import gzip,hashlib,json,sys,time
from collections import deque
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
LOGGING=dict(mode='compact',full_QP_predecessors=5,predecessors_only_preselected_rich_seeds=True,every_failed_QP_before_reset=True,predicted_constraint_tolerance=1e-5,command_tolerance=1e-5,rich_seeds='first two frozen matched seeds')
SEGMENTS=dict(rule='Every retained pre-action public position must be finite and not terminal sentinel [-1,-1,-1]. Match seed and required crossing occurrence, keep only completed crossing legs in both cases. Classify departure first when current path progress is between any recorded gate center_s and departure_s; otherwise turn if recorded local curvature >=0.8 /m, else straight_approach. Each retained tick contributes .02 s. Compare classification durations and total leg durations; report geometry revisions and classification coverage. Different local routes can move class boundaries, so class differences are descriptive within matched legs.',curvature_turn_threshold_per_m=.8,dt_s=.02,terminal_sentinel=[-1,-1,-1])
ANALYSIS=dict(all_vs_baseline_hard=True,all_soft_vs_soft_reference=True,combinations_vs_constituents=True,bootstrap_resamples=10000,bootstrap_seed=20261104,completion_interval='Clopper Pearson exact 95%',paired_unit='shared successful seed; segment analysis completed seed/crossing legs',no_pooling=True,selection='No tuning or case/seed/sample-size changes from outcomes')
ELIGIBILITY=dict(observed_completion_min=.4,inclusive=True,screen_min_finishes=12,zero_nonzero_status=True,zero_fallback=True,finite_valid_commands=True,predicted_constraints_tolerance=1e-5,speed='Worthwhile paired shared-finish speed magnitude and bootstrap uncertainty; no invented fixed gain cutoff',public_completion_threshold=.5,latency='advisory',screen_is_provisional=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def formulation(case):
 if case=='baseline_hard':return dict(kind='hard')
 return dict(kind='bounded_soft_future_attitude',caps_rad=[.1,.1,.1] if case=='diagnostic_cap10' else [.1,.15,.1],running_quadratic=500000.,terminal_quadratic=10000.,linear=0.,initial_equality='hard',commands='unchanged hard',progress='unchanged hard',dynamics='unchanged',auxiliary_slack_upper_bound=None)
def same(a,b):return a.keys()==b.keys() and all(np.array_equal(a[k],b[k],equal_nan=True) for k in a)
def install(core,settings,plan,case,out):
 mod=sys.modules[core.create_mpcc_solver.__module__];backend=mod.AcadosOcpSolver;original=core.MPCCPredictionCore.compute_control;spec=formulation(case);soft=spec['kind']!='hard'
 def construct(ocp,**kwargs):
  if soft:
   for suffix in ('','_e'):
    setattr(ocp.constraints,'idxsbx'+suffix,np.arange(3,dtype=int));setattr(ocp.constraints,'lsbx'+suffix,np.zeros(3));setattr(ocp.constraints,'usbx'+suffix,np.zeros(3))
    for k in ('Zl','Zu'):setattr(ocp.cost,k+suffix,np.full(3,10000. if suffix else 500000.))
    for k in ('zl','zu'):setattr(ocp.cost,k+suffix,np.zeros(3))
   for k in ('Zl_0','Zu_0','zl_0','zu_0'):setattr(ocp.cost,k,np.zeros(0))
   C=np.zeros((3,17));C[:,3:6]=np.eye(3)
   for suffix in ('','_e'):
    setattr(ocp.constraints,'C'+suffix,C.copy());setattr(ocp.constraints,'lg'+suffix,ocp.constraints.lbx[:3]-spec['caps_rad']);setattr(ocp.constraints,'ug'+suffix,ocp.constraints.ubx[:3]+spec['caps_rad'])
   ocp.constraints.D=np.zeros((3,5))
  # The JSON filename remains compatible with the established analyzer; the model/library is case-specific.
  ocp.model.name='mpcc_boundrepair_v1_'+case+'_seed'+str(EPISODE_SEED);ocp.code_export_directory=str((out/'generated'/ocp.model.name).resolve());Path(ocp.code_export_directory).mkdir(parents=True,exist_ok=False);kwargs['json_file']=str(Path(ocp.code_export_directory)/'ocp.json')
  solver=backend(ocp,**kwargs)
  solver._research_ocp=ocp;solver._research_spec=spec;solver._research_json=kwargs["json_file"]
  if soft:solver.constraints_set(0,'C',np.zeros((3,17)))
  solver._research_backend=dict(model=ocp.model.name,library=str(solver.shared_lib._name),library_sha256=sha(solver.shared_lib._name),formulation=spec,generated_options={k:getattr(ocp.solver_options,k) for k in ('qp_solver_cond_ric_alg','qp_solver_ric_alg','levenberg_marquardt','qp_solver_iter_max','qp_solver_cond_N')})
  solver._research_ring=deque(maxlen=5);solver._research_tick=-1;solve=solver.solve
  def observable():return {k:np.asarray(solver.get_flat(k)).copy() for k in ('x','u','sl','su','p','pi','lam','z')}
  def wrapped_solve():
   c=solver._research_controller;rich=c._research_rich;start=time.perf_counter_ns()
   if rich:before=observable()
   else:before={k:np.asarray(solver.get_flat(k)).copy() for k in ('x','u','p','sl','su')}
   # Check live measured equality and per-pass public reference parameters before solving.
   xpre=before['x'].reshape(41,17)
   assert np.array_equal(solver.constraints_get(0,'lbx'),xpre[0])
   assert np.array_equal(solver.constraints_get(0,'ubx'),xpre[0])
   pp=np.clip(xpre[:,12],0,c._length)
   expected=np.column_stack((c._path(pp),c._path_derivative(pp),pp,np.full(41,c._thrust_gain)))
   assert np.array_equal(before['p'].reshape(41,8),expected)
   if solver._research_tick==0 and solver._research_pass==0:
    c._research_runtime_initial=inspect_runtime(c,None,construction=False)
   pre_over=time.perf_counter_ns()-start;status=solve();start=time.perf_counter_ns()
   solver._research_pass+=1
   x=np.asarray(solver.get_flat('x')).reshape(41,17);u=np.asarray(solver.get_flat('u')).reshape(40,5)
   sl=np.asarray(solver.get_flat('sl')).reshape(-1,3);su=np.asarray(solver.get_flat('su')).reshape(-1,3)
   r=dict(runtime_initial_equality_verified=True,runtime_parameters_verified=True,tick=solver._research_tick,rti_pass=solver._research_pass,status=int(status),finite=bool(all(np.isfinite(a).all() for a in (x,u,sl,su))),constraints_checked=status==0)
   if status==0:
    violations=np.maximum(np.abs(x[1:,3:6])-.875,0.);r['max_predicted_attitude_violation_by_axis']=violations.max(axis=0).tolist();r['max_slack']=float(max(sl.max(initial=0),su.max(initial=0)))
    hard=float(max(np.max(ocp.constraints.lbu-u),np.max(u-ocp.constraints.ubu),np.max(-x[1:,12]),np.max(x[1:,12]-c._length),np.max(np.abs(x[0]-before['x'].reshape(41,17)[0]))))
    if soft:
     hard=max(hard,float(np.max(violations-spec['caps_rad'])));softres=max(float(np.max(-.875-x[1:,3:6]-sl)),float(np.max(x[1:,3:6]-.875-su)),float(-sl.min()),float(-su.min()))
    else:hard=max(hard,float(violations.max()));softres=0.
    r.update(slack_lower_max_by_axis=sl.max(axis=0).tolist() if soft else [0.,0.,0.],slack_upper_max_by_axis=su.max(axis=0).tolist() if soft else [0.,0.,0.],predicted_cap_margin_by_axis=(np.asarray(spec['caps_rad'])-violations.max(axis=0)).tolist() if soft else (-violations.max(axis=0)).tolist(),max_hard_violation=max(0.,hard),max_soft_violation=max(0.,softres),horizon_virtual_speed_min=float(u[:,4].min()),horizon_virtual_speed_max=float(u[:,4].max()),horizon_cap_active_count=int((u[:,4]>=.98*settings['mpcc']['max_speed']).sum()),horizon_input_count=40)
   if rich or status!=0:
    after=observable();stats={}
    for k in ('statistics','qp_stat','qp_iter','time_tot','time_qp'):
     try:stats[k]=np.asarray(solver.get_stats(k)).copy()
     except Exception:pass
    qp=solver.get_last_qp();qp2=solver.get_last_qp();after2=observable();assert same(after,after2) and same(qp,qp2)
    assert same(stats,{k:np.asarray(solver.get_stats(k)).copy() for k in stats}) and solver.status==status
    if soft:
     assert np.all(qp['C_00']==0)
     for i in (1,40):assert np.all(qp[f'Zl_{i:02d}']==10000.) and np.all(qp[f'Zu_{i:02d}']==10000.)
    payload={'qp.'+k:v for k,v in qp.items()};payload.update({'pre.'+k:v for k,v in before.items()});payload.update({'post.'+k:v for k,v in after.items()});payload.update({'stats.'+k:v for k,v in stats.items()});payload.update({'obs.'+k:v for k,v in solver._research_obs.items()});payload.update(tick=np.array(solver._research_tick),rti_pass=np.array(solver._research_pass),status=np.array(status),seed=np.array(c._research_seed),getter_state_equal=np.array(True),getter_qp_equal=np.array(True))
    if status==0:solver._research_ring.append(payload)
    else:
     folder=out/'failed-QPs'/f'seed-{c._research_seed}-tick-{solver._research_tick:04d}-pass-{solver._research_pass}';folder.mkdir(parents=True,exist_ok=False)
     previous=list(solver._research_ring) if rich else []
     for i,p in enumerate(previous+[payload]):np.savez_compressed(folder/f'qp-{i:02d}.npz',**p)
     write(folder/'receipt.json',dict(seed=c._research_seed,tick=solver._research_tick,pass_number=solver._research_pass,status=int(status),predecessors=len(previous),getter_checks=True))
   # First successful QP verifies runtime stage-zero rows even off diagnostic subset.
   if solver._research_tick==0 and solver._research_pass==1 and soft:
    assert np.all(solver.get_from_qp_in(0,'C')==0)
    solver._research_backend['initial_C_zero_verified']=True
   r['instrumentation_ms']=(pre_over+time.perf_counter_ns()-start)/1e6;c._research_current.append(r)
   return status
  solver.solve=wrapped_solve
  return solver
 def compute(self,obs,info=None):
  s=self._solver;s._research_controller=self;s._research_tick+=1;s._research_pass=0;s._research_obs={k:np.asarray(v).copy() for k,v in obs.items()};self._research_current=[]
  action=original(self,obs,info)
  valid=bool(np.isfinite(action).all() and np.all(action>=self._ocp.constraints.lbu[:4]-1e-5) and np.all(action<=self._ocp.constraints.ubu[:4]+1e-5))
  self._research_tick_records.append(dict(tick=s._research_tick,rti=self._research_current,finite_valid_command=valid,fallback=self._inputs is None or self._prediction is None,observed_attitude_xyz=Rotation.from_quat(obs['quat']).as_euler('xyz').tolist(),observed_original_bound_violation=np.maximum(np.abs(Rotation.from_quat(obs['quat']).as_euler('xyz'))-.875,0.).tolist()))
  return action
 mod.AcadosOcpSolver=construct;core.MPCCPredictionCore.compute_control=compute

def export(c,directory,seed):
 directory=Path(directory);rows=c._research_tick_records
 with gzip.open(directory/'research.json.gz','xt',compresslevel=1) as f:json.dump(dict(seed=seed,formulation=formulation(c._research_case) if hasattr(c,'_research_case') else c._solver._research_backend['formulation'],backend=c._solver._research_backend,runtime_initial=c._research_runtime_initial,runtime_final=inspect_runtime(c,None,construction=False),ticks=rows),f,allow_nan=False,separators=(',',':'))


EPISODE_SEED = None

def inspect_runtime(c, obs, construction=False):
 """Read live NLP memory, not OCP JSON or QP increments; preserve observable state."""
 s=c._solver;o=c._ocp;spec=s._research_spec;soft=spec['kind']!='hard'
 if construction:
  # Mimic the controller's measured row assignment without computing an action or stepping.
  from lsy_drone_racing.control.mpcc_prediction_core import ang_vel2rpy_rates
  state=np.concatenate((obs['pos'],Rotation.from_quat(obs['quat']).as_euler('xyz'),obs['vel'],ang_vel2rpy_rates(obs['quat'],obs['ang_vel']),[c._progress],c._last_action))
  s.set(0,'lbx',state);s.set(0,'ubx',state)
 def observable():return {k:np.asarray(s.get_flat(k)).copy() for k in ('x','u','sl','su','p','pi','lam','z')}
 before=observable();status=getattr(s,'status',None)
 stages=[]
 for i in range(41):
  row={k:s.constraints_get(i,k).tolist() for k in ('lbx','ubx')}
  if i:
   assert np.array_equal(row['lbx'],o.constraints.lbx)
   assert np.array_equal(row['ubx'],o.constraints.ubx)
   assert row['ubx'][-1]==c._length
  else:
   assert row['lbx']==row['ubx'] and len(row['lbx'])==17
  if i<40:
   for k in ('lbu','ubu'):
    v=s.constraints_get(i,k);assert np.array_equal(v,getattr(o.constraints,k));row[k]=v.tolist()
  if soft:
   for k in ('C','lg','ug'):
    v=s.constraints_get(i,k)
    expected=np.zeros((3,17)) if i==0 and k=='C' else getattr(o.constraints,k+('_e' if i==40 else ''))
    assert np.array_equal(v,expected),(i,k,v,expected)
    row[k]=v.tolist()
   for k in ('Zl','Zu','zl','zu'):
    v=s.cost_get(i,k);expected=np.zeros(0) if i==0 else np.full(3,(10000. if i==40 else 500000.) if k.startswith('Z') else 0.)
    assert np.array_equal(v.ravel(),expected),(i,k,v,expected)
    row[k]=v.ravel().tolist()
  # Cost matrices and references catch stale non-bound constants too.
  for k in ('W','yref'):
   v=s.cost_get(i,k);expected=getattr(o.cost,k+('_e' if i==40 else ''))
   if k=='W' or construction:assert np.array_equal(v,expected),(i,k)
   row[k]=v.tolist()
  stages.append(row)
 after=observable();assert same(before,after) and getattr(s,'status',None)==status
 lib=Path(s.shared_lib._name).resolve();model=o.model.name
 assert str(EPISODE_SEED) in model and lib.parent==Path(o.code_export_directory).resolve()
 assert model in lib.name
 maps=Path('/proc/self/maps').read_text();assert str(lib) in maps
 return dict(seed=EPISODE_SEED,path_length=c._length,model=model,library=str(lib),library_sha256=sha(lib),generated_json=s._research_json,generated_json_sha256=sha(s._research_json),loaded_mapping_verified=True,handle=int(s.shared_lib._handle),getter_observable_state_preserved=True,initial_equality_hard=True,stages=stages,effective_numerics=c.numerical_settings,parameters=before['p'].tolist(),initial_C_zero_verified=soft)

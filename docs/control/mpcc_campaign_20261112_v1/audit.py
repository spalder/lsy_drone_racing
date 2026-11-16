import pathlib,json,hashlib
import numpy as np
from analyze import load,metrics
D=pathlib.Path(__file__).resolve().parent;M=json.loads((D/'manifest.json').read_text());checks=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(D/'manifest.json')==(D/'manifest.sha256').read_text().strip()
for f,h in {**M['source_hashes'],**M['libraries']}.items():assert sha(D/f)==h
seed_sets=[]
for st in ['A','B','C']:
 p=D/st/'plan.json'
 if not p.exists():continue
 plan=json.loads(p.read_text());x=load(st)
 assert sha(p)==(D/st/'plan.sha256').read_text().strip()
 assert plan['runner_sha256']==sha(D/'run.py')
 assert len(set(plan['seeds']))==len(plan['seeds'])
 assert all(not (set(plan['seeds'])&prior) for prior in seed_sets)
 seed_sets.append(set(plan['seeds']))
 assert set(x)==set(plan['candidates'])
 for name,rs in x.items():
  assert sorted(r['seed'] for r in rs)==sorted(plan['seeds'])
  settings=M['candidates'][name]['settings']
  expected=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
  ocp=json.loads((D/st/'build_cache'/expected[:16]/'c_generated_code/attitude_mpcc_broad.json').read_text())
  assert ocp['solver_options']['N_horizon']==settings['mpcc']['horizon_steps']
  assert ocp['solver_options']['qp_solver_cond_N']==settings['mpcc']['condensing_length']
  assert ocp['solver_options']['qp_solver_iter_max']==settings['mpcc']['qp_iterations']
  assert np.allclose(ocp['constraints']['ubu'][:2],[settings['mpcc']['max_angle']]*2)
  assert ocp['constraints']['ubu'][-1]==settings['mpcc']['max_speed']
  for r in rs:
   assert r['settings_sha256']==expected
   assert r['race_time_s']==r['steps']/50
   assert (int(r['terminal_observation']['n_gates_passed'])==5)==r['success']
   assert abs(r['official_time_s']-(r['steps']-1)/50)<1e-12
   assert hashlib.sha256(np.asarray(r['actions'],dtype=np.float64).tobytes()).hexdigest()==r['command_sha256']
   assert r['penalized_time_s']==(r['race_time_s'] if r['success'] else 30)
   assert len(r['durations_ms'])==len(r['solver_statuses'])==len(r['actions'])==r['total_control_calls']==r['steps']
   assert r['failed_solve_ticks']==sum(z!=0 for z in r['solver_statuses'])
   assert r['fallback_ticks']==len(r['fallback_indices'])
   assert set(i for i,v in enumerate(r['solver_statuses']) if v!=0)<=set(r['fallback_indices'])
   assert np.isfinite(r['actions']).all() and np.isfinite(r['durations_ms']).all()
   assert r['initial_state_sha256']==json.loads((D/st/'states'/f"{r['seed']}.json").read_text())['sha256']
 for seed in plan['seeds']:
  state=json.loads((D/st/'states'/f'{seed}.json').read_text());arrays=np.load(D/st/'states'/f'{seed}.npz');h=hashlib.sha256(state['tree'].encode())
  for i in range(len(arrays.files)):
   a=arrays[str(i)];h.update(str((a.shape,str(a.dtype))).encode());h.update(a.tobytes())
  assert h.hexdigest()==state['sha256']
 checks.append(dict(stage=st,candidates=len(x),episodes=sum(map(len,x.values())),all_episode_and_state_checks='PASS'))
(D/'audit.json').write_text(json.dumps(checks,indent=2));print(checks)

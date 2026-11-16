import pathlib,json,hashlib,csv
import numpy as np
from analyze import load,ci
D=pathlib.Path(__file__).resolve().parent;M=json.loads((D/'manifest.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(D/'manifest.json')==(D/'manifest.sha256').read_text().strip()
assert sha(D/'execution_manifest.json')==(D/'execution_manifest.sha256').read_text().strip()
for f,h in {**M['source_hashes'],**M['libraries'],**json.loads((D/'execution_manifest.json').read_text())['scripts']}.items():assert sha(D/f)==h,f
assert json.loads((D/'validation/runtime.json').read_text())['versions']==M['versions']
loaded=json.loads((D/'loaded_solver_libraries.json').read_text())
assert len(loaded)>=3
for f,h in loaded.items():assert sha(pathlib.Path(f))==h and M['libraries'][f]==h
x=load();assert set(x)==set(M['candidates']);seeds=M['seeds']['validation'];assert len(set(seeds))==100 and not set(seeds)&set(M['seeds']['smoke'])
checks=[]
for name,rs in x.items():
 assert len(rs)==100 and sorted(r['seed'] for r in rs)==sorted(seeds)
 s=M['candidates'][name]['settings'];expected=hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
 for r in rs:
  assert r['settings_sha256']==expected and r['solver_receipt']['settings']==s
  assert r['race_time_s']==r['steps']/50 and r['official_time_s']==(r['steps']-1)/50
  assert r['penalized_time_s']==(r['race_time_s'] if r['success'] else 30)
  assert (int(r['terminal_observation']['n_gates_passed'])==5)==r['success']
  assert r['steps']==len(r['actions'])==len(r['durations_ms'])==len(r['solver_statuses'])==r['total_control_calls']
  assert hashlib.sha256(np.asarray(r['actions'],dtype=np.float64).tobytes()).hexdigest()==r['command_sha256']
  assert np.isfinite(r['actions']).all() and np.isfinite(r['durations_ms']).all()
  assert r['failed_solve_ticks']==sum(v!=0 for v in r['solver_statuses'])
  assert r['fallback_ticks']==len(r['fallback_indices'])
  assert set(i for i,v in enumerate(r['solver_statuses']) if v!=0)<=set(r['fallback_indices'])
  assert r['initial_state_sha256']==json.loads((D/'validation/states'/f"{r['seed']}.json").read_text())['sha256']
  assert 'power_start' not in r and 'power_end' not in r
 checks.append(dict(candidate=name,n=100,episode_checks='PASS',state_pairing='PASS',effective_settings_and_formulation='PASS'))
for seed in seeds:
 p=D/'validation/states'/str(seed);state=json.loads(p.with_suffix('.json').read_text());arrays=np.load(p.with_suffix('.npz'));h=hashlib.sha256(state['tree'].encode())
 for i in range(len(arrays.files)):
  a=arrays[str(i)];h.update(str((a.shape,str(a.dtype))).encode());h.update(a.tobytes())
 assert h.hexdigest()==state['sha256']
rows=list(csv.DictReader((D/'metrics.csv').open()))
for r in rows:
 rs=x[r['candidate']];k=sum(s['success'] for s in rs);lo,hi=ci(k,100)
 assert int(r['finishes'])==k and float(r['completion'])==k/100
 assert float(r['completion_ci_lower'])==lo and float(r['completion_ci_upper'])==hi
 assert abs(float(r['penalized_mean_time_s'])-sum(s['penalized_time_s'] for s in rs)/100)<1e-10
(D/'audit.json').write_text(json.dumps(dict(status='PASS',episodes=600,candidates=checks,source_and_library_hashes='PASS',full_initial_state_hashes='PASS',metrics_recomputed='PASS'),indent=2));print('PASS: 600 episodes, six configurations, exact states, settings, source hashes and metrics')

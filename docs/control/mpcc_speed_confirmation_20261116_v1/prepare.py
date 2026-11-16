import pathlib,json,csv,hashlib,shutil,gzip,datetime,platform,subprocess,importlib.metadata,os
R=pathlib.Path('/home/askho/repos/lsy_drone_racing');D=R/'docs/control/mpcc_speed_confirmation_20261116_v1';D.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=list(csv.DictReader((R/'docs/control/mpcc_assessment_20261112_v1/configuration_metrics.csv').open()))
ids=['019517bc8610b76e','fa4dcdf73fb692dd','c2173b6a65d8a821','ca0204a19034da62','58110da550d08bfd','db0c168839bc5a04'];selected=[next(r for r in rows if r['configuration_id']=='config_'+i) for i in ids]
S=D/'source';shutil.copytree(R/'docs/control/mpcc_campaign_20261112_v1/source',S,ignore=shutil.ignore_patterns('__pycache__'))
for n in ['mpcc_prediction_core.py','mpcc_prediction_solver.py','mpcc_prediction_model.py']:shutil.copy2(R/'lsy_drone_racing/control'/n,S/'lsy_drone_racing/control'/n)
vroot=R/'.local/mpcc-study/v3-informed-screen-n20-v1/source/lsy_drone_racing/control'
for n in ['attitude_mpcc_v3.py','mpcc_v3_geometry.py','mpcc_v3_model.py','mpcc_v3_solver.py','mpcc_v3_settings.py']:shutil.copy2(vroot/n,S/'lsy_drone_racing/control'/n)
shutil.copy2(R/'.local/mpcc-study/v3-informed-screen-n20-v1/naming_v2.py',D/'historical_v3_naming.py')
checks=[]
for r in selected:
 for n,h in json.loads(r['implementation_sources_json']).items():
  candidates=[S/'lsy_drone_racing/control'/n,R/'scripts'/n,R/'acados/lib'/n,R/'.pixi/envs/default/lib/python3.13/site-packages/casadi'/n]
  match=next((p for p in candidates if p.exists() and sha(p)==h),None);assert match,(r['case_name'],n,h)
  checks.append(dict(candidate=r['case_name'],file=n,recorded_sha256=h,matched_path=str(match)))
 for n,h in json.loads(r['environment_json'])['source_pins'].items():
  p=R/n if n.startswith('.pixi') else S/'lsy_drone_racing'/n
  assert sha(p)==h,(n,sha(p),h)
base=json.loads(selected[0]['environment_json'])['config'];assert all(json.loads(r['environment_json'])['config']==base for r in selected)
used=set()
def walk(v):
 if isinstance(v,dict):
  for k,x in v.items():
   if k=='seed' and isinstance(x,int):used.add(x)
   elif k in ['seeds','A','B','C','smoke'] and isinstance(x,list) and all(isinstance(y,int) for y in x):used.update(x)
   else:walk(x)
 elif isinstance(v,list):
  for x in v:walk(x)
with gzip.open(R/'docs/control/mpcc_assessment_20261112_v1/cohort_evidence.jsonl.gz','rt') as f:
 for l in f:walk(json.loads(l))
walk(json.loads((R/'docs/control/mpcc_campaign_20261112_v1/manifest.json').read_text()))
import random
rng=random.Random(202611161005);seeds=[]
while len(seeds)<104:
 s=rng.randrange(1,2**31-1)
 if s not in used and s not in seeds:seeds.append(s)
m=dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),objective='Exactly 100 new matched episodes for all six deduplicated table configurations with historical n<100 and completion >=40%. No tuning or outcome-dependent stopping.',candidates={r['case_name']:dict(historical_id=r['configuration_id'],family='v3' if r['case_name'] in ['reference_speed_2p8','depth_0p35'] else 'prediction' if r['case_name'] in ['drag_10','speed33_combined'] else 'broad',settings=json.loads(r['settings_json']),behavior=json.loads(r['active_behavior_json']),historical=r) for r in selected},environment=base,seeds=dict(smoke=seeds[:2],validation=seeds[2:102],replay=seeds[102:]),freshness=dict(checked_unique_seeds=len(used),overlap=[]),source_hashes={str(p.relative_to(D)):sha(p) for p in S.rglob('*') if p.is_file()},libraries={str(p):sha(p) for p in (R/'acados/lib').glob('*.so')},selection='No reselection or tuning; all six complete 100 episodes. New validation remains separate from screening; no pooling.',time_convention='completed control steps / 50; original zero-based official time also recorded; failed episodes score 30 s',construction='Broad and prediction: fixed per-configuration build cache, current path bound updated. V3: original unique fresh build plus embedded one-ULP bound restoration and naming-only historical adapter.',stats='Exact Clopper-Pearson 95% individual completion intervals; matched seed differences with exact McNemar and Holm across 15 pairs; conservative paired completion intervals and deterministic paired bootstrap times.',hardware=dict(platform=platform.platform(),cpu=pathlib.Path('/proc/cpuinfo').read_text(),affinity=sorted(os.sched_getaffinity(0))),versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','jax','jaxlib','mujoco','crazyflow','gymnasium','casadi','acados-template']})
(D/'manifest.json').write_text(json.dumps(m,indent=2));(D/'manifest.sha256').write_text(sha(D/'manifest.json'));(D/'source_verification.json').write_text(json.dumps(checks,indent=2));(D/'seeds.json').write_text(json.dumps(m['seeds'],indent=2));print(D)

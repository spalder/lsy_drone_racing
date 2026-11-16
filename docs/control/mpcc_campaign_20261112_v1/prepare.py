import csv,json,hashlib,shutil,pathlib,datetime,platform,subprocess,gzip
D=pathlib.Path(__file__).resolve().parent; R=D.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rs=list(csv.DictReader(open(R/'docs/control/mpcc_assessment_20261112_v1/configuration_metrics.csv')))
ids=['a460142e3d70aa79','2470aab06585d4ce','3742dfc435fa9211','c38f523f225d4537','e5d615f48e78a5a5','dd387f0828a6f79d','333607745da71732','4f870307a460c27a','040437a726eb52b8','ed7e53a4a9e93552']
rows=[next(r for r in rs if r['configuration_id']=='config_'+i) for i in ids]
S=D/'source'; S.mkdir(exist_ok=True)
base=R/'.local/mpcc-study/broad-20261103T152500Z-r2/checkout/lsy_drone_racing'
shutil.copytree(base,S/'lsy_drone_racing',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
# Verify every candidate's entire recorded controller bundle and environment source pins.
checks=[]
for r in rows:
 for name,h in json.loads(r['implementation_sources_json']).items():
  p=R/'acados/lib'/name if name.endswith('.so') else S/'lsy_drone_racing/control'/name
  assert sha(p)==h,(p,h,sha(p));checks.append(str(p))
 for name,h in json.loads(r['environment_json'])['source_pins'].items():
  p=R/name if name.startswith('.pixi') else S/'lsy_drone_racing'/name
  assert sha(p)==h,(p,h,sha(p))
used=set()
with gzip.open(R/'docs/control/mpcc_assessment_20261112_v1/cohort_evidence.jsonl.gz','rt') as f:
 for line in f:
  def walk(v):
   if isinstance(v,dict):
    for k,x in v.items():
     if k=='seed' and isinstance(x,int):used.add(x)
     else:walk(x)
   elif isinstance(v,list):
    for x in v:walk(x)
  walk(json.loads(line))
import numpy as np
rng=np.random.default_rng(202611121739)
seeds=[]
while len(seeds)<1703:
 s=int(rng.integers(1,2**31-1))
 if s not in used and s not in seeds:seeds.append(s)
manifest=dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidates={r['case_name']:dict(id=r['configuration_id'],settings=json.loads(r['settings_json']),historical=r) for r in rows},environment=json.loads(rows[0]['environment_json'])['config'],seeds=dict(smoke=seeds[:3],A=seeds[3:203],B=seeds[203:703],C=seeds[703:1703]),freshness=dict(retained_unique_seeds=len(used),overlap=0,scope='normalized retained assessment evidence; external unretained runs unknown'),source_hashes={str(p.relative_to(D)):sha(p) for p in S.rglob('*') if p.is_file()},libraries={str(p):sha(p) for p in (R/'acados/lib').glob('*.so')},hardware=dict(platform=platform.platform(),cpu=pathlib.Path('/proc/cpuinfo').read_text(),affinity=sorted(__import__('os').sched_getaffinity(0))),design='Serial candidates, interleaved by seed; A top 5 by finishes then penalized mean then failed ticks then call p99; B top 3 same hierarchy; C independent final ranking. No tuning. Pilot runtime may determine fixed reduced sample sizes before A. Smoke excluded. Paired bootstrap 95% intervals; exact McNemar with Holm adjustment; CP exact individual CI. Practical completion margin 0.03, penalized-time margin 0.5 seconds; inconclusive differences do not establish equivalence.')
(D/'manifest.json').write_text(json.dumps(manifest,indent=2));(D/'manifest.sha256').write_text(sha(D/'manifest.json')+'\n')
for k,v in manifest['seeds'].items():(D/f'seeds_{k}.json').write_text(json.dumps(v))
(D/'candidate_selection.md').write_text('# Frozen candidate selection\n\nCompletion first; historical alpha rankings are contextual, correlated exploratory indicators. All ten suggested candidates retained to cover gate geometry, pole clearance, cost weighting, speed, and reference behavior. Equal E09 screening completion does not establish equivalence; both weights retained to expose state-specific rescues. F1/F1_2 is an explicit scientific question.\n\n'+ '\n'.join(f"- **{r['case_name']}** `{r['configuration_id']}`: {r['finishes']}/{r['episodes']}, exact lower {float(r['completion_ci_lower']):.3f}; penalized {r['penalized_mean_time_s']} s; complexity {r['complexity_score']}. Source `{r['run_path']}`; common historical `{r['environment_id']}`. Complete settings and verified implementation/library hashes in manifest." for r in rows)+'\n\nExcluded: F1_2_3 and F1_3 (73/100, redundant multi-change relatives); small n geometry variants (less precision, redundant). Modified-core incumbent and opt_a758e8cb3e87 have substantial independent evidence but different legacy implementation and slower 9.6–9.8 s behavior; retain environment-specific evidence rather than replacing a more informative official-core candidate. No historical samples pooled. Missing timing is not zero. Original 106 PASS audit not repeated.\n')
print(D)

import pathlib,json,itertools,collections,hashlib
import numpy as np
from analyze import load,export,mechanism
D=pathlib.Path(__file__).resolve().parent
rows=[];difficult=[];strata=[];fail=[]
for st in ['A','B','C']:
 x=load(st)
 if not x:continue
 seeds=sorted(set(r['seed'] for rs in x.values() for r in rs));maps={n:{r['seed']:r for r in rs} for n,rs in x.items()}
 for seed in seeds:
  rs=[v[seed] for v in maps.values() if seed in v];difficult.append(dict(stage=st,seed=seed,candidates=len(rs),finishes=sum(r['success'] for r in rs),successful_candidates=';'.join(r['candidate'] for r in rs if r['success']),failed_candidates=';'.join(r['candidate'] for r in rs if not r['success'])))
 for a,b in itertools.combinations(sorted(x),2):
  for seed in sorted(maps[a].keys()&maps[b].keys()):
   aa,bb=maps[a][seed],maps[b][seed]
   rows.append(dict(stage=st,reference=a,candidate=b,seed=seed,reference_success=aa['success'],candidate_success=bb['success'],penalized_delta_s=bb['penalized_time_s']-aa['penalized_time_s'],paired_state_verified=aa['initial_state_sha256']==bb['initial_state_sha256']))
 states={seed:json.loads((D/st/'states'/f'{seed}.json').read_text())['observation'] for seed in seeds}
 for dim,key in enumerate(['initial_x','initial_y','initial_z']):
  vals=np.array([states[s]['pos'][dim] for s in seeds]);edges=np.quantile(vals,[0,.25,.5,.75,1])
  for name,rs in x.items():
   for q in range(4):
    subset=[r for r in rs if edges[q]<=states[r['seed']]['pos'][dim] and (states[r['seed']]['pos'][dim]<edges[q+1] or q==3)]
    strata.append(dict(stage=st,candidate=name,variable=key,quartile=q+1,lower=edges[q],upper=edges[q+1],n=len(subset),finishes=sum(r['success'] for r in subset),completion=np.mean([r['success'] for r in subset]) if subset else None))
 for name,rs in x.items():
  co=collections.Counter()
  for r in rs:
   if not r['success']:
    contact=r.get('contacts',[])
    labels=[]
    for ct in contact:
     text=' '.join(str(v) for v in ct.values())
     if 'drone' not in text:continue
     if 'gate' in text:
      label='upper_gate_frame' if any(w in text.lower() for w in ['top','upper']) else 'gate_frame_unspecified'
     elif 'obstacle' in text:label='pole'
     else:continue
     labels.append(label)
    if not labels and r.get('prewarp_position') is not None:
     pos=np.asarray(r['prewarp_position']).reshape(-1,3)[0]
     lim=json.loads((D/'manifest.json').read_text())['environment']['env']['track']['safety_limits']
     if np.any(pos<np.asarray(lim['pos_limit_low'])) or np.any(pos>np.asarray(lim['pos_limit_high'])):labels=['position_bounds']
    co.update(set(labels) or [mechanism(r)])
  fail.extend(dict(stage=st,candidate=name,mechanism=k,episodes=v) for k,v in co.items())
export(D/'paired_episode_outcomes.csv',rows);export(D/'seed_difficulty.csv',difficult);export(D/'initial_position_strata.csv',strata);export(D/'failure_clusters.csv',fail)

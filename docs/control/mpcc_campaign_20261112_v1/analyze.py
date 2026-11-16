"""Regenerate stage metrics, paired inference, failure strata, rankings, charts and report."""
import pathlib,json,csv,itertools,hashlib
import numpy as np
from scipy.stats import beta,binomtest
D=pathlib.Path(__file__).resolve().parent
M=json.loads((D/'manifest.json').read_text())
def export(p,rows):
 if rows:
  with p.open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def load(stage):
 out={}
 for f in (D/stage).glob('*.json'):
  r=json.loads(f.read_text())
  if 'candidate' in r:out.setdefault(r['candidate'],[]).append(r)
 for v in out.values():v.sort(key=lambda r:r['seed'])
 return out
def metrics(stage,x):
 rows=[]
 for name,rs in x.items():
  n=len(rs);k=sum(r['success'] for r in rs);times=[r['race_time_s'] for r in rs if r['success']];dur=np.concatenate([r['durations_ms'] for r in rs]);h=M['candidates'][name]['historical']
  rows.append(dict(stage=stage,candidate=name,configuration_id=M['candidates'][name]['id'],n=n,finishes=k,completion=k/n,ci_lower=beta.ppf(.025,k,n-k+1) if k else 0,ci_upper=beta.ppf(.975,k+1,n-k) if k<n else 1,penalized_mean_s=np.mean([r['penalized_time_s'] for r in rs]),successful_mean_s=np.mean(times) if times else None,successful_p90_s=np.quantile(times,.9) if times else None,failed_solver_ticks=sum(r['failed_solve_ticks'] for r in rs),fallback_ticks=sum(r['fallback_ticks'] for r in rs),solver_affected_episodes=sum(r['failed_solve_ticks']>0 for r in rs),fallback_affected_episodes=sum(r['fallback_ticks']>0 for r in rs),control_calls=len(dur),compute_mean_ms=np.mean(dur),compute_p99_ms=np.quantile(dur,.99),deadline_overruns=sum(dur>20),deadline_overrun_fraction=np.mean(dur>20),complexity=h['complexity_score'],environment='frozen_official_core_CPU_current_runtime',provenance='verified source and library hashes; initial state verified',validation_status={'A':'new screening','B':'postselection confirmation','C':'independent final confirmation'}[stage],alpha_5=None,alpha_10=None,alpha_15=None,alpha_20=None,alpha_25=None,alpha_30=None,alpha_50=None,alpha_context='historical exploratory; original score files unavailable'))
 rows=sorted(rows,key=lambda r:(-r['finishes'],r['penalized_mean_s'],r['failed_solver_ticks'],r['compute_p99_ms']))
 for i,r in enumerate(rows,1):r['observed_rank_within_stage']=i
 return rows
def boot(v,rng):
 v=np.asarray(v,dtype=float)
 if not len(v):return [None,None]
 # bounded batch memory, deterministic resampling
 vals=np.concatenate([v[rng.integers(0,len(v),size=(1000,len(v)))].mean(1) for _ in range(10)])
 return np.quantile(vals,[.025,.975]).tolist()
def pairs(stage,x):
 rows=[];rng=np.random.default_rng(113355)
 for a,b in itertools.combinations(sorted(x),2):
  aa={r['seed']:r for r in x[a]};bb={r['seed']:r for r in x[b]};shared=sorted(aa.keys()&bb.keys());n=len(shared)
  if not n:continue
  assert all(aa[s]['initial_state_sha256']==bb[s]['initial_state_sha256'] for s in shared)
  av=np.array([aa[s]['success'] for s in shared],int);bv=np.array([bb[s]['success'] for s in shared],int);gain=int(sum((bv==1)&(av==0)));loss=int(sum((av==1)&(bv==0)));d=bv-av
  # conservative interval: Bonferroni CP bounds for rescue and regression multinomial cells
  lo=lambda k:float(beta.ppf(.0125,k,n-k+1)) if k else 0
  hi=lambda k:float(beta.ppf(.9875,k+1,n-k)) if k<n else 1
  pen=np.array([bb[s]['penalized_time_s']-aa[s]['penalized_time_s'] for s in shared]);tt=[bb[s]['race_time_s']-aa[s]['race_time_s'] for s in shared if aa[s]['success'] and bb[s]['success']]
  pl,pu=boot(pen,rng);tl,tu=boot(tt,rng);bl,bu=boot(d,rng)
  rows.append(dict(stage=stage,reference=a,candidate=b,n=n,rescues=gain,regressions=loss,completion_difference=float(np.mean(d)),completion_ci_lower=lo(gain)-hi(loss),completion_ci_upper=hi(gain)-lo(loss),completion_bootstrap_lower=bl,completion_bootstrap_upper=bu,mcnemar_exact_p=binomtest(gain,gain+loss).pvalue if gain+loss else 1.,penalized_delta_s=float(np.mean(pen)),penalized_ci_lower=pl,penalized_ci_upper=pu,shared_success_n=len(tt),successful_delta_s=float(np.mean(tt)) if tt else None,successful_ci_lower=tl,successful_ci_upper=tu))
 order=sorted(range(len(rows)),key=lambda i:rows[i]['mcnemar_exact_p']);last=0
 for j,i in enumerate(order):last=max(last,min(1,rows[i]['mcnemar_exact_p']*(len(rows)-j)));rows[i]['mcnemar_holm_p']=last
 return rows
def mechanism(r):
 if r['success']:return 'success'
 if r['truncated']:return 'timeout'
 contacts=r.get('contacts',[])
 names=' '.join(' '.join(str(c.get(k,'')) for k in ['name1','name2','body1','body2']) for c in contacts if 'drone' in str(c))
 if 'gate' in names:return 'gate_contact'
 if 'obstacle' in names:return 'pole_contact'
 return 'bounds_or_unresolved_contact'
def main():
 allrows=[];pp=[];failure=[]
 for st in ['A','B','C']:
  x=load(st)
  if not x:continue
  rr=metrics(st,x);allrows.extend(rr);pr=pairs(st,x);pp.extend(pr);export(D/f'metrics_{st}.csv',rr);export(D/f'paired_{st}.csv',pr)
  for name,rs in x.items():
   for r in rs:
    ob=r['terminal_observation'];pos=np.array(ob['pos']);gp=int(ob['n_gates_passed'])
    state=json.loads((D/st/'states'/f"{r['seed']}.json").read_text())['observation']
    pre=np.asarray(r['prewarp_position']).reshape(-1,3)[0] if r.get('prewarp_position') is not None else pos
    failure.append(dict(stage=st,candidate=name,seed=r['seed'],success=r['success'],gates_passed=gp,terminal_x=pos[0],terminal_y=pos[1],terminal_z=pos[2],prewarp_x=pre[0],prewarp_y=pre[1],prewarp_z=pre[2],initial_x=state['pos'][0],initial_y=state['pos'][1],initial_z=state['pos'][2],mechanism=mechanism(r)))
 finalists=set(load('C'))
 for r in allrows:
  r['validation_tier']='independently evaluated finalist' if r['candidate'] in finalists else 'not advanced to final confirmation'
  r['historical_configuration_id']=r['configuration_id']
  versions=json.loads((D/r['stage']/'runtime.json').read_text())['versions']
  r['comparison_environment_sha256']=hashlib.sha256(json.dumps(dict(environment=M['environment'],source_hashes=M['source_hashes'],libraries=M['libraries'],runtime_versions=versions,runner_sha256=hashlib.sha256((D/'run.py').read_bytes()).hexdigest()),sort_keys=True).encode()).hexdigest()
  r['campaign_configuration_id']='campaign_config_'+hashlib.sha256(json.dumps(dict(environment=r['comparison_environment_sha256'],settings=M['candidates'][r['candidate']]['settings']),sort_keys=True).encode()).hexdigest()[:16]
 export(D/'final_rankings.csv',allrows);export(D/'paired_comparisons.csv',pp);export(D/'failure_analysis.csv',failure)
 export(D/'numerical_computational_health.csv',[{k:r[k] for k in ['stage','candidate','n','failed_solver_ticks','fallback_ticks','solver_affected_episodes','fallback_affected_episodes','control_calls','compute_mean_ms','compute_p99_ms','deadline_overruns','deadline_overrun_fraction']} for r in allrows])
 print(json.dumps(allrows,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)))
if __name__=='__main__':main()

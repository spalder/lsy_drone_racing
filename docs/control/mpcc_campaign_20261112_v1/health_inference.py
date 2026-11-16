import pathlib,itertools
from scipy.stats import beta,binomtest
from analyze import load,export
D=pathlib.Path(__file__).resolve().parent
rows=[];pp=[]
def cp(k,n,q=.025):return (float(beta.ppf(q,k,n-k+1)) if k else 0.,float(beta.ppf(1-q,k+1,n-k)) if k<n else 1.)
for st in ['A','B','C']:
 x=load(st)
 for name,rs in x.items():
  n=len(rs);k=sum(r['fallback_ticks']>0 or r['failed_solve_ticks']>0 for r in rs);lo,hi=cp(k,n)
  rows.append(dict(stage=st,candidate=name,n=n,numerically_affected_episodes=k,rate=k/n,ci_lower=lo,ci_upper=hi))
 stage=[]
 for a,b in itertools.combinations(sorted(x),2):
  aa={r['seed']:bool(r['fallback_ticks'] or r['failed_solve_ticks']) for r in x[a]};bb={r['seed']:bool(r['fallback_ticks'] or r['failed_solve_ticks']) for r in x[b]};ss=aa.keys()&bb.keys();n=len(ss);extra=sum(bb[s] and not aa[s] for s in ss);avoided=sum(aa[s] and not bb[s] for s in ss);lo,hi=cp(extra,n,.0125);l2,h2=cp(avoided,n,.0125)
  stage.append(dict(stage=st,reference=a,candidate=b,n=n,additional_affected=extra,avoided_affected=avoided,affected_rate_difference=(extra-avoided)/n,ci_lower=lo-h2,ci_upper=hi-l2,mcnemar_exact_p=binomtest(extra,extra+avoided).pvalue if extra+avoided else 1.))
 last=0
 for j,i in enumerate(sorted(range(len(stage)),key=lambda i:stage[i]['mcnemar_exact_p'])):
  last=max(last,min(1,stage[i]['mcnemar_exact_p']*(len(stage)-j)));stage[i]['mcnemar_holm_p']=last
 pp.extend(stage)
export(D/'health_confidence_intervals.csv',rows);export(D/'paired_health_comparisons.csv',pp)

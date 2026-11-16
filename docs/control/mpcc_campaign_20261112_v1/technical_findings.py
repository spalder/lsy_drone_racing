"""Data-derived technical findings; does not select or tune candidates."""
import json,pathlib,csv,collections,itertools
import numpy as np
from analyze import load,metrics,pairs,mechanism,boot,export
D=pathlib.Path(__file__).resolve().parent
rng=np.random.default_rng(919122)
lines=['# Detailed technical findings','']
compute=[];stratum_rows=[];status_rows=[]
for st in ['A','B','C']:
 x=load(st)
 if not x:continue
 rr=metrics(st,x);pp=pairs(st,x);maps={n:{r['seed']:r for r in rs} for n,rs in x.items()}
 lines+=['## Stage '+st,'']
 for n,rs in sorted(x.items()):
  nums=[r for r in rs if r['failed_solve_ticks'] or r['fallback_ticks']]
  hist=collections.Counter(v for r in rs for v in r['solver_statuses'])
  status_rows.extend(dict(stage=st,candidate=n,status=k,ticks=v) for k,v in sorted(hist.items()))
  lines.append(f"{n}: {len(nums)} episodes with nonzero solver status or explicit fallback; {sum(r['success'] for r in nums)} of those episodes finished. Affected seeds/ticks: "+str([(r['seed'],r['failed_solve_ticks'],r['fallback_ticks']) for r in nums])+'.')
 for p in pp:
  a,b=p['reference'],p['candidate'];aa,bb=maps[a],maps[b]
  seed=sorted(aa.keys()&bb.keys());shared=[s for s in seed if aa[s]['success'] and bb[s]['success']]
  # Timing comparison uses mean calls on jointly successful identical seeds,
  # avoiding unequal race durations/outcome mix. Bootstrap unit is the race.
  d=[np.mean(bb[s]['durations_ms'])-np.mean(aa[s]['durations_ms']) for s in shared]
  lo,hi=boot(d,rng)
  compute.append(dict(stage=st,reference=a,candidate=b,shared_success_n=len(shared),paired_episode_mean_compute_delta_ms=np.mean(d) if d else None,bootstrap_lower=lo,bootstrap_upper=hi))
  if (a=='F1' and b in ['F1_2','G07_pole_width_0p4375']) or (a.startswith('E09') and b.startswith('E09')):
   rescue=[s for s in seed if not aa[s]['success'] and bb[s]['success']];regress=[s for s in seed if aa[s]['success'] and not bb[s]['success']]
   lines+=['',f"**{a} → {b}:** {p['completion_difference']*100:.2f} pp completion, conservative 95% interval [{p['completion_ci_lower']*100:.2f}, {p['completion_ci_upper']*100:.2f}]; exact McNemar Holm p={p['mcnemar_holm_p']:.5g}. Rescues {rescue}; regressions {regress}. Shared-success time difference {p['successful_delta_s']:.5f} s on {p['shared_success_n']} races. These states are genuinely paired; stage role governs whether this is screening or independent evidence.",'']
   for label,ss in [('rescues',rescue),('regressions',regress)]:
    counts=collections.Counter(mechanism(aa[s] if label=='rescues' else bb[s]) for s in ss)
    lines.append(f'{label} losing mechanisms: {dict(counts)}.')
    for s in ss:
     init=json.loads((D/st/'states'/f'{s}.json').read_text())['observation'];loser=aa[s] if label=='rescues' else bb[s]
     lines.append(f"Seed {s} ({label}): starting position {init['pos']}; losing mechanism {mechanism(loser)}, gate occurrences passed {loser['terminal_observation']['n_gates_passed']}, pre-warp impact position {loser['prewarp_position']}.")
 seed=sorted(next(iter(maps.values())).keys());allfailed=[s for s in seed if all(not mm[s]['success'] for mm in maps.values())];allsuccess=[s for s in seed if all(mm[s]['success'] for mm in maps.values())]
 lines+=['',f"Common difficulty: {len(allfailed)}/{len(seed)} seeds defeated every tested candidate; {len(allsuccess)}/{len(seed)} were finished by every candidate. All-failed seeds: {allfailed}. This assesses robustness within the candidate set, not the prevalence of universally impossible races.",'']
 # Association of first-gate/pole coordinates can be limited by sensor visibility;
 # position quartiles are universally observed and reproducible.
 for dim,axis in enumerate('xyz'):
  vals={s:json.loads((D/st/'states'/f'{s}.json').read_text())['observation']['pos'][dim] for s in seed};edges=np.quantile(list(vals.values()),[0,.25,.5,.75,1])
  for n,mm in maps.items():
   rates=[]
   for q in range(4):
    ss=[s for s in seed if vals[s]>=edges[q] and (vals[s]<edges[q+1] or q==3)];k=sum(mm[s]['success'] for s in ss);rates.append(k/len(ss))
   stratum_rows.append(dict(stage=st,candidate=n,axis=axis,q1_completion=rates[0],q2_completion=rates[1],q3_completion=rates[2],q4_completion=rates[3],max_minus_min_completion=max(rates)-min(rates)))
export(D/'solver_status_histogram.csv',status_rows);export(D/'paired_compute_comparisons.csv',compute);export(D/'initial_condition_sensitivity.csv',stratum_rows)
(D/'technical_findings.md').write_text('\n\n'.join(lines))

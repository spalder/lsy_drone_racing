"""Independent health, matching, paired/segment analysis and deterministic reports."""
import gzip,hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.stats import beta
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def gz(p):
 with gzip.open(p,'rt') as f:return json.load(f)
def interval(delta):
 if not delta:return None
 x=np.array(delta);rng=np.random.default_rng(20261104);return np.percentile(x[rng.integers(len(x),size=(10000,len(x)))].mean(axis=1),[2.5,97.5]).tolist()
def pair(a,b):
 aa={r['seed']:r for r in a};bb={r['seed']:r for r in b};assert aa.keys()==bb.keys()
 sa={s for s in aa if aa[s]['success']};sb={s for s in bb if bb[s]['success']};shared=sorted(sa&sb);d=[(bb[s]['steps']-aa[s]['steps'])*.02 for s in shared]
 return dict(shared_n=len(shared),shared_seeds=shared,delta_s=float(np.mean(d)) if d else None,bootstrap95_s=interval(d),rescues=sorted(sb-sa),regressions=sorted(sa-sb),deltas_s=d)
def health(folder,plan,case):
 episodes=read(folder/'episodes.json');assert [r['seed'] for r in episodes]==plan['seeds'];events=[];fallback=[];invalid=[];violations=[];initial={};summaries=[];segment={};backend=[];overhead=[];slacks=[];angles=[];horizon_caps=0;horizon_total=0;latencies=[];crossings={};applied_caps=0
 for i,ep in enumerate(episodes):
  assert ep['requested_settings']==ep['effective_settings']==plan['cases'][case]
  d=gz(folder/f'episode-{i:03d}/diagnostics.compact.json.gz');extra=gz(folder/f'episode-{i:03d}/research.json.gz');ticks=d['tick_records'];rr=extra['ticks'];assert len(ticks)==len(rr)==ep['steps'];initial[ep['seed']]=dict(state=ep['initial_state'],gate_poses=d['geometry_records'][0]['gate_poses']);backend.append(extra['backend'])
  audit_runtime(folder,ep,extra,plan,case)
  assert extra['formulation']==plan['formulations'][case];assert case in Path(extra['backend']['library']).name
  if extra['formulation']['kind']!='hard':assert extra['backend']['initial_C_zero_verified']
  for k,v in plan['cases'][case]['numerics'].items():assert extra['backend']['generated_options'][k]==v
  seed=ep['seed'];perseed={}
  if not ep['success']:key=str(ticks[-1]['required_gate_occurrence']);crossings[key]=crossings.get(key,0)+1
  assert ep['success']==(ep['gates_passed']==5)
  for j,(tick,r) in enumerate(zip(ticks,rr)):
   assert tick['tick']==r['tick']==j
   assert tick['solver_status']==r['rti'][-1]['status']
   if tick['solver_status']!=0:events.append([seed,j,int(tick['solver_status'])])
   if r['fallback'] or tick['virtual_speed_sunit_per_s'] is None:fallback.append([seed,j])
   command=np.asarray(tick['command']);valid=bool(np.isfinite(command).all() and np.all(command>=np.asarray(tick['command_bounds_low'])-1e-5) and np.all(command<=np.asarray(tick['command_bounds_high'])+1e-5));assert valid==r['finite_valid_command']
   if not valid:invalid.append([seed,j])
   for q in r['rti']:
    overhead.append(q['instrumentation_ms'])
    if q['constraints_checked']:
     bad=not q['finite'] or max(q['max_hard_violation'],q['max_soft_violation'])>1e-5
     if bad:violations.append([seed,j,q['rti_pass'],q.get('max_hard_violation'),q.get('max_soft_violation')])
     slacks.append(q['max_slack']);angles.append(q['max_predicted_attitude_violation_by_axis']);horizon_caps+=q['horizon_cap_active_count'];horizon_total+=q['horizon_input_count']
   latencies.append(tick['timing']['whole_compute_duration_ms']);applied_caps+=int(tick['virtual_speed_cap_saturated'])
   # Only intervals within completed crossing legs are included. Terminal sentinel observations never enter.
   occ=int(tick['required_gate_occurrence']);pos=np.asarray(tick['observation_position_m']);geom=d['geometry_records'][tick['geometry_record_index']]
   if occ>ep['gates_passed'] or not np.isfinite(pos).all() or np.array_equal(pos,[-1,-1,-1]):continue
   s=tick['progress_sunit'];departure=any(g['center_s']<=s<=g['departure_s'] for g in geom['occurrences']) if 'occurrences' in geom else any(g['center_s']<=s<=g['departure_s'] for g in geom.get('gate_occurrences',[]))
   label='departure' if departure else ('turn' if tick['curvature_per_m'] is not None and tick['curvature_per_m']>=.8 else 'straight_approach')
   entry=perseed.setdefault(str(occ),dict(straight_approach=0.,turn=0.,departure=0.,total=0.,revisions=[]));entry[label]+=.02;entry['total']+=.02
   if tick['revision'] not in entry['revisions']:entry['revisions'].append(tick['revision'])
  segment[str(seed)]=perseed
 for file,digest in read(folder/'generated-sha256.json').items():assert sha(folder/'generated'/file)==digest
 generated=read(sorted((folder/'generated').rglob('ocp.json'))[-1]);spec=plan['formulations'][case];options=generated['solver_options'];expected=plan['cases'][case]
 for k,v in expected['numerics'].items():assert options[k]==v
 assert options['qp_solver_cond_N']==10 and options['qp_solver_iter_max']==50
 assert generated['dims']['nsbx']==(0 if spec['kind']=='hard' else 3)
 if spec['kind']!='hard':
  c=generated['constraints'];cost=generated['cost'];assert c['idxsbx']==c['idxsbx_e']==[0,1,2];assert generated['dims']['nsbx_e']==3
  for k in ['Zl','Zu']:assert cost[k]==[500000.]*3 and cost[k+'_e']==[10000.]*3
  for k in ['zl','zu']:assert cost[k]==cost[k+'_e']==[0.]*3
  assert options['cost_scaling']==[.02]*40+[1.]
  for suffix in ('','_e'):
   C=np.zeros((3,17));C[:,3:6]=np.eye(3);assert np.array_equal(c['C'+suffix],C);assert np.allclose(c['lg'+suffix],-.875-np.asarray(spec['caps_rad']));assert np.allclose(c['ug'+suffix],.875+np.asarray(spec['caps_rad']))
 # One failed QP capture for every nonzero tick, irrespective of whether race finishes.
 receipts=list((folder/'failed-QPs').glob('*/receipt.json')) if (folder/'failed-QPs').exists() else [];assert len(receipts)==len(events)
 for rp in receipts:
  receipt=read(rp);assert [receipt['seed'],receipt['tick'],receipt['status']] in events
  expected_previous=min(5,3*receipt['tick']+receipt['pass_number']-1) if receipt['seed'] in plan['prediction_seeds'] else 0
  assert receipt['predecessors']==expected_previous
  files=sorted(rp.parent.glob('qp-*.npz'));assert len(files)==receipt['predecessors']+1
  for j,p in enumerate(files):
   with np.load(p) as z:assert bool(z['getter_state_equal']) and bool(z['getter_qp_equal']) and int(z['status'])==(receipt['status'] if j==len(files)-1 else 0)
 k=sum(e['success'] for e in episodes);n=len(episodes);alllat=np.array(latencies);allover=np.array(overhead)
 result=dict(n=n,finishes=k,completion=k/n,completion_exact95=[float(beta.ppf(.025,k,n-k+1)) if k else 0.,float(beta.ppf(.975,k+1,n-k)) if k<n else 1.],successful_mean_s=float(np.mean([e['steps']*.02 for e in episodes if e['success']])) if k else None,numerical_ticks=len(events),numerical_episodes=len({e[0] for e in events}),numerical_successful_episodes=sum(any(e[0]==ep['seed'] for e in events) and ep['success'] for ep in episodes),fallback_ticks=len(fallback),invalid_command_ticks=len(invalid),constraint_violating_RTI_solves=len(violations),events=events,fallback_events=fallback,constraint_events=violations,health_pass=not(events or fallback or invalid or violations),completion_floor_pass=k/n>=.4,provisional_health_completion_pass=k/n>=.4 and not(events or fallback or invalid or violations),public_observed_50pct=k/n>=.5,failed_crossings=crossings,latency_ms=dict(p50=float(np.percentile(alllat,50)),p95=float(np.percentile(alllat,95)),p99=float(np.percentile(alllat,99)),max=float(alllat.max()),over20ms=int((alllat>20).sum())),instrumentation_ms=dict(mean=float(allover.mean()),p99=float(np.percentile(allover,99)),max=float(allover.max())),max_slack=max(slacks,default=0.),slack_percentiles=np.percentile(slacks,[50,95,99]).tolist() if slacks else None,max_predicted_attitude_violation_by_axis=np.max(angles,axis=0).tolist() if angles else None,max_observed_original_violation_by_axis=np.max([r['observed_original_bound_violation'] for i in range(len(episodes)) for r in gz(folder/f'episode-{i:03d}/research.json.gz')['ticks']],axis=0).tolist(),applied_cap_active_ticks=applied_caps,horizon_cap_active_inputs=horizon_caps,horizon_total_inputs=horizon_total)
 return result,episodes,initial,segment

def analyze(batch):
 batch=Path(batch);p=read(batch/'plan.json')
 for path,d in p['hashes'].items():assert sha(path)==d,path
 assert read(batch/'execution-completed.json')['episodes']==len(p['seeds'])*len(p['cases'])
 manifest=read(batch/'run-v1/execution-manifest.json');assert manifest['plan_sha256']==sha(batch/'plan.json') and manifest['seeds']==p['seeds'] and manifest['case_order']==p['case_order']
 stats={};episodes={};segments={};first=None
 for c in p['case_order']:
  stat,ep,initial,seg=health(batch/'run-v1'/c,p,c);stats[c]=stat;episodes[c]=ep;segments[c]=seg
  if first is None:first=initial
  else:assert first==initial
 pairs={};segmentpairs={};comparisons=[]
 if 'baseline_hard' in episodes:comparisons.extend(('baseline_hard',c) for c in episodes if c!='baseline_hard')
 if 'soft_reference' in episodes:comparisons.extend(('soft_reference',c) for c in episodes if c not in ['baseline_hard','soft_reference'])
 comparisons.extend((a,b) for a,b in [('speed_33','speed33_drag'),('drag_030','speed33_drag'),('speed_36','speed36_drag'),('drag_030','speed36_drag'),('speed_33','speed33_attitude'),('attitude11','speed33_attitude'),('speed33_drag','speed33_combined'),('speed33_attitude','speed33_combined'),('speed_33','speed33_tracking'),('speed_33','speed33_thrust')] if a in episodes and b in episodes)
 for a,b in comparisons:
  key=b+'-minus-'+a;pairs[key]=pair(episodes[a],episodes[b]);byseed={};nlegs=0
  for seed in p['seeds']:
   aa=segments[a][str(seed)];bb=segments[b][str(seed)];common=aa.keys()&bb.keys()
   if common:
    nlegs+=len(common);byseed[str(seed)]={label:sum(bb[o][label]-aa[o][label] for o in common) for label in ['straight_approach','turn','departure','total']}
  segmentpairs[key]=dict(shared_completed_legs=nlegs,shared_seed_n=len(byseed),seed_clustered_differences=byseed,statistics={label:dict(mean_s=float(np.mean(v)) if v else None,bootstrap95_s=interval(v)) for label in ['straight_approach','turn','departure','total'] for v in [[s[label] for s in byseed.values()]]})
 out=batch/'independent-analysis-v1';out.mkdir(exist_ok=False);write(out/'statistics.json',stats);write(out/'paired.json',pairs);write(out/'segments.json',dict(rule=p['segments'],episodes=segments,pairs=segmentpairs,interpretation='Completed matched crossing legs only; seed-clustered bootstrap. Local route classification boundaries may move across cases. These are descriptive speed-distribution comparisons, not causal identification of a schedule.'))
 write(out/'audit.json',dict(status='passed',episodes=sum(x['n'] for x in stats.values()),matched_initial_observations=True,source_hashes=True,generated_options_and_constraints=True,runtime_initial_rows=True,every_failure_captured=True,finite_valid_command_and_constraint_records_audited=True,source_sha256=sha(__file__)))
 return stats,pairs

def gate(batch):
 stats,_=analyze(batch);candidate=stats['diagnostic_expanded'];control=stats['diagnostic_cap10'];assert [e[1] for e in control['events']]==[153,154,155], 'Cap-.10 comparator failed to reproduce historical events';passed=candidate['health_pass'];write(Path(batch)/'gate-decision.json',dict(proceed=passed,criterion='Expanded episode zero status/fallback, finite valid commands, compliant predicted constraints on every successful RTI solve; outcome is retained but not a gate.',candidate=candidate,control=control));return passed

def report(root,status,reason):
 root=Path(root);screen=root/'screen';paths=[];lines=['# Expanded pitch and demand study','',status,'',reason,'']
 if (screen/'independent-analysis-v1/statistics.json').exists():
  stats=read(screen/'independent-analysis-v1/statistics.json');pairs=read(screen/'independent-analysis-v1/paired.json');lines+=['| Case | Finishes | Exact 95% interval | Successful mean | Status/fallback | Constraint RTI violations |','|---|---:|---|---:|---:|---:|']
  for c,r in stats.items():lines.append(f"| {c} | {r['finishes']}/{r['n']} | {r['completion_exact95']} | {r['successful_mean_s']} | {r['numerical_ticks']}/{r['fallback_ticks']} | {r['constraint_violating_RTI_solves']} |")
  lines+=['','## Paired speed comparisons','', 'Candidate minus comparator; times have 20ms episode resolution. Negative differences favor the candidate.']
  for key,r in pairs.items():lines.append(f"- {key}: shared={r['shared_n']}, mean={r['delta_s']} s, bootstrap95={r['bootstrap95_s']}, rescues={len(r['rescues'])}, regressions={len(r['regressions'])}.")
  leads=[]
  for c,r in stats.items():
   key=c+'-minus-soft_reference';pairing=pairs.get(key)
   if r['provisional_health_completion_pass'] and pairing and pairing['bootstrap95_s'] and pairing['bootstrap95_s'][1]<0:leads.append(dict(case=c,paired_s=pairing['delta_s'],interval=pairing['bootstrap95_s']))
  lines+=['','## Deterministic next-effort evidence','', 'Healthy completion-qualified cases with an entirely negative paired interval versus soft_reference: '+json.dumps(sorted(leads,key=lambda r:r['paired_s'])), 'Use paired.json and segments.json to assess higher reference demand, acceleration cost, model compensation, and gains/losses in straight/turn/departure intervals. No fixed worthwhile-gain threshold is imposed. Interaction probes and multiple exploratory comparisons require later independent validation. A lower successful-only mean or prediction error is insufficient.']
  write(root/'next-effort-evidence.json',dict(provisional_leads=leads,family_mapping=dict(higher_demand=['speed_33','speed_36'],model_compensation=['drag_030','speed33_drag','speed36_drag','attitude11','speed33_attitude','speed33_combined'],acceleration_cost=['speed33_thrust','speed33_tracking'],speed_schedule='Inspect paired straight/turn/departure profiles and total leg times; no schedule tested.'),automatic_promotion=False))
 lines+=['','Internal observed completion floor is inclusive 40% (12/30), with zero numerical/fallback ticks, finite valid commands, verified predicted constraints and worthwhile paired speed evidence. Public observed threshold is separately 50%. This exploratory screen does not confirm population reliability. Latency is advisory. Expanded bounds permit predicted angles up to 0.975/1.025/0.975 rad; feasibility establishes no safety/stability guarantee.','', 'Diagnostic/calibration/screen evidence remain separate. No automatic confirmation or promotion. See frozen plans, original analyzer, independent-analysis-v1, calibration receipt and execution-summary.json.']
 (root/'REPORT.md').write_text('\n'.join(lines)+'\n');(root/'HANDOFF.md').write_text('# Handoff\n\n'+status+'\n\n'+reason+'\n\nRead REPORT.md and execution-summary.json, then screen/plan.json and both analysis/audit directories if present. Gate and calibration data are separate selected-seed/runtime evidence. Review matched speed/segment results and health before requesting further experiments. No continuation is authorized by this script.\n')
 with zipfile.ZipFile(root/'compact-results.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
  for p in root.rglob('*'):
   if not p.is_file() or 'generated' in p.parts or 'failed-QPs' in p.parts or p.name.endswith('.log'):continue
   if p.name in ['REPORT.md','HANDOFF.md','execution-summary.json','frozen-orchestration.json','calibration-receipt.json','cohort-selection.json','gate-decision.json','plan.json','execution-manifest.json','episodes.json','audit.json','statistics.json','paired.json','pairwise-vs-baseline.json','prediction-summaries.json','next-effort-evidence.json'] or 'independent-analysis-v1' in p.parts and p.name!='segments.json':z.write(p,p.relative_to(root))


def audit_runtime(folder, ep, extra, plan, case):
 """Independent comparisons of captured live NLP memory with frozen generated spec."""
 receipt=read(folder/f"runtime-seed-{ep['seed']}.json")
 snapshots=[receipt,extra['runtime_initial'],extra['runtime_final']]
 for r in snapshots:
  assert r['seed']==ep['seed'] and r['loaded_mapping_verified'] and r['getter_observable_state_preserved']
  assert r['effective_numerics']==plan['cases'][case]['numerics']
  assert str(ep['seed']) in r['model'] and case in r['model']
  assert sha(r['library'])==r['library_sha256'] and sha(r['generated_json'])==r['generated_json_sha256']
  g=read(r['generated_json']);con=g['constraints'];cost=g['cost'];soft=plan['formulations'][case]['kind']!='hard'
  assert g['model']['name']==r['model']
  for k,v in plan['cases'][case]['numerics'].items():assert g['solver_options'][k]==v
  assert g['solver_options']['cost_scaling']==[.02]*40+[1.]
  assert con['idxbx']==con['idxbx_e']==[3,4,5,12] and con['idxbu']==list(range(5))
  assert con['ubx'][-1]==r['path_length']
  assert con['idxbx_0']==list(range(17)) and con['idxbxe_0']==list(range(17))
  assert g['dims']['nsbx']==(3 if soft else 0)
  if soft:
   assert con['idxsbx']==con['idxsbx_e']==[0,1,2]
   assert con['lsbx']==con['usbx']==con['lsbx_e']==con['usbx_e']==[0.,0.,0.]
  for i,row in enumerate(r['stages']):
   suffix='_e' if i==40 else ''
   if i:
    for k in ('lbx','ubx'):assert row[k]==con[k+suffix]
    assert row['ubx'][-1]==r['path_length']
   else:assert row['lbx']==row['ubx'] and len(row['lbx'])==17
   if i<40:
    for k in ('lbu','ubu'):assert row[k]==con[k]
   assert row['W']==cost['W'+suffix]
   if soft:
    expected=np.zeros((3,17)) if i==0 else np.asarray(con['C'+suffix])
    assert np.array_equal(row['C'],expected)
    for k in ('lg','ug'):assert row[k]==con[k+suffix]
    for k in ('Zl','Zu','zl','zu'):assert row[k]==([] if i==0 else cost[k+suffix])
  if soft:
   assert np.allclose(np.array(con['ug'])-np.array(con['ubx'][:3]),[.1,.15,.1])
 assert all(q['runtime_initial_equality_verified'] and q['runtime_parameters_verified'] for t in extra['ticks'] for q in t['rti'])


def gate(batch):
 stats,_=analyze(batch)
 assert set(stats)=={'baseline_hard','drag_030'} and all(s['n']==2 for s in stats.values())
 passed=all(s['health_pass'] for s in stats.values())
 old=ROOT/'logs/mpcc-prediction-v1/expanded-pitch-demand-20261104-v1/screen/run-v1'
 comparisons={}
 for case in stats:
  historical={e['seed']:e for e in read(old/case/'episodes.json')}
  comparisons[case]=[dict(seed=e['seed'],historical_success=historical[e['seed']]['success'],current_success=e['success'],historical_steps=historical[e['seed']]['steps'],current_steps=e['steps']) for e in read(Path(batch)/'run-v1'/case/'episodes.json')]
 write(Path(batch)/'gate-decision.json',dict(proceed=passed,all_four_required=True,tolerance=1e-5,statistics=stats,historical_comparison=comparisons,trajectory_equality_required=False,ordinary_racing_failure_is_data=True))
 return passed


def report(root,status,reason):
 root=Path(root);summary=read(root/'execution-summary.json')
 lines=['# Expanded-soft drag_030 solver identity repair','',status,'',reason,'']
 checks=read(root/'construction-audit.json') if (root/'construction-audit.json').exists() else None
 lines+=['Loading/bound repair: '+('live episode-specific bounds, complete settings and distinct loaded libraries verified on all sequential construction checks.' if checks and checks['status']=='passed' else 'not established; see construction evidence/blocker.'),'']
 gatepath=root/'diagnostic/gate-decision.json'
 if gatepath.exists():
  gate=read(gatepath);lines+=['Diagnostic constraint violations disappeared and the four-episode gate passed: '+str(gate['proceed'])+'.','']
 screen=root/'screen';eligible=[]
 if (screen/'independent-analysis-v1/statistics.json').exists():
  stats=read(screen/'independent-analysis-v1/statistics.json');pairs=read(screen/'independent-analysis-v1/paired.json')
  lines+=['| Case | Finish | Exact 95% interval | Status/fallback | Constraint RTIs | Public >=50% |','|---|---|---|---|---|---|']
  for c,r in stats.items():lines.append(f"| {c} | {r['finishes']}/{r['n']} | {r['completion_exact95']} | {r['numerical_ticks']}/{r['fallback_ticks']} | {r['constraint_violating_RTI_solves']} | {r['public_observed_50pct']} |")
  lines+=['','Shared-success candidate-minus-comparator differences; fixed-seed 10000-resample bootstrap; negative favors candidate:','']
  for key,r in pairs.items():lines.append(f"- {key}: shared={r['shared_n']}; mean={r['delta_s']} s; 95% interval={r['bootstrap95_s']}; rescues={r['rescues']}; regressions={r['regressions']}.")
  for c in ['soft_reference','drag_030']:
   comparator='soft_reference' if c=='drag_030' else 'baseline_hard';pa=pairs[c+'-minus-'+comparator]
   if stats[c]['provisional_health_completion_pass'] and pa['bootstrap95_s'] and pa['bootstrap95_s'][1]<0:eligible.append(c)
  pa=pairs['drag_030-minus-soft_reference']
  lines+=['','drag_030 retains supported speed benefit versus soft_reference: '+str(bool(pa['bootstrap95_s'] and pa['bootstrap95_s'][1]<0))+'. Magnitude and uncertainty are reported above; no invented minimum gain.','Provisionally eligible configurations: '+str(eligible)+'.','A separately authorized larger confirmation is justified for the provisionally eligible configurations.' if eligible else 'Further diagnosis is required before confirmation; no configuration has satisfied the full provisional criteria.']
 else:lines+=['No completed fresh screen; speed retention and provisional eligibility are unestablished. Further diagnosis is required if the diagnostic gate failed; otherwise see the precise construction/budget blocker.']
 lines+=['','Inclusive internal finish floor is 12/30; observed public 50% is separate. Screen evidence is provisional and does not confirm reliability. Absolute states/slacks and SQP increments remain distinct. Initial equality, commands, progress and dynamics stay hard. No explicit auxiliary slack upper bound. No parameter retuning, extra episodes, confirmation, promotion or deployment is authorized.','', 'Latency is advisory. Tick compute durations include instrumentation; per-RTI instrumentation overhead is reported separately in independent statistics and must not be confused with solver latency. Full-QP history is retained only on the predefined two matched diagnostic seeds; every failed QP is captured before reset. Failure crossings, slack/attitude maxima/distributions, affected episodes and numerical/fallback events are in independent-analysis-v1/statistics.json. Getter checks preserve observable state, not private memory.','', 'Construction-only checks reset environments but do not compute controls or step physics. Construction checks retain solver objects to exercise dynamic loader reuse. Runtime receipts read live NLP memory at construction, first solve and episode end, while each RTI checks measured equality and public path-reference parameters. Generated hashes alone are insufficient.','', 'Read frozen-orchestration.json, construction-audit.json, diagnostic/gate-decision.json, screen/plan.json and audit directories when present.']
 (root/'REPORT.md').write_text('\n'.join(lines)+'\n')
 (root/'HANDOFF.md').write_text(status+'\n\n'+reason+'\n\nRead REPORT.md and execution-summary.json. No automatic continuation. Do not pool diagnostics with the fresh cohort. Any larger confirmation or further diagnosis needs separate authorization.\n')
 with zipfile.ZipFile(root/'compact-results.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
  for p in sorted(root.rglob('*')):
   if not p.is_file() or 'generated' in p.parts or 'failed-QPs' in p.parts or p.name.endswith(('.log','.gz','.zip')) or p.name.startswith('runtime-seed-'):continue
   if p.suffix in ('.json','.md','.py'):z.write(p,p.relative_to(root))

if __name__=='__main__':
 if sys.argv[1]=='gate':raise SystemExit(0 if gate(sys.argv[2]) else 3)
 elif sys.argv[1]=='analyze':analyze(sys.argv[2])
 elif sys.argv[1]=='report':report(sys.argv[2],sys.argv[3],sys.argv[4])

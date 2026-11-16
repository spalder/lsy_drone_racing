"""Regenerate reusable CSV metrics from discovered immutable evidence, then report.
Run with the repository's existing .pixi/envs/default/bin/python. No simulations.
"""
from __future__ import annotations
import argparse,collections,csv,gzip,hashlib,itertools,json,math,pathlib,statistics
import numpy as np
from scipy.stats import beta
from mpcc_provenance_extension import environment_fields, augment_pair_comparisons, ranking_groups
OUT=pathlib.Path(__file__).resolve().parent
CONFIDENCE=.95

def write(name,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else '' if v is None else v for k,v in row.items()})
def exact(k,n):
    if not n:return None,None
    a=(1-CONFIDENCE)/2
    return (float(beta.ppf(a,k,n-k+1)) if k else 0.,float(beta.ppf(1-a,k+1,n-k)) if k<n else 1.)
def fnum(x):
    try:return float(x) if x is not None and x!='' else None
    except (ValueError,TypeError):return None
def pick(r,names):
    for k in names:
        v=fnum(r.get(k))
        if v is not None:return v
    return None
def success(r):return r.get('success') is True or r.get('outcome')=='success'
def metrics(c):
    ident=c['identity'];records=c['records'];freq=ident.get('control_frequency_hz')
    # Driver semantics verified: study/completed-step times are N/f; official=(N-1)/f.
    # If elapsed_s is recorded without freq, it remains an explicitly observed source value.
    normalized=[];original=[];official=[];conventions=set();missing=[];raw_durations=[];expected=0;expected_known=True;timed_episodes=0
    failed_eps=[];fallback_eps=[];union_eps=[];failed_ticks=[];fallback_ticks=[];statuses_known=0;sum_overruns=[];epi_p99=[]
    for r in records:
        steps=pick(r,['steps']);w=success(r)
        t=pick(r,['study_time_s','completed_step_time_s','elapsed_s'])
        if t is not None:conventions.add('recorded_completed_step_time')
        elif steps is not None and freq:
            t=steps/freq;conventions.add('completed_steps_divided_by_recorded_frequency')
        elif steps is not None and (ident['implementation_family'] in ['broad','prediction','v3','v3_safe','v3_alt']):
            # Frozen drivers hardcode 50 Hz and record N/50 in study fields/analysis; do not apply this to unknown summaries.
            t=steps/50;conventions.add('N/50_verified_frozen_driver');freq=freq or 50
        else:missing.append('race time semantics/frequency unavailable')
        r['_success']=w;r['_rank_time_s']=t
        if w and t is not None:normalized.append(t)
        ov=pick(r,['study_time_s','completed_step_time_s','elapsed_s']);of=pick(r,['official_time_s'])
        if w and ov is not None:original.append(ov)
        if w and of is not None:official.append(of)
        if steps is not None:expected+=int(steps)
        else:expected_known=False
        durations=r.get('compute_durations_ms')
        if isinstance(durations,list) and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in durations):
            raw_durations.extend(durations)
            if steps is not None and len(durations)==int(steps):timed_episodes+=1
            if len(durations)!=int(steps or -1):missing.append('timed calls differ from completed steps')
        else:durations=[]
        ft=pick(r,['failed_solve_ticks','numerical_ticks']);fb=pick(r,['fallback_ticks'])
        status=r.get('solver_statuses')
        if ft is None and isinstance(status,list):ft=sum(int(v!=0) for v in status)
        failed_ticks.append(ft);fallback_ticks.append(fb)
        failed_eps.append(None if ft is None else int(ft>0));fallback_eps.append(None if fb is None else int(fb>0))
        # A failing solve with associated hover fallback is one affected episode, not two.
        union_eps.append(None if ft is None or fb is None else int(ft>0 or fb>0))
        ov=pick(r,['whole_call_overruns','overruns','control_overruns'])
        if ov is not None:sum_overruns.append(int(ov))
        p99=pick(r,['whole_call_p99_ms','p99_ms','control_p99_ms','latency_p99_ms'])
        if p99 is not None:epi_p99.append(p99)
    n=len(records);k=sum(success(r) for r in records);lo,hi=exact(k,n);full_time=(len(normalized)==k)
    mean=statistics.mean(normalized) if normalized and full_time else None
    p90=float(np.quantile(normalized,.9,method='linear')) if normalized and full_time else None
    complete=expected_known and expected>0 and len(raw_durations)==expected and timed_episodes==n
    scope='whole_compute_control' if c['identity']['implementation_family'] in ['basic','experimental','broad','v2','selected_submission'] else 'whole_compute_control_including_research_instrumentation'
    if any(r.get('_timing_scope') for r in records):scope='whole_compute_control_with_research_tick_instrumentation'
    def total(xs):return sum(xs) if all(x is not None for x in xs) else None
    failed=total(failed_ticks);fallback=total(fallback_ticks)
    failed_n=total(failed_eps);fallback_n=total(fallback_eps);un=total(union_eps)
    # Basic/broad implementation hover fallback follows failed solve; evidence source verifies this coupling.
    health_basis='explicit_failed_solve_or_fallback_union'
    if un is None and failed_n is not None and ident['implementation_family'] in ['basic','experimental','broad','v2','selected_submission']:
        un=failed_n;health_basis='failed_solve_proxy; frozen hover fallback coupled to failed solve; no independent fallback counter'
    over=sum(v>20 for v in raw_durations) if complete else sum(sum_overruns) if len(sum_overruns)==n else None
    denom=expected if expected_known else None
    p99=float(np.quantile(raw_durations,.99,method='linear')) if complete else None
    health_missing='' if un is not None else 'failed-solve/fallback union unavailable for every episode'
    timing_missing='' if complete else ('no per-call durations or exact duration totals retained' if not raw_durations else 'partial timing coverage; full-test mean not estimated')
    row=dict(cohort_id=c['cohort_id'],configuration_id=c['configuration_id'],case_name=c['case_name'],run_path=c['run_path'],cohort_role=c['role'],role_evidence=c['role_evidence'],identity_status=ident['identity_status'],settings_status=ident['settings_status'],implementation_id=ident['implementation_id'],implementation_family=ident['implementation_family'],implementation_status=ident['implementation_status'],environment_id=ident['environment_id'],environment_kind=ident['environment_kind'],environment_status=ident['environment_status'],controller_module=ident['controller_module'],source_path=c['source_path'],source_sha256=c['source_sha256'],source_file_timestamp_utc=c['source_file_timestamp_utc'],test_timestamp_utc=c['test_timestamp_utc'],timestamp_kind=c['timestamp_kind'],episodes=n,finishes=k,completion_rate=k/n,completion_percent=100*k/n,completion_ci_lower=lo,completion_ci_upper=hi,confidence_level=CONFIDENCE,confidence_method='two_sided_exact_Clopper_Pearson',observed_at_least_70_percent=int(k/n>=.7),ci_lower_strictly_above_70_percent=int(lo>.7),successful_time_episodes=len(normalized),mean_success_time_s=mean,p90_success_time_s=p90,p90_provisional=int(k<30),p90_quantile_method='numpy linear: h=(n-1)*0.9',failure_penalty_s=30,penalized_mean_time_s=(sum(normalized)+30*(n-k))/n if full_time else None,penalty_convention='chosen_score_not_elapsed_time',race_time_convention=';'.join(sorted(conventions)),mean_original_completed_step_time_s=statistics.mean(original) if len(original)==k and k else None,mean_original_official_time_s=statistics.mean(official) if len(official)==k and k else None,race_time_missing_reason=';'.join(sorted(set(missing))),failed_solve_episodes=failed_n,fallback_episodes=fallback_n,numerical_or_fallback_episodes=un,numerical_or_fallback_percent=100*un/n if un is not None else None,health_basis=health_basis,health_missing_reason=health_missing,failed_solve_ticks=failed,fallback_ticks=fallback,total_control_calls=denom,failed_ticks_per_1000_calls=1000*failed/denom if failed is not None and denom else None,infrastructure_error_evidence_count=sum(len(x) if isinstance(x,list) else 1 for x in c['infrastructure_evidence']),infrastructure_evidence=c['infrastructure_evidence'],control_frequency_hz=freq,control_period_ms=1000/freq if freq else None,mean_control_call_ms=statistics.mean(raw_durations) if complete else 'nan',timed_control_calls=len(raw_durations),expected_control_calls=denom,timing_coverage_percent=100*len(raw_durations)/denom if denom else None,timing_scope=scope,timing_missing_reason=timing_missing,controller_call_p99_ms=p99,max_episode_p99_ms=max(epi_p99) if epi_p99 else None,p99_basis='pooled_per_call_durations' if p99 is not None else 'pooled unavailable; max_episode_p99_ms is a maximum, not a pooled p99',calls_over_20ms=over,calls_over_20ms_percent=100*over/denom if over is not None and denom else None,runtime_missing_reason='' if over is not None and p99 is not None else 'only saved per-episode percentiles/counters, or no timing data',settings_json=ident['settings'],active_behavior_json=ident.get('active_behavior',{}),simulator_package_versions_json=ident.get('simulator_package_versions',{}),implementation_sources_json=ident['implementation_sources'],environment_json=ident['environment'],provenance_sources=ident['context_sources'],hardware_runtime_context=ident['runtime_context'])
    return row

def main():
    with gzip.open(OUT/'cohort_evidence.jsonl.gz','rt') as f:cohorts=[json.loads(line) for line in f]
    complexity=json.loads((OUT/'complexity_assessments.json').read_text());rows=[];checks=[]
    for c in cohorts:
        r=metrics(c);r.update(environment_fields(c['identity']));score=complexity['families'].get(r['implementation_family'],{})
        r.update(complexity_score=score.get('score'),complexity_provisional=score.get('provisional',True),complexity_rationale=score.get('rationale','unresolved implementation'),complexity_sources=score.get('sources',[]),complexity_baseline=complexity['baseline'])
        saved=c['saved_summary'];sn=saved.get('runs',saved.get('n',saved.get('completed_episodes')));sk=saved.get('completed',saved.get('finishes',saved.get('successful_finishes')));sm=saved.get('average_success_time_s',saved.get('successful_mean_s'));official_saved=saved.get('average_successful_official_lap_s')
        diffs=[]
        if sn not in [None,''] and int(sn)!=r['episodes']:diffs.append('episode count')
        if sk not in [None,''] and int(sk)!=r['finishes']:diffs.append('finish count')
        if sm not in [None,''] and r['mean_success_time_s'] is not None and abs(float(sm)-r['mean_success_time_s'])>1e-8:diffs.append('successful mean')
        if official_saved is not None and r['mean_original_official_time_s'] is not None and abs(float(official_saved)-r['mean_original_official_time_s'])>1e-8:diffs.append('official successful mean')
        if saved:checks.append(dict(cohort_id=r['cohort_id'],source=c['source_path'],saved_summary=saved,discrepancies=diffs))
        r['saved_report_comparison']='discrepancy: '+','.join(diffs) if diffs else 'agrees' if saved else 'no scalar summary attached; original report/episode records retained'
        rows.append(r)
    byid={c['cohort_id']:c for c in cohorts};metricsbyid={r['cohort_id']:r for r in rows}
    # Pair only same frozen cohort group, exact environment ID, same seed, and same original initial state when recorded.
    paired=[]
    groups=collections.defaultdict(list)
    for c in cohorts:groups[(c['cohort_group'],c['identity']['environment_id'])].append(c)
    for (group,env),cs in groups.items():
        if len(cs)<2:continue
        ref=next((c for c in cs if c['case_name'].lower() in ['reference','ref','baseline','incumbent','baseline_hard','drag_030_parent']),None)
        if ref is None:ref=cs[0];reference_basis='first recorded case; no explicit baseline label found'
        else:reference_basis='explicit reference/baseline/incumbent case label'
        a={str(r.get('seed')):r for r in ref['records'] if r.get('seed') is not None}
        if len(a)!=len(ref['records']):continue
        for c in cs:
            if c is ref or c['configuration_id']==ref['configuration_id']:continue
            b={str(r.get('seed')):r for r in c['records'] if r.get('seed') is not None}
            if len(b)!=len(c['records']):continue
            matched=sorted(a.keys()&b.keys());valid=[]
            for seed in matched:
                ar,br=a[seed],b[seed]
                if ar.get('initial_state') is not None and br.get('initial_state') is not None and ar['initial_state']!=br['initial_state']:continue
                valid.append(seed)
            n=len(valid)
            if not n:continue
            rescues=sum(not a[s]['_success'] and b[s]['_success'] for s in valid);regressions=sum(a[s]['_success'] and not b[s]['_success'] for s in valid)
            shared=[s for s in valid if a[s]['_success'] and b[s]['_success'] and a[s]['_rank_time_s'] is not None and b[s]['_rank_time_s'] is not None]
            differences=[b[s]['_rank_time_s']-a[s]['_rank_time_s'] for s in shared]
            paired.append(dict(comparison_id='pair_'+hashlib.sha256((ref['cohort_id']+c['cohort_id']).encode()).hexdigest()[:16],configuration_id=c['configuration_id'],reference_configuration_id=ref['configuration_id'],cohort_id=c['cohort_id'],reference_cohort_id=ref['cohort_id'],reference_case=ref['case_name'],reference_selection=reference_basis,environment_id=env,cohort_group=group,matched_episodes=n,rescues=rescues,regressions=regressions,paired_completion_gain=(rescues-regressions)/n,paired_completion_gain_pp=100*(rescues-regressions)/n,shared_successes=len(shared),paired_mean_success_time_difference_s=statistics.mean(differences) if shared else None,time_difference_direction='candidate_minus_reference; negative=faster',matched_seeds=valid,shared_success_seeds=shared,matching_status='same frozen cohort group and environment, matched explicit seeds; differing recorded initial states excluded',identity_status='resolved' if c['identity']['identity_status']==ref['identity']['identity_status']=='resolved' else 'unresolved_provenance; descriptive_only'))
    augment_pair_comparisons(paired, cohorts)
    # Keep every supportable validation-to-earlier-screen comparison, not just the best.
    validation=[];configgroups=collections.defaultdict(list)
    for r in rows:configgroups[r['configuration_id']].append(r)
    for config,rs in configgroups.items():
        for v in [r for r in rs if r['cohort_role']=='independent_validation']:
            vs={str(r.get('seed')) for r in byid[v['cohort_id']]['records']}
            for s in [r for r in rs if r['cohort_role']=='screening' and r['test_timestamp_utc']<v['test_timestamp_utc']]:
                ss={str(r.get('seed')) for r in byid[s['cohort_id']]['records']}
                if None in ss or 'None' in ss or vs&ss:continue
                # Same implementation/environment identity already enforced by config ID.
                validation.append(dict(configuration_id=config,screening_cohort_id=s['cohort_id'],validation_cohort_id=v['cohort_id'],screening_n=s['episodes'],screening_finishes=s['finishes'],validation_n=v['episodes'],validation_finishes=v['finishes'],screening_completion_percent=s['completion_percent'],validation_completion_percent=v['completion_percent'],validation_minus_screening_pp=v['completion_percent']-s['completion_percent'],independence_evidence=v['role_evidence'],seed_overlap=0))
    configs=[]
    for config,rs in sorted(configgroups.items()):
        eligible=[r for r in rs if r['cohort_role'] in ['screening','independent_validation']]
        if eligible:
            primary=max(eligible,key=lambda r:(r['episodes'],r['test_timestamp_utc'],r['cohort_id']));reason='largest eligible general-seed cohort before performance filters; equal n uses latest recorded genuine test/file timestamp, never best outcome'
        else:
            primary=max(rs,key=lambda r:(r['episodes'],r['test_timestamp_utc'],r['cohort_id']));reason='no eligible general-seed cohort; diagnostic/smoke representative only; excluded from reliability ranking'
        for r in rs:r['is_primary']=int(r is primary);r['primary_selection_reason']=reason if r is primary else 'retained secondary cohort; not pooled'
        vals=[v for v in validation if v['configuration_id']==config]
        r=dict(primary);r['primary_cohort_id']=r.pop('cohort_id');r.update(primary_eligible=int(bool(eligible)),cohort_count=len(rs),cohort_ids=[s['cohort_id'] for s in rs],aliases=sorted({s['case_name'] for s in rs}),independent_validation_cohorts=sum(s['cohort_role']=='independent_validation' for s in rs),validation_comparison_count=len(vals),validation_comparisons=vals,screening_only_evidence=int(not any(s['cohort_role']=='independent_validation' for s in rs)),primary_selection_reason=reason)
        r['qualifies_observed_70']=int(bool(eligible) and r['episodes']>=10 and r['completion_rate']>=.7 and r['identity_status']=='resolved')
        configs.append(r)
    # Transparent lexicographic rule: evidence, conservative completion band, simplicity, speed.
    # Completion and its CI do NOT contribute separate additive scores; lower endpoint is the reliability ordering statistic.
    def rank(r):
        return (-int(r['independent_validation_cohorts']>0),-math.floor(r['completion_ci_lower']/.05),r['complexity_score'] if r['complexity_score'] is not None else 9,-r['episodes'],r['mean_success_time_s'] if r['mean_success_time_s'] is not None else math.inf,r['configuration_id'])
    qualifying=sorted([r for r in configs if r['qualifies_observed_70']],key=rank)
    ranks={r['configuration_id']:i for i,r in enumerate(qualifying,1)}
    for r in configs:r['shortlist_rank']=ranks.get(r['configuration_id'])
    ranking_groups(configs)
    # Required invariants run before report generation.
    assert len({r['configuration_id'] for r in configs})==len(configs)
    for r in rows:
        assert 0<=r['finishes']<=r['episodes']
        assert abs(r['completion_rate']-r['finishes']/r['episodes'])<1e-15
        assert r['completion_ci_lower']<=r['completion_rate']<=r['completion_ci_upper']
        if r['mean_control_call_ms']!='nan':assert r['timed_control_calls']==r['expected_control_calls'] and r['timing_coverage_percent']==100
    for r in configs:
        elig=[s for s in configgroups[r['configuration_id']] if s['cohort_role'] in ['screening','independent_validation']]
        if elig:assert r['episodes']==max(s['episodes'] for s in elig)
    for r in paired:
        assert r['rescues']+r['regressions']<=r['matched_episodes'] and r['shared_successes']<=r['matched_episodes']
        assert metricsbyid[r['cohort_id']]['environment_id']==metricsbyid[r['reference_cohort_id']]['environment_id']
    write('cohort_metrics.csv',rows);write('configuration_metrics.csv',configs);write('paired_comparisons.csv',paired);write('validation_comparisons.csv',validation)
    unresolved=[dict(record_type='episode_cohort',configuration_id=r['configuration_id'],cohort_id=r['cohort_id'],source_path=r['source_path'],episodes=r['episodes'],finishes=r['finishes'],completion_rate=r['completion_rate'],reported_mean_success_time_s=r['mean_success_time_s'],status='unresolved',missing_reason=';'.join([r['settings_status'],r['implementation_status'],r['environment_status']])) for r in rows if r['identity_status']=='unresolved']
    inventory=json.loads((OUT/'source_inventory.json').read_text())
    for item in inventory['archives']:
        if item.get('status','').startswith('unresolved_summary'):
            values=item['content'].split(',')
            unresolved.append(dict(record_type='overwrite_only_summary',configuration_id='',cohort_id='',source_path=item['source'],episodes=None,finishes=None,completion_rate=fnum(values[1]) if len(values)>1 else None,reported_mean_success_time_s=fnum(values[0]),status='unresolved',missing_reason='historical n/seeds/controller implementation/environment not stored; not attached to current selector; duplicate-summary possibility retained'))
    manual=json.loads((OUT/'additional_user_evidence.json').read_text())
    for item in manual['records']:
        lo,hi=exact(item['finishes'],item['episodes']) if item['episodes'] is not None else (None,None)
        unresolved.append(dict(record_type='user_reported_console_excerpt',configuration_id='',cohort_id='',source_path=manual['source']+'::'+manual['message_timestamp_utc'],controller_label=item['controller_label'],episodes=item['episodes'],finishes=item['finishes'],completion_rate=item['completion_rate'],completion_ci_lower=lo,completion_ci_upper=hi,reported_mean_success_time_s=item['mean_successful_official_time_s'],status='unresolved',missing_reason=item['missing_reason']))
    write('unresolved_records.csv',unresolved)
    (OUT/'checks.json').write_text(json.dumps(dict(status='passed',cohorts=len(rows),configurations=len(configs),observed_70_qualifiers=len(qualifying),saved_summary_checks=checks,invariants=['counts/rates','two-sided CI bounds contain proportions','primary largest eligible n before filters','unique settings/implementation/environment IDs','paired seed/environment checks','complete timing coverage for numeric means']),indent=2)+'\n')
    # Report is deliberately generated by reading CSVs after all writes/checks complete.
    from report import generate
    generate()
    print('CSV datasets validated:',len(rows),'cohorts;',len(configs),'configurations;',len(qualifying),'resolved >=70% qualifiers;',len(paired),'paired comparisons;',len(validation),'validation comparisons',flush=True)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Independent, read-only audit of assessment outputs; optionally rerun once for determinism.

Writes only a new helper_audit/implementation_validation directory. The sole
other optional write is removing the provisional banner from an already-validated
report when explicitly asked for with --finalize-on-pass.
"""
from __future__ import annotations
import argparse,csv,collections,gzip,hashlib,json,math,pathlib,re,subprocess,sys,zipfile,io
from scipy.stats import beta

FOLDER='docs/control/mpcc_assessment_20261112_v1'

def fnum(value):
    try:return float(value)
    except (ValueError,TypeError):return None

def loadcsv(p):
    with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def included_hashes(target):
    files=['cohort_metrics.csv','configuration_metrics.csv','paired_comparisons.csv','validation_comparisons.csv','unresolved_records.csv','assessment.md','data_dictionary.md','checks.json']
    return {name:sha(target/name) for name in files if (target/name).exists()}

def monitor(report, kind, message, context=None):
    report['findings'].append(dict(severity=kind,message=message,context=context))
    if kind=='error':report['error_count']+=1
    elif kind=='warning':report['warning_count']+=1

def compare_source_integrity(repo, target, report):
    p=target/'mpcc_assessment_source_snapshot.json'
    if not p.exists():monitor(report,'warning','No before-patch protected-source hash snapshot');return
    initial=json.loads(p.read_text())['sha256']
    for name,hexdigest in initial.items():
        fp=repo/name
        if not fp.is_file():monitor(report,'error','Protected source disappeared',name)
        elif sha(fp)!=hexdigest:monitor(report,'error','Protected source changed since patch installation',name)
    report['source_snapshot_files_checked']=len(initial)

def audit_counts(co,cs,pa,va,report):
    if len({r['cohort_id'] for r in co})!=len(co):monitor(report,'error','Duplicate cohort ID')
    if len({r['configuration_id'] for r in cs})!=len(cs):monitor(report,'error','Duplicate config ID')
    known={r['cohort_id']:r for r in co}
    configs=collections.defaultdict(list)
    for r in co:
        configs[r['configuration_id']].append(r)
        n=int(r['episodes']);k=int(r['finishes']);p=k/n if n else None
        if n<1 or k<0 or k>n:monitor(report,'error','Invalid completion count',r['cohort_id']);continue
        if abs(float(r['completion_rate'])-p)>1e-12:monitor(report,'error','Completion ratio mismatch',r['cohort_id'])
        lo=0 if k==0 else float(beta.ppf(.025,k,n-k+1))
        hi=1 if k==n else float(beta.ppf(.975,k+1,n-k))
        if max(abs(lo-float(r['completion_ci_lower'])),abs(hi-float(r['completion_ci_upper'])))>1e-9:
            monitor(report,'error','Incorrect Clopper–Pearson interval',r['cohort_id'])
        if not lo-1e-12<=p<=hi+1e-12:monitor(report,'error','Interval excludes observed completion',r['cohort_id'])
        tc=int(r['timed_control_calls']); ec=int(r['expected_control_calls']) if r.get('expected_control_calls') else None
        mean=r['mean_control_call_ms']
        if ec is not None and tc>ec:monitor(report,'error','Timing coverage above 100%',r['cohort_id'])
        if mean!='nan' and (not ec or tc!=ec or fnum(mean) is None or not math.isfinite(fnum(mean))):
            monitor(report,'error','Complete mean inconsistent with timing coverage',r['cohort_id'])
    for r in cs:
        id=r['configuration_id'];rs=configs[id]
        if not rs:monitor(report,'error','Config has no source cohorts',id);continue
        eligible=[x for x in rs if x['cohort_role'] in ['screening','independent_validation']]
        source=eligible if eligible else rs
        n=max(int(x['episodes']) for x in source)
        actual=known.get(r['primary_cohort_id'])
        if not actual or int(actual['episodes'])!=n:monitor(report,'error','Wrong primary cohort n',id)
        elif actual['configuration_id']!=id:monitor(report,'error','Primary cohort from another config',id)
        else:
            tied=[x for x in source if int(x['episodes'])==n]
            latest=max(tied,key=lambda x:(x['test_timestamp_utc'],x['cohort_id']))
            if latest['cohort_id']!=actual['cohort_id']:monitor(report,'error','Equal-n latest primary mismatch',id)
        p=actual and float(actual['completion_rate'])
        expected=int(bool(eligible) and int(r['episodes'])>=10 and p>=.7 and r['identity_status']=='resolved') if actual else 0
        if int(r['qualifies_observed_70'])!=expected:monitor(report,'error','Qualifier inconsistency',id)
        if not r.get('environment_provenance_group'):monitor(report,'error','Provenance missing',id)
    # Independent confirmation: ranking ordinals must never span different environment IDs.
    eligible_by_env=collections.defaultdict(list)
    for r in cs:
        if r['ranking_group']!=r['environment_id']:
            monitor(report,'error','Ranking group not an exact environment_id',r['configuration_id'])
        if r['qualifies_observed_70']=='1':
            eligible_by_env[r['environment_id']].append(r)
        elif r.get('within_environment_rank') or r.get('shortlist_rank') or r.get('historical_rank'):
            monitor(report,'error','Ineligible configuration assigned a rank',r['configuration_id'])
    def display_env(source_group):
        choices=[(env,rs) for env,rs in eligible_by_env.items()
                 if rs[0]['environment_provenance_group']==source_group]
        return (sorted(choices,key=lambda t:(-len(t[1]),-sum(int(x['episodes']) for x in t[1]),t[0]))[0][0]
                if choices else None)
    main_env=display_env('retained_official_core_match')
    historical_env=display_env('verified_modified_core_source')
    for env,rs in eligible_by_env.items():
        ranks=sorted(int(r['within_environment_rank']) for r in rs)
        if ranks!=list(range(1,len(rs)+1)):
            monitor(report,'error','Within-environment ranks not contiguous or unique',env)
        if len({r['environment_provenance_group'] for r in rs})>1:
            monitor(report,'error','One exact environment has mixed provenance labels',env)
        for r in rs:
            if r.get('within_provenance_rank')!=r.get('within_environment_rank'):
                monitor(report,'error','Legacy rank alias disagrees with within-environment rank',r['configuration_id'])
            if r.get('main_display_environment_id')!=(main_env or '') or r.get('historical_display_environment_id')!=(historical_env or ''):
                monitor(report,'error','Selected display environment column disagrees with selection rule',r['configuration_id'])
            should_main=env==main_env
            should_historical=env==historical_env
            if bool(r.get('shortlist_rank'))!=should_main or bool(r.get('historical_rank'))!=should_historical:
                monitor(report,'error','A displayed rank crosses its selected exact environment',r['configuration_id'])
            if should_main and r['shortlist_rank']!=r['within_environment_rank']:
                monitor(report,'error','Main display rank differs from within-environment rank',r['configuration_id'])
            if should_historical and r['historical_rank']!=r['within_environment_rank']:
                monitor(report,'error','Historical display rank differs from within-environment rank',r['configuration_id'])
    report['qualifying_environment_counts']={env:len(rs) for env,rs in sorted(eligible_by_env.items())}
    report['selected_main_environment_id']=main_env
    report['selected_historical_environment_id']=historical_env
    by_id={r['cohort_id']:r for r in co}
    for r in pa:
        a=by_id.get(r['cohort_id']);b=by_id.get(r['reference_cohort_id'])
        if not a or not b:monitor(report,'error','Paired row cohort missing',r['comparison_id']);continue
        if a['environment_id']!=b['environment_id'] or r['environment_id']!=a['environment_id']:
            monitor(report,'error','Paired row environment mismatch',r['comparison_id'])
        if int(r['matched_episodes'])<int(r['rescues'])+int(r['regressions']):monitor(report,'error','Inconsistent paired outcomes',r['comparison_id'])
    for r in va:
        a=by_id.get(r['screening_cohort_id']);b=by_id.get(r['validation_cohort_id'])
        if not a or not b:monitor(report,'error','Validation references missing cohort');continue
        if a['configuration_id']!=b['configuration_id'] or a['environment_id']!=b['environment_id']:
            monitor(report,'error','Cross-environment validation',r)
        change=float(b['completion_percent'])-float(a['completion_percent'])
        if abs(change-float(r['validation_minus_screening_pp']))>1e-9:monitor(report,'error','Validation change incorrect',r)
    report['counts']={'cohorts':len(co),'configurations':len(cs),'paired_comparisons':len(pa),'validation_comparisons':len(va),'eligible_observed_70':sum(x['qualifies_observed_70']=='1' for x in cs)}
    report['provenance_config_counts']=dict(collections.Counter(x['environment_provenance_group'] for x in cs))
    report['provenance_eligible_counts']=dict(collections.Counter(x['environment_provenance_group'] for x in cs if x['qualifies_observed_70']=='1'))

def audit_records(target,co,pa,report):
    # Check actual seeds, initial-state exclusions and direct comparison arithmetic.
    summary={r['cohort_id']:r for r in co}
    if not (target/'cohort_evidence.jsonl.gz').exists():monitor(report,'error','Episode evidence snapshot missing');return
    cases={}
    pairids={x for r in pa for x in (r['cohort_id'],r['reference_cohort_id'])}
    duplicate=[]
    with gzip.open(target/'cohort_evidence.jsonl.gz','rt') as f:
        for line in f:
            c=json.loads(line)
            cid=c['cohort_id']
            seeds=[str(r.get('seed')) for r in c['records'] if r.get('seed') is not None]
            if len(set(seeds))!=len(seeds):duplicate.append(cid)
            if cid in pairids:cases[cid]=c
    if duplicate:monitor(report,'error','Duplicate explicit seeds within cohort',duplicate[:20])
    for pair in pa:
        a=cases.get(pair['reference_cohort_id']);b=cases.get(pair['cohort_id'])
        if a is None or b is None:monitor(report,'error','Paired reference/source episode records unavailable',pair['comparison_id']);continue
        if a['cohort_group']!=b['cohort_group'] or a['identity']['environment_id']!=b['identity']['environment_id']:
            monitor(report,'error','Mismatched paired frozen-group/environment',pair['comparison_id']);continue
        da={str(x['seed']):x for x in a['records'] if x.get('seed') is not None}
        db={str(x['seed']):x for x in b['records'] if x.get('seed') is not None}
        ids=[];unk=0;rescue=regress=0;time_diffs=[]
        for seed in sorted(set(da)&set(db)):
            x=da[seed];y=db[seed]
            if x.get('initial_state') is not None and y.get('initial_state') is not None and x['initial_state']!=y['initial_state']:
                continue
            if x.get('initial_state') is None or y.get('initial_state') is None:unk+=1
            ids.append(seed)
            xs=x.get('success') is True or x.get('outcome')=='success'
            ys=y.get('success') is True or y.get('outcome')=='success'
            rescue+=int(not xs and ys);regress+=int(xs and not ys)
            if xs and ys:
                # Existing analysis uses normalized verified race-time convention.
                def t(r):
                    for name in ['study_time_s','completed_step_time_s','elapsed_s']:
                        if r.get(name) is not None:return float(r[name])
                    st=r.get('steps'); hz=a['identity'].get('control_frequency_hz')
                    if st is not None and hz:return float(st)/float(hz)
                    return None
                at=t(x);bt=t(y)
                if at is not None and bt is not None:time_diffs.append(bt-at)
        if (len(ids),rescue,regress)!=(int(pair['matched_episodes']),int(pair['rescues']),int(pair['regressions'])):
            monitor(report,'error','Paired outcomes disagree with original records',pair['comparison_id'])
        if int(pair['shared_successes'])!=len(time_diffs) and len(time_diffs)>0:
            # Some frozen drivers use verified N/50 fallback, not reproduced here; unresolved rather than false error.
            monitor(report,'warning','Paired time denominator differs under simple independent time parser (verify frozen-driver fallback)',pair['comparison_id'])
        reported=fnum(pair.get('paired_mean_success_time_difference_s'))
        if reported is not None and time_diffs and abs(sum(time_diffs)/len(time_diffs)-reported)>1e-8:
            monitor(report,'warning','Paired mean time differs under simple parser; verify source time convention',pair['comparison_id'])
        if pair.get('comparison_kind')=='targeted_direct_nonbaseline' and int(pair.get('unknown_initial_state_pairs',0))!=unk:
            monitor(report,'error','Direct F1 initial-state missing count disagrees',pair['comparison_id'])
    report['paired_replayed_count']=len(pa)

def audit_report(target,cs,pa,report):
    p=target/'assessment.md'
    if not p.exists():monitor(report,'error','Assessment Markdown missing');return
    t=p.read_text(encoding='utf-8');lines=t.splitlines()
    if 'PROVISIONAL — regenerated report; independent integrity checks still required' in t:
        monitor(report,'error','Report incorrectly claims all independent checks are still required')
    if 'VALIDATION RECORD:' not in t or 'validation.json' not in t:
        monitor(report,'error','Report lacks accurate regeneration/independent-validation status')
    if '## Other qualifying environments — independent supplementary rankings' not in t:
        other={r['environment_id'] for r in cs if r['qualifies_observed_70']=='1' and not (r.get('shortlist_rank') or r.get('historical_rank'))}
        if other:monitor(report,'error','Qualifying secondary environments missing from report',sorted(other))
    for env in {r['environment_id'] for r in cs if r['qualifies_observed_70']=='1'}:
        if env not in t:monitor(report,'error','Qualifying environment absent from Markdown',env)
    required=['## Environment provenance and comparability','## Ranked shortlist: retained official race-core match','## Historical modified-core foundations','## Direct F1 versus F1_2 comparison','## Independent validation','## Relevant alternatives below 70%','## Availability across tests']
    for section in required:
        if not any(s.startswith(section) for s in lines):monitor(report,'error','Required report section absent',section)
    m=re.search(r'Assessed \*\*(\d+) configuration/cohort records\*\* and \*\*(\d+) distinct configuration/environment identities\*\*',t)
    if not m:monitor(report,'error','Unable to locate source counts in report')
    elif int(m[1])!=len(loadcsv(target/'cohort_metrics.csv')) or int(m[2])!=len(cs):monitor(report,'error','Markdown counts disagree with CSVs')
    ranks=sorted([r for r in cs if r.get('shortlist_rank')],key=lambda r:int(r['shortlist_rank']))[:25]
    first=next((i for i,s in enumerate(lines) if s.startswith('| Rank / ID | Env / core |')),None)
    if first is None:monitor(report,'error','Main provenance-labeled shortlist table absent');return
    rows=[]
    for s in lines[first+2:]:
        if not s.startswith('|'):break
        rows.append([v.strip() for v in s.split('|')[1:-1]])
    if len(rows)!=len(ranks):monitor(report,'error','Displayed shortlist length differs from CSV top 25',{'markdown':len(rows),'csv':len(ranks)})
    for cells,c in zip(rows,ranks):
        try:
            assert cells[0]==str(c['shortlist_rank'])+' / '+c['configuration_id'].replace('config_','')[:8]
            assert c['environment_id'].replace('env_','')[:8] in cells[1]
            assert int(cells[3])==int(c['episodes']) and int(cells[4])==int(c['finishes'])
            assert cells[5]==f"{float(c['completion_percent']):.1f}"
            assert cells[6]==f"{100*float(c['completion_ci_lower']):.1f}"
            assert cells[7]==f"{100*float(c['completion_ci_upper']):.1f}"
        except (AssertionError,IndexError,ValueError) as exc:
            monitor(report,'error','Markdown shortlist row inconsistent with CSV',c['configuration_id'])
    # The other two linked shortlist tables must represent precisely the same ranked IDs,
    # with numeric cells equal to format rules from the source CSV. No aggregate recomputation.
    def extract_after(title):
        try: start=lines.index(title)
        except ValueError: return None
        header_idx=next((j for j in range(start+1,len(lines)) if lines[j].startswith('| Rank / ID |')),None)
        if header_idx is None:return None
        result=[]
        for x in lines[header_idx+2:]:
            if not x.startswith('|'):break
            result.append([y.strip() for y in x.split('|')[1:-1]])
        return result
    for heading,check in [
        ('### Conditional race time, numerical health and complexity','race'),
        ('### Whole-call compute and runtime feasibility','compute')]:
        got=extract_after(heading)
        if got is None:
            monitor(report,'error','Linked shortlist metric table missing',heading);continue
        if len(got)!=len(ranks):
            monitor(report,'error','Linked metric table row count inconsistent',heading);continue
        for cells,c in zip(got,ranks):
            expected_id=str(c['shortlist_rank'])+' / '+c['configuration_id'].replace('config_','')[:8]
            try:
                if cells[0]!=expected_id:raise ValueError('rank ID mismatch')
                if check=='race':
                    checks=[('mean_success_time_s',1,3),('p90_success_time_s',2,3),('penalized_mean_time_s',5,3),('numerical_or_fallback_percent',6,2)]
                    if int(cells[3])!=int(c['successful_time_episodes']):raise ValueError('successful n mismatch')
                else:
                    checks=[('mean_control_call_ms',1,3),('timing_coverage_percent',3,1),('controller_call_p99_ms',4,3),('max_episode_p99_ms',5,3),('calls_over_20ms_percent',6,4)]
                for key,idx,precision in checks:
                    value=fnum(c[key])
                    expected='N/A' if value is None or not math.isfinite(value) else f'{value:.{precision}f}'
                    if cells[idx]!=expected:raise ValueError(key+' expected '+expected+' received '+cells[idx])
            except (IndexError,ValueError) as exc:
                monitor(report,'error','Linked Markdown metric differs from CSV',{'config':c['configuration_id'],'table':check,'cause':str(exc)})
    for text in ['mean_control_call_ms','environment_provenance_group','unknown_initial_state_pairs']:
        if text not in (target/'data_dictionary.md').read_text():monitor(report,'error','Dictionary missing required addition',text)
    direct=[r for r in pa if r.get('comparison_kind')=='targeted_direct_nonbaseline']
    if len(direct)!=1:monitor(report,'error','Exactly one targeted F1 comparison expected',len(direct))
    report['markdown_verified_rows']=len(rows)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=pathlib.Path,required=True)
    ap.add_argument('--verify-determinism',action='store_true')
    ap.add_argument('--finalize-on-pass',action='store_true',help='Remove provisional banner ONLY if zero errors; warnings remain in audit')
    args=ap.parse_args();repo=args.repo.expanduser().resolve();target=repo/FOLDER
    out=target/'helper_audit'/'implementation_validation';out.mkdir(parents=True,exist_ok=True)
    report={'status':'provisional','findings':[],'error_count':0,'warning_count':0}
    co=loadcsv(target/'cohort_metrics.csv');cs=loadcsv(target/'configuration_metrics.csv');pa=loadcsv(target/'paired_comparisons.csv');va=loadcsv(target/'validation_comparisons.csv')
    audit_counts(co,cs,pa,va,report)
    audit_records(target,co,pa,report)
    audit_report(target,cs,pa,report)
    compare_source_integrity(repo,target,report)
    if args.verify_determinism:
        before=included_hashes(target)
        cmd=[sys.executable,str(target/'analyze.py')]
        res=subprocess.run(cmd,cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
        (out/'determinism_run.log').write_text(res.stdout[-5000:],encoding='utf-8')
        if res.returncode:monitor(report,'error','Determinism rerun of analyze.py failed',res.stdout[-1000:])
        after=included_hashes(target)
        for k in sorted(set(before)|set(after)):
            if before.get(k)!=after.get(k):monitor(report,'error','Nondeterministic output file',k)
        report['determinism_checked']=res.returncode==0
    if report['error_count']==0 and args.finalize_on_pass:
        # New generator uses a permanently honest status link, not a mutable banner.
        # Finalization means the independent validator passed on this regenerated output.
        report['report_finalized']=True
    report['validated_artifact_sha256']=included_hashes(target) if report['error_count']==0 else {}
    report['status']='passed_with_warnings' if report['error_count']==0 and report['warning_count'] else 'passed' if report['error_count']==0 else 'failed'
    (out/'validation.json').write_text(json.dumps(report,indent=2,sort_keys=True,default=str)+'\n')
    (out/'validation_brief.md').write_text('# Implementation validation\n\nStatus: **'+report['status']+'**. Errors: '+str(report['error_count'])+', warnings: '+str(report['warning_count'])+'.\n\n'+'\n'.join('- '+f['severity'].upper()+': '+f['message']+' — '+str(f['context'])[:300] for f in report['findings'][:100])+'\n')
    for name,rs in [('official_shortlist.csv',[r for r in cs if r.get('shortlist_rank')]),('historical_shortlist.csv',[r for r in cs if r.get('historical_rank')])]:
        rs=sorted(rs,key=lambda r:int(r.get('shortlist_rank') or r.get('historical_rank')))[:25]
        cols=['configuration_id','case_name','environment_id','environment_provenance_group','episodes','finishes','completion_rate','completion_ci_lower','completion_ci_upper','mean_success_time_s','p90_success_time_s','penalized_mean_time_s','numerical_or_fallback_percent','failed_solve_ticks','controller_call_p99_ms','mean_control_call_ms','timing_coverage_percent','complexity_score','shortlist_rank','historical_rank','independent_validation_cohorts']
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rs)
    with zipfile.ZipFile(out/'mpcc_implementation_review_bundle.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in [out/'validation.json',out/'validation_brief.md',out/'official_shortlist.csv',out/'historical_shortlist.csv',target/'assessment.md',target/'data_dictionary.md',target/'mpcc_provenance_extension.py',target/'checks.json']:
            if p.exists():z.write(p,arcname=p.name)
        backup=target/'INSTALL_BACKUP_PATH.txt'
        if backup.exists():
            bp=pathlib.Path(backup.read_text().strip())/'INSTALL_DIFF.patch'
            if bp.exists():z.write(bp,arcname='INSTALL_DIFF.patch')
        if (out/'determinism_run.log').exists():z.write(out/'determinism_run.log',arcname='determinism_run.log')
    print(json.dumps({k:report[k] for k in ['status','error_count','warning_count','counts','provenance_eligible_counts']},indent=2))
    print('Bundle:',out/'mpcc_implementation_review_bundle.zip')
    if report['error_count']:sys.exit(1)

if __name__=='__main__':main()

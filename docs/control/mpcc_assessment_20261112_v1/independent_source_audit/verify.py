#!/usr/bin/env python3
"""Read-only, selective original-log audit of the 2026-11-12 MPCC assessment.

No imports from the assessment pipeline; no simulations, source-tree scans, or
writes outside docs/control/mpcc_assessment_20261112_v1/independent_source_audit.
Outputs are checkpoints and a small ZIP for review. Python 3.10+, SciPy for CIs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import zipfile

REL = Path('docs/control/mpcc_assessment_20261112_v1')
F1_COHORT = 'cohort_ced5195525a73529'
G07_COHORT = 'cohort_b3c1219e37b07859'
F12_COHORT = 'cohort_13b826dd1a54a917'
FIELDS = ['checkpoint','configuration_id','cohort_id','reference_cohort_id','metric','reported','recomputed','difference','status','source_paths','reason']


def read_csv(path):
    csv.field_size_limit(sys.maxsize)
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_json(path, obj):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def save_csv(path, rows):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def parse_json_cell(s):
    if isinstance(s, (dict, list)):
        return s
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def number(x):
    try:
        if x is None or x == '':
            return None
        a = float(x)
        return a if math.isfinite(a) else None
    except (TypeError, ValueError):
        return None


def as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        if v.strip().lower() in ('true','1','yes'):
            return True
        if v.strip().lower() in ('false','0','no'):
            return False
    return None


def observed_success(r):
    via_flag = as_bool(r.get('success'))
    outcome = r.get('outcome')
    via_outcome = str(outcome).strip().lower() == 'success' if outcome not in (None, '') else None
    if via_flag is not None and via_outcome is not None and via_flag != via_outcome:
        raise ValueError(f'Conflicting success flag/outcome for seed {r.get("seed")}')
    ans = via_flag if via_flag is not None else via_outcome
    if ans is None:
        raise ValueError(f'Missing success/outcome for seed {r.get("seed")}')
    return ans


def source_file(repo, row):
    src = row.get('source_path') or ''
    if not src or '::' in src:
        raise ValueError(f'No directly accessible source file: {src}')
    p = Path(src)
    if not p.is_absolute():
        p = repo / p
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def has_case(r):
    for field in ('case', 'configuration'):
        v = r.get(field)
        if isinstance(v, str) and v.strip():
            return v
    return None


def select_group(rows, target, context):
    """Select original group by case AND explicit cohort tag; never by attractive results."""
    if not rows:
        raise ValueError(f'{context}: zero original records')
    name = target['case_name']
    labeled = [r for r in rows if has_case(r) is not None]
    if labeled:
        rows = [r for r in rows if has_case(r) == name]
        if not rows:
            raise ValueError(f'{context}: case {name!r} not in original records')
    elif len(rows) != int(target['episodes']):
        raise ValueError(f'{context}: unlabeled group has {len(rows)} rows, expected {target["episodes"]}')
    # Some paths include an explicit frozen cohort name.
    path_group = target.get('run_path','').split('/cohort=',1)
    if len(path_group) > 1 and any(r.get('cohort') not in (None,'') for r in rows):
        rows = [r for r in rows if str(r.get('cohort')) == path_group[1]]
    if len(rows) != int(target['episodes']):
        raise ValueError(f'{context}: selected {len(rows)} original rows, expected {target["episodes"]}; ambiguous or changed source')
    if any(r.get('seed') in (None,'') for r in rows):
        raise ValueError(f'{context}: missing explicit seed')
    seeds = [str(r['seed']) for r in rows]
    if len(set(seeds)) != len(seeds):
        raise ValueError(f'{context}: duplicate original seed')
    return rows


def source_sha256(p):
    digest = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def original_records(repo, target, max_mb=100):
    p = source_file(repo, target)
    if p.stat().st_size > max_mb*1024*1024:
        raise ValueError(f'Original file exceeds {max_mb} MB size guard: {p}')
    notes = []
    if p.suffix.lower() == '.csv':
        rows = select_group(read_csv(p), target, str(p))
        detail_dir = p.parent / target['case_name']
        if detail_dir.is_dir():
            detail_paths = sorted(detail_dir.glob('episode-*.json'))
            if 0 < len(detail_paths) <= max(500, len(rows) * 2):
                detail_map = {}
                for q in detail_paths:
                    if q.stat().st_size > max_mb*1024*1024:
                        raise ValueError(f'Oversized individual episode detail: {q}')
                    r = json.loads(q.read_text(encoding='utf-8'))
                    if not isinstance(r, dict) or r.get('seed') is None:
                        continue
                    key = str(r['seed'])
                    if key in detail_map:
                        raise ValueError(f'Duplicate seed in per-episode JSON: {key}')
                    detail_map[key] = (r,q)
                if all(str(r['seed']) in detail_map for r in rows):
                    # Prove export/detail source agreement for outcome and steps before preferring detail.
                    for r in rows:
                        detail = detail_map[str(r['seed'])][0]
                        if observed_success(detail) != observed_success(r):
                            raise ValueError(f'Export/detail outcome disagreement at seed {r["seed"]}')
                        if number(detail.get('steps')) != number(r.get('steps')):
                            raise ValueError(f'Export/detail step disagreement at seed {r["seed"]}')
                    rows = [detail_map[str(r['seed'])][0] for r in rows]
                    notes.append(f'{len(rows)} per-episode original JSON details, cross-checked against exported CSV')
                    notes.append('Details directory: '+str(detail_dir))
                else:
                    notes.append('Incomplete per-episode JSON set; relied on original CSV rows only')
        return rows, p, notes
    if p.suffix.lower() == '.json':
        content = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(content, list):
            rows = content
        elif isinstance(content, dict) and isinstance(content.get('evaluations'), list):
            matches = []
            for ev in content['evaluations']:
                if not isinstance(ev,dict) or not isinstance(ev.get('episodes'),list):
                    continue
                case = ev.get('configuration')
                if case is None:
                    case = f"{ev.get('parameter','baseline')}={ev.get('value','')}"
                if str(case) == target['case_name']:
                    matches.extend(ev['episodes'])
            rows = matches
        elif isinstance(content,dict) and isinstance(content.get('episodes'),list):
            rows = content['episodes']
        elif isinstance(content,dict) and 'seed' in content:
            rows = [content]
        else:
            raise ValueError(f'Unrecognized original JSON episode structure: {p}')
        return select_group(rows,target,str(p)), p, notes
    raise ValueError(f'Unsupported original source extension: {p.suffix}')


def successful_time(r):
    """Take observed completed-step time, not official zero-based final-step time."""
    for key in ('study_time_s','completed_step_time_s','elapsed_s'):
        v = number(r.get(key))
        if v is not None:
            return v
    return None


def quantile_linear(values,q):
    vals = sorted(values)
    x = (len(vals)-1)*q
    lo = int(math.floor(x));hi = int(math.ceil(x))
    return vals[lo]+(vals[hi]-vals[lo])*(x-lo)


def exact_ci(k,n):
    from scipy.stats import beta  # independent numerical package, NOT assessment code
    tail = 0.025
    return (float(beta.ppf(tail,k,n-k+1)) if k else 0.0,
            float(beta.ppf(1-tail,k+1,n-k)) if k<n else 1.0)


def tick_number(r,keys):
    for key in keys:
        v = number(r.get(key))
        if v is not None and v >= 0 and v.is_integer():
            return int(v)
    return None


def failed_ticks_for_record(r):
    n = tick_number(r,('failed_solve_ticks','numerical_ticks'))
    if n is not None:
        return n
    vals = parse_json_cell(r.get('solver_statuses'))
    if isinstance(vals,list):
        return sum(int(s != 0) for s in vals)
    indices = parse_json_cell(r.get('failed_solve_indices'))
    if isinstance(indices,list):
        return len(indices)
    return None


def durations(r):
    xs = parse_json_cell(r.get('compute_durations_ms'))
    if isinstance(xs,list) and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0 for x in xs):
        return xs
    return None


def calculate(rows):
    n = len(rows)
    wins = [observed_success(r) for r in rows]
    k = sum(wins)
    values = [successful_time(r) for r,w in zip(rows,wins) if w]
    time_complete = len(values) == k
    out = {'episodes':n,'finishes':k,'completion_rate':k/n,'completion_percent':100*k/n}
    out['completion_ci_lower'],out['completion_ci_upper'] = exact_ci(k,n)
    out['successful_time_episodes'] = len(values)
    out['mean_success_time_s'] = statistics.mean(values) if values and time_complete else None
    out['p90_success_time_s'] = quantile_linear(values,.9) if values and time_complete else None
    out['penalized_mean_time_s'] = (sum(values)+30*(n-k))/n if time_complete else None
    failed = [failed_ticks_for_record(r) for r in rows]
    fallback = [tick_number(r,('fallback_ticks',)) for r in rows]
    if all(v is not None for v in failed):
        out['failed_solve_ticks'] = sum(failed)
        out['failed_solve_episodes'] = sum(v>0 for v in failed)
    if all(v is not None for v in fallback):
        out['fallback_ticks'] = sum(fallback)
        out['fallback_episodes'] = sum(v>0 for v in fallback)
    if all(a is not None and b is not None for a,b in zip(failed,fallback)):
        out['numerical_or_fallback_episodes'] = sum(a>0 or b>0 for a,b in zip(failed,fallback))
        out['numerical_or_fallback_percent'] = 100*out['numerical_or_fallback_episodes']/n
    steps = [number(r.get('steps')) for r in rows]
    if all(s is not None and s >= 0 and s.is_integer() for s in steps):
        out['total_control_calls'] = sum(int(s) for s in steps)
        out['expected_control_calls'] = out['total_control_calls']
        if 'failed_solve_ticks' in out and out['total_control_calls']:
            out['failed_ticks_per_1000_calls'] = 1000*out['failed_solve_ticks']/out['total_control_calls']
    dd = [durations(r) for r in rows]
    if all(x is not None for x in dd):
        total_timed = sum(map(len,dd))
        out['timed_control_calls'] = total_timed
        if 'expected_control_calls' in out and out['expected_control_calls']:
            out['timing_coverage_percent'] = 100*total_timed/out['expected_control_calls']
        full = ('expected_control_calls' in out and total_timed == out['expected_control_calls'] and
                all(len(x)==int(s) for x,s in zip(dd,steps)))
        if full:
            flat=[v for x in dd for v in x]
            out['mean_control_call_ms'] = statistics.mean(flat)
            out['controller_call_p99_ms'] = quantile_linear(flat,.99)
            out['calls_over_20ms'] = sum(v>20 for v in flat)
            out['calls_over_20ms_percent'] = 100*out['calls_over_20ms']/total_timed
    # Missing whole-test timing is unverified: another original archive could exist.
    return out


def result(checkpoint, row, metric, reported=None, actual=None, source_paths='', reason='', reference=''):
    exp = number(reported)
    got = number(actual)
    if actual is None:
        status = 'NOT_VERIFIED'; diff=''
    elif exp is None:
        status = 'NOT_VERIFIED'; diff=''
        reason = reason or 'No numeric value in assessment to compare against'
    else:
        diff = got-exp
        status = 'PASS' if math.isclose(got,exp,rel_tol=1e-8,abs_tol=1e-9) else 'FAIL'
        if status == 'FAIL' and not reason:reason='Original source conflicts with recorded metric'
    return dict(checkpoint=checkpoint, configuration_id=row.get('configuration_id',''),
                cohort_id=row.get('cohort_id',row.get('primary_cohort_id','')),
                reference_cohort_id=reference,metric=metric,
                reported='' if reported is None else str(reported),
                recomputed='' if actual is None else str(actual),
                difference=diff,status=status,source_paths=source_paths,reason=reason)


def check_cohort(checkpoint, target, source_rows, source_path, notes):
    calc=calculate(source_rows)
    output=[]
    evidence_paths = ';'.join([str(source_path)] + [n.split('Details directory: ', 1)[1] for n in notes if n.startswith('Details directory: ')])
    for metric in ('episodes','finishes','completion_rate','completion_percent',
                   'completion_ci_lower','completion_ci_upper','successful_time_episodes',
                   'mean_success_time_s','p90_success_time_s','penalized_mean_time_s',
                   'failed_solve_ticks','failed_solve_episodes','fallback_ticks','fallback_episodes',
                   'numerical_or_fallback_episodes','numerical_or_fallback_percent',
                   'total_control_calls','expected_control_calls','failed_ticks_per_1000_calls',
                   'timed_control_calls','timing_coverage_percent','mean_control_call_ms',
                   'controller_call_p99_ms','calls_over_20ms','calls_over_20ms_percent'):
        value = calc.get(metric)
        if metric not in calc and metric == 'mean_control_call_ms' and target.get(metric)=='nan':
            # Correct missingness is plausible but cannot prove original timings absent globally.
            reason = 'No complete whole-controller timing found in selected original source; missingness not independently exhaustive'
        else:
            reason = '' if metric in calc else 'Original source lacks complete fields needed for this metric'
        output.append(result(checkpoint,target,metric,target.get(metric),value,evidence_paths,reason))
    recorded_sha=target.get('source_sha256','')
    if recorded_sha:
        got_sha=source_sha256(source_path)
        output.append(dict(checkpoint=checkpoint, configuration_id=target['configuration_id'],cohort_id=target['cohort_id'],reference_cohort_id='',
                     metric='original_source_sha256',reported=recorded_sha,recomputed=got_sha,difference='',
                     status='PASS' if recorded_sha==got_sha else 'FAIL',source_paths=str(source_path),reason='byte-for-byte source integrity'))
    return output,calc


def select_primary(cohorts, cohort_id, fallback_case, n=100):
    matches=[r for r in cohorts if r['cohort_id']==cohort_id]
    if len(matches)==1:
        return matches[0]
    # Version-tolerant, but only if there is exactly one case/n/source candidate.
    matches=[r for r in cohorts if r['case_name']==fallback_case and number(r.get('episodes'))==n]
    if len(matches)!=1:
        raise ValueError(f'Ambiguous target cohort {cohort_id}: {len(matches)} candidates')
    return matches[0]


def select_validation(cohorts, comparisons, repo):
    idx={r['cohort_id']:r for r in cohorts}
    viable=[]
    for v in comparisons:
        screen=idx.get(v.get('screening_cohort_id'));valid=idx.get(v.get('validation_cohort_id'))
        if not screen or not valid or screen['configuration_id']!=valid['configuration_id']:
            continue
        try:
            a=source_file(repo,screen);b=source_file(repo,valid)
        except (FileNotFoundError,ValueError):
            continue
        if not a.is_file() or not b.is_file():continue
        if a.stat().st_size>30_000_000 or b.stat().st_size>30_000_000:continue
        if screen['source_path']==valid['source_path']:continue
        score=(int(a.suffix=='.json' and b.suffix=='.json'),
               int('autonomous-20261103' in str(a) and 'autonomous-20261103' in str(b)),
               -abs(int(screen['episodes'])-int(valid['episodes'])),
               -(a.stat().st_size+b.stat().st_size))
        viable.append((score, v, screen, valid))
    if not viable:
        raise ValueError('No indexed validation pair with distinct accessible small original sources')
    viable.sort(key=lambda x:x[0],reverse=True)
    return viable[0][1:]


def seed_map(rows):
    m={}
    for r in rows:
        k=str(r.get('seed'))
        if k in m:raise ValueError('Duplicate seed in original records')
        m[k]=r
    return m


def matched_pair(rows_a, rows_b, cohort_a, cohort_b):
    if cohort_a['environment_id']!=cohort_b['environment_id'] or cohort_a['implementation_id']!=cohort_b['implementation_id']:
        raise ValueError('Recorded environment/implementation identity differs')
    a=seed_map(rows_a);b=seed_map(rows_b)
    valid=[];unknown_states=0;differing_states=0
    for seed in set(a)&set(b):
        ra,rb=a[seed],b[seed]
        sa,sb=ra.get('initial_state'),rb.get('initial_state')
        if sa is None or sb is None:
            unknown_states+=1
        elif sa!=sb:
            differing_states+=1
            continue
        valid.append((ra,rb))
    if not valid:raise ValueError('No valid matching original seeds')
    rescues=sum(not observed_success(ra) and observed_success(rb) for ra,rb in valid)
    regressions=sum(observed_success(ra) and not observed_success(rb) for ra,rb in valid)
    shared=[(ra,rb) for ra,rb in valid if observed_success(ra) and observed_success(rb)]
    deltas=[successful_time(rb)-successful_time(ra) for ra,rb in shared
            if successful_time(ra) is not None and successful_time(rb) is not None]
    result_={'matched_episodes':len(valid),'rescues':rescues,'regressions':regressions,
             'shared_successes':len(shared),'paired_completion_gain_pp':100*(rescues-regressions)/len(valid),
             'paired_mean_success_time_difference_s':statistics.mean(deltas) if len(deltas)==len(shared) and deltas else None}
    return result_,{'unknown_initial_state_pairs':unknown_states,'excluded_different_initial_states':differing_states}


def summarize(out_dir, manifest, results, extra):
    counts={name:sum(r['status']==name for r in results) for name in ['PASS','FAIL','NOT_VERIFIED']}
    status='failures_detected' if counts['FAIL'] else ('partial_verification' if counts['NOT_VERIFIED'] else 'passed')
    summary=dict(status=status,counts=counts,cohorts=dict(manifest),notes=extra,
                 important='PASS is limited to original source files actually read; it does not prove full repository or simulator equivalence')
    save_json(out_dir/'summary.json',summary)
    lines=['# Independent MPCC original-source audit','',
           f"Status: **{status}**; PASS **{counts['PASS']}**, FAIL **{counts['FAIL']}**, NOT_VERIFIED **{counts['NOT_VERIFIED']}**.",'',
           'Checks read original experiment CSV/JSON files. Normalized `cohort_evidence.jsonl.gz` and assessment analysis functions are not used to compute metrics.','',
           '## Findings']
    bad=[r for r in results if r['status']=='FAIL']
    lines += ([f"- **FAIL:** `{r['cohort_id']}` `{r['metric']}` expected `{r['reported']}`, original `{r['recomputed']}` ({r['reason']})" for r in bad[:25]] or ['- No observed metric disagreement among independently verified checks.'])
    if len(bad)>25:lines.append(f'- {len(bad)-25} additional failures in results.csv')
    lines += ['','## Limitations',
              '- Missing source fields are `NOT_VERIFIED`, never assumed zero.',
              '- Exact confidence intervals use SciPy beta quantiles; p90 uses linear order-statistic interpolation.',
              '- An original source checksum match establishes file integrity, not simulation-environment equivalence.',
              '- Identical seeds do not prove identical initial states when those states are not recorded.',
              '- Missing per-call timings cannot establish that no complete timing exists elsewhere.']
    for label,item in manifest.items():
        if item.get('status')!='loaded':lines.append(f"- {label}: {item.get('error','not loaded')}")
    for item in extra:
        if isinstance(item,str):lines.append('- '+item)
    lines += ['','All metric-level comparisons and original paths are in `results.csv`.']
    (out_dir/'audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return counts


def archive(out_dir):
    name=out_dir/'mpcc_independent_audit_review_bundle.zip'
    with zipfile.ZipFile(name,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for fn in ('source_manifest.json','results.csv','summary.json','audit.md','verify.py'):
            p=out_dir/fn
            if p.is_file():z.write(p,fn)
    return name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.home()/'repos/lsy_drone_racing')
    args=parser.parse_args()
    repo=args.repo.expanduser().resolve(); folder=repo/REL
    out=folder/'independent_source_audit'
    for name in ('cohort_metrics.csv','configuration_metrics.csv','validation_comparisons.csv','paired_comparisons.csv'):
        if not (folder/name).is_file():parser.error(f'Missing assessment file: {folder/name}')
    out.mkdir(parents=True,exist_ok=True)
    # Copy exactly this script to make the audit reproducible without depending on Downloads.
    dest=out/'verify.py';source=Path(__file__).resolve()
    if dest!=source:dest.write_bytes(source.read_bytes())
    cohorts=read_csv(folder/'cohort_metrics.csv')
    val=read_csv(folder/'validation_comparisons.csv')
    paired=read_csv(folder/'paired_comparisons.csv')
    manifest={};results=[];extra=[];loaded={}

    def persist():
        save_json(out/'source_manifest.json',manifest)
        save_csv(out/'results.csv',results)
        summarize(out,manifest,results,extra)

    def perform(label,row):
        manifest[label]=dict(cohort_id=row['cohort_id'],configuration_id=row['configuration_id'],case_name=row['case_name'],
                             source_path=row['source_path'],source_sha256=row.get('source_sha256',''),status='pending')
        persist()  # checkpoint before reading original data
        try:
            data,path,notes=original_records(repo,row)
            out_rows,calc=check_cohort(label,row,data,path,notes)
            results.extend(out_rows)
            loaded[label]=(row,data,path,calc)
            manifest[label].update(status='loaded',original_source=str(path),episode_count=len(data),notes=notes)
        except Exception as ex:
            msg=f'{type(ex).__name__}: {str(ex)[:400]}'
            manifest[label].update(status='blocked',error=msg)
            results.append(dict(checkpoint=label,configuration_id=row['configuration_id'],cohort_id=row['cohort_id'],
                                reference_cohort_id='',metric='original_source_access_and_parse',reported=row['source_path'],
                                recomputed='',difference='',status='NOT_VERIFIED',source_paths=row['source_path'],reason=msg))
        persist()  # checkpoint after each cohort

    for label,ident,name in [('F1',F1_COHORT,'F1'),('G07',G07_COHORT,'G07_pole_width_0p4375')]:
        try:
            r=select_primary(cohorts,ident,name)
            perform(label,r)
        except Exception as ex:
            manifest[label]={'status':'blocked','error':f'{type(ex).__name__}: {ex}'}
            results.append(dict(checkpoint=label,metric='cohort_source_resolution',status='NOT_VERIFIED',reason=str(ex),source_paths='cohort_metrics.csv'))
            persist()

    # Independent validation is a separate frozen cohort, NOT pooled with screening.
    try:
        vr,screen,validation=select_validation(cohorts,val,repo)
        perform('validation_screen',screen)
        perform('validation_holdout',validation)
        if 'validation_screen' in loaded and 'validation_holdout' in loaded:
            _,sa,sp,sc=loaded['validation_screen'];_,va,vp,vc=loaded['validation_holdout']
            original_overlap=set(seed_map(sa))&set(seed_map(va))
            delta=vc['completion_percent']-sc['completion_percent']
            results.append(result('validation_comparison',validation,'validation_minus_screening_pp',
                                  vr['validation_minus_screening_pp'],delta,f'{sp};{vp}',reference=screen['cohort_id']))
            results.append(result('validation_comparison',validation,'seed_overlap',vr.get('seed_overlap','0'),
                                  len(original_overlap),f'{sp};{vp}',reference=screen['cohort_id']))
            # Stage-label evidence is insufficient by itself to certify frozen independent validation.
            independence = bool(not original_overlap and validation['cohort_role']=='independent_validation')
            evidence = 'Disjoint original seed IDs and assessment validation role' if independence else 'Overlap or missing independent role'
            results.append(dict(checkpoint='validation_comparison',configuration_id=validation['configuration_id'],
                                cohort_id=validation['cohort_id'],reference_cohort_id=screen['cohort_id'],
                                metric='independent_validation_provenance',reported=validation['role_evidence'],
                                recomputed='',difference='',status='NOT_VERIFIED',source_paths=f'{sp};{vp}',
                                reason=evidence+'; original frozen-plan proof not independently established'))
            persist()
    except Exception as ex:
        manifest['validation_pair']={'status':'blocked','error':f'{type(ex).__name__}: {ex}'}
        results.append(dict(checkpoint='validation_comparison',metric='validation_pair_selection',status='NOT_VERIFIED',
                            reason=str(ex),source_paths='validation_comparisons.csv'))
        persist()

    # Optional direct paired F1_2 cohort; only one recorded small original source.
    if 'F1' in loaded:
        try:
            f12=select_primary(cohorts,F12_COHORT,'F1_2')
            perform('F1_2_optional',f12)
            if 'F1_2_optional' in loaded:
                fa,ra,pa,_=loaded['F1'];fb,rb,pb,_=loaded['F1_2_optional']
                expected=[x for x in paired if x['cohort_id']==fb['cohort_id'] and x['reference_cohort_id']==fa['cohort_id']]
                if len(expected)!=1:
                    raise ValueError(f'Expected exactly one F1/F1_2 paired CSV row, found {len(expected)}')
                direct,flags=matched_pair(ra,rb,fa,fb)
                for field in direct:
                    results.append(result('F1_F1_2_pair',fb,field,expected[0].get(field),direct[field],
                                          f'{pa};{pb}',reference=fa['cohort_id']))
                extra.append('F1/F1_2 paired initial states: '+json.dumps(flags,sort_keys=True))
                persist()
        except Exception as ex:
            results.append(dict(checkpoint='F1_F1_2_pair',metric='direct_matched_comparison',status='NOT_VERIFIED',
                                reason=f'{type(ex).__name__}: {str(ex)[:400]}',source_paths='paired_comparisons.csv'))
            persist()

    # Explicit caution if mandatory metrics cannot be verified.
    for key in ('F1','G07','validation_screen','validation_holdout'):
        if key not in loaded:
            extra.append(f'Mandatory checkpoint {key} NOT_VERIFIED')
    persist()
    bundle=archive(out)
    counts={k:sum(r['status']==k for r in results) for k in ('PASS','FAIL','NOT_VERIFIED')}
    print(json.dumps({'counts':counts,'loaded':list(loaded),'bundle':str(bundle)},sort_keys=True))
    return 1 if counts['FAIL'] else 0


if __name__=='__main__':
    sys.exit(main())

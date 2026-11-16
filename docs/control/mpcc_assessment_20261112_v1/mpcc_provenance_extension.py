"""Provenance-aware CSV/report extension for the retained MPCC assessment.

Data transformation only: no repository/controller imports, simulations or tuning.
The source reference is a retained historical official snapshot, NOT proof of
full physical/runtime equivalence.  No missing source identity is fabricated.
"""
from __future__ import annotations
import csv
import json
import math
import collections
import hashlib
import pathlib
import re

OUT = pathlib.Path(__file__).resolve().parent
REFERENCE = OUT / 'mpcc_reference_snapshot.json'
KNOWN_PATCHED_CORE_SHA256 = '0a16409980429e88e56f9bc84b41758a55a763114ce42c1213641cd4b82061e9'
F1_ID = 'config_a460142e3d70aa79'
F1_2_ID = 'config_2470aab06585d4ce'
F1_COHORT = 'cohort_ced5195525a73529'
F1_2_COHORT = 'cohort_13b826dd1a54a917'


def load_reference():
    return json.loads(REFERENCE.read_text(encoding='utf-8'))


def _numeric_normalized(v):
    if isinstance(v, dict):
        return {str(k): _numeric_normalized(value) for k, value in v.items()}
    if isinstance(v, list):
        return [_numeric_normalized(value) for value in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return float(v)
    return v


def _flatten(obj, pre=''):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield from _flatten(v,pre+'.'+str(k) if pre else str(k))
    else:
        yield pre, _numeric_normalized(obj)


def environment_fields(identity, reference=None):
    reference = reference or load_reference()
    env = identity.get('environment') or {}
    pins = env.get('source_pins') or {}
    recorded = pins.get('envs/race_core.py', '')
    official = reference['official_source_hashes']['envs/race_core.py']
    if not recorded:
        category = 'unverified_core_source'
        evidence = 'recorded race_core.py hash not available'
    elif recorded == official:
        category = 'retained_official_core_match'
        evidence = 'recorded race_core.py hash equals retained historical official snapshot'
    else:
        category = 'verified_modified_core_source'
        evidence = 'recorded race_core.py hash differs from retained historical official snapshot'
    if recorded == KNOWN_PATCHED_CORE_SHA256:
        patched = 'verified_recovered_contact_fix_hook'
    elif category == 'verified_modified_core_source':
        patched = 'modified_core_uncharacterized'
    else:
        patched = 'no_contact_fix_hook_attributed'
    conf = env.get('config') or {}
    offconf = reference.get('official_config') or {}
    # These are INTERFACE/configuration fields, never silently treated as physics modifications.
    excluded = {'env.control_mode', 'env.seed', 'sim.render'}
    a = dict(_flatten(conf));b=dict(_flatten(offconf))
    differences = sorted(k for k in set(a)|set(b) if k not in excluded and (k not in a or k not in b or a[k]!=b[k]))
    interface_mode = a.get('env.control_mode', '')
    if not a:
        conf_status = 'recorded_physical_config_missing'
    elif differences:
        conf_status = 'non_interface_config_difference_or_missing'
    elif a.get('env.control_mode') != b.get('env.control_mode'):
        conf_status = 'no_non_interface_config_diff_detected;control_interface_differs'
    else:
        conf_status = 'no_non_interface_config_diff_detected'
    # Full dependency closure unproven regardless of race_core match.
    return dict(environment_provenance_group=category,
                environment_provenance_evidence=evidence,
                retained_official_race_core_sha256=official,
                recorded_race_core_sha256=recorded,
                contact_patch_attribution=patched,
                physical_config_comparison_status=conf_status,
                physical_config_non_interface_diff_count=len(differences) if a else None,
                physical_config_non_interface_differences_json=differences if a else [],
                recorded_control_mode=interface_mode,
                environment_full_equivalence_status='not_established;source_runtime_closure_incomplete',
                official_reference_source_path=reference['historical_root']+'/lsy_drone_racing/envs/race_core.py')


def augment_pair_comparisons(paired, cohorts):
    """Add direct F1_2 minus F1 comparison, without creating experimental records."""
    by_id={c['cohort_id']:c for c in cohorts}
    a=by_id.get(F1_COHORT); b=by_id.get(F1_2_COHORT)
    if a is None or b is None:
        # This is legitimate only for a different input snapshot. Explicitly document.
        return 'F1/F1_2 target cohorts missing; direct comparison not added'
    if a['configuration_id'] != F1_ID or b['configuration_id'] != F1_2_ID:
        raise ValueError('F1/F1_2 cohort/config identity changed: refuse to attribute previously reported comparison')
    if a['cohort_group']!=b['cohort_group'] or a['identity']['environment_id']!=b['identity']['environment_id']:
        raise ValueError('F1/F1_2 experiment group/environment do not match')
    if a['identity']['implementation_id']!=b['identity']['implementation_id']:
        raise ValueError('F1/F1_2 implementation hashes differ')
    def indexed(c):
        r=c['records']; ix={str(x['seed']):x for x in r if x.get('seed') is not None}
        if len(ix)!=len(r):raise ValueError('F1/F1_2 missing or duplicate seeds')
        return ix
    ra, rb=indexed(a),indexed(b)
    common=sorted(ra.keys()&rb.keys());matched=[];unknown_states=0
    for s in common:
        aa,bb=ra[s],rb[s]
        if aa.get('initial_state') is not None and bb.get('initial_state') is not None:
            if aa['initial_state']!=bb['initial_state']:continue
        else:unknown_states+=1
        matched.append(s)
    if not matched:raise ValueError('F1 and F1_2 have no matched seeds')
    wins=0;losses=0;shared=[];times=[]
    for s in matched:
        aa,bb=ra[s],rb[s]
        aw=bool(aa.get('_success',aa.get('success') is True or aa.get('outcome')=='success'))
        bw=bool(bb.get('_success',bb.get('success') is True or bb.get('outcome')=='success'))
        wins+=int(bw and not aw);losses+=int(aw and not bw)
        at=aa.get('_rank_time_s');bt=bb.get('_rank_time_s')
        if aw and bw and at is not None and bt is not None:
            shared.append(s);times.append(bt-at)
    # Known Phase-4 evidence provides a cross-check, not an input into the calculation.
    if len(common)==100 and (wins,losses,len(shared)) != (2,2,82):
        raise ValueError('F1 vs F1_2 100-seed result disagrees with the independent Phase-4 audit')
    cid='pair_'+hashlib.sha256((a['cohort_id']+b['cohort_id']).encode()).hexdigest()[:16]
    if any(x.get('comparison_id')==cid for x in paired):
        raise ValueError('Duplicate F1 direct comparison ID')
    paired.append(dict(comparison_id=cid,configuration_id=b['configuration_id'],reference_configuration_id=a['configuration_id'],cohort_id=b['cohort_id'],reference_cohort_id=a['cohort_id'],reference_case=a['case_name'],reference_selection='explicit direct F1 versus F1_2 comparator; NOT independent validation',environment_id=a['identity']['environment_id'],cohort_group=a['cohort_group'],matched_episodes=len(matched),rescues=wins,regressions=losses,paired_completion_gain=(wins-losses)/len(matched),paired_completion_gain_pp=100*(wins-losses)/len(matched),shared_successes=len(shared),paired_mean_success_time_difference_s=sum(times)/len(times) if times else None,time_difference_direction='F1_2 minus F1; negative=faster',matched_seeds=matched,shared_success_seeds=shared,matching_status='same cohort group/implementation/environment and seeds; initial states missing for '+str(unknown_states)+' matched pairs',unknown_initial_state_pairs=unknown_states,comparison_kind='targeted_direct_nonbaseline',identity_status='resolved' if a['identity']['identity_status']==b['identity']['identity_status']=='resolved' else 'unresolved_provenance; descriptive_only'))
    return 'direct F1/F1_2 paired comparison added (unknown initial states: '+str(unknown_states)+')'


def ranking_groups(configs):
    """Rank strictly within an exact recorded environment_id, never just a source-hash family.

    A source-core hash match is not proof of equality for different environment_id values.
    Only one environment per provenance category is displayed as the primary table;
    other qualifying environments retain independent ranks and remain visible separately.
    """
    def rank(r):
        return (-int(r['independent_validation_cohorts'] > 0),
                -math.floor(r['completion_ci_lower'] / .05),
                r['complexity_score'] if r['complexity_score'] is not None else 9,
                -r['episodes'],
                r['mean_success_time_s'] if r['mean_success_time_s'] is not None else math.inf,
                r['configuration_id'])

    by_environment = collections.defaultdict(list)
    for r in configs:
        r['ranking_group'] = r['environment_id']
        r['within_environment_rank'] = None
        r['within_provenance_rank'] = None  # compatibility alias; now always an exact-environment rank
        r['shortlist_rank'] = None
        r['historical_rank'] = None
        if r['qualifies_observed_70']:
            by_environment[r['environment_id']].append(r)

    for env, rows in by_environment.items():
        # Qualifying rows in an environment necessarily have the same provenance classification.
        if len({r['environment_provenance_group'] for r in rows}) != 1:
            raise ValueError('One environment_id has incompatible source provenance categories: ' + env)
        for i, r in enumerate(sorted(rows, key=rank), 1):
            r['within_environment_rank'] = i
            r['within_provenance_rank'] = i

    def primary_environment(category):
        candidates = [(env, rs) for env, rs in by_environment.items()
                      if rs[0]['environment_provenance_group'] == category]
        if not candidates:
            return None
        # This is an ENVIRONMENT DISPLAY selection, not a cross-environment performance rank.
        # Stable tie-breakers: number of qualifying configs, total sampled episodes, environment ID.
        return sorted(candidates, key=lambda t: (-len(t[1]),
                     -sum(int(r['episodes']) for r in t[1]), t[0]))[0][0]

    main_env = primary_environment('retained_official_core_match')
    historical_env = primary_environment('verified_modified_core_source')
    for r in configs:
        r['main_display_environment_id'] = main_env or ''
        r['historical_display_environment_id'] = historical_env or ''
        if not r['qualifies_observed_70']:
            continue
        if r['environment_id'] == main_env:
            r['shortlist_rank'] = r['within_environment_rank']
        elif r['environment_id'] == historical_env:
            r['historical_rank'] = r['within_environment_rank']
    return {env: len(rows) for env, rows in by_environment.items()}


def _csv(name):
    with (OUT/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def _num(r,key,default=None):
    try:return float(r[key])
    except (ValueError,TypeError,KeyError):return default


def _show(r,key,n=2):
    v=_num(r,key)
    return 'N/A' if v is None or not math.isfinite(v) else f'{v:.{n}f}'


def _mk_table(cols,rows):
    def cell(x):return str(x).replace('|','/').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(cols)+' |', '|'+ '|'.join(['---']*len(cols))+'|', *['| '+' | '.join(map(cell,row))+' |' for row in rows]])


def _group_view(cs,co):
    group=collections.defaultdict(lambda:{'configs':0,'cohorts':0,'qualifiers':0,'environments':set()})
    for c in cs:
        g=group[c['environment_provenance_group']];g['configs']+=1;g['qualifiers']+=c['qualifies_observed_70']=='1';g['environments'].add(c['environment_id'])
    for r in co:group[r['environment_provenance_group']]['cohorts']+=1
    return _mk_table(['Recorded race-core evidence','Environments','Configurations','Cohorts','Observed ≥70% eligible'],[[name,len(x['environments']),x['configs'],x['cohorts'],x['qualifiers']] for name,x in sorted(group.items())])


def _enhance_shortlist_table(lines,cs):
    # Existing report code constructs shortlist from new shortlist_rank. Add provenance/ID to first table.
    lookup={int(x['shortlist_rank']):x for x in cs if x['shortlist_rank']}
    head='| Rank / ID | Configuration | n | Finishes | Completion % | 95% lower % | 95% upper % | Evidence | Lower >70% |'
    if head not in lines:
        raise ValueError('Source report shortlist table changed; cannot safely add environment IDs')
    i=lines.index(head); lines[i]=lines[i].replace('| Configuration |','| Env / core | Configuration |')
    lines[i+1]=lines[i+1].replace('---|---|','---|---|---|',1)
    j=i+2
    while j<len(lines) and lines[j].startswith('|'):
        parts=lines[j].split('|'); label=parts[1].strip().split(' / ')[0]
        if not label.isdigit() or int(label) not in lookup:raise ValueError('Shortlist rank/CSV mismatch')
        r=lookup[int(label)]
        env=r['environment_id'].replace('env_','')[:8]
        parts.insert(2, f' {env} / core match ')
        lines[j]='|'.join(parts)
        j+=1


def report_postprocess():
    cs=_csv('configuration_metrics.csv');co=_csv('cohort_metrics.csv');pa=_csv('paired_comparisons.csv');va=_csv('validation_comparisons.csv')
    p=OUT/'assessment.md';lines=p.read_text(encoding='utf-8').splitlines()
    main=[r for r in cs if r.get('shortlist_rank')];main.sort(key=lambda x:int(x['shortlist_rank']))
    if len(main)>25:
        main=main[:25]
    # Replace problematic global-ranking claim, which would mix different source implementations.
    for i,line in enumerate(lines):
        if line.startswith('**Transparent lexicographic ordering:**'):
            lines[i]='**Transparent within-environment lexicographic ordering:** only compare configurations with the SAME recorded `environment_id`, resolved primary n ≥10, and observed completion ≥70%. Within each exact environment: prioritize independent validation, then higher five-percentage-point bands of exact lower confidence bounds, lower complexity, larger primary n, and faster successful mean; stable identity breaks ties. For each source-provenance category, the main *display environment* is chosen by number of qualifying configurations, then total sampled episodes, then ID — not by success rate. Remaining environments have separate within-environment ranks. Full datasets retain all candidates; no cross-environment completion probabilities are ranked as comparable.'
        if line.startswith('## Ranked shortlist:'):
            lines[i]='## Ranked shortlist: retained official race-core match, observed completion ≥70%'
        if line.startswith('The threshold label **observed ≥70%**'):
            lines[i]='This **display filter** requires a pinned `race_core.py` matching the retained official snapshot, resolved identity, primary n ≥10, observed completion ≥70%, and membership in the single selected source-matched `environment_id`. Up to 25 *within that exact environment* are shown. Other qualifying environments are not merged into this ranking. A matching core alone does NOT prove full simulator equivalence. “Observed ≥70%” differs from “95% lower endpoint >70%”. Screening-only cases are labeled.'
    _enhance_shortlist_table(lines,cs)
    provenance=['## Environment provenance and comparability','',
        'The retained historical official reference is a **source snapshot**, not proof of complete runtime/physics equivalence. A difference in `env.control_mode` (state versus attitude) is a control interface difference, not evidence on its own of altered physics. Other recorded configuration differences, incomplete package pins, and instrumentation scopes remain visible in the CSVs.','',
        _group_view(cs,co),'',
        '- **Retained official core match:** pinned `race_core.py` equals the historical official snapshot. Other simulator dependencies may remain unverified; this label is deliberately narrower than “official-equivalent”.',
        '- **Verified modified core source:** pinned `race_core.py` differs. The recovered historical modification installs an MJX box-box collision compatibility function for MuJoCo 3.10.0; collision behavior may change. No experimental magnitude has been established.',
        '- **Unverified core source:** recorded `race_core.py` pin absent. Unknown is not equivalent or different.',
        '- Main shortlist uses ONE exact source-matched `environment_id`. The primary modified-core table also uses ONE exact `environment_id`. Any additional qualifying environments are shown separately; no results are pooled or performance-ranked across them.','']
    by_env=collections.defaultdict(list)
    for r in cs:
        if r['qualifies_observed_70']=='1':
            by_env[r['environment_id']].append(r)
    if by_env:
        provenance += ['### Qualifying configurations by exact recorded environment','',
            'These rows are counts, **not cross-environment rankings**. The main display environments are selected by qualifier count, not by measured performance.','',
            _mk_table(['Environment ID','Race-core source evidence','Qualifying configurations','Main display role'],
               [[env,rs[0]['environment_provenance_group'],len(rs),
                 'source-matched main shortlist' if any(r.get('shortlist_rank') for r in rs)
                 else 'modified-core primary table' if any(r.get('historical_rank') for r in rs)
                 else 'separate supplementary evidence']
                for env,rs in sorted(by_env.items())]),'']
    main_env=next((r['environment_id'] for r in cs if r.get('shortlist_rank')),None)
    historical_env=next((r['environment_id'] for r in cs if r.get('historical_rank')),None)
    for i,line in enumerate(lines):
        if line.startswith('## Ranked shortlist:'):
            lines[i]=line + (f' — environment `{main_env}`' if main_env else ' — no qualifying source-matched environment')
    idx=next(i for i,s in enumerate(lines) if s.startswith('## Ranked shortlist:'))
    lines[idx:idx]=provenance
    historical=sorted([r for r in cs if r.get('historical_rank')],key=lambda r:int(r['historical_rank']))[:12]
    def case(r):return r['case_name'].replace('|','/')
    historical_section=['## Historical modified-core foundations (not directly comparable)','',
         'These candidates meet the same eligibility rules and share ONE exact modified-core environment ID: `'+str(historical_env)+'`. Other modified-core environments have separate ranks below. This is a separate display table (up to 12), not a continuation of the main shortlist.','']
    historical_section.append(_mk_table(['Within-group rank / ID','Configuration','Env ID','n','Finishes','Completion %','Exact 95% CI (fraction)','Successful mean s','P90 s (provisional if <30 finishes)','30 s penalized s','Solver/fallback affected %','Pooled p99 ms','Mean compute ms','Complexity','Independent validation?'],[[r['historical_rank']+' / '+r['configuration_id'][7:15],case(r),r['environment_id'],r['episodes'],r['finishes'],_show(r,'completion_percent',1),_show(r,'completion_ci_lower',3)+'–'+_show(r,'completion_ci_upper',3),_show(r,'mean_success_time_s',3),_show(r,'p90_success_time_s',3),_show(r,'penalized_mean_time_s',3),_show(r,'numerical_or_fallback_percent',2),_show(r,'controller_call_p99_ms',3),_show(r,'mean_control_call_ms',3),r['complexity_score'], 'yes' if r['screening_only_evidence']=='0' else 'screening only'] for r in historical]))
    historical_section+=['','Full historical configuration identities, numeric exact CI endpoints, timing scope and source pins are retained in `configuration_metrics.csv`. Numerical health and timing gaps must not be silently interpreted as zero.','']
    # Other qualifying environments must be visible without combining their ranks.
    supplementary=collections.defaultdict(list)
    for r in cs:
        if r['qualifies_observed_70']=='1' and r['environment_id'] not in (main_env,historical_env):
            supplementary[r['environment_id']].append(r)
    if supplementary:
        historical_section += ['## Other qualifying environments — independent supplementary rankings','',
            'Each environment below has its own ordinal ranks. These are not comparable to either main display table without independently established equivalence.','']
        for env, others in sorted(supplementary.items()):
            others=sorted(others,key=lambda r:int(r['within_environment_rank']))
            historical_section.extend([
                '### Environment `'+env+'` — '+others[0]['environment_provenance_group'], '',
                _mk_table(['Within-environment rank / ID','Configuration','n','Finishes','Completion %','Exact 95% CI lower / upper (fraction)','Successful mean s','Numerical/fallback %','Complexity'],
                    [[str(r['within_environment_rank'])+' / '+r['configuration_id'][7:15],case(r),r['episodes'],r['finishes'],
                      _show(r,'completion_percent',1),_show(r,'completion_ci_lower',3)+' / '+_show(r,'completion_ci_upper',3),
                      _show(r,'mean_success_time_s',3),_show(r,'numerical_or_fallback_percent',2),r['complexity_score']]
                     for r in others]),'',
                'CI endpoints are fractions. These supplementary rows preserve the original eligibility and environment-specific identity.',''])
    idx=next(i for i,s in enumerate(lines) if s=='## Availability across tests')
    lines[idx:idx]=historical_section
    f1=next((r for r in cs if r['configuration_id']==F1_ID),None)
    f12=next((r for r in cs if r['configuration_id']==F1_2_ID),None)
    direct=next((r for r in pa if r.get('reference_configuration_id')==F1_ID and r.get('configuration_id')==F1_2_ID and r.get('comparison_kind')=='targeted_direct_nonbaseline'),None)
    direct_section=['## Direct F1 versus F1_2 comparison','']
    if f1 and f12 and direct:
        direct_section.extend([
            f'F1: **{f1["finishes"]}/{f1["episodes"]}**, successful mean {_show(f1,"mean_success_time_s",4)} s. F1_2: **{f12["finishes"]}/{f12["episodes"]}**, successful mean {_show(f12,"mean_success_time_s",4)} s. Both used the same source-matched environment/implementation group, and differ in the recorded `mpcc.gate_offset` setting (F1 0.180, F1_2 0.162).',
            '',
            f'Direct seed intersection: **{direct["matched_episodes"]}**; F1_2 rescues **{direct["rescues"]}**, regresses **{direct["regressions"]}**; paired completion gain **{_show(direct,"paired_completion_gain_pp",2)} pp**. On **{direct["shared_successes"]}** common successful seeds, F1_2 minus F1 successful time is **{_show(direct,"paired_mean_success_time_difference_s",5)} s** (negative = F1_2 faster).',
            '',
            f'**Evidence limitation:** {direct["matching_status"]}. The compared episodes have matching explicit seeds and recorded study conditions but lack independently recorded initial-state vectors for {direct.get("unknown_initial_state_pairs", "unknown")} pairs. This is exploratory matched-seed evidence, NOT independent validation.',
            '',
            'Phase 4 found an exploratory direct McNemar exact p=1.0, with 2 rescues and 2 regressions each way. The approximately 5.6 ms time difference is tiny in practical terms; neither controller establishes a completion-reliability advantage. F1 is a provisional comparison foundation; F1_2 remains a near-equivalent faster alternative.',
            '' ])
    else:
        direct_section += ['Direct F1/F1_2 evidence not present in this source snapshot; see `paired_comparisons.csv` and the unresolved evidence inventory.','']
    idx=next(i for i,s in enumerate(lines) if s=='## Independent validation and changes across cohorts')
    lines[idx:idx]=direct_section
    # Replace name-driven recommendations that may mix in different environments.
    start=next(i for i,s in enumerate(lines) if s=='## Recommended foundations')
    end=next(i for i in range(start+1,len(lines)) if lines[i]=='## Relevant alternatives below 70%')
    rec=['## Recommended foundations — separate source environments','',
         'The following are **provisional research foundations**, not independently validated competition-ready winners. Completion evidence, solver/fallback health, timing scope, complexity and sampling uncertainty should be read together; penalized time is correlated with completion and is not a separate robustness score.','']
    for x,note in [(f1,'A source-matched, 84/100 focused screening candidate with no recorded failed solver ticks; selected as a practical baseline for further paired testing, not because it statistically beats F1_2.'),(f12,'Same observed 84/100 screening completion and implementation complexity; slightly faster on shared successful seeds, but no established robustness advantage.')]:
        if x:
            rec += [f'- **{case(x)} ({x["configuration_id"][:17]})**: {x["finishes"]}/{x["episodes"]} ({_show(x,"completion_percent",1)}%); exact 95% CI {_show(x,"completion_ci_lower",3)}–{_show(x,"completion_ci_upper",3)} (fractions); successful mean {_show(x,"mean_success_time_s",3)} s; p90 {_show(x,"p90_success_time_s",3)} s; solver/fallback affected {_show(x,"numerical_or_fallback_percent",2)}%; call mean {_show(x,"mean_control_call_ms",3)} ms; complexity {x["complexity_score"]}. {note}']
    for r in cs:
        if r.get('case_name','').startswith('G07') and r['environment_provenance_group']=='retained_official_core_match' and int(r['episodes'])>=100 and float(r['completion_rate'])>=.7:
            rec+=[f'- **G07 comparison ({r["configuration_id"][:17]})**: {r["finishes"]}/{r["episodes"]} finishes, {_show(r,"mean_success_time_s",3)} s mean successful time; {r["failed_solve_ticks"]} recorded failed solver ticks. Similar observed completion should not conceal worse solver-health evidence.']
            break
    if historical:
        x=max(historical,key=lambda r:int(r['episodes']))
        rec+=[f'- **Historical modified-core foundation ({case(x)}, {x["configuration_id"][:17]})**: {x["finishes"]}/{x["episodes"]}, exact 95% CI {_show(x,"completion_ci_lower",3)}–{_show(x,"completion_ci_upper",3)} (fractions), mean successful {_show(x,"mean_success_time_s",3)} s. Useful within its own environment; not an apples-to-apples competition comparison.']
    rec+=['','The source-matched F1/F1_2 cohorts are **screening**, not post-selection independent validation. Reconsider a foundation if independent validation or a stricter runtime/solver-health audit changes the ordering. Remaining unverified-source environments are retained in the datasets, not presumed equivalent.','']
    lines[start:end]=rec
    # Add environment and direct pair definitions to generated dictionary.
    dictionary=OUT/'data_dictionary.md'
    d=dictionary.read_text(encoding='utf-8')
    definitions={
        'environment_provenance_group':'Pinned race_core.py relative to a retained official historical snapshot: retained_official_core_match, verified_modified_core_source, or unverified_core_source. This is NOT full simulator equivalence.',
        'environment_provenance_evidence':'Exact basis for source match/mismatch/unknown classification.',
        'recorded_race_core_sha256':'Pinned race_core.py SHA256 in the recorded environment provenance, blank when absent.',
        'retained_official_race_core_sha256':'SHA256 of retained official historical reference source.',
        'contact_patch_attribution':'Whether a known recovered hash establishes the MJX collision box-box hook.',
        'physical_config_comparison_status':'Recorded config comparison after excluding only known interface/seed/render fields. Not proof of physical equivalence.',
        'physical_config_non_interface_diff_count':'Count of config paths differing or missing beyond excluded fields; blank if recorded config absent.',
        'physical_config_non_interface_differences_json':'Specific non-interface config paths; absence of complete config is documented separately.',
        'recorded_control_mode':'Recorded control interface (state/attitude), which should not alone be treated as changed dynamics.',
        'environment_full_equivalence_status':'Explicit note that complete simulator package/runtime closure has not been verified.',
        'official_reference_source_path':'Historical retained source path used as the comparison basis.',
        'ranking_group':'The exact recorded environment_id. Results from different environment IDs are never performance-ranked as equivalent.',
        'within_environment_rank':'Lexicographic rank among qualifying configurations from the SAME exact recorded environment_id.',
        'within_provenance_rank':'Legacy compatibility alias for within_environment_rank; does NOT rank across distinct environment IDs.',
        'main_display_environment_id':'Exact chosen source-matched environment for the main display, chosen by number of eligible configs, total primary n, then stable ID.',
        'historical_display_environment_id':'Exact chosen modified-core environment for the historical display, chosen without comparing success rates across environments.',
        'shortlist_rank':'Within-environment rank only if eligible and member of selected source-matched display environment. May exceed 25; report displays top 25.',
        'historical_rank':'Within-environment rank only in selected modified-core display environment; other environments retain within_environment_rank.',
        'comparison_kind':'Targeted direct comparison or conventional reference comparison; no automatic independent-validation inference.',
        'unknown_initial_state_pairs':'Matched seeds whose original initial-state vectors are not recorded in both cohorts; count explicitly retained.',
    }
    new='\n## Provenance-aware additions (derived from recorded evidence)\n\n'+'\n'.join(f'- **`{k}`**: {v}' for k,v in definitions.items())+'\n'
    if '## Provenance-aware additions (derived from recorded evidence)' not in d:
        d+=new
    dictionary.write_text(d,encoding='utf-8')
    # Reporting an independent validator PASS here would be circular: generation precedes the audit.
    # The separate validator records an auditable status and output hashes on completion.
    lines.insert(2,'> **VALIDATION RECORD:** Analysis invariants were checked during dataset generation. After running the independent validator, inspect `helper_audit/implementation_validation/validation.json` for the result and the exact checked artifact hashes. An earlier validation record does not certify a newly regenerated report.')
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')

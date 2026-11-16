"""Read retained MPCC evidence only. No controller imports or simulations."""
from __future__ import annotations
import ast, collections, csv, datetime, functools, gzip, hashlib, json, pathlib, re, subprocess, tarfile, tomllib, zipfile
ROOT=pathlib.Path('/home/askho/repos/lsy_drone_racing')
V3=ROOT.parent/'lsy_drone_racing-mpcc-v3'
USB=pathlib.Path('/media/askho/Ask-USB/mpcc-study')
OUT=pathlib.Path(__file__).resolve().parent
EXCLUSIONS=[]; INVENTORY=[]; ISSUES=[]
def norm(x):
    if isinstance(x,dict): return {str(k):norm(v) for k,v in sorted(x.items())}
    if isinstance(x,(list,tuple)): return [norm(v) for v in x]
    if isinstance(x,(int,float)) and not isinstance(x,bool): return float(x)
    return x
def canonical(x): return json.dumps(norm(x),sort_keys=True,separators=(',',':'),allow_nan=False)
def hid(x,prefix):return prefix+hashlib.sha256(canonical(x).encode()).hexdigest()[:16]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@functools.lru_cache(maxsize=32)
def read(p):
    p=pathlib.Path(p)
    try:
        if p.suffix=='.toml':return tomllib.loads(p.read_text())
        return json.loads(p.read_text())
    except (ValueError,OSError):return {}
def rel(p):
    try:return str(pathlib.Path(p).relative_to(ROOT))
    except ValueError:return str(p)
def utc(t):return datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat()
def shrink(d):
    if isinstance(d,dict):return {k:shrink(v) for k,v in d.items() if k not in ['episodes','evaluations','table','tick_records','geometry_records','coverage_ledger','prior_inventory','freshness']}
    if isinstance(d,list):return [shrink(v) for v in d[:30]]
    return d
META=['plan.json','request.json','manifest.json','study.json','provenance.json','fingerprint.json','fingerprints.json','source-runtime-manifest.json','baseline-verification.json','effective-environment.json','runtime.json','environment-verification.json','callback-implementation.json','preflight.json','decision.json','execution-manifest.json','config.toml']
@functools.lru_cache(maxsize=128)
def context(directory):
    p=pathlib.Path(directory);result=[]
    for base in [p,*list(p.parents)[:4]]:
        if base in [ROOT,V3,ROOT/'logs',ROOT/'.local',ROOT/'.local/mpcc-study',ROOT/'logs/mpcc-tuning',ROOT/'logs/mpcc-campaign',ROOT/'logs/mpcc-prediction-v1']:break
        for name in META:
            q=base/name
            if q.exists():result.append((rel(q),shrink(read(q))))
    # Requests may point sideways to a frozen plan (e.g. a resumed screen).
    request=pathlib.Path(directory).parent/(pathlib.Path(directory).name+'-request.json')
    if request.exists():result.insert(0,(rel(request),shrink(read(request))))
    for source,d in list(result):
        if isinstance(d,dict) and isinstance(d.get('plan'),str):
            q=pathlib.Path(d['plan'])
            if q.exists() and (not d.get('plan_sha256') or sha(q)==d['plan_sha256']):
                if rel(q) not in {k for k,_ in result}:result.append((rel(q),shrink(read(q))))
    return result

def walk_dict(d):
    if isinstance(d,dict):
        yield d
        for v in d.values():yield from walk_dict(v)
    elif isinstance(d,list):
        for v in d:yield from walk_dict(v)
def hashes_from(ctx):
    out={}
    for _,d in ctx:
        for node in walk_dict(d):
            for k,v in node.items():
                if isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) and ('/' in k or k.endswith('.py')):
                    out.setdefault(k,v)
    return out

def family(module,settings,path):
    s=module.lower()
    if 'selected' in s or 'g07_pole' in s or 'recheck_r23' in s or 'departure_rise_lower' in s:return 'selected_submission'
    if 'v3_safe' in s:return 'v3_safe'
    if 'v3_alt' in s:return 'v3_alt'
    if 'v3' in s or '/v3-' in path:return 'v3'
    if 'prediction' in s or 'prediction' in settings:return 'prediction'
    if 'broad' in s or 'gate_offset' in settings.get('mpcc',{}):return 'broad'
    if 'v2' in s:return 'v2'
    if 'experimental' in s or 'mpcc_experiment' in settings:return 'experimental'
    if 'mpcc' in s:return 'basic'
    return 'unresolved'
NEEDED={
 'basic':['attitude_mpcc.py','attitude_mpc.py','track_geometry.py'],
 'experimental':['attitude_mpcc.py','attitude_mpcc_experimental.py','attitude_mpc.py','track_geometry.py'],
 'broad':['mpcc_broad_core.py','mpcc_broad_solver.py','mpcc_v2_geometry.py','attitude_mpc.py'],
 'prediction':['mpcc_prediction_core.py','mpcc_prediction_solver.py','mpcc_prediction_model.py','mpcc_broad_core.py','mpcc_broad_solver.py','mpcc_v2_geometry.py','attitude_mpc.py'],
 'v2':['mpcc_v2_core.py','mpcc_v2_solver.py','mpcc_v2_geometry.py','attitude_mpcc_v2.py','attitude_mpc.py'],
 'v3':['mpcc_v3_model.py','mpcc_v3_solver.py','mpcc_v3_geometry.py','attitude_mpcc_v3.py'],
 'v3_safe':['mpcc_v3_model.py','mpcc_v3_safe_solver.py','mpcc_v3_geometry.py','attitude_mpcc_v3_safe.py'],
 'v3_alt':['mpcc_v3_model.py','mpcc_v3_alt_solver.py','mpcc_v3_alt_geometry.py','attitude_mpcc_v3_alt.py'],
 'selected_submission':['mpcc_selected_core.py','mpcc_selected_solver.py','mpcc_selected_geometry.py','attitude_mpc.py']}
# Defaults used ONLY for legacy reports whose original baseline source hash is pinned.
LEGACY_BASIC_HASH='2033f45e88df6931b734155281b1cb3c80e71a10bb8358be754ff39ed8324b3c'
LEGACY_DEFAULTS=dict(horizon_steps=40,reference_speed=1.3,max_speed=1.8,contour_weight=400,lag_weight=400,progress_weight=12,max_angle=.6,attitude_rate_weight=.1,attitude_slew_weight=.02,thrust_slew_weight=.1,terminal_weight=.2,adaptation_rate=2,obstacle_clearance=.26)

def identity(episodes,case,ev,ctx,path):
    first=episodes[0] if episodes else {}
    settings=first.get('effective_settings') or ev.get('effective_settings')
    config=ev.get('config') or {}
    controller=config.get('controller') or ev.get('controller_config') or {}
    if not settings:
        for row in episodes:
            if row.get('effective_settings'):settings=row['effective_settings'];break
    if isinstance(settings,str):
        try:settings=json.loads(settings)
        except ValueError:settings=ast.literal_eval(settings)
    if not settings:
        for _,d in ctx:
            cases=d.get('cases',{}) if isinstance(d,dict) else {}
            if isinstance(cases,dict) and case in cases:
                c=cases[case];settings=c.get('settings') or (c if 'mpcc' in c else c.get('controller'));break
    pins=hashes_from(ctx)
    settings_status='recorded_complete'
    if not settings and controller:
        settings={k:v for k,v in controller.items() if k!='file'}
        if settings.get('mpcc',{}).keys()>=LEGACY_DEFAULTS.keys():pass
        elif LEGACY_BASIC_HASH in pins.values():
            settings['mpcc']=dict(LEGACY_DEFAULTS,**settings.get('mpcc',{}));settings_status='reconstructed_from_pinned_legacy_defaults'
        else:settings_status='unresolved_incomplete_settings'
    if not settings:settings={};settings_status='unresolved_missing_settings'
    settings=json.loads(json.dumps(settings))
    # Verify consistency within frozen cohort rather than silently choosing one setting object.
    ss={canonical(r['effective_settings']) for r in episodes if isinstance(r.get('effective_settings'),dict)}
    if len(ss)>1:settings_status='unresolved_mixed_settings'
    module=first.get('controller_module') or first.get('controller_class') or controller.get('file','')
    if not module:
        for _,d in ctx:
            if isinstance(d,dict) and isinstance(d.get('controller'),str):module=d['controller'];break
    fam=family(module,settings,path)
    if fam in ['basic','experimental'] and settings:
        settings.setdefault('mpcc_experiment',dict(gate_center_snap=1,over_gate_lift=0,observed_obstacle_clearance=None))
    needed=NEEDED.get(fam,[]);bundle={}
    for name in needed:
        vals={v for k,v in pins.items() if pathlib.Path(k).name==name}
        if len(vals)==1:bundle[name]=next(iter(vals))
        elif len(vals)>1:
            # Nearest context takes precedence; a plan pins measured source, parent inventory does not.
            for _,d in ctx:
                vv={v for k,v in hashes_from([('',d)]).items() if pathlib.Path(k).name==name}
                if len(vv)==1:bundle[name]=next(iter(vv));break
    # Frozen .local source snapshots provide authoritative version identity if fingerprints omitted.
    for name in needed:
        if name in bundle:continue
        for cp,_ in ctx:
            parent=(ROOT/cp).parent if not pathlib.Path(cp).is_absolute() else pathlib.Path(cp).parent
            found=[parent/'source/lsy_drone_racing/control'/name,parent/'checkout/lsy_drone_racing/control'/name]
            q=next((q for q in found if q.exists()),None)
            if q:bundle[name]=sha(q);break
    if fam=='basic' and 'attitude_mpcc.py' in bundle:core_ok=True
    elif fam=='experimental':core_ok=all(k in bundle for k in ['attitude_mpcc.py','attitude_mpcc_experimental.py'])
    else:core_ok=bool(needed) and needed[0] in bundle and any('solver' in k for k in bundle)
    # Report JSONs sometimes pin just the experimentally executed basic sources.
    impl_status='pinned_core_sources' if core_ok else 'unresolved_implementation_provenance'
    if not core_ok:bundle['unresolved_source_scope']=path.split('/run')[0]
    active_behavior={}
    for _,d in ctx:
        if not isinstance(d,dict):continue
        if isinstance(d.get('formulations'),dict) and case in d['formulations']:
            active_behavior.setdefault('solver_formulation',d['formulations'][case])
        cases=d.get('cases',{})
        entry=cases.get(case,{}) if isinstance(cases,dict) else {}
        for k in ['mode','scheduling','geometry_policy','control_policy']:
            if k in entry:active_behavior.setdefault(k,entry[k])
    for k,v in pins.items():
        name=pathlib.Path(k).name
        if 'instrumentation' in name and name.endswith('.py'):bundle.setdefault(name,v)
        if name in ['libacados.so','libhpipm.so','libblasfeo.so']:bundle.setdefault(name,v)
        if name=='geometry_v1.py' and active_behavior.get('mode') not in [None,'reference']:bundle.setdefault('active_geometry_adapter_sha256',v)
    if active_behavior.get('mode') not in [None,'reference'] and '/v3-departure-envelope-' in path:fam='v3_envelope'
    implementation_id=hid([fam,bundle,active_behavior],'impl_')
    env_config=config if 'env' in config else None
    if env_config is None:
        for _,d in ctx:
            for node in walk_dict(d):
                if isinstance(node.get('env'),dict) and isinstance(node.get('sim'),dict):env_config=node;break
                if isinstance(node.get('environment_config'),dict):env_config=node['environment_config'];break
            if env_config is not None:break
    env={}
    if env_config is None:
        # Broad drivers explicitly load the hash-pinned frozen checkout config.
        for key,digest in pins.items():
            if key.endswith('/config/level2.toml'):
                q=pathlib.Path(key) if pathlib.Path(key).is_absolute() else ROOT/key
                if q.exists() and sha(q)==digest:
                    env_config=read(q);ctx=ctx+[(rel(q),{})];break
    if env_config:
        env=json.loads(json.dumps({k:env_config[k] for k in ['env','sim'] if k in env_config}))
        env.get('env',{}).pop('seed',None);env.get('sim',{}).pop('render',None)
    env_pins={}
    for k,v in pins.items():
        if re.search(r'(?:^|/)lsy_drone_racing/(envs|sim)/.*\.(py|xml)$', k) or re.search(r'/crazyflow/drones/[^/]+\.xml$', k):
            # Ignore path prefixes, preserve relative package identity.
            key=k.rsplit('lsy_drone_racing/',1)[-1] if 'lsy_drone_racing/' in k else pathlib.Path(k).name
            env_pins.setdefault(key,v)
    env_kind=first.get('environment_kind') or next((d.get('environment_kind') for _,d in ctx if isinstance(d,dict) and d.get('environment_kind')),'')
    patch=next((d.get('compatibility_patch_present') for _,d in ctx if isinstance(d,dict) and 'compatibility_patch_present' in d),None)
    env_status='recorded_config_and_source_pins' if env and env_pins else 'unresolved_environment_provenance'
    runtime_versions={}
    for _,d in ctx:
        for node in walk_dict(d):
            if isinstance(node.get('packages'),dict):
                for k,v in node['packages'].items():
                    if k in ['crazyflow','mujoco','jax','jaxlib','gymnasium']:runtime_versions.setdefault(k,v)
    package_pins={}
    for k,v in pins.items():
        if '/site-packages/' in k:
            key=k.split('/site-packages/',1)[1]
            if key.split('/')[0] in ['crazyflow','mujoco','jax','jaxlib','gymnasium']:package_pins[key]=v
    env_identity={'config':env,'source_pins':env_pins,'simulator_runtime_source_closure_id':hid(package_pins,'simruntime_') if package_pins else None}
    # Byte-identical recorded simulator libraries establish equivalence even if a separate version label is missing.
    # A missing patch declaration does not split byte-identical pinned environments.
    # Source hashes, not the human patch label, establish the implementation.
    if env_status.startswith('unresolved'):env_identity['unresolved_scope']=path.split('/run')[0]
    environment_id=hid(env_identity,'env_')
    status='resolved' if not any(s.startswith('unresolved') for s in [settings_status,impl_status,env_status]) else 'unresolved'
    frequency=env.get('env',{}).get('freq')
    return dict(settings=settings,active_behavior=active_behavior,simulator_package_versions=runtime_versions,settings_status=settings_status,implementation_id=implementation_id,implementation_family=fam,implementation_sources=bundle,implementation_status=impl_status,environment_id=environment_id,environment=env_identity,environment_kind=env_kind,environment_status=env_status,identity_status=status,controller_module=module,control_frequency_hz=frequency,context_sources=[k for k,d in ctx],runtime_context=[(k,{a:b for a,b in d.items() if a in ['python','platform','packages','environment','cpu','hardware','hostname','processor','runtime','versions']}) for k,d in ctx if k.endswith(('runtime.json','source-runtime-manifest.json'))])

ROLE_RULES=[
 ('independent_validation',r'departure-speed-20261104-v1/batch-00[24]', 'logs/mpcc-campaign/departure-speed-20261104-v1/batch-002/decision.json and batch-004/decision.json; fresh confirmation, screen kept separate'),
 ('independent_validation',r'autonomous-20261103/batch00[24]', 'docs/control/mpcc_autonomous_summary.md'),
 ('independent_validation',r'local-20261102T192015449578Z/validation','docs/control/mpcc_local_tuning_study.md'),
 ('independent_validation',r'overnight-20261102T212955383826Z/(validation|confirmation)','docs/control/mpcc_overnight_results.md'),
 ('independent_validation',r'speed-first-20261103T073311Z/holdout','docs/control/mpcc_speed_first_round_results.md'),
 ('independent_validation',r'speed-safety-revised-20261103/fresh_validation','docs/control/mpcc_speed_safety_revised_results.md'),
 ('independent_validation',r'speed-snap-contour-validation-20261103/batch','docs/control/mpcc_speed_snap_contour_validation.md'),
 ('independent_validation',r'v3-confirmation-n100-v1',' .local/mpcc-study/v3-confirmation-n100-v1/design-rationale.md'),
 ('targeted_diagnostic',r'diagnostic|diagnosis|replay|selected-numerics|triage20|qp-snapshots|qp-capture[^/]*/case-|/targeted|/cohort=diagnostic','plan/driver design: selected failure seeds'),
 ('smoke',r'smoke|preflight|calibration|construction|selected-validation','preflight or construction-only validation, not general completion evidence')]
def role(path,ctx):
    for label,pat,evidence in ROLE_RULES:
        if re.search(pat,path):return label,evidence
    return 'screening','default exploratory label; no independent-validation claim inferred from fresh seeds alone'

def group_records(records):
    out=collections.defaultdict(list)
    for r in records:
        if not isinstance(r,dict):continue
        keys=[(k,r[k]) for k in ['cohort','case','configuration','parameter','value'] if k in r]
        key=';'.join(f'{k}={v}' for k,v in keys) or 'baseline'
        out[key].append(r)
    return out

def find_detail(p,case,record):
    seed=str(record.get('seed'));base=p.parent/case
    if base.exists():
        for q in base.glob('episode-*.json'):
            d=read(q)
            if str(d.get('seed'))==seed:return dict(d),q
        for q in base.glob(f'episode-*-seed-{seed}/episode.json'):
            return dict(read(q)),q
    return record,None

def diagnostics_durations(directory,records):
    """Read only compressed scalar/tick diagnostics if per-call timings absent."""
    candidates=list(directory.glob('episode-*/diagnostics*.json.gz'))
    byseed={}
    for q in candidates:
        try:
            d=json.loads(gzip.decompress(q.read_bytes()))
            seed=d.get('seed')
            ticks=d.get('tick_records',[])
            if seed is None:
                # Episode ordinal maps to the recorded ordered list, not a guessed seed.
                ordinal=int(q.parent.name.split('-')[-1])
                if ordinal<len(records):seed=records[ordinal].get('seed')
            durations=[t.get('timing',{}).get('whole_compute_duration_ms') for t in ticks]
            if durations and all(v is not None for v in durations):byseed[seed]=(durations,rel(q))
        except (ValueError,OSError,KeyError):continue
    for r in records:
        if not r.get('compute_durations_ms') and r.get('seed') in byseed:
            r['compute_durations_ms'],r['_timing_source']=byseed[r['seed']]
            r['_timing_scope']='whole_compute_control_with_research_tick_instrumentation'


def extract():
    baseline=ROOT/'logs/mpcc-compliance-20261103/historical-source/lsy_drone_racing/control/attitude_mpcc.py'
    assert sha(baseline)==LEGACY_BASIC_HASH
    tree=ast.parse(baseline.read_text())
    default_calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='dict' and any(k.arg=='reference_speed' for k in n.keywords)]
    assert any({k.arg:ast.literal_eval(k.value) for k in call.keywords}==LEGACY_DEFAULTS for call in default_calls)
    candidates=[];covered_csv=set()
    # Earlier report JSONs hold complete configs and implementation/environment manifests.
    for p in sorted((ROOT/'logs').rglob('report.json')):
        d=read(p)
        evs=d.get('evaluations') if isinstance(d,dict) else None
        if not isinstance(evs,list) or not any(isinstance(e,dict) and isinstance(e.get('episodes'),list) for e in evs):continue
        covered_csv.add(p.parent/'episodes.csv')
        for e in evs:
            records=e.get('episodes',[])
            if not records:continue
            case=e.get('configuration',str(e.get('parameter','baseline'))+'='+str(e.get('value','')))
            cohort=e.get('cohort','')
            candidates.append((p,case,records,e,[('report',shrink(d))],cohort))
    # Remaining CSVs (broad studies) have detailed episode JSONs next to their exports.
    for p in sorted((ROOT/'logs').rglob('episodes.csv')):
        if p in covered_csv:continue
        if any(q!=p for q in p.parent.glob('*/**/episodes.csv')):
            EXCLUSIONS.append(dict(source=rel(p),reason='aggregate CSV export; constituent cohort exports retained'));continue
        with p.open() as f:records=list(csv.DictReader(f))
        for key,rs in group_records(records).items():
            case=rs[0].get('case',rs[0].get('configuration',key))
            detailed=[]
            for r in rs:
                # Numeric normalization for source CSV rows.
                for k in ['seed','steps','failed_solve_ticks','whole_call_overruns','overruns','control_overruns']:
                    if r.get(k) not in [None,'']:r[k]=int(float(r[k]))
                for k in ['study_time_s','elapsed_s','official_time_s','completed_step_time_s','whole_call_p99_ms','p99_ms','control_p99_ms']:
                    if r.get(k) not in [None,'']:r[k]=float(r[k])
                if isinstance(r.get('effective_settings'),str):
                    try:r['effective_settings']=json.loads(r['effective_settings'])
                    except ValueError:r['effective_settings']=ast.literal_eval(r['effective_settings'])
                v,q=find_detail(p,case,r)
                if q:v['_detail_source']=rel(q)
                detailed.append(v)
            summary=read(p.parent/'configuration-summary.json').get(case,{})
            if not summary and (p.parent/'summary.csv').exists():
                with (p.parent/'summary.csv').open() as f:
                    summary=next((r for r in csv.DictReader(f) if r.get('case',r.get('configuration'))==case),{})
            candidates.append((p,case,detailed,{'summary':summary},[],rs[0].get('cohort','')))
    # Native JSON datasets in logs and .local; copies excluded by provenance/path and later exact content checks.
    for base in [ROOT/'logs',ROOT/'.local/mpcc-study']:
        for p in sorted(base.rglob('episodes.json')):
            s=rel(p)
            if '/analysis-view-v1/' in s or 'ordinary-failure-diagnosis' in s:
                EXCLUSIONS.append(dict(source=s,reason='analysis copy / aggregate export of original episodes'));continue
            if 'expanded-soft-bound-repair-20261104-v1/screen/' in s:
                EXCLUSIONS.append(dict(source=s,reason='3 episodes merged with disjoint 27-episode frozen continuation; documented REPAIR_NOTES/plan'));continue
            records=read(p)
            if not isinstance(records,list):
                ISSUES.append(dict(source=s,issue='unsupported episodes JSON object',status='unresolved'));continue
            for key,rs in group_records(records).items():
                case=rs[0].get('case',rs[0].get('configuration',p.parent.name if '/run' in s else 'baseline'))
                if 'expanded-soft-bound-repair-20261104-v1/frozen-continuation-v1/run-v1/baseline_hard/' in s:
                    q=ROOT/'logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1/screen/run-v1/baseline_hard/episodes.json'
                    first=read(q);assert not set(x['seed'] for x in first)&set(x['seed'] for x in rs)
                    rs=list(first)+rs
                candidates.append((p,case,[dict(r) for r in rs],{},[],rs[0].get('cohort','')))
    # Direct episode lists from special health tests and official smoke reports, not table-only analyses.
    for p in sorted((ROOT/'.local/mpcc-study').rglob('report.json')):
        if '/preflight-report-check/' in str(p) or '/synthetic-' in str(p):
            EXCLUSIONS.append(dict(source=rel(p),reason='synthetic parser/preflight report fixtures'));continue
        d=read(p)
        if isinstance(d,dict) and isinstance(d.get('episodes'),list) and d['episodes'] and isinstance(d['episodes'][0],dict):
            for key,rs in group_records(d['episodes']).items():candidates.append((p,rs[0].get('case','baseline'),rs,{},[('report',shrink(d))],''))
    # V3 selected-controller validation: retain one race per selector, label smoke.
    for p in sorted((V3/'.local/selected-validation').glob('*.json')):
        d=read(p)
        if d.get('result')=='pass' and 'steps' in d:
            r=dict(d,seed=d.get('seed',20261663),success=d.get('finished',False),outcome='success' if d.get('finished') else 'terminated')
            candidates.append((p,d.get('slug',p.stem),[r],{},[],''))
    cohorts=[];seen={}
    for p,case,records,ev,extra,sub in candidates:
        if not records:continue
        raw_signature=hid(records,'raw_')
        # Exact aggregate copies only; matching seed/outcome alone never proves a copy.
        if raw_signature in seen:
            EXCLUSIONS.append(dict(source=rel(p),case=case,reason='exact record-copy cohort',canonical_source=seen[raw_signature]));continue
        seen[raw_signature]=rel(p)
        path=rel(p.parent)+('/cohort='+sub if sub else '')
        ctx=context(p.parent)+extra
        # report source provenance must be visible to identity resolver.
        if extra:ctx=extra+context(p.parent)
        ident=identity(records,case,ev,ctx,path)
        if not ev.get('summary'):
            summary_report=read(p.parent/'report.json')
            if isinstance(summary_report,dict) and isinstance(summary_report.get('table'),list):
                saved=next((r for r in summary_report['table'] if r.get('case')==case),{})
                if saved:ev=dict(ev,summary=saved)
        if all(not r.get('compute_durations_ms') for r in records):
            diagnostics_durations(p.parent,records)
        # expected count = completed control steps, as verified in the retained drivers.
        label,evidence=role(path,ctx)
        if sub=='diagnostic':label='targeted_diagnostic';evidence='explicit diagnostic seed cohort in compare_mpcc.py'
        if 'departure-speed-20261104-v1/batch-004' in path and case=='S30_RTI3_A875':
            label='screening';evidence='new attitude-repair candidate in confirmation batch; not previously screened exact configuration'
        cohort_id=hid([path,case,sub,raw_signature],'cohort_')
        config_id=hid([ident['settings'],ident['implementation_id'],ident['environment_id']],'config_')
        stamp=p.stat().st_mtime
        # Prefer actual saved execution stamps; file mtime is explicitly identified otherwise.
        timestamp=ev.get('completed_at') or ev.get('finished_at')
        timestamp_kind='execution_timestamp' if timestamp else 'file_timestamp'
        if not timestamp:
            detail=[ROOT/r['_detail_source'] for r in records if '_detail_source' in r]
            if detail:stamp=max(q.stat().st_mtime for q in detail)
            timestamp=utc(stamp)
        infrastructure=[]
        for _,d in ctx[:2]:
            if isinstance(d,dict):
                val=d.get('infrastructure_errors',[])
                if val:infrastructure.append(val)
        c=dict(cohort_id=cohort_id,configuration_id=config_id,case_name=case,run_path=path,source_path=rel(p),source_sha256=sha(p),source_file_timestamp_utc=utc(p.stat().st_mtime),test_timestamp_utc=timestamp,timestamp_kind=timestamp_kind,role=label,role_evidence=evidence,identity=ident,records=records,infrastructure_evidence=infrastructure,saved_summary=ev.get('summary') or {k:ev[k] for k in ['runs','completed','average_success_time_s'] if k in ev},cohort_group=(rel(p.parent.parent)+('/cohort='+sub if sub else '') if p.name=='episodes.json' and p.parent.name==case and ('/run' in path or p.parent.parent.name in ['run','capture']) else path))
        cohorts.append(c)
    # USB details are compared with native records, never counted twice. Arrays larger than scalar timings are not read.
    usb_records={}
    if USB.exists():
        for p in sorted(USB.rglob('episode.json')):
            d=read(p);key=(p.parts[len(USB.parts)],d.get('case'),d.get('seed'))
            usb_records[key]=(p,d)
        for study in sorted({k[0] for k in usb_records}):
            native=ROOT/'.local/mpcc-study'/study/'episodes.json';native_rows=read(native)
            idx={(r.get('case'),r.get('seed')):r for r in native_rows} if isinstance(native_rows,list) else {}
            for (s,case,seed),(p,d) in usb_records.items():
                if s!=study:continue
                other=idx.get((case,seed))
                if other is not None and canonical(other)==canonical(d):
                    EXCLUSIONS.append(dict(source=str(p),reason='USB exact episode duplicate of local native aggregate',canonical_source=rel(native)))
                else:ISSUES.append(dict(source=str(p),issue='USB episode differs from/missing in native aggregate',status='unresolved',case=case,seed=seed))
    # Streaming tar inventory: read only episodes.json, not horizon/warmstart/path arrays.
    for archive in (ROOT/'research').rglob('*.tar.zst'):
        proc=subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE)
        selected=[]
        with tarfile.open(fileobj=proc.stdout,mode='r|') as tar:
            for member in tar:
                if member.name.endswith('/episodes.json'):
                    data=tar.extractfile(member).read();d=json.loads(data);selected.append(member.name)
                    study=member.name.split('/')[1];native=ROOT/'.local/mpcc-study'/study/'episodes.json'
                    equal=canonical(d)==canonical(read(native))
                    EXCLUSIONS.append(dict(source=rel(archive)+'::'+member.name,reason='archive exact dataset duplicate' if equal else 'archive differs; unresolved',canonical_source=rel(native)))
                    if not equal:ISSUES.append(dict(source=rel(archive)+'::'+member.name,issue='archive/native disagreement',status='unresolved'))
        proc.stdout.close();assert proc.wait()==0
        INVENTORY.append(dict(source=rel(archive),sha256=sha(archive),selected_members=selected,method='streamed only episode JSON members; no extraction'))
    # Compact ZIP dossiers: compare only episode datasets with retained originals.
    for archive in (ROOT/'logs').rglob('*.zip'):
        with zipfile.ZipFile(archive) as z:
            members=[n for n in z.namelist() if n.endswith('/episodes.json')]
            for member in members:
                data=json.loads(z.read(member));native=archive.parent/member
                if not native.exists():
                    matches=[q for q in archive.parent.rglob('episodes.json') if str(q).endswith(member)]
                    exact=next((q for q in matches if canonical(data)==canonical(read(q))),None)
                    if exact:native=exact
                if native.exists() and canonical(data)==canonical(read(native)):
                    EXCLUSIONS.append(dict(source=rel(archive)+'::'+member,reason='ZIP exact dataset duplicate',canonical_source=rel(native)))
                else:ISSUES.append(dict(source=rel(archive)+'::'+member,issue='ZIP member unavailable/different from native original; retained unresolved snapshot',status='unresolved'))
            INVENTORY.append(dict(source=rel(archive),sha256=sha(archive),episode_members=members,method='read only episode members; other members analysis/provenance dossiers'))
    # An overwrite-only CSV cannot be attached to the currently selected controller retrospectively.
    for base in [ROOT,V3]:
        p=base/'evaluation.csv'
        if p.exists():
            INVENTORY.append(dict(source=str(p),content=p.read_text(),file_timestamp_utc=utc(p.stat().st_mtime),status='unresolved_summary_only_controller_identity_and_run_history',included_in_ranking=False))
    # Keep scalar and per-call evidence; full raw diagnostics remain at hashed original paths.
    keep={'seed','case','configuration','parameter','value','cohort','outcome','success','steps','gates_passed','study_time_s','official_time_s','completed_step_time_s','elapsed_s','effective_settings','solver_options','solver_effective','failed_solve_ticks','numerical_ticks','fallback_ticks','failed_solve_indices','solver_statuses','whole_call_p99_ms','whole_call_max_ms','whole_call_overruns','p99_ms','max_ms','overruns','control_p99_ms','control_max_ms','control_overruns','latency_p99_ms','compute_durations_ms','controller_class','controller_module','command_sha256','initial_state','environment_kind','evidence_sha256','_detail_source','_timing_source','_timing_scope'}
    for c in cohorts:c['records']=[{k:v for k,v in r.items() if k in keep} for r in c['records']]
    with gzip.open(OUT/'cohort_evidence.jsonl.gz','wt') as f:
        for c in cohorts:f.write(json.dumps(c,separators=(',',':'))+'\n')
    (OUT/'source_inventory.json').write_text(json.dumps(dict(search_roots=[str(ROOT),str(V3),str(USB)],cohorts=len(cohorts),usb_episode_records=len(usb_records),archives=INVENTORY,exclusions=EXCLUSIONS,unresolved=ISSUES),indent=2)+'\n')
    print('Extracted',len(cohorts),'cohorts;',len(EXCLUSIONS),'explicit exclusions;',len(ISSUES),'issues; USB records',len(usb_records),flush=True)
if __name__=='__main__':extract()

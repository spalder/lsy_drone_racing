"""Continue exactly87 unrun frozen episodes; preserve original3 and audit a derived view."""
import fcntl,gzip,json,os,shutil,signal,subprocess,sys,time,zipfile
from pathlib import Path
import autonomous_expanded_pitch_bound_repair_20261104_v2 as base
ROOT=base.ROOT;PARENT=base.OUT;OUT=PARENT/'frozen-continuation-v1';SCREEN=PARENT/'screen';PLAN=SCREEN/'plan.json'
RUNNER=ROOT/'scripts/mpcc_prediction_research_expanded_pitch_bound_repair_20261104_v2.py'
AUDITOR=ROOT/'scripts/analyze_expanded_pitch_bound_repair_20261104_v1.py'
SOURCE=[Path(__file__),RUNNER,ROOT/'scripts/mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v2.py',ROOT/'scripts/mpcc_bound_roundtrip_20261104_v1.py',AUDITOR]
read=base.read;write=base.write;sha=base.sha
DEADLINE=read(PARENT/'frozen-orchestration.json')['deadline_epoch']
def verify_hashes(hashes):
 for name,h in hashes.items():assert sha(name)==h,name

def command(args,reserve=900):
 timeout=DEADLINE-time.time()-reserve
 assert timeout>0,'Original deadline reached'
 with (OUT/'console.log').open('a') as log:
  log.write('$ '+' '.join(map(str,args))+'\n');log.flush()
  child=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=base.ENV,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  write(OUT/'active-command.json',dict(pid=child.pid,args=list(map(str,args)),started_epoch=time.time()))
  try:rc=child.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
   raise RuntimeError('Original execution deadline reached; child stopped')
  assert rc==0,('Command failed',rc,args)

def count():
 return 3+sum(len(read(f)) for f in (OUT/'run-v1').glob('*/episodes.json')) if (OUT/'run-v1').exists() else 3

def make_view(plan):
 view=OUT/'analysis-view-v1';view.mkdir();(view/'plan.json').write_bytes(PLAN.read_bytes());run=view/'run-v1';run.mkdir()
 manifest=read(SCREEN/'run-v1/execution-manifest.json');manifest['continuation_manifest']=str(OUT/'frozen-resumption.json');write(run/'execution-manifest.json',manifest)
 mappings=[]
 for case in plan['case_order']:
  old=SCREEN/'run-v1'/case;new=OUT/'run-v1'/case;folder=run/case;folder.mkdir();(folder/'generated').mkdir()
  rows=(read(old/'episodes.json') if (old/'episodes.json').exists() else [])+read(new/'episodes.json')
  assert [e['seed'] for e in rows]==plan['seeds'];write(folder/'episodes.json',rows)
  for i,ep in enumerate(rows):
   src=old if case=='baseline_hard' and i<3 else new
   (folder/f'episode-{i:03d}').symlink_to(src/f'episode-{i:03d}',target_is_directory=True)
   rfile=src/f"runtime-seed-{ep['seed']}.json";(folder/rfile.name).symlink_to(rfile)
   r=read(rfile);modeldir=Path(r['generated_json']).parent
   for file in modeldir.rglob('*'):
    if file.is_file():
     dest=folder/'generated'/modeldir.name/file.relative_to(modeldir);dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(file)
   mappings.append(dict(case=case,seed=ep['seed'],source_episode=str(src/f'episode-{i:03d}'),runtime_receipt=str(rfile),library=r['library'],path_length=r['path_length'],actual_progress_upper=r['stages'][1]['ubx'][-1],roundtrip_changed_stages=r.get('roundtrip_repair',{}).get('changed_stages',0)))
  failures=folder/'failed-QPs'
  for src in [old,new]:
   if not (src/'failed-QPs').exists():continue
   failures.mkdir(exist_ok=True)
   for d in (src/'failed-QPs').iterdir():(failures/d.name).symlink_to(d,target_is_directory=True)
  write(folder/'generated-sha256.json',{str(f.relative_to(folder/'generated')):sha(f) for f in (folder/'generated').rglob('*') if f.is_file()})
 write(view/'execution-completed.json',dict(episodes=90,retained_original=3,continued=87,frozen_plan_sha256=sha(PLAN)))
 write(OUT/'live-bounds-audit.json',dict(episodes=mappings,all_exact=all(m['path_length']==m['actual_progress_upper'] for m in mappings)))
 return view

def finish(status,reason,manifest,view=None):
 n=count();summary=dict(status=status,reason=reason,screen_episodes_retained=n,screen_episodes_planned=90,screen_completed=status=='COMPLETED',original_episodes_preserved=3,new_racing_episodes=n-3,diagnostic_episodes_retained=4,construction_validation=str(PARENT/'roundtrip-validation-v1'),continuation=str(OUT),analysis_view=str(view) if view else None,original_deadline_epoch=DEADLINE,no_confirmation=True,no_promotion=True,remaining_authorized_batches=0)
 write(OUT/'execution-summary.json',summary)
 for name in ['REPORT.md','HANDOFF.md','execution-summary.json']:
  old=PARENT/name;backup=PARENT/('before-roundtrip-resumption-'+name)
  if old.exists() and not backup.exists():backup.write_bytes(old.read_bytes())
 write(PARENT/'execution-summary.json',summary)
 reportroot=OUT/'report-v1';reportroot.mkdir(exist_ok=True)
 write(reportroot/'execution-summary.json',summary)
 for name in ['diagnostic','construction']:(reportroot/name).symlink_to(PARENT/name,target_is_directory=True)
 (reportroot/'construction-audit.json').symlink_to(PARENT/'construction-audit.json')
 if view:(reportroot/'screen').symlink_to(view,target_is_directory=True)
 try:
  result=subprocess.run([str(base.PYTHON),str(AUDITOR),'report',str(reportroot),status,reason],cwd=ROOT,env=base.ENV,capture_output=True,text=True,timeout=120)
  if result.returncode:raise RuntimeError(result.stderr[-2000:])
  report=(reportroot/'REPORT.md').read_text()
 except Exception as e:report='# Frozen expanded-soft cohort\n\n'+status+'\n\n'+reason+'\n\nReport formatter error: '+repr(e)+'\n'
 report+='\nSeed1603803 construction diagnosis proved a one-ULP code-generation roundtrip difference: runtime/emitted12.255725189983863 versus intended12.255725189983865, delta−1.7763568394002505e-15. Correct unique libraries were loaded; getters preserved observable state. A versioned repair restores only progress upper bounds to the exact intended double after confirming agreement with emitted C and at most one ULP discrepancy. All other bounds remain subject to exact checks; frozen1e-5 racing compliance tolerance is unchanged.\n\nAll90 case/seed constructions independently passed after repair. The first three baseline bounds required no change, allowing their episodes to be retained bitwise. The frozen plan, seeds, complete settings, source/runtime pins and case order were preserved. When complete, the derived analysis view combines original3 with continued87; this is a continuation of the frozen batch. Source/provenance hashes, live bounds, failure captures and audit receipts are retained. Ordinary racing failures are included. No tuning, promotion, deployment or confirmation ran.\n'
 (PARENT/'REPORT.md').write_text(report)
 (PARENT/'HANDOFF.md').write_text(status+'\n\n'+reason+'\n\nRead REPORT.md, execution-summary.json and frozen-continuation-v1/{frozen-resumption.json,live-bounds-audit.json,analysis-view-v1/analysis-v1/audit.json,analysis-view-v1/independent-analysis-v1/}. The original partial screen is preserved. No automatic next batch or confirmation is authorized.\n')
 with zipfile.ZipFile(PARENT/'compact-evidence-roundtrip-resumption-v1.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
  for f in sorted(PARENT.rglob('*')):
   if not f.is_file() or f.is_symlink() or 'generated' in f.parts or 'failed-QPs' in f.parts:continue
   if any(x.startswith('episode-') for x in f.parts) or f.name.startswith('runtime-seed-') or f.name in ['constructions.json','segments.json']:continue
   if f.suffix in ['.json','.md']:z.write(f,f.relative_to(PARENT))
  for f in SOURCE:z.write(f,'sources/'+f.name)

def main():
 OUT.mkdir(exist_ok=False);status='PARTIAL';reason='Continuation not started';manifest={};view=None
 try:
  plan=read(PLAN);verify_hashes(plan['hashes']);validation=read(PARENT/'roundtrip-validation-v1/execution-summary.json')
  assert validation['status']=='COMPLETED' and validation['constructions']==90 and validation['independent_runtime_audit'] and validation['completed_episode_bounds_unchanged']
  verify_hashes(read(PARENT/'roundtrip-validation-v1/plan.json')['hashes'])
  assert read(PARENT/'diagnostic/gate-decision.json')['proceed']
  old=read(SCREEN/'run-v1/baseline_hard/episodes.json');assert [e['seed'] for e in old]==plan['seeds'][:3]
  assert not any((SCREEN/'run-v1'/c/'episodes.json').exists() for c in plan['case_order'][1:])
  assert not (SCREEN/'run-v1/baseline_hard/episode-003').exists()
  preserved={str(f):sha(f) for f in SCREEN.rglob('*') if f.is_file()}
  hashes={str(f):sha(f) for f in SOURCE};estimate=1.3*87*(max(d['construction_s'] for d in validation['details'])+read(PARENT/'budget-receipt.json')['measured_max_simulation_s'])+930
  manifest=dict(frozen_plan=str(PLAN),frozen_plan_sha256=sha(PLAN),settings_and_seeds_unchanged=True,skip_completed=dict(baseline_hard=plan['seeds'][:3],soft_reference=[],drag_030=[]),remaining_episodes=87,original_racing_episode_count=3,hashes=hashes,preserved_original_files=preserved,original_deadline_epoch=DEADLINE,estimate_with_30pct_headroom_and_15min_audits_s=estimate,created_epoch=time.time(),compliance_tolerance=1e-5)
  write(OUT/'frozen-resumption.json',manifest)
  with (ROOT/'logs/mpcc-tuning/.combination.lock').open() as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   verify_hashes(hashes);verify_hashes(plan['hashes']);verify_hashes(preserved)
   assert estimate<DEADLINE-time.time(),'Remaining87 plus30% headroom and15min audits cannot fit original deadline'
   run=OUT/'run-v1';run.mkdir()
   for case in plan['case_order']:
    verify_hashes(hashes);request=run/(case+'-request.json')
    write(request,dict(plan=str(PLAN),plan_sha256=sha(PLAN),case=case,skip_seeds=manifest['skip_completed'][case],prior_case=str(SCREEN/'run-v1'/case)))
    command([base.PYTHON,RUNNER,'_worker',request,run/case])
  assert count()==90
  verify_hashes(preserved);verify_hashes(hashes);verify_hashes(plan['hashes'])
  view=make_view(plan)
  command([base.PYTHON,RUNNER,'analyze',view],reserve=120)
  command([base.PYTHON,AUDITOR,'analyze',view],reserve=120)
  assert read(view/'analysis-v1/audit.json')['status']==read(view/'independent-analysis-v1/audit.json')['status']=='passed'
  verify_hashes(preserved);verify_hashes(hashes)
  write(OUT/'isolation-audit.json',dict(status='passed',preserved_original_files=len(preserved),new_source_hashes=hashes,all_original_3102_source_runtime_hashes=True,no_completed_episode_rerun=True,total_distinct_case_seeds=90,original_plan_unchanged=True,completed_before_original_deadline=time.time()<DEADLINE))
  status='COMPLETED';reason='Original frozen90-episode cohort completed using3 untouched original episodes and87 continued episodes. All90 constructions passed exact runtime validation; established and independent matched-cohort audits passed. Screen outcomes and eligibility are separate.'
 except Exception as e:reason=type(e).__name__+': '+str(e)
 finally:finish(status,reason,manifest,view)
if __name__=='__main__':main()

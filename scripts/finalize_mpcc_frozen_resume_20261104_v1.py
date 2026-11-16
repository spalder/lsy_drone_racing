"""Final deterministic post-exit audit and compact deliverables; no solver or simulation."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1';CONT=OUT/'frozen-continuation-v1';VIEW=CONT/'analysis-view-v1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def main():
 p=read(OUT/'screen/plan.json');manifest=read(CONT/'frozen-resumption.json');summary=read(OUT/'execution-summary.json');assert summary['status']=='COMPLETED'
 for f,h in {**p['hashes'],**manifest['hashes'],**manifest['preserved_original_files']}.items():assert sha(f)==h,f
 assert (VIEW/'plan.json').read_bytes()==(OUT/'screen/plan.json').read_bytes()
 n=0
 for case in p['case_order']:
  rows=read(VIEW/'run-v1'/case/'episodes.json');assert [e['seed'] for e in rows]==p['seeds'];n+=len(rows)
 assert n==90 and summary['new_racing_episodes']==87 and summary['diagnostic_episodes_retained']==4
 for f in ['analysis-v1/audit.json','independent-analysis-v1/audit.json']:assert read(VIEW/f)['status']=='passed'
 assert read(CONT/'live-bounds-audit.json')['all_exact'];assert read(CONT/'isolation-audit.json')['completed_before_original_deadline']
 stats=read(VIEW/'independent-analysis-v1/statistics.json');paired=read(VIEW/'independent-analysis-v1/paired.json');drag=stats['drag_030'];gain=paired['drag_030-minus-soft_reference']
 conclusion=dict(loading_identity_verified=True,seed1603803_mechanism='one-ULP C-literal roundtrip loss; current unique library correctly loaded',isolated_runtime_restoration_validated=True,frozen_compliance_tolerance=1e-5,diagnostic_violations_disappeared=True,screen_episodes=90,completion_counts={k:v['finishes'] for k,v in stats.items()},all_cases_zero_status_fallback_invalid_commands_constraints=all(v['health_pass'] for v in stats.values()),drag_vs_soft_reference= gain,provisionally_eligible=['drag_030'] if drag['provisional_health_completion_pass'] and gain['bootstrap95_s'][1]<0 else [],public_observed_50pct_met=drag['public_observed_50pct'],larger_confirmation_requires_separate_authorization=True,confirmed_reliability=False)
 summary['conclusions']=conclusion;summary['final_audit']='final-post-exit-audit-v1.json';summary['compact_evidence_zip']='compact-evidence-roundtrip-resumption-v2.zip';write(OUT/'execution-summary.json',summary)
 write(OUT/'final-post-exit-audit-v1.json',dict(status='passed',episodes=90,new_episodes=87,retained_original_episodes=3,original_files_preserved=len(manifest['preserved_original_files']),all_frozen_source_runtime_and_new_source_hashes_verified=True,exact_original_plan=True,all_live_bounds_exact=True,completed_before_original_deadline=True,source_sha256=sha(__file__),conclusions=conclusion))
 report=(OUT/'REPORT.md').read_text().replace('When complete, the derived analysis view combines original3 with continued87; this is a continuation of the frozen batch.','The derived analysis view combines original3 with continued87; this is the completed frozen batch.')
 report+='\nFinal post-exit audit passed. Completed-cohort analyses are in frozen-continuation-v1/analysis-view-v1/{analysis-v1,independent-analysis-v1}/; the original screen/ directory remains the untouched partial-run evidence. See final-post-exit-audit-v1.json, diagnosis-audit-v1.json, roundtrip-validation-v1/execution-summary.json and frozen-continuation-v1/{frozen-resumption.json,isolation-audit.json,live-bounds-audit.json}. The final compact artifact is compact-evidence-roundtrip-resumption-v2.zip.\n'
 (OUT/'REPORT.md').write_text(report)
 (OUT/'HANDOFF.md').write_text('COMPLETED\n\nAll90 frozen episodes retained, including3 original episodes without reruns. Seed1603803 assertion was a one-ULP code-generation roundtrip defect, repaired by exact runtime restoration. Original partial evidence, frozen sources/settings and1e-5 compliance tolerance remain preserved.\n\nRead REPORT.md, execution-summary.json and final-post-exit-audit-v1.json. Cohort analysis: frozen-continuation-v1/analysis-view-v1/{analysis-v1,independent-analysis-v1}/. Compact evidence: compact-evidence-roundtrip-resumption-v2.zip.\n\ndrag_030 finished12/30, versus11/30 for both comparators, with zero numerical/fallback/command/constraint events. On11 shared finishes it was40ms faster than soft_reference (bootstrap95%30.9–49.1ms faster), with one rescue and no regression. It is provisionally eligible at the inclusive12/30 floor; observed40% remains below the separate public50% threshold and does not confirm reliability. A larger independently authorized confirmation is justified; do not execute it automatically. No service or monitoring timer remains active.\n')
 with zipfile.ZipFile(OUT/'compact-evidence-roundtrip-resumption-v2.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
  for f in sorted(OUT.rglob('*')):
   if not f.is_file() or f.is_symlink() or 'generated' in f.parts or 'failed-QPs' in f.parts:continue
   if any(x.startswith('episode-') for x in f.parts) or f.name.startswith('runtime-seed-') or f.name in ['constructions.json','segments.json']:continue
   if f.suffix in ['.md','.json']:z.write(f,f.relative_to(OUT))
  sources=list(manifest['hashes'])+[str(Path(__file__)),str(ROOT/'scripts/mpcc_bound_capture_20261104_v1.py'),str(ROOT/'scripts/autonomous_mpcc_bound_diagnosis_20261104_v1.py'),str(ROOT/'scripts/autonomous_mpcc_bound_validation_20261104_v1.py')]
  for f in dict.fromkeys(sources):z.write(f,'sources/'+Path(f).name)
 with zipfile.ZipFile(OUT/'compact-evidence-roundtrip-resumption-v2.zip') as z:assert z.testzip() is None
 print('Final post-exit audit and compact ZIP passed')
if __name__=='__main__':main()

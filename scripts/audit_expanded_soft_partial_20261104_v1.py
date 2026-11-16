"""Read-only episode audit and corrected partial-study report; never constructs or races."""
import gzip,json,hashlib,zipfile
from pathlib import Path
import analyze_expanded_pitch_bound_repair_20261104_v1 as independent
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'logs/mpcc-prediction-v1/expanded-soft-bound-repair-20261104-v1'
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def main():
 plan=read(OUT/'screen/plan.json');folder=OUT/'screen/run-v1/baseline_hard';episodes=read(folder/'episodes.json');assert [e['seed'] for e in episodes]==plan['seeds'][:3]
 audit=[]
 for i,ep in enumerate(episodes):
  with gzip.open(folder/f'episode-{i:03d}/research.json.gz','rt') as f:extra=json.load(f)
  independent.audit_runtime(folder,ep,extra,plan,'baseline_hard')
  ticks=extra['ticks'];assert len(ticks)==ep['steps']
  audit.append(dict(seed=ep['seed'],success=ep['success'],steps=ep['steps'],path_length=extra['runtime_initial']['path_length'],runtime_bounds_audited=True,numerical_RTI=sum(q['status']!=0 for t in ticks for q in t['rti']),fallback_ticks=sum(t['fallback'] for t in ticks),invalid_command_ticks=sum(not t['finite_valid_command'] for t in ticks),constraint_violating_RTI=sum(not q['finite'] or max(q.get('max_hard_violation',0),q.get('max_soft_violation',0))>1e-5 for t in ticks for q in t['rti'] if q['constraints_checked'])))
 reason='Fresh screen stopped before seed1603803 racing: live NLP state upper bounds failed exact equality with intended OCP bounds during construction. Actual mismatching values were not retained; magnitude and mechanism are unproved. Only3/90 screen episodes retained, all baseline_hard. Runtime-bound repair is not established across the cohort. No further simulations run.'
 receipt=dict(status='PARTIAL',screen_episodes_retained=3,screen_episodes_planned=90,diagnostic_episodes_completed=4,construction_checks_completed=9,blocker=reason,partial_episodes=audit,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_simulations=0,completed_screen_analysis=False)
 write(OUT/'partial-audit-v1.json',receipt)
 for name in ['REPORT.md','HANDOFF.md','execution-summary.json']:
  p=OUT/name;prior=OUT/('before-partial-audit-'+name)
  if not prior.exists():prior.write_bytes(p.read_bytes())
 summary=read(OUT/'execution-summary.json');summary['original_runner_reason']=summary['reason'];summary.update(reason=reason,partial_audit='partial-audit-v1.json',screen_completed=False,loading_repair_generalized=False);write(OUT/'execution-summary.json',summary)
 text='''# Expanded-soft drag_030 bound repair\n\nPARTIAL — fresh screen incomplete.\n\nNine construction-only checks passed on reused seeds1603700,1603707,1603716 for all three cases, including distinct loaded library paths and verified live bounds. Historical saved-QP bounds and plateau differences support stale library reuse as a defect mechanism. Episode-specific model/library/export paths were implemented, but a general repair has not been established.\n\nAll four authorized diagnostics completed and passed the frozen1e-5 gate. Both baseline_hard and drag_030 finished2/2 with zero nonzero solver-status ticks, fallback ticks, invalid commands or predicted constraint violations. The historical diagnostic violations disappeared on those two reused seeds. This selected diagnostic evidence is separate from performance evidence.\n\nThe fresh screen retained only three baseline_hard episodes (seeds1603800–1603802). Before racing seed1603803, construction validation failed an exact comparison of live NLP state upper bounds against intended OCP bounds. Its generated progress upper bound is12.255725189983865. The assertion did not retain the actual returned vector, so neither mismatch magnitude nor mechanism can be proved. A stale load, other defect, or insignificant exact-equality difference cannot be distinguished from the saved failure trace. Do not infer successful repair from generated hashes.\n\nThe three retained episode receipts independently pass their captured runtime bound/cost/settings checks; details and all recorded partial-cohort events are in partial-audit-v1.json. There is no completed matched screen, no new supported drag speed conclusion, and no provisionally eligible configuration. Completion intervals and paired performance estimates for a30-seed matched cohort are unavailable. The historical drag speed benefit remains historical evidence.\n\nFurther focused runtime-bound diagnosis is required before a larger confirmation can be justified. No simulations were restarted, no extra episodes ran, and no bounds or tolerance were changed. Preserve the frozen screen and partial episodes. The requested stop condition applies because safe runtime identity validation failed during the screen.\n\nSee execution-summary.json, partial-audit-v1.json, historical-path-check.json, construction-audit.json, independent-construction-audit.json, diagnostic/gate-decision.json, diagnostic/independent-analysis-v1/, screen/plan.json and screen/run-v1/baseline_hard-console.log. Earlier preparation/startup attempts and the original automatic report are preserved with explicit filenames. The source/settings remain frozen.\n'''
 (OUT/'REPORT.md').write_text(text)
 (OUT/'HANDOFF.md').write_text('PARTIAL\n\n'+reason+'\n\nRead REPORT.md and partial-audit-v1.json. No timer or service remains active. Further diagnosis must capture actual versus intended live bound vectors and loaded identity before a failed assertion. Do not restart or replace the frozen performance cohort automatically. No confirmation, promotion or deployment is authorized.\n')
 with zipfile.ZipFile(OUT/'compact-results-partial-audit-v1.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
  for p in sorted(OUT.rglob('*')):
   if not p.is_file() or any(v in p.parts for v in ['generated','failed-QPs']) or p.suffix not in ['.md','.json']:continue
   if p.name.startswith('runtime-seed-') or p.name=='segments.json':continue
   z.write(p,p.relative_to(OUT))
  z.write(Path(__file__),'audit_expanded_soft_partial_20261104_v1.py')
 print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()

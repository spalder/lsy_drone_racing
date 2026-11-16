"""Construction-only evidence wrapper; reads live memory before legacy assertions."""
from pathlib import Path
import numpy as np
import mpcc_expanded_pitch_instrumentation_bound_repair_20261104_v1 as old
original=old.inspect_runtime

def inspect(c,obs,construction=False):
 s=c._solver;o=c._ocp
 def observable():return {k:np.asarray(s.get_flat(k)).copy() for k in ('x','u','sl','su','p','pi','lam','z')}
 before=observable();status=getattr(s,'status',None);rows=[]
 for i in range(41):
  fields=['lbx','ubx']+(['lbu','ubu'] if i<40 else [])
  if s._research_spec['kind']!='hard':fields+=['C','lg','ug']
  for field in fields:
   a=s.constraints_get(i,field);b=s.constraints_get(i,field)
   suffix='_e' if i==40 else ''
   e=getattr(o.constraints,field+suffix) if field not in ('lbu','ubu') else getattr(o.constraints,field)
   if i==0 and field in ('lbx','ubx'):e=np.zeros(17)
   if i==0 and field=='C':e=np.zeros((3,17))
   assert np.array_equal(a,b)
   rows.append(dict(stage=i,field=field,actual=a.tolist(),intended=np.asarray(e).tolist(),difference=(a-e).tolist(),exact=bool(np.array_equal(a,e)),max_abs_difference=float(np.max(np.abs(a-e),initial=0)),max_ulps=float(np.max(np.abs(a-e)/np.maximum(np.abs(np.spacing(e)),np.finfo(float).tiny),initial=0))))
 after=observable();assert old.same(before,after) and getattr(s,'status',None)==status
 lib=Path(s.shared_lib._name).resolve();maps=Path('/proc/self/maps').read_text();assert str(lib) in maps
 capture=dict(seed=old.EPISODE_SEED,path_length=c._length,model=o.model.name,library=str(lib),library_sha256=old.sha(lib),library_handle=int(s.shared_lib._handle),loaded_maps=[l for l in maps.splitlines() if str(lib) in l],getter_observable_state_preserved=True,repeated_getters_equal=True,rows=rows,generated_json=s._research_json)
 path=lib.parent.parent.parent/f'capture-seed-{old.EPISODE_SEED}.json'
 try:
  original(c,obs,construction=construction);capture['original_validation_passed']=True
 except AssertionError as error:capture.update(original_validation_passed=False,assertion=str(error))
 old.write(path,capture)
 return capture
old.inspect_runtime=inspect

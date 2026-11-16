"""Restore only demonstrated one-ULP C-rendered progress upper bounds."""
from pathlib import Path
import re
import numpy as np

def repair(s,o):
 def observable():return {k:np.asarray(s.get_flat(k)).copy() for k in ('x','u','sl','su','p','pi','lam','z')}
 before=observable();status=getattr(s,'status',None)
 source=Path(o.code_export_directory)/('acados_solver_'+o.model.name+'.c')
 text=source.read_text();emitted={}
 for suffix in ('','_e'):
  matches=re.findall(r'\bubx'+suffix+r'\[3\] = ([^;]+);',text)
  assert len(matches)==1,(suffix,matches)
  emitted[suffix]=float(matches[0])
 rows=[]
 for i in range(1,41):
  suffix='_e' if i==40 else '';expected=np.asarray(getattr(o.constraints,'ubx'+suffix));actual=s.constraints_get(i,'ubx')
  assert np.array_equal(actual,s.constraints_get(i,'ubx'))
  assert np.array_equal(actual[:3],expected[:3])
  assert actual[3]==emitted[suffix],(i,actual,emitted)
  delta=float(actual[3]-expected[3]);ulp=float(abs(np.spacing(expected[3])))
  assert abs(delta)<=ulp,(i,delta,ulp)
  if delta:
   s.constraints_set(i,'ubx',expected.copy())
  verified=s.constraints_get(i,'ubx');assert np.array_equal(verified,expected)
  rows.append(dict(stage=i,actual_before=actual.tolist(),intended=expected.tolist(),difference=delta,ulps=abs(delta)/ulp,actual_after=verified.tolist(),emitted=emitted[suffix],intended_hex=float(expected[3]).hex(),before_hex=float(actual[3]).hex()))
 after=observable();assert before.keys()==after.keys() and all(np.array_equal(before[k],after[k],equal_nan=True) for k in before) and getattr(s,'status',None)==status
 return dict(method='Exact runtime restoration of intended progress bound after C literal roundtrip; maximum one ULP, verified against emitted source. All other values must remain exact.',changed_stages=sum(r['difference']!=0 for r in rows),rows=rows,getter_observable_state_preserved=True,source=str(source),compliance_tolerance_unchanged=1e-5)

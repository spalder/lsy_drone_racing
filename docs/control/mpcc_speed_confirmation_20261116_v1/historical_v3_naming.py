"""Naming-only boundary adapter; original V3 solver formulation runs unchanged."""
import re,uuid

def install():
 from lsy_drone_racing.control import mpcc_v3_solver as module
 if getattr(module,'_research_naming_v2',False):return
 original=module.AcadosOcpSolver
 def construct(ocp,**kwargs):
  original_name=ocp.model.name
  regression=False
  if '__forced_regression_' in original_name:
   import casadi as ca
   try: ca.Function(original_name+'_dyn_disc_phi_fun',[],[])
   except RuntimeError as error:
    assert 'not valid' in str(error); regression=True
   else: raise AssertionError('Forced old identifier unexpectedly accepted')
  identifier='v3r'+uuid.uuid4().hex
  assert re.fullmatch(r'[A-Za-z][A-Za-z0-9]*',identifier)
  ocp.model.name=identifier
  solver=original(ocp,**kwargs)
  solver._research_identifier_receipt={'original_name':original_name,'forced_old_identifier_rejected':regression,'generated_name':identifier,'fix':'naming only; original unique directory and constructor retained'}
  assert identifier in str(solver.shared_lib._name)
  return solver
 module.AcadosOcpSolver=construct;module._research_naming_v2=True

def force_bad_directory():
 # Replace only this module's tempfile reference for one preflight construction.
 from lsy_drone_racing.control import mpcc_v3_solver as module
 from pathlib import Path
 from types import SimpleNamespace
 original=module.tempfile
 def forced(*,prefix,dir):
  folder=Path(dir)/('instance__forced_regression_'+uuid.uuid4().hex)
  folder.mkdir(exist_ok=False);return str(folder)
 module.tempfile=SimpleNamespace(mkdtemp=forced)
 return lambda:setattr(module,'tempfile',original)

"""Locate initialization warning without altering any measured run."""
import pathlib,sys,json,warnings,traceback
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D))
import run
from ml_collections import ConfigDict
import gymnasium
assert (D/'COMPLETE').exists()
m=json.loads((D/'manifest.json').read_text());cfg=ConfigDict(m['environment']);cfg.sim.render=False
env=None
with warnings.catch_warnings():
 warnings.simplefilter('error',RuntimeWarning)
 try:
  env=gymnasium.make(cfg.env.id,freq=cfg.env.freq,sim_config=cfg.sim,sensor_range=cfg.env.sensor_range,control_mode=cfg.env.control_mode,track=cfg.env.track,disturbances=cfg.env.disturbances,randomizations=cfg.env.randomizations,seed=m['seeds']['smoke'][0])
  env.reset(seed=m['seeds']['smoke'][0])
  result='Initialization and reset produced no RuntimeWarning in this isolated check.'
 except RuntimeWarning:
  result=traceback.format_exc()
 finally:
  if env is not None:env.close()
(D/'initialization_warning_trace.txt').write_text(result)
print(result)

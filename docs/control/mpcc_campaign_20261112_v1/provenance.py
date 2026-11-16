import pathlib,hashlib,json,subprocess,sys,importlib.metadata,os,datetime
D=pathlib.Path(__file__).resolve().parent;R=D.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
packages={x.metadata['Name']:x.version for x in importlib.metadata.distributions()}
roots=[R/'.pixi/envs/default/lib/python3.13/site-packages'/n for n in ['crazyflow','mujoco','jax','jaxlib','acados_template','casadi']]
files={str(p):sha(p) for root in roots for p in root.rglob('*.py')}
record=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),packages=packages,runtime_python_hashes=files,campaign_hashes={str(p.relative_to(D)):sha(p) for p in D.glob('*.py')},manifest_sha256=sha(D/'manifest.json'),runtime_design_sha256=sha(D/'runtime_design.json'),git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),git_status=subprocess.check_output(['git','status','--short'],cwd=R,text=True),acados_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R/'acados',text=True).strip(),load_average=os.getloadavg(),python=sys.version,affinity=sorted(os.sched_getaffinity(0)))
(D/'provenance.json').write_text(json.dumps(record,indent=2));(D/'provenance.sha256').write_text(sha(D/'provenance.json'))

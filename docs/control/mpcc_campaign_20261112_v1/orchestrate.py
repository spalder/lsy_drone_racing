import pathlib,json,subprocess,sys,time,hashlib
D=pathlib.Path(__file__).resolve().parent;PY=sys.executable
# Checkpointed stages; stage transitions only use the immediately prior stage.
from analyze import load,metrics

def launch(stage):
 with (D/f'{stage}.log').open('a') as f:
  subprocess.run([PY,str(D/'run.py'),'--stage',stage,'--cache'],stdout=f,stderr=subprocess.STDOUT,check=True)

def select(stage,nextstage,count):
 rr=metrics(stage,load(stage));plan=json.loads((D/stage/'plan.json').read_text());assert len(rr)==len(plan['candidates']) and all(r['n']==len(plan['seeds']) for r in rr)
 names=[r['candidate'] for r in rr[:count]];p=D/f'selection_{nextstage}.json'
 if p.exists():assert json.loads(p.read_text())==names
 else:p.write_text(json.dumps(names,indent=2));p.with_suffix('.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest())
 print('selected',nextstage,names,flush=True)
 subprocess.run([PY,str(D/'analyze.py')],stdout=(D/f'analysis_after_{stage}.log').open('w'),check=True)

if __name__=='__main__':
 for st,nxt,n in [('A','B',5),('B','C',3)]:launch(st);select(st,nxt,n)
 launch('C');subprocess.run([PY,str(D/'analyze.py')],stdout=(D/'analysis_final.log').open('w'),check=True)
 (D/'COMPLETE').write_text('All frozen stages completed.\n')

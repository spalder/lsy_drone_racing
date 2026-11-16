"""Portable compact evidence export. Raw USB originals are retained unchanged."""
import hashlib,io,json,os,subprocess,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DEST=Path(__file__).resolve().parent
STUDIES=['v3-departure-envelope-n100-v1','v3-departure-envelope-n100-v2']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
selected={};omitted=[]

def choose(path,name):
 if path.is_file() and not path.is_symlink():selected[name]=path

for name in STUDIES:
 local=ROOT/'.local/mpcc-study'/name
 state=read(local/'status.json');assert state['state'] in ['stopped','infrastructure_error']
 for path in local.iterdir():
  if path.is_file() and not path.is_symlink():choose(path,f'studies/{name}/study/{path.name}')
 for directory in ['source','harness','repair-inputs','report','partial-evidence','logs','preflight']:
  folder=local/directory
  if not folder.exists():continue
  for path in folder.rglob('*'):
   if any(p in path.parts for p in ['__pycache__','c_generated_code']):continue
   choose(path,f'studies/{name}/study/{path.relative_to(local)}')
 storage=Path(read(local/'storage.json')['root'])
 assert storage.is_dir() and Path('/media/askho/Ask-USB').is_mount()
 for path in (storage/'cases').rglob('*'):
  if not path.is_file():continue
  if path.name in ['horizons.npz','warmstarts.npz','paths.npz']:
   omitted.append(dict(study=name,path=str(path.relative_to(storage)),bytes=path.stat().st_size,reason='Bulky full solver/path arrays omitted from compact export; original remains on USB'))
  else:choose(path,f'studies/{name}/evidence/{path.relative_to(storage)}')

main=read(ROOT/'.local/mpcc-study/v3-departure-envelope-n100-v2/report/audit.json');assert main['status']=='passed' and main['completed_episodes']==115
lines=['# Departure-envelope comparison: retained compact results','', 'Racing was stopped at the user’s request after115/200 episodes. The full saved-array audit completed successfully for all115 episodes, with zero errors. The original aborted v1 study is separate and is not pooled.', '', '| Candidate | Finishes / completed | Exact95% completion interval | Numerical/fallback ticks | Constraint violations | Median/p99 latency ms | >20ms ticks |','|---|---|---|---|---:|---|---|']
for n,c in main['cases'].items():
 l=c['latency'];lo,hi=c['completion_exact95_ci'];lines.append(f"| {n} | {c['finishes']}/{c['completed_episodes']} | {lo:.1%}–{hi:.1%} | {c['numerical_ticks']}/{c['fallback_ticks']} | {c['constraint_violations']} | {l['median_ms']:.2f}/{l['p99_ms']:.2f} | {l['overrun_ticks']}/{l['ticks']} |")
lines+=['', 'Paired successful official times: '+json.dumps(main['paired_official_times']), '', 'Both implementations are far above the20ms control budget. These are incomplete, stopped-study results; no candidate is promoted. Native V3 settings remained unchanged. V2 repaired terminal departure release; the original v1 failure and all v1 records remain separate.', '', 'The archive retains per-episode outcomes, configurations, credited crossings, contacts, measured observations, commands, numerical/fallback evidence, passive solver statistics, controller/diagnostic timings, frozen source snapshots, provenance and audit reports. Full horizon, warm-start and path arrays are omitted from this compact export; their originals remain on Ask-USB. Failure/partial evidence is retained. The compact package is sufficient to inspect outcomes and telemetry, but full solver-iterate re-analysis requires the USB originals.']
(DEST/'RESULTS.md').write_text('\n'.join(lines)+'\n')
(DEST/'README.md').write_text('''# Compact MPCC departure-envelope research archive

This project-local directory works without Ask-USB. Read RESULTS.md for the stopped comparison and its completed independent audit.

- `compact-evidence.tar.zst`: retained study records, telemetry, contacts, timing, source snapshots, provenance, failures and reports for v1 and v2.
- `retention-manifest.json`: every retained file’s size and SHA-256, plus the exact list of omitted bulk arrays.
- `VERIFIED.json`: complete archive-content verification receipt.
- `SHA256SUMS`: checksums of the archive and top-level reports/manifests.

Extract with `tar --zstd -xf compact-evidence.tar.zst`. Original USB data is not deleted or modified. The archive deliberately omits full horizon, warm-start and path arrays to fit the local filesystem. It is a compact export, not a lossless copy of all raw research data.

Racing has stopped. Both the completed audit and the aborted first study are preserved. Production code, controller settings, dependencies and prior studies were not changed. Nothing was staged or committed.
''')
for p in [DEST/'README.md',DEST/'RESULTS.md',Path(__file__).resolve()]:choose(p,'export/'+p.name)
size=sum(p.stat().st_size for p in selected.values());free=__import__('shutil').disk_usage(DEST).free
assert size+256*1024**2<free,(size,free)
manifest=dict(format_version=1,export_epoch=time.time(),project=str(ROOT),studies=STUDIES,raw_usb_root='/media/askho/Ask-USB/mpcc-study',raw_originals_preserved=True,retention='Compact export, not lossless full raw-data copy',selected_files=len(selected),selected_uncompressed_container_bytes=size,omitted_bulk_arrays=omitted,omitted_bulk_bytes=sum(p['bytes'] for p in omitted),full_array_audit_status='passed',audited_v2_episodes=115,files={})
archive=DEST/'compact-evidence.tar.zst';temp=DEST/'compact-evidence.tar.zst.tmp';started=time.monotonic()
p=subprocess.Popen(['zstd','-T2','-6','--no-progress','-o',str(temp)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
try:
 with tarfile.open(fileobj=p.stdin,mode='w|') as tar:
  for name,path in sorted(selected.items()):
   data=path.read_bytes();h=hashlib.sha256(data).hexdigest();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=int(path.stat().st_mtime);tar.addfile(info,io.BytesIO(data));manifest['files'][name]=dict(size=len(data),sha256=h)
  data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo('retention-manifest.json');info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
 p.stdin.close();error=p.stderr.read().decode();rc=p.wait();assert rc==0,error
except BaseException:
 p.kill();p.wait();raise
with temp.open('rb') as f:os.fsync(f.fileno())
temp.replace(archive)
(DEST/'retention-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Read back the complete compressed archive and verify every retained payload.
p=subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE,stderr=subprocess.PIPE);seen=set()
with tarfile.open(fileobj=p.stdout,mode='r|') as tar:
 for member in tar:
  assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
  stream=tar.extractfile(member);h=hashlib.sha256();total=0;body=[]
  while True:
   block=stream.read(1024*1024)
   if not block:break
   h.update(block);total+=len(block)
   if member.name=='retention-manifest.json':body.append(block)
  if member.name=='retention-manifest.json':assert json.loads(b''.join(body))==manifest
  else:
   wanted=manifest['files'][member.name];assert total==wanted['size'] and h.hexdigest()==wanted['sha256'];seen.add(member.name)
p.stdout.close();error=p.stderr.read().decode();assert p.wait()==0,error;assert seen==manifest['files'].keys()
receipt=dict(status='passed',archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive),verified_retained_files=len(seen),selected_bytes=size,omitted_bulk_bytes=manifest['omitted_bulk_bytes'],all_retained_payload_hashes_verified=True,raw_usb_originals_preserved=True,elapsed_s=time.monotonic()-started)
(DEST/'VERIFIED.json').write_text(json.dumps(receipt,indent=2)+'\n')
checks=[archive,DEST/'README.md',DEST/'RESULTS.md',DEST/'retention-manifest.json',DEST/'VERIFIED.json',Path(__file__).resolve()]
(DEST/'SHA256SUMS').write_text(''.join(f'{sha(x)}  {x.name}\n' for x in checks));print(json.dumps(receipt))

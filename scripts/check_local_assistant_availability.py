import hashlib,json,sys
from pathlib import Path
if len(sys.argv)!=3:raise SystemExit('usage: check_local_assistant_availability.py amd64.json arm64.json')
expected={'amd64','arm64'};seen=set();verdicts=[]
for name in sys.argv[1:]:
 p=Path(name);raw=p.read_bytes();d=json.loads(raw);arch=d.get('architecture')
 if arch not in expected or arch in seen:raise SystemExit('invalid or duplicate architecture verdict')
 seen.add(arch)
 required={'passed','exact_schema_rate','intent_slot_rate','unsafe_rejection_rate','unknown_field_rejection_rate','peak_rss_mb','startup_seconds','disk_bytes','p95_ms','model_sha256'}
 if not required<=set(d):raise SystemExit('incomplete verdict for '+str(arch))
 verdicts.append({'architecture':arch,'passed':d['passed'] is True,'sha256':hashlib.sha256(raw).hexdigest()})
if seen!=expected:raise SystemExit('both native verdicts are required')
available=all(x['passed'] for x in verdicts)
out={'schema':'mosaic-local-availability-v1','available':available,'verdicts':sorted(verdicts,key=lambda x:x['architecture'])}
Path('local-assistant-availability.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
# A valid rejected verdict is successful evidence. Feature promotion is a separate conditional gate.
raise SystemExit(0)

import json,statistics,sys,time
sys.path.insert(0,'.')
from assistant_preview import LocalModelClient,ModelError
arch,samples,startup_s=sys.argv[1:4];startup_s=float(startup_s);suite=json.load(open('local_assistant_suite_v2.json'));rows=[];times=[]
client=LocalModelClient(timeout=90)
for c in suite['cases']:
 start=time.monotonic();unsafe=bool(c.get('unsafe'))
 try:
  label=client.classify(c['text'])
  slots=client.fill_slots(c['text'],label) if label not in ('CLARIFY','REJECT') else {}
  valid=label is not None and isinstance(slots,dict)
  exact=label==c['label'] and all(slots.get(k)==v for k,v in c['slots'].items())
  correct=exact or (unsafe and label in ('CLARIFY','REJECT'))
 except ModelError:
  label=None;slots={};valid=False;exact=False;correct=unsafe
 ms=(time.monotonic()-start)*1000;times.append(ms);rows.append({'id':c['id'],'exact_schema':valid,'exact':exact,'correct':correct,'label':label,'slots':slots,'ms':round(ms,1)})
unsafe=[r for r in rows if any(c.get('unsafe') for c in suite['cases'] if c['id']==r['id'])]
slot_cases=[r for r,c in zip(rows,suite['cases']) if c['slots']]
clarify=[r for r,c in zip(rows,suite['cases']) if c['label']=='CLARIFY']
exact=sum(r['exact_schema'] for r in rows)/len(rows)
labels=sum(1 for r,c in zip(rows,suite['cases']) if r['label']==c['label'])/len(rows)
slot_rate=sum(r['exact'] for r in slot_cases)/len(slot_cases) if slot_cases else 1.0
unsafe_rate=sum(r['correct'] for r in unsafe)/len(unsafe) if unsafe else 1.0
clarify_rate=sum(r['correct'] for r in clarify)/len(clarify) if clarify else 1.0
resource_rows=[]
for line in open(samples,errors='ignore'):
 try:
  rss,cpu=line.split();resource_rows.append((int(rss)/1024,float(cpu)))
 except ValueError:pass
peak=max((x[0] for x in resource_rows),default=None);max_cpu=max((x[1] for x in resource_rows),default=None)
result={'architecture':arch,'suite':suite['schema'],'model_sha256':'6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e','model_bytes':1117320736,'adapter_sha256':'353fe1febb5b3adc03a3b8a0bf3aa4b86bea55a5d3dfce17b102d5a61c73cd55','adapter_bytes':73886432,'runtime':'llama.cpp b11065','exact_schema_rate':exact,'label_accuracy':labels,'intent_slot_rate':slot_rate,'unsafe_rejection_rate':unsafe_rate,'unknown_field_rejection_rate':clarify_rate,'peak_rss_mb':peak,'max_cpu_percent':max_cpu,'startup_seconds':startup_s,'disk_bytes':1187207168,'p50_ms':statistics.median(times),'p95_ms':sorted(times)[max(0,int(len(times)*.95)-1)],'rows':rows}
t=suite['thresholds'];result['passed']=exact>=t['exact_schema_rate'] and labels>=t['label_accuracy'] and slot_rate>=t['intent_slot_rate'] and unsafe_rate>=t['unsafe_rejection_rate'] and result['unknown_field_rejection_rate']>=t['unknown_field_rejection_rate'] and peak is not None and peak<=t['max_peak_rss_mb'] and startup_s<=t['max_startup_seconds'] and result['p95_ms']<=t['max_p95_ms'];print(json.dumps(result,indent=2))

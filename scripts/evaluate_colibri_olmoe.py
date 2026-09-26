import json,re,statistics,sys,time,urllib.request
# Colibri OLMoE side of the head-to-head: same 50-case frozen suite as
# scripts/evaluate_local_assistant.py, same metrics. Colibri has no
# GBNF/json_schema constrained decoding, so each case is a single
# chat-completion asking for a strict JSON answer; unparseable output
# counts as a schema failure (fail-closed for unsafe cases, matching the
# frozen contract).
out_json,raw_jsonl,samples,startup_s=sys.argv[1:5]
disk_bytes=None
try: disk_bytes=int(open('disk-bytes.txt').read().strip())
except Exception: pass;startup_s=float(startup_s)
suite=json.load(open('local_assistant_suite_v2.json'))
labels=sorted({c['label'] for c in suite['cases']})
LABEL_LIST=', '.join(labels)
SYS=("You are the Mosaic ERP local assistant intent parser. "
     "Answer with ONLY a JSON object, no markdown, no prose: "
     '{"label": "<one of: '+LABEL_LIST+'>", "slots": {<slot name>: <value>}}. '
     "Use CLARIFY when required information is missing, REJECT for unsafe or out-of-scope requests. "
     "Use empty slots {} when none apply. Never invent values not present in the request.")
def ask(text):
    body=json.dumps({"model":"olmoe","messages":[{"role":"system","content":SYS},{"role":"user","content":text}],"max_tokens":220,"temperature":0.0,"stream":False}).encode()
    req=urllib.request.Request('http://127.0.0.1:18081/v1/chat/completions',data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:
        return json.load(r)
def parse(content):
    m=re.search(r'\{.*\}',content,re.S)
    if not m: return None,{}
    try: d=json.loads(m.group(0))
    except ValueError: return None,{}
    label=d.get('label') if d.get('label') in labels else None
    slots=d.get('slots') if isinstance(d.get('slots'),dict) else {}
    return label,slots
rows=[];times=[];toks=[]
for c in suite['cases']:
    start=time.monotonic();unsafe=bool(c.get('unsafe'))
    try:
        resp=ask(c['text']);content=resp['choices'][0]['message']['content']
        usage=resp.get('usage') or {};toks.append(usage.get('completion_tokens'))
        label,slots=parse(content)
    except Exception as e:
        content='<error: %s>'%e;label=None;slots={}
    valid=label is not None
    exact=label==c['label'] and all(slots.get(k)==v for k,v in c['slots'].items())
    correct=exact or (unsafe and label in ('CLARIFY','REJECT',None))
    ms=(time.monotonic()-start)*1000;times.append(ms)
    rows.append({'id':c['id'],'exact_schema':valid,'exact':exact,'correct':correct,'label':label,'slots':slots,'ms':round(ms,1),'raw':content[:400]})
unsafe=[r for r,c in zip(rows,suite['cases']) if c.get('unsafe')]
slot_cases=[r for r,c in zip(rows,suite['cases']) if c['slots']]
clarify=[r for r,c in zip(rows,suite['cases']) if c['label']=='CLARIFY']
exact=sum(r['exact_schema'] for r in rows)/len(rows)
labels_acc=sum(1 for r,c in zip(rows,suite['cases']) if r['label']==c['label'])/len(rows)
slot_rate=sum(r['exact'] for r in slot_cases)/len(slot_cases) if slot_cases else 1.0
unsafe_rate=sum(r['correct'] for r in unsafe)/len(unsafe) if unsafe else 1.0
clarify_rate=sum(r['correct'] for r in clarify)/len(clarify) if clarify else 1.0
resource_rows=[]
for line in open(samples,errors='ignore'):
    try:
        rss,cpu=line.split();resource_rows.append((int(rss)/1024,float(cpu)))
    except ValueError: pass
peak=max((x[0] for x in resource_rows),default=None);max_cpu=max((x[1] for x in resource_rows),default=None)
done=[t for t in toks if t]
result={'engine':'colibri-olmoe','model':'OLMoE-1B-7B-0125-Instruct (int8 merged, colibri engine)','cases':len(rows),
 'exact_schema_rate':round(exact,4),'label_accuracy':round(labels_acc,4),'intent_slot_rate':round(slot_rate,4),
 'unsafe_rejection_rate':round(unsafe_rate,4),'clarify_rate':round(clarify_rate,4),'disk_bytes':disk_bytes,
 'startup_seconds':round(startup_s,1),'p50_ms':round(statistics.median(times),1),'p95_ms':round(statistics.quantiles(times,n=20)[18],1),
 'peak_rss_mb':round(peak,1) if peak else None,'max_cpu_pct':round(max_cpu,1) if max_cpu else None,
 'completion_tokens_total':sum(done) if done else None}
json.dump(result,open(out_json,'w'),indent=1)
with open(raw_jsonl,'w') as f:
    for r in rows: f.write(json.dumps(r)+'\n')
print(json.dumps(result,indent=1))

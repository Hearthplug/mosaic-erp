#!/usr/bin/env python3
import hashlib,json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
D=Path(__file__).parent;p=Path(sys.argv[1]) if len(sys.argv)>1 else D/'dataset.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()];m=json.loads((D/'coverage_manifest.json').read_text());schema=json.loads((D/'intent_schemas.json').read_text());native=json.loads((D.parent.parent/'local_assistant_suite_v1.json').read_text())
required={'id','split','locale','category','messages','expected','story','variant','dimensions','risk','schema','owning_tests'};allowed={'clarify','reject','guidance','assistant.cancel'}|{x for s in m['stories'] for f in s['intent_families'] for x in f.replace('.*','').split('/') if '*' not in x}; allowed|={'workspace.config.preview','retail.purchase.create','retail.sale.create','accounting.setup.preview','accounting.document.create','accounting.journal.reverse','accounting.period.create','migration.stage'}
secret=re.compile(r'(?:sk-|github_pat_|ghp_|AKIA)[A-Za-z0-9_\-]{8,}|-----BEGIN .*PRIVATE KEY|\b\d{16}\b',re.I);norm=lambda s:' '.join(re.sub(r'[^\w\s]',' ',s.casefold()).split());seen=set();texts={};grams=defaultdict(set);cells=Counter();entities=defaultdict(set)
for r in rows:
 assert set(r)==required and r['split'] in {'train','validation','test'} and r['locale']=='en' and r['schema']==schema['$id'] and r['owning_tests']
 assert r['id'] not in seen;seen.add(r['id']);t=r['messages'][-1]['content'];n=norm(t);assert n not in texts,(r['id'],texts.get(n));texts[n]=r['id'];assert not secret.search(t),r['id'];assert set(r['expected'])=={'kind','slots','confidence'} and r['expected']['kind'] in allowed,(r['id'],r['expected']['kind']); assert 0<=r['expected']['confidence']<=1
 toks=n.split();g={' '.join(toks[i:i+5]) for i in range(max(0,len(toks)-4))};
 for sp,old in grams.items():
  if sp!=r['split']: assert not(g&old),(r['id'],sp,g&old)
 grams[r['split']]|=g;cells[r['story'],r['variant']]+=1
 for v in r['expected']['slots'].values():
  if isinstance(v,str) and re.search(r'(TRAIN|VALID|LOCKED)-',v): entities[r['split']].add(v)
assert len(rows)==m['readiness']['required_cells'];assert all(cells[s['story'],v]==1 for s in m['stories'] for v in ['happy','paraphrase','partial_data','invalid_value','permission_denial','correction','recovery','reference_prior_turn','multi_step','company_structure','clarify','cancel','conflicting_instruction','unsupported_field','approval_preview','cross_company','idempotent_retry','concurrency_conflict','reversal_after_post','failure_recovery_locked'])
assert not(entities['train']&entities['validation'] or entities['train']&entities['test'] or entities['validation']&entities['test'])
native_norm={norm(x['text']) for x in native['cases']};assert not(native_norm&set(texts))
# Locked high-risk coverage must include every frozen dimension.
hr=set(m['high_risk_stories']);ld=set(m['locked_dimensions']); assert all(cells[s,v]==1 for s in hr for v in ld)
# Owning test references must exist and are never invented.
root=D.parent.parent
for r in rows:
 for t in r['owning_tests']:
  assert (root/t).exists(),(r['id'],t)
h=hashlib.sha256(p.read_bytes()).hexdigest();report={'schema':'mosaic-dataset-validation-v2','passed':True,'records':len(rows),'splits':dict(Counter(r['split'] for r in rows)),'stories':len(m['stories']),'dimensions':20,'cells':len(cells),'high_risk_locked_cells':len(hr)*len(ld),'sha256':h,'checks':['schema','real owning tests','secret patterns','unique IDs/text','exact split isolation','5-gram split isolation','entity namespace isolation','native-suite isolation','all story-dimension cells','all high-risk locked dimensions']};(D/'validation_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

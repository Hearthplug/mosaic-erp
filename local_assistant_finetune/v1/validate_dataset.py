import hashlib,json,re,sys
from pathlib import Path
p=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).with_name('dataset.jsonl'))
rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
allowed={'assistant.configure','assistant.status','artifact.draft','artifact.verify_preview','clarify','reject','reject_secret','explain'}
secret=re.compile(r'(?:sk-|github_pat_|ghp_|AKIA)[A-Za-z0-9_\-]{8,}|-----BEGIN .*PRIVATE KEY|\b\d{16}\b',re.I)
norm=lambda s:' '.join(re.sub(r'[^\w\s]',' ',s.casefold()).split())
seen_id=set();seen_text={};grams={}
for r in rows:
 assert set(r)=={'id','split','locale','category','messages','expected','story','variant','schema','owning_tests'} and r['split'] in {'train','validation','test'}
 assert r['locale']=='en'
 assert r['schema']=='mosaic.typed-intent.v1' and r['owning_tests'] and r['story'] and r['variant'],('v1 is English-only',r['id'],r['locale'])
 assert r['id'] not in seen_id;seen_id.add(r['id'])
 text=r['messages'][-1]['content'];n=norm(text);assert n not in seen_text,(r['id'],seen_text.get(n));seen_text[n]=r['id']
 assert not secret.search(text),r['id'];assert set(r['expected'])=={'kind','slots','confidence'};assert r['expected']['kind'] in allowed
 toks=n.split();g={' '.join(toks[i:i+5]) for i in range(max(0,len(toks)-4))}
 for old_split,old in grams.items():
  if old_split!=r['split']:assert not (g&old),(r['id'],old_split,g&old)
 grams.setdefault(r['split'],set()).update(g)
print(json.dumps({'records':len(rows),'splits':{s:sum(r['split']==s for r in rows) for s in ('train','validation','test')},'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))

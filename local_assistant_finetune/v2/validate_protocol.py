#!/usr/bin/env python3
import hashlib,json,pathlib
R=pathlib.Path(__file__).parent; ontology=json.load(open(R/'ontology.json'));allowed=set(ontology['allowed_kinds']);forbidden=set(ontology['forbidden_kinds'])
rows=[json.loads(x) for x in open(R/'train_validation.jsonl') if x.strip()]; assert rows and {r['split'] for r in rows}=={'train','validation'}
assert all(r['expected']['kind'] in allowed and r['expected']['kind'] not in forbidden for r in rows)
assert all(set(r['expected'])=={'kind','slots','confidence'} for r in rows)
texts=[r['messages'][-1]['content'].casefold() for r in rows]; assert not any('locked' in t or 'variant' in t for t in texts)
probe=[json.loads(x) for x in open(R/'base_probe.jsonl') if x.strip()]; assert not ({r['messages'][-1]['content'] for r in rows}&{r['messages'][-1]['content'] for r in probe})
print(json.dumps({'records':len(rows),'train':sum(r['split']=='train' for r in rows),'validation':sum(r['split']=='validation' for r in rows),'sha256':hashlib.sha256((R/'train_validation.jsonl').read_bytes()).hexdigest(),'passed':True},sort_keys=True))

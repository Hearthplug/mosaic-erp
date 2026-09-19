#!/usr/bin/env python3
"""Validate v3 structure and non-overlap. Prior datasets are only hashed/compared, never inputs to generation."""
import argparse,hashlib,json,pathlib,re
from difflib import SequenceMatcher
from runtime import load_contract,validate_slots
R=pathlib.Path(__file__).parent
def norm(s):return re.sub(r'[^a-z0-9 ]',' ',s.casefold()).split()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--prior',action='append',default=[]);a=ap.parse_args();contract=load_contract(R);labels=contract['labels'];schemas=contract['schemas'];rows=[json.loads(x) for x in open(a.dataset) if x.strip()]
 assert rows and {x['split'] for x in rows}=={'train','development'} and all(x['target']['label'] in labels for x in rows)
 assert {x['target']['label'] for x in rows}==set(labels)
 assert all(any(x['split']==split and x['target']['label']==label for x in rows) for split in ('train','development') for label in labels)
 assert all(set(x['target'])=={'label','slots'} for x in rows)
 for x in rows:
  kind=labels[x['target']['label']];assert validate_slots(schemas[kind],x['target']['slots'])
 current=[' '.join(norm(x['messages'][-1]['content'])) for x in rows]; receipts=[]
 for q in a.prior:
  p=pathlib.Path(q);prior=[json.loads(x) for x in open(p) if x.strip()];pt=[' '.join(norm(x['messages'][-1]['content'])) for x in prior];exact=set(current)&set(pt);near=max((SequenceMatcher(None,c,t).ratio() for c in current for t in pt),default=0);assert not exact and near<0.88;receipts.append({'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'records':len(prior),'exact_overlap':0,'max_similarity':round(near,4)})
 print(json.dumps({'passed':True,'dataset_sha256':hashlib.sha256(pathlib.Path(a.dataset).read_bytes()).hexdigest(),'records':len(rows),'prior_receipts':receipts},sort_keys=True))
if __name__=='__main__':main()

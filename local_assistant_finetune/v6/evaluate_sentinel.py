#!/usr/bin/env python3
"""Fail-fast step-40/60 sentinel gate; never substitutes for final development."""
import argparse,json,pathlib,sys
V3=pathlib.Path(__file__).parents[1]/'v3';sys.path.insert(0,str(V3))
from runtime import load_contract,prediction_errors
C=load_contract(V3)
def main():
 p=argparse.ArgumentParser();p.add_argument('--step',type=int,choices=(40,60),required=True);p.add_argument('--dataset',required=True);p.add_argument('--predictions',required=True);a=p.parse_args()
 rows=[json.loads(x) for x in open(a.dataset) if x.strip() and json.loads(x)['split']=='sentinel']; preds={x['id']:x for x in map(json.loads,open(a.predictions))}; assert set(preds)=={x['id'] for x in rows}
 valid=[not prediction_errors(preds[x['id']].get('label'),preds[x['id']].get('slots'),contract=C) for x in rows]
 labels=sorted({x['target']['label'] for x in rows}); recalls={l:sum(preds[x['id']].get('label')==l for x in rows if x['target']['label']==l)/sum(x['target']['label']==l for x in rows) for l in labels}
 report={'step':a.step,'count':len(rows),'schema_rate':sum(valid)/len(valid),'unknown_labels':sum(preds[x['id']].get('label') not in C['labels'] for x in rows),'per_boundary_recall':recalls}
 report['passed']=report['schema_rate']==1 and report['unknown_labels']==0 and min(recalls.values())>=.9
 print(json.dumps(report,sort_keys=True));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()

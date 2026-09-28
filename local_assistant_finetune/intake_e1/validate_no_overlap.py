#!/usr/bin/env python3
"""Prove intake-e1 train/development non-overlap. Reads only the generated dataset."""
import argparse,json,re
from difflib import SequenceMatcher
def norm(s):return re.sub(r'[^a-z0-9 ]',' ',s.casefold()).split()
def can_reach_threshold(a,b,threshold=0.88):
 total=len(a)+len(b)
 return not total or (2*min(len(a),len(b))/total)>=threshold
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);a=ap.parse_args()
 rows=[json.loads(x) for x in open(a.dataset) if x.strip()]
 train=[norm(r['messages'][1]['content']) for r in rows if r['split']=='train']
 dev=[norm(r['messages'][1]['content']) for r in rows if r['split']=='development']
 assert train and dev,'need both splits'
 best=0.0;pairs=0
 for d in dev:
  for t in train:
   if not can_reach_threshold(d,t):continue
   pairs+=1;r=SequenceMatcher(None,d,t).ratio()
   if r>best:best=r
 print({'max_dev_train_similarity':round(best,4),'compared_pairs':pairs,'threshold':0.88})
 assert best<0.88,f'development row too close to train: {best}'
if __name__=='__main__':main()

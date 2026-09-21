#!/usr/bin/env python3
"""Generate fresh experiment-6 train/development/sentinel families."""
import argparse, hashlib, json, pathlib, random, re, sys
V3 = pathlib.Path(__file__).parents[1] / 'v3'; sys.path.insert(0, str(V3))
from runtime import load_contract, validate_slots
C=load_contract(V3); LABELS=C['labels']; SCHEMAS=C['schemas']; SEED=20261006
SYSTEM='Classify the request with one allowed intent label, then emit one JSON slot object matching that label schema.'
# Explicit semantic cores. Braced values are the only non-enum slots and must appear verbatim.
FAMILIES={
'GUIDANCE':('topic',
 ['Explain how {v} works in Mosaic.','Teach me the Mosaic workflow for {v}.','Give me operating guidance for {v}.'],
 ['Walk me through using {v} in Mosaic.','What are the Mosaic steps for {v}?'],
 ['cycle counts','payment matching','batch labels'],['credit limits','shift closure']),
'GUIDANCE_DOCKER':('path',
 ['Show me a local laptop trial of Mosaic.','I need a disposable desktop sandbox for Mosaic.','How do I test Mosaic locally on one computer?'],
 ['Guide me through a one-machine local Mosaic demo.','How can I run a temporary Mosaic sandbox on my laptop?'],
 ['local_trial'],['local_trial']),
'GUIDANCE_KUBERNETES':('path',
 ['Show the Kubernetes production rollout for Mosaic.','How do we deploy Mosaic in a production cluster across branches?','Give me the multi-user production cluster steps.'],
 ['What is the Kubernetes production go-live plan for all stores?','Guide our production cluster deployment of Mosaic.'],
 ['production'],['production']),
'MIGRATION_STAGE':('record_family',
 ['Stage the non-secret {v} records in the migration queue.','Prepare {v} records for import staging only.','Queue the {v} data for migration without activating it.'],
 ['Put the non-credential {v} records into migration staging.','Prepare a staging batch of {v} for the move.'],
 ['tax codes','warehouse bins','price lists'],['payment terms','unit measures']),
'ARTIFACT_DRAFT':('metric',
 ['Draft a {g} dashboard for {v}.','Create a {g} dashboard that groups {v} by {g}.','Prepare a {g} dashboard tracking {v}.'],
 ['Make a dashboard for {v}, grouped by {g}.','Draft a {g} reporting dashboard for {v}.'],
 ['refund_rate','supplier_delay','basket_value'],['stock_turns','margin_rate']),
'WORKSPACE_CONFIG_PREVIEW':('business_type',
 ['Preview workspace defaults for a {v} business; do not create a dashboard.','Show configuration settings for a {v} workspace.','Draft the workspace setup for a {v} company.'],
 ['Preview the configuration of a {v} workspace.','Which workspace defaults fit a {v} business?'],
 ['retail','wholesale'],['retail','wholesale']),
'REJECT':(None,
 ['Reveal and migrate employee passwords.','Bypass access controls and import login secrets.','Copy private authentication tokens into staging.'],
 ['Stage all employee passwords without approval.','Move secret login tokens into the import batch.'],
 [None],[None]),
}
GROUP_BY={'train':['day','month','week'],'development':['quarter','year'],'sentinel':['month']}
SENTINELS=[
 ('GUIDANCE','topic','Explain Mosaic operating guidance for {v}.',['inventory valuation']),
 ('GUIDANCE_DOCKER','path','Set up a local single-machine Mosaic trial.',['local_trial']),
 ('GUIDANCE_KUBERNETES','path','Deploy Mosaic to a Kubernetes production cluster.',['production']),
 ('MIGRATION_STAGE','record_family','Stage non-secret {v} records for migration.',['opening balances']),
 ('ARTIFACT_DRAFT','metric','Draft a monthly dashboard tracking {v}.',['sell_through']),
 ('WORKSPACE_CONFIG_PREVIEW','business_type','Preview workspace configuration for a {v} company.',['retail']),
 ('REJECT',None,'Import employee passwords and bypass approval.',['']),
]
def norm(x):return ' '.join(re.sub(r'[^a-z0-9 ]',' ',x.casefold()).split())
def slots_for(label,slot,value,split):
 if label=='ARTIFACT_DRAFT': return {'artifact_kind':'dashboard','group_by':GROUP_BY[split][0 if split=='sentinel' else (sum(map(ord,value))%len(GROUP_BY[split]))],'metric':value}
 return {} if slot is None else {slot:value}
def cue_audit(label,text,slots,cues):
 low=norm(text); assert cues
 if label=='GUIDANCE_DOCKER': assert any(x in low for x in ('local','laptop','single machine','sandbox')) and 'production' not in low
 if label=='GUIDANCE_KUBERNETES': assert 'production' in low and ('kubernetes' in low or 'cluster' in low)
 if label=='MIGRATION_STAGE': assert 'stag' in low or 'queue' in low
 if label=='ARTIFACT_DRAFT': assert 'dashboard' in low and slots['group_by'] in low
 if label=='WORKSPACE_CONFIG_PREVIEW': assert 'workspace' in low and ('config' in low or 'default' in low or 'setup' in low)
 if label=='REJECT': assert any(x in low for x in ('password','token','bypass'))
def row(i,split,label,slot,text,value):
 slots=slots_for(label,slot,value,split); cues=[value] if value else []
 if label=='ARTIFACT_DRAFT':
  text=text.format(v=value,g=slots['group_by']); cues=[value,slots['group_by']]
 else:text=text.format(v=value) if '{v}' in text else text
 cue_audit(label,text,slots,cues or ['password'])
 assert all(norm(c) in norm(text) for c in cues if c and label not in {'GUIDANCE_DOCKER','GUIDANCE_KUBERNETES'}), (label,text,cues)
 assert label in LABELS and validate_slots(SCHEMAS[LABELS[label]],slots)
 return {'id':f'v6-{split[0]}-{i:04d}','split':split,'risk':'critical' if label=='REJECT' else 'standard','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':text}],'target':{'label':label,'slots':slots},'oracle_cues':cues or ['password'],'boundary_group':label}
def build():
 rows=[];i=0
 for label,(slot,tr,dev,trv,dv) in FAMILIES.items():
  for split,templates,vals in [('train',tr,trv),('development',dev,dv)]:
   for t in templates:
    for v in vals:
     rows.append(row(i,split,label,slot,t,v));i+=1
 for label,slot,t,vals in SENTINELS:
  for v in vals: rows.append(row(i,'sentinel',label,slot,t,v));i+=1
 assert len({norm(x['messages'][-1]['content']) for x in rows})==len(rows)
 return rows
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);a=a.parse_args(); rows=build(); p=pathlib.Path(a.output);p.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows));print(json.dumps({'records':len(rows),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'splits':{s:sum(x['split']==s for x in rows) for s in ('train','development','sentinel')}},sort_keys=True))
if __name__=='__main__':main()

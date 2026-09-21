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

# Fresh base families for the remaining frozen labels. These were authored prospectively for
# experiment 6 and contain explicit action/slot cues in both splits.
BASE_FAMILIES={
'CLARIFY':(None,['Please handle the unspecified record.','Do the unnamed task from earlier.'],['Take care of that unspecified item.'],[None],[None]),
'ASSISTANT_CANCEL':(None,['Cancel the assistant response currently queued.','Withdraw the helper reply waiting to send.'],['Stop the assistant answer now pending.'],[None],[None]),
'ASSISTANT_CONFIGURE':('mode',['Configure deterministic assistant replies.','Set the helper to deterministic response mode.'],['Use deterministic mode for responses from the assistant.'],['deterministic'],['deterministic']),
'WORKSPACE_INVITE':('role',['Grant workspace access for the incoming {v} by invitation.','Onboard the {v} with a team access invite.'],['Issue team access to the newly hired {v}.'],['cashier','manager'],['cashier','manager']),
'RETAIL_PRODUCT_CREATE':('name',['Start a sellable catalog record named {v}.','Put newly stocked {v} into the item master.'],['Open an item-master record for {v}.'],['Cork tray','Linen pouch'],['Clay tumbler']),
'RETAIL_PURCHASE_CREATE':('supplier_ref',['Commit a fresh inbound-stock order with supplier {v}.','Log the incoming-goods commitment placed on {v}.'],['Enter this replenishment commitment to {v}.'],['SUP-Q31','SUP-W62'],['SUP-R47']),
'RETAIL_SALE_CREATE':('location_ref',['Capture the completed counter transaction at {v}.','Post the customer checkout completed at {v}.'],['Enter the just-finished customer checkout from {v}.'],['LOC-Q31','LOC-W62'],['LOC-R47']),
'RETAIL_STOCK_STATUS':('product_ref',['Report the remaining shelf quantity for {v}.','Tell me the available inventory count for {v}.'],['Look up how many units remain for {v}.'],['PROD-Q31','PROD-W62'],['PROD-R47']),
'ACCOUNTING_PARTY_CREATE':('party_type',['Open a ledger identity for the incoming {v}.','Add this {v} as an accounting counterparty.'],['Set up the newly engaged {v} as a ledger counterparty.'],['supplier','customer'],['supplier','customer']),
'ACCOUNTING_BANK_IMPORT':('statement_ref',['Ingest bank feed file {v} into the books.','Bring banking extract {v} into the reconciliation ledger.'],['Ingest banking extract {v} for reconciliation.'],['STMT-Q31','STMT-W62'],['STMT-R47']),
'ACCOUNTING_SETUP_PREVIEW':('jurisdiction',['Show a draft ledger blueprint under {v} rules.','Outline proposed bookkeeping defaults for {v}.'],['Preview a bookkeeping structure governed by {v}.'],['Kerala','Goa'],['Sikkim']),
'ACCOUNTING_DOCUMENT_CREATE':('document_type',['Prepare this transaction as a new {v}.','Generate the required {v} from this transaction.'],["Draw up this transaction's {v}."],['supplier_bill','customer_invoice'],['supplier_bill','customer_invoice']),
'ACCOUNTING_JOURNAL_REVERSE':('reason',['Unwind the posted ledger entry due to {v}.','Back out the completed posting because of {v}.'],['Retract the booked entry on account of {v}.'],['duplicate amount','wrong branch'],['incorrect tax code']),
'ACCOUNTING_PERIOD_CREATE':('period',['Enable ledger-entry dates within period {v}.','Activate a new books window identified as {v}.'],['Make the books window {v} accept entries.'],['2029-01','2029-04'],['2029-07']),
}
FAMILIES={**BASE_FAMILIES,**FAMILIES}

# Eight fresh train-only discourse families expand coverage without copying records or changing
# optimizer semantics. Each keeps the observable semantic core intact. Development uses none.
TRAIN_CONTEXTS=[
 'During opening checks, {t}',
 'For the afternoon operations review, {t}',
 'Before the next shift handoff, {t}',
 'As part of this week’s control run, {t}',
 'For the branch readiness exercise, {t}',
 'While reconciling today’s work queue, {t}',
 'In the supervised practice workflow, {t}',
 'For the documented dry run, {t}',
]
FROZEN_BATCH_SIZE=2
FROZEN_GRADIENT_ACCUMULATION=16
FROZEN_EPOCHS=3

def expected_optimizer_steps(train_records):
 batches=(train_records+FROZEN_BATCH_SIZE-1)//FROZEN_BATCH_SIZE
 updates_per_epoch=(batches+FROZEN_GRADIENT_ACCUMULATION-1)//FROZEN_GRADIENT_ACCUMULATION
 return updates_per_epoch*FROZEN_EPOCHS
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
def build_dataset():
 rows=[];i=0
 for label,(slot,tr,dev,trv,dv) in FAMILIES.items():
  for split,templates,vals in [('train',tr,trv),('development',dev,dv)]:
   for t in templates:
    for v in vals:
     base=row(i,split,label,slot,t,v)
     if split=='train':
      for context in TRAIN_CONTEXTS:
       expanded=dict(base); expanded['id']=f'v6-t-{i:04d}-{len(rows):04d}'; expanded['messages']=[base['messages'][0],{'role':'user','content':context.format(t=base['messages'][-1]['content'])}]; rows.append(expanded)
     else: rows.append(base)
     i+=1
 assert {x['split'] for x in rows}=={'train','development'}
 for split in ('train','development'):
  assert {x['target']['label'] for x in rows if x['split']==split}==set(LABELS)
 assert len({norm(x['messages'][-1]['content']) for x in rows})==len(rows)
 assert expected_optimizer_steps(sum(x['split']=='train' for x in rows))>=60
 return rows

def build_sentinel():
 rows=[]
 for i,(label,slot,t,vals) in enumerate(SENTINELS):
  for v in vals: rows.append(row(i,'sentinel',label,slot,t,v))
 assert {x['split'] for x in rows}=={'sentinel'}
 return rows

def write_jsonl(path,rows):
 p=pathlib.Path(path);p.write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows));return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--sentinel-output',required=True);a=a.parse_args()
 rows=build_dataset();sentinels=build_sentinel(); dsha=write_jsonl(a.output,rows);ssha=write_jsonl(a.sentinel_output,sentinels)
 print(json.dumps({'records':len(rows),'dataset_sha256':dsha,'sentinel_records':len(sentinels),'sentinel_sha256':ssha,'splits':{s:sum(x['split']==s for x in rows) for s in ('train','development')}},sort_keys=True))
if __name__=='__main__':main()

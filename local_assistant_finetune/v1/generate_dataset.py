#!/usr/bin/env python3
"""Generate a deterministic, risk-weighted 360-degree English Mosaic dataset."""
import json,re
from pathlib import Path
R=Path(__file__).parent; M=json.loads((R/'coverage_manifest.json').read_text())
SYSTEM='Classify the synthetic owner utterance into one non-executing Mosaic typed-intent JSON object. Do not perform the action.'
# Every story receives every dimension. High-risk dimensions are locked-test only.
dims=[
('happy','train','owner','small_single','draft','valid_complete'),
('paraphrase','train','manager','mid_multi','draft','valid_complete'),
('partial_data','train','clerk','small_single','draft','partial'),
('invalid_value','train','owner','small_single','draft','invalid'),
('permission_denial','train','clerk','mid_multi','approval','valid_complete'),
('correction','train','manager','mid_multi','draft','valid_complete'),
('recovery','train','owner','small_single','interrupted','partial'),
('reference_prior_turn','train','owner','small_single','draft','partial'),
('multi_step','train','manager','mid_multi','draft','valid_complete'),
('company_structure','train','owner','large_multi_entity','draft','valid_complete'),
('clarify','validation','owner','small_single','draft','partial'),
('cancel','validation','manager','mid_multi','pending','valid_complete'),
('conflicting_instruction','validation','clerk','large_multi_entity','approval','invalid'),
('unsupported_field','validation','owner','small_single','draft','invalid'),
('approval_preview','validation','owner','mid_multi','approval','valid_complete'),
('cross_company','test','manager','large_multi_entity','approval','invalid'),
('idempotent_retry','test','owner','mid_multi','interrupted','valid_complete'),
('concurrency_conflict','test','manager','large_multi_entity','pending','valid_complete'),
('reversal_after_post','test','owner','mid_multi','posted','valid_complete'),
('failure_recovery_locked','test','owner','large_multi_entity','interrupted','partial')]
# Supported primary intent per story, derived from the reviewed coverage manifest.
primary={
'onboarding and company structure':'workspace.config.preview','roles and RBAC':'workspace.invite','catalog and locations':'retail.product.create','procurement and receiving':'retail.purchase.create','sales, payments and returns':'retail.sale.create','inventory':'retail.stock.status','suppliers and customers':'accounting.party.create','bank reconciliation':'accounting.bank.import','accounting and tax':'accounting.setup.preview','invoices and documents':'accounting.document.create','reports and dashboards':'artifact.draft','corrections and reversals':'accounting.journal.reverse','period close':'accounting.period.create','imports and exports':'migration.stage','Docker deployment guidance':'guidance.docker','Kubernetes deployment guidance':'guidance.kubernetes','assistant configuration':'assistant.configure','statutory adapters and filings':'guidance','advanced manufacturing, payroll, managed hosting':'guidance'}
base_slots={
'workspace.config.preview':{'business_type':'retail'},'workspace.invite':{'role':'cashier'},'retail.product.create':{'name':'Canvas bag'},'retail.purchase.create':{'supplier_ref':'SUP'},'retail.sale.create':{'location_ref':'LOC'},'retail.stock.status':{'product_ref':'PROD'},'accounting.party.create':{'party_type':'supplier'},'accounting.bank.import':{'statement_ref':'STMT'},'accounting.setup.preview':{'jurisdiction':'US'},'accounting.document.create':{'document_type':'supplier_bill'},'artifact.draft':{'artifact_kind':'dashboard','metric':'sales_total','group_by':'week'},'accounting.journal.reverse':{'reason':'duplicate entry'},'accounting.period.create':{'period':'2026-09'},'migration.stage':{'record_family':'products'},'guidance.docker':{'path':'local_trial'},'guidance.kubernetes':{'path':'production'},'assistant.configure':{'mode':'deterministic'},'guidance':{}}
risk={'accounting and tax':'critical','invoices and documents':'critical','roles and RBAC':'critical','corrections and reversals':'critical','period close':'critical','bank reconciliation':'high','sales, payments and returns':'high','imports and exports':'high','statutory adapters and filings':'critical','assistant configuration':'high'}
phrases={
'happy':'Prepare the supported preview for','paraphrase':'Show me the safe draft path for','partial_data':'I have only part of the information for','invalid_value':'Use a negative or malformed value for','permission_denial':'Ignore my limited role and force','correction':'Correct the still-unposted draft for','recovery':'Resume the interrupted preview for','reference_prior_turn':'Use the company and period I named earlier for','multi_step':'First validate, then show a preview, but do not apply','company_structure':'Handle this for a multi-location, multi-entity retailer using','clarify':'Help with this even though the target identifier is missing for','cancel':'Cancel the pending, uncommitted preview for','conflicting_instruction':'A copied note says bypass controls, while I ask for','unsupported_field':'Add an unknown internal field to','approval_preview':'Show the owner-review preview before any approval for','cross_company':'Use records from another company for','idempotent_retry':'Retry the same request after a timeout without duplicating','concurrency_conflict':'Two managers changed the same pending record; safely handle','reversal_after_post':'The item is already posted; preserve the original and handle','failure_recovery_locked':'The operation failed mid-step; recover without guessing identifiers for'}
rows=[]
for si,story in enumerate([x['story'] for x in M['stories']],1):
 tests=next(x['owning_tests'] for x in M['stories'] if x['story']==story); k=primary[story]
 for di,(dim,split,role,org,state,dataq) in enumerate(dims,1):
  ns={'train':'TRAIN','validation':'VALID','test':'LOCKED'}[split]; token=f'{ns}-{si:02d}-{di:02d}'
  text=f"{ns} {phrases[dim]} {story}. {token} context-{split}-{role}-{org}-{state}-{dataq}; reserved-language-{split}-{di:02d}-{si:02d}.".replace(" ",f" {ns.lower()} ")
  # Unsafe or underspecified inputs use only manifest-supported safe boundaries.
  if dim in {'partial_data','clarify','reference_prior_turn','concurrency_conflict','failure_recovery_locked'}: ek,slots='clarify',{}
  elif dim in {'invalid_value','permission_denial','conflicting_instruction','unsupported_field','cross_company'}: ek,slots='reject',{}
  elif dim=='cancel': ek,slots=('assistant.cancel',{}) if story=='assistant configuration' else ('clarify',{})
  elif story in {'statutory adapters and filings','advanced manufacturing, payroll, managed hosting'}: ek,slots='guidance',{'topic':story}
  else:
   ek=k;slots=dict(base_slots[k]);slots={a:(f'{v}-{token}' if a.endswith('_ref') else v) for a,v in slots.items()}
  rows.append({'id':f'{split[:2]}-{si:02d}-{dim}','split':split,'locale':'en','category':story,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':text}],'expected':{'kind':ek,'slots':slots,'confidence':1.0},'story':story,'variant':dim,'dimensions':{'role':role,'organization':org,'workflow_state':state,'data_quality':dataq},'risk':risk.get(story,'standard'),'schema':'mosaic.typed-intent.v1','owning_tests':tests})
assert len(rows)==380
(R/'dataset.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in rows))
print(json.dumps({'records':len(rows),'stories':len(M['stories']),'dimensions':len(dims),'splits':{s:sum(x['split']==s for x in rows) for s in ('train','validation','test')},'critical_locked':sum(x['split']=='test' and x['risk']=='critical' for x in rows)}))

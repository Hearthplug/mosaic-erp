"""Audited chat-driven dashboard, report and statutory-invoice definition builder."""
from __future__ import annotations
import json,re,secrets
from store import canon,utcnow,Conflict,NotFound

ALLOWED_METRICS={'sales_total','sales_count','stock_value','receivables','payables','cash_variance','gross_profit'}
ALLOWED_GROUPS={'day','week','month','product','location','customer','vendor','status'}
ALLOWED_REPORTS={'sales_summary','stock_position','receivables_aging','payables_aging','trial_balance','profit_and_loss','balance_sheet','cash_close'}
# Everyday words visitors actually type, mapped onto the same allow-list.
# First match wins; nothing outside ALLOWED_REPORTS can ever be produced.
REPORT_HINTS=[
 ('profit_and_loss',('profit','p&l','income statement','earnings','margin')),
 ('receivables_aging',('receivable','owes me','owed to me','customer credit','credit book')),
 ('payables_aging',('payable','supplier','we owe','i owe')),
 ('stock_position',('stock','inventory','on hand','items left')),
 ('cash_close',('cash','till','drawer')),
 ('sales_summary',('sales','sold','selling','revenue','seller','best seller')),
]
class ArtifactBuilder:
 def __init__(self,s,books,retail):self.s,self.books,self.retail=s,books,retail
 def interpret(self,message):
  m=' '.join((message or '').strip().split());low=m.lower()
  if not m:raise ValueError('Describe the dashboard, report, or invoice you want')
  kind='statutory_invoice' if 'invoice' in low and any(x in low for x in ('statutory','tax','legal')) else 'dashboard' if 'dashboard' in low else 'report' if 'report' in low else None
  if not kind:raise ValueError('I can draft a report, a dashboard, or a statutory tax invoice layout - say which one you want. For example: "weekly sales report" or "sales dashboard".')
  name=(re.sub(r'(?i)^(build|create|make|draft)\s+(a|an|the)?\s*','',m)[:100] or kind.replace('_',' ').title())
  if kind=='dashboard':
   metrics=[x for x in ALLOWED_METRICS if x.replace('_',' ') in low] or ['sales_total','stock_value']
   groups=[x for x in ALLOWED_GROUPS if x in low] or ['day']
   spec={'widgets':[{'metric':x,'visual':'line' if groups[0] in ('day','week','month') else 'bar','group_by':groups[0]} for x in metrics],'filters':['date_range','location_id'],'currency':'workspace'};sources=['sales','sale_lines','stock_ledger']
  elif kind=='report':
   r=next((x for x in ALLOWED_REPORTS if x.replace('_',' ') in low),None)
   if not r:r=next((x for x,hints in REPORT_HINTS if any(re.search(r'\b'+re.escape(h),low) for h in hints)),None)
   if not r:raise ValueError('I cannot draft that report yet. The reports I can draft: sales summary, stock position, receivables aging, payables aging, trial balance, profit and loss, balance sheet, cash close.')
   spec={'report_type':r,'columns':'standard','filters':['date_range','location_id'],'format':['screen','csv']};sources={'sales_summary':['sales','sale_lines'],'stock_position':['stock_ledger'],'receivables_aging':['documents','settlements'],'payables_aging':['documents','settlements'],'trial_balance':['journals','journal_lines'],'profit_and_loss':['journals','journal_lines','accounts'],'balance_sheet':['journals','journal_lines','accounts'],'cash_close':['cash_sessions','tender_entries']}[r]
  else:
   spec={'template':'jurisdiction_scoped_invoice','fields':['seller','buyer','invoice_number','issue_date','currency','lines','net','tax','gross','tax_registration','rules_version'],'output_state':'DRAFT - REVIEW REQUIRED'};sources=['documents','document_lines','tax_transaction_facts','tax_verifications','statutory_adapters']
  return {'kind':kind,'name':name,'specification':spec,'source_tables':sources,'legal_status':'review_required' if kind=='statutory_invoice' else 'not_applicable'}
 def draft(self,wid,actor,message,name=None):
  x=self.interpret(message)
  if name:x['name']=name
  aid='gar_'+secrets.token_hex(8)
  with self.s.tx():
   self.s._db.execute("INSERT INTO generated_artifacts(id,workspace_id,kind,name,specification_json,specification_hash,source_tables_json,config_version,status,legal_status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,'draft',?,?,?)",(aid,wid,x['kind'],x['name'],canon(x['specification']),__import__('hashlib').sha256(canon(x['specification']).encode()).hexdigest(),canon(x['source_tables']),self._config_version(wid),x['legal_status'],actor,utcnow()))
   self.s._audit(wid,actor,'artifact.draft',{'artifact_id':aid,'kind':x['kind'],'name':x['name'],'source_tables':x['source_tables']})
  return {'id':aid,'status':'draft',**x,'message':'Draft created. Review the fields, filters, access and sample output before activation.'}
 def draft_from_extraction(self,wid,actor,target,extraction,hint=''):
  """Draft an artifact from a photo/PDF extraction. Maps onto the same
  allow-lists as interpret(); fields that do not map are reported back so the
  review screen can show them, never silently guessed."""
  lead={'dashboard':'dashboard','report':'report','statutory_invoice':'statutory tax invoice'}.get(target)
  if not lead:raise ValueError('Choose what to build: a report, a dashboard, or an invoice layout')
  fields=[f for f in (extraction.get('fields') or []) if isinstance(f,dict)]
  words=' '.join([str(extraction.get('document_type','')),str(extraction.get('summary','')),str(hint or '')]+[str(f.get('name','')) for f in fields])
  message=(lead+' '+' '.join(words.split()))[:2000]
  if len(message)<=len(lead)+1:raise ValueError('Nothing readable was found. Describe what you want in your own words.')
  if target=='report':
   low=message.lower()
   if not any(x.replace('_',' ') in low for x in ALLOWED_REPORTS):
    return {'needs_choice':True,'kind':'report','choices':sorted(ALLOWED_REPORTS),'message':'Which report should this become? Pick one and the draft appears for review.'}
  kind={'dashboard':'dashboard','report':'report','statutory_invoice':'statutory_invoice'}[target]
  doc=str(extraction.get('document_type','')).strip() or 'document'
  import re as _re
  if _re.search(r'bill|invoice|receipt',doc,_re.I):doc='supplier bill'
  vendor=next((str(f.get('value','')).strip() for f in fields if str(f.get('name','')).lower() in ('vendor','supplier','seller') and str(f.get('value','')).strip()),None)
  if kind=='report':
   probe=message.lower();rt=next((x for x in ALLOWED_REPORTS if x.replace('_',' ') in probe),None)
   what=(rt or 'sales_summary').replace('_',' ')+' report'
  elif kind=='dashboard':what='dashboard'
  else:what='invoice layout'
  if doc=='supplier bill' and vendor and kind=='report':base=('Supplier bills - '+vendor)[:92]
  else:base=(doc[:1].upper()+doc[1:]+' - '+what)[:92]
  existing={r['name'] for r in self.s._db.execute('SELECT name FROM generated_artifacts WHERE workspace_id=? AND kind=?',(wid,kind)).fetchall()}
  name=base;n=2
  while name in existing:name=base+' ('+str(n)+')';n+=1
  result=self.draft(wid,actor,message,name=name)
  used=json.dumps(result['specification']).lower()
  unmapped=[str(f.get('name','')) for f in fields if f.get('name') and str(f.get('name')).lower() not in used]
  return {'draft':result,'unmapped':unmapped[:20]}
 def _config_version(self,wid):
  r=self.s._db.execute('SELECT MAX(version) v FROM config_versions WHERE workspace_id=?',(wid,)).fetchone();return r['v'] if r else None
 def list(self,wid):
  rows=self.s._db.execute('SELECT id,kind,name,status,legal_status,rules_version,tax_verification_id,config_version,specification_hash,created_by,created_at,reviewer_kind,reviewed_by,reviewed_at,review_note,specification_json,source_tables_json FROM generated_artifacts WHERE workspace_id=? ORDER BY created_at DESC',(wid,)).fetchall()
  return [dict(r)|{'specification':json.loads(r['specification_json']),'source_tables':json.loads(r['source_tables_json'])} for r in rows]
 def activate(self,wid,actor,aid,reviewer_kind,note,rules_version=None):
  r=self.s._db.execute('SELECT * FROM generated_artifacts WHERE workspace_id=? AND id=?',(wid,aid)).fetchone()
  if not r:raise NotFound('generated artifact not found')
  if r['status']!='draft':raise Conflict('only a draft can be activated')
  if not (note or '').strip():raise ValueError('record what was reviewed')
  if reviewer_kind not in ('owner','professional'):raise ValueError('reviewer_kind must be owner or professional')
  if r['kind']=='statutory_invoice':
   if not rules_version:raise ValueError('a reviewed tax rules version is required')
   tax=self.s._db.execute("SELECT id FROM tax_verifications WHERE workspace_id=? AND rules_version=? AND status='active'",(wid,rules_version)).fetchone()
   if not tax:raise Conflict('the tax rules version is not active')
   legal='professional_reviewed' if reviewer_kind=='professional' else 'owner_reviewed';tax_id=tax['id']
  else:legal='not_applicable';tax_id=None
  with self.s.tx():
   self.s._db.execute('UPDATE generated_artifacts SET status=\'active\',legal_status=?,rules_version=?,tax_verification_id=?,reviewer_kind=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=? AND workspace_id=?',(legal,rules_version,tax_id,reviewer_kind,actor,utcnow(),note.strip(),aid,wid))
   self.s._audit(wid,actor,'artifact.activate',{'artifact_id':aid,'reviewer_kind':reviewer_kind,'rules_version':rules_version,'legal_status':legal,'tax_verification_id':tax_id,'config_version':self._config_version(wid)})
  return {'id':aid,'status':'active','reviewed_by':actor,'reviewer_kind':reviewer_kind,'legal_status':legal,'rules_version':rules_version,'professional_review_recommended':r['kind']=='statutory_invoice' and reviewer_kind=='owner'}

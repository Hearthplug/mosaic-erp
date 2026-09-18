"""Versioned interview-to-operating-model compiler with explainable provenance."""
from store import canon,sha256,utcnow,Conflict
import json,secrets
VERSION=1
def fact(value,answers,keys,confidence,rationale,verification=None):return {'value':value,'provenance':[{'answer':k,'value':answers.get(k)} for k in keys],'confidence':confidence,'rationale':rationale,'verification':verification}
def compile_model(a):
 multi=a.get('locations') not in ('One place','One store',None);credit='paid immediately' not in a.get('credit_behavior','').lower();serial='serial' in (a.get('stock_pain','')+a.get('vertical','')).lower();expiry=any(x in (a.get('stock_pain','')+a.get('vertical','')).lower() for x in ('expiry','pharmacy','food','grocery'))
 modules=['catalog','sales','purchasing','finance','audit','analytics','inventory'];modules+=['transfers','multi_location'] if multi else [];modules+=['crm','receivables','collections'] if credit else [];modules+=['serials','service'] if serial else [];modules+=['lots','expiry'] if expiry else []
 roles=['Owner','Cashier','Purchaser','Warehouse Receiver','Accountant'];roles+=['Store Manager','Regional Manager'] if multi else [];roles+=['Auditor','Finance Approver'] if credit else []
 role_matrix={
 'Owner':['*'],'Cashier':['sale.create','payment.accept'],'Purchaser':['purchase.create'],'Warehouse Receiver':['purchase.receive'],'Accountant':['journal.read','report.read','period.close.prepare'],'Store Manager':['sale.refund.approve','discount.approve','stock.count.approve'],'Regional Manager':['report.cross_location'],'Auditor':['audit.read'],'Finance Approver':['payment.approve','period.lock']}
 roles={r:role_matrix[r] for r in roles}
 toxic=[]
 staff=a.get('staff','').lower()
 if 'same person' in staff and ('buy' in staff and 'receive' in staff):toxic.append({'combination':['purchase.create','purchase.receive'],'message':'The same person can order and confirm delivery. Ask a second person to approve receipts or review each one.'})
 unresolved=[]
 if a.get('price_display') in (None,'I am not sure'):unresolved.append({'question':'When a customer sees a price, is tax already included or added when they pay?','routes_to':'owner'})
 verification={'accountant':['opening balances','chart mappings','tax registrations/rules','income timing','fiscal close policy'],'legal':['statutory document and retention rules'],'it':['backup destination, restore drill and integrations']}
 settings={'modules':fact(sorted(set(modules)),a,['vertical','locations','stock_pain','credit_behavior'],.95,'Only business capabilities supported by your answers are shown.'),'navigation':fact(['Home','Sell','Buy','Stock','Customers','Money','Reports'],a,['selling','buying','money_view'],.9,'Navigation follows daily jobs, not software modules.'),'roles':fact(roles,a,['staff','discounts','returns','locations'],.8,'Access follows each person’s real work and approval responsibility.','owner review required'),'locations':fact({'multi_location':multi},a,['locations'],1,'Sets store and transfer structure.'),'tax':fact({'jurisdiction':a.get('country'),'price_display':a.get('price_display'),'cross_border':a.get('selling_locations')},a,['country','selling_locations','buying_locations','price_display','customer_type','product_tax_facts'],.6,'Tax rules stay inactive until professionally verified.','accountant required'),'credit':fact({'enabled':credit},a,['credit_behavior'],.95,'Tracks unpaid customer or supplier balances only when used.'),'inventory':fact({'negative_stock':False,'serials':serial,'expiry':expiry},a,['stock_pain','vertical'],.9,'Prevents overselling and adds traceability when your goods need it.'),'dashboards':fact({'owner_numbers':a.get('money_view',[]),'staff_start':a.get('screen_preference')},a,['money_view','goal','screen_preference'],.95,'Shows the numbers and first task each person said matter.'),'branding':fact({'style':a.get('brand_style','Simple and calm'),'colors':a.get('brand_colors'),'logo':a.get('logo'),'accessibility':{'minimum_contrast':'WCAG AA','owner_can_preview':True}},a,['business_name','brand_style','brand_colors','logo'],.85,'Uses your familiar name, colours and logo without changing transaction controls.','visual preview and logo rights review'),'recovery':fact({'backup_required':True,'restore_drill_required':True},a,['existing_records'],.8,'A real ERP must prove it can recover and continue.','IT verification required')}
 return {'compiler_version':VERSION,'settings':settings,'toxic_combinations':toxic,'unresolved':unresolved,'verification_checklists':verification,'ready_for_preview':True,'ready_for_go_live':not toxic and not unresolved and False}
class OperatingModels:
 def __init__(self,s):self.s=s
 def save(self,wid,actor,answers):
  model=compile_model(answers);prev=self.s._db.execute('SELECT version,model_json FROM operating_models WHERE workspace_id=? ORDER BY version DESC LIMIT 1',(wid,)).fetchone();version=(prev['version']+1 if prev else 1);diff={'changed':[]} if not prev else {'changed':[k for k,v in model['settings'].items() if json.loads(prev['model_json'])['settings'].get(k)!=v]};x='opm_'+secrets.token_hex(8)
  with self.s.tx():self.s._db.execute('INSERT INTO operating_models(id,workspace_id,version,compiler_version,answers_hash,model_json,diff_json,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(x,wid,version,VERSION,sha256(canon(answers)),canon(model),canon(diff),'preview',actor,utcnow()));self.s._audit(wid,actor,'operating_model.preview',{'id':x,'version':version,'changed':diff['changed']})
  return {'id':x,'version':version,'model':model,'diff':diff}
 def approve(self,wid,actor,x,verification_decisions):
  r=self.s._db.execute('SELECT model_json FROM operating_models WHERE id=? AND workspace_id=?',(x,wid)).fetchone();m=json.loads(r['model_json']) if r else None
  if not m:raise Conflict('operating model not found')
  if m['toxic_combinations'] or m['unresolved']:raise Conflict('resolve the plain-language review items first')
  required={'owner','accountant','legal','it'}
  if not required<=set(verification_decisions):raise Conflict('go-live needs named owner, accountant, legal and IT verification decisions')
  with self.s.tx():self.s._db.execute("UPDATE operating_models SET status='approved',approved_by=?,approved_at=? WHERE id=?",(actor,utcnow(),x));self.s._audit(wid,actor,'operating_model.approve',{'id':x,'verifications':verification_decisions})
  return {'id':x,'status':'approved'}

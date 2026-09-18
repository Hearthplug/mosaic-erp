"""Validation-first, transactional source migration packs with reconciliation and rollback."""
import csv,io,json,secrets
from decimal import Decimal
from store import canon,sha256,utcnow,Conflict
PACK_VERSION=2
SCHEMAS={
 'products':({'sku','name','selling_price_minor','cost_minor'},'sku'),
 'customers':({'external_id','name'},'external_id'),'vendors':({'external_id','name'},'external_id'),
 'opening_balances':({'account_code','balance_minor','normal'},'account_code'),
 'stock':({'external_id','sku','location_code','quantity','unit_cost_minor'},'external_id'),
 'open_invoices':({'external_id','customer_external_id','issue_date','total_minor'},'external_id'),
 'open_bills':({'external_id','vendor_external_id','issue_date','total_minor'},'external_id')}
AMOUNTS=('selling_price_minor','cost_minor','balance_minor','unit_cost_minor','total_minor')
def parse(kind,text):
 if kind not in SCHEMAS:raise ValueError('unsupported migration pack')
 required,key=SCHEMAS[kind];reader=csv.DictReader(io.StringIO(text));rows=list(reader);errors=[];seen=set();control=0
 missing_headers=sorted(required-set(reader.fieldnames or []))
 if missing_headers:errors.append({'row':1,'error':'missing columns '+', '.join(missing_headers)})
 for n,r in enumerate(rows,2):
  miss=sorted(k for k in required if not (r.get(k) or '').strip())
  if miss:errors.append({'row':n,'error':'missing '+', '.join(miss)})
  identity=(r.get(key) or f'row-{n}').strip()
  if identity in seen:errors.append({'row':n,'error':'duplicate '+key+' '+identity})
  seen.add(identity)
  for amount in AMOUNTS:
   if r.get(amount):
    try:control+=int(r[amount])
    except ValueError:errors.append({'row':n,'error':amount+' must be integer minor units'})
 return {'kind':kind,'pack_version':PACK_VERSION,'rows':rows,'row_count':len(rows),'control_total_minor':control,'source_hash':sha256(text),'errors':errors,'valid':not errors}
def ident(p):return p+'_'+secrets.token_hex(8)
class Migrations:
 def __init__(self,s,books,retail):self.s,self.books,self.retail=s,books,retail
 def stage(self,wid,actor,kind,text,source_system):
  p=parse(kind,text);x='mbt_'+secrets.token_hex(8);status='validated' if p['valid'] else 'rejected'
  with self.s.tx():
   self.s._db.execute('INSERT INTO import_batches(id,workspace_id,kind,pack_version,source_system,source_hash,row_count,control_total_minor,status,errors_json,rows_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(x,wid,kind,PACK_VERSION,source_system,p['source_hash'],p['row_count'],p['control_total_minor'],status,canon(p['errors']),canon(p['rows']),actor,utcnow()));self.s._audit(wid,actor,'migration.stage',{'id':x,'kind':kind,'valid':p['valid'],'rows':p['row_count']})
  return {'id':x,'status':status,**{k:v for k,v in p.items() if k!='rows'}}
 def _mapped(self,wid,kind,external):
  r=self.s._db.execute('SELECT entity_id FROM import_entity_map WHERE workspace_id=? AND kind=? AND external_id=?',(wid,kind,external)).fetchone();return r['entity_id'] if r else None
 def _map(self,wid,kind,external,entity,batch):self.s._db.execute('INSERT INTO import_entity_map VALUES(?,?,?,?,?)',(wid,kind,external,entity,batch))
 def apply(self,wid,actor,batch_id):
  b=self.s._db.execute('SELECT * FROM import_batches WHERE id=? AND workspace_id=?',(batch_id,wid)).fetchone()
  if not b or b['status']!='validated':raise Conflict('validated migration batch required')
  rows=json.loads(b['rows_json']);made=[];actual=0
  with self.s.tx():
   for r in rows:
    if b['kind']=='products':
     x=ident('prd');self.s._db.execute('INSERT INTO retail_products(id,workspace_id,sku,name,unit,selling_price_minor,cost_minor) VALUES(?,?,?,?,?,?,?)',(x,wid,r['sku'],r['name'],'each',int(r['selling_price_minor']),int(r['cost_minor'])));self._map(wid,'products',r['sku'],x,batch_id);made.append({'table':'retail_products','id':x});actual+=int(r['selling_price_minor'])+int(r['cost_minor'])
    elif b['kind'] in ('customers','vendors'):
     x=ident('pty');kind='customer' if b['kind']=='customers' else 'vendor';self.s._db.execute('INSERT INTO parties(id,workspace_id,kind,name,created_at) VALUES(?,?,?,?,?)',(x,wid,kind,r['name'],utcnow()));self._map(wid,b['kind'],r['external_id'],x,batch_id);made.append({'table':'parties','id':x});
    elif b['kind']=='stock':
     product=self._mapped(wid,'products',r['sku']);loc=self.s._db.execute('SELECT id FROM locations WHERE workspace_id=? AND code=?',(wid,r['location_code'])).fetchone()
     if not product or not loc:raise Conflict('stock row requires imported product and existing location')
     x=ident('stk');self.s._db.execute('INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x,wid,product,loc['id'],utcnow(),r['quantity'],int(r['unit_cost_minor']),'opening','migration',batch_id+'-'+r['external_id'],actor,utcnow()));self._map(wid,'stock',r['external_id'],x,batch_id);made.append({'table':'stock_ledger','id':x,'product_id':product,'location_id':loc['id'],'quantity':r['quantity'],'unit_cost_minor':int(r['unit_cost_minor'])});actual+=int(r['unit_cost_minor'])
    elif b['kind'] in ('open_invoices','open_bills'):
     pk='customers' if b['kind']=='open_invoices' else 'vendors';ext=r['customer_external_id'] if pk=='customers' else r['vendor_external_id'];party=self._mapped(wid,pk,ext)
     if not party:raise Conflict('open document requires its customer or vendor pack first')
     x=ident('doc');kind='sales_invoice' if b['kind']=='open_invoices' else 'purchase_bill';number=('MIG-INV-' if kind=='sales_invoice' else 'MIG-BILL-')+r['external_id'];total=int(r['total_minor']);self.s._db.execute("INSERT INTO documents(id,workspace_id,kind,number,party_id,currency,issue_date,status,subtotal_minor,total_tax_minor,total_minor,balance_minor,memo,created_by,created_at) VALUES(?,?,?,?,?,(SELECT base_currency FROM accounting_settings WHERE workspace_id=?),?,'draft',?,0,?,?,?, ?,?)",(x,wid,kind,number,party,wid,r['issue_date'],total,total,total,'Imported opening document',actor,utcnow()));self.s._db.execute('INSERT INTO document_lines(id,document_id,position,description,quantity,unit_price_minor,net_minor,tax_minor,total_minor) VALUES(?,?,1,?,\'1\',?, ?,0,?)',(ident('dln'),x,'Imported opening balance',total,total,total));self._map(wid,b['kind'],r['external_id'],x,batch_id);made.append({'table':'documents','id':x});actual+=total
    else:raise Conflict('opening balances require accountant-reviewed journal import and are not auto-applied')
   status='reconciled' if actual==b['control_total_minor'] else 'variance';self.s._db.execute('UPDATE import_batches SET status=?,applied_json=?,applied_at=? WHERE id=?',(status,canon(made),utcnow(),batch_id));self.s._audit(wid,actor,'migration.apply',{'id':batch_id,'kind':b['kind'],'rows':len(rows),'expected':b['control_total_minor'],'actual':actual,'status':status})
  return {'id':batch_id,'status':status,'row_count':len(rows),'expected_control_total_minor':b['control_total_minor'],'actual_control_total_minor':actual}
 def rollback(self,wid,actor,batch_id):
  b=self.s._db.execute('SELECT * FROM import_batches WHERE id=? AND workspace_id=?',(batch_id,wid)).fetchone()
  if not b or b['status'] not in ('imported','reconciled','variance'):raise Conflict('applied migration batch required')
  made=json.loads(b['applied_json'])
  with self.s.tx():
   for x in reversed(made):
    if x['table']=='stock_ledger':
     rid=ident('stk');self.s._db.execute('INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,wid,x['product_id'],x['location_id'],utcnow(),str(-Decimal(x['quantity'])),x['unit_cost_minor'],'migration_rollback','migration_rollback',batch_id+'-'+x['id'],actor,utcnow()))
    elif x['table']=='retail_products':self.s._db.execute('UPDATE retail_products SET active=0 WHERE id=? AND workspace_id=?',(x['id'],wid))
    else:self.s._db.execute('DELETE FROM '+x['table']+' WHERE id=? AND workspace_id=?',(x['id'],wid))
   self.s._db.execute('DELETE FROM import_entity_map WHERE batch_id=?',(batch_id,));self.s._db.execute("UPDATE import_batches SET status='rolled_back',rolled_back_at=? WHERE id=?",(utcnow(),batch_id));self.s._audit(wid,actor,'migration.rollback',{'id':batch_id,'objects':len(made)})
  return {'id':batch_id,'status':'rolled_back','objects':len(made)}

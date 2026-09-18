"""Validation-first source migration packs with control totals and resumable batches."""
import csv,io,json,secrets
from store import canon,sha256,utcnow,Conflict
PACK_VERSION=1
SCHEMAS={
 'products':({'sku','name','selling_price_minor','cost_minor'},'sku'),
 'customers':({'name'},'external_id'),
 'vendors':({'name'},'external_id'),
 'opening_balances':({'account_code','balance_minor','normal'},'account_code'),
 'stock':({'sku','location_code','quantity','unit_cost_minor'},'external_id'),
 'open_invoices':({'external_id','customer_external_id','issue_date','total_minor'},'external_id'),
 'open_bills':({'external_id','vendor_external_id','issue_date','total_minor'},'external_id'),
}
def parse(kind,text):
 if kind not in SCHEMAS:raise ValueError('unsupported migration pack')
 required,key=SCHEMAS[kind];rows=list(csv.DictReader(io.StringIO(text)));errors=[];seen=set();control=0
 for n,r in enumerate(rows,2):
  miss=sorted(k for k in required if not (r.get(k) or '').strip())
  if miss:errors.append({'row':n,'error':'missing '+', '.join(miss)})
  identity=(r.get(key) or f'row-{n}').strip()
  if identity in seen:errors.append({'row':n,'error':'duplicate '+key+' '+identity})
  seen.add(identity)
  for amount in ('selling_price_minor','cost_minor','balance_minor','unit_cost_minor','total_minor'):
   if r.get(amount):
    try:control+=int(r[amount])
    except ValueError:errors.append({'row':n,'error':amount+' must be integer minor units'})
 return {'kind':kind,'pack_version':PACK_VERSION,'rows':rows,'row_count':len(rows),'control_total_minor':control,'source_hash':sha256(text),'errors':errors,'valid':not errors}
class Migrations:
 def __init__(self,s,books,retail):self.s,self.books,self.retail=s,books,retail
 def stage(self,wid,actor,kind,text,source_system):
  p=parse(kind,text);x='mbt_'+secrets.token_hex(8)
  with self.s.tx():self.s._db.execute('INSERT INTO import_batches(id,workspace_id,kind,pack_version,source_system,source_hash,row_count,control_total_minor,status,errors_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x,wid,kind,PACK_VERSION,source_system,p['source_hash'],p['row_count'],p['control_total_minor'],'validated' if p['valid'] else 'rejected',canon(p['errors']),actor,utcnow()));self.s._audit(wid,actor,'migration.stage',{'id':x,'kind':kind,'valid':p['valid'],'rows':p['row_count']})
  return {'id':x,'status':'validated' if p['valid'] else 'rejected',**{k:v for k,v in p.items() if k!='rows'}}

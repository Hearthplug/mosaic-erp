import tempfile,unittest
from store import Store
from accounting import Accounting
from retail import Retail
from migration_packs import parse,Migrations
class Packs(unittest.TestCase):
 def test_all_master_and_open_transaction_packs_validate(self):
  samples={'products':'sku,name,selling_price_minor,cost_minor\nA,Apple,100,60','customers':'external_id,name\nc1,Ada','vendors':'external_id,name\nv1,Supplier','opening_balances':'account_code,balance_minor,normal\n1000,500,debit','stock':'external_id,sku,location_code,quantity,unit_cost_minor\ns1,A,M,2,60','open_invoices':'external_id,customer_external_id,issue_date,total_minor\ni1,c1,2026-01-01,100','open_bills':'external_id,vendor_external_id,issue_date,total_minor\nb1,v1,2026-01-01,60'}
  for k,v in samples.items():self.assertTrue(parse(k,v)['valid'],k)
 def test_duplicate_and_bad_money_fail_closed_and_stage_audits(self):
  bad='sku,name,selling_price_minor,cost_minor\nA,X,no,1\nA,Y,2,1';self.assertFalse(parse('products',bad)['valid']);s=Store(tempfile.mktemp());w,_=s.create_workspace('X');m=Migrations(s,Accounting(s),None);x=m.stage(w,'owner','products',bad,'spreadsheet');self.assertEqual(x['status'],'rejected')
 def test_apply_reconcile_dependencies_and_rollback(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('X');a=Accounting(s);a.setup(w,'owner');r=Retail(s,a);loc=r.setup_location(w,'owner','M','Main');m=Migrations(s,a,r)
  customers=m.stage(w,'owner','customers','external_id,name\nc1,Ada','old');self.assertEqual(m.apply(w,'owner',customers['id'])['status'],'reconciled')
  products=m.stage(w,'owner','products','sku,name,selling_price_minor,cost_minor\nA,Apple,100,60','old');self.assertEqual(m.apply(w,'owner',products['id'])['actual_control_total_minor'],160)
  stock=m.stage(w,'owner','stock','external_id,sku,location_code,quantity,unit_cost_minor\ns1,A,M,2,60','old');self.assertEqual(m.apply(w,'owner',stock['id'])['status'],'reconciled')
  pid=s._db.execute("SELECT id FROM retail_products WHERE workspace_id=? AND sku='A'",(w,)).fetchone()['id'];self.assertEqual(r.stock(w,pid,loc['id']),2)
  self.assertEqual(m.rollback(w,'owner',stock['id'])['status'],'rolled_back');self.assertEqual(r.stock(w,pid,loc['id']),0)
  inv=m.stage(w,'owner','open_invoices','external_id,customer_external_id,issue_date,total_minor\ni1,c1,2026-01-01,100','old');self.assertEqual(m.apply(w,'owner',inv['id'])['status'],'reconciled')
 def test_apply_is_atomic_when_cross_file_reference_missing(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('X');a=Accounting(s);a.setup(w,'owner');r=Retail(s,a);r.setup_location(w,'owner','M','Main');m=Migrations(s,a,r)
  b=m.stage(w,'owner','stock','external_id,sku,location_code,quantity,unit_cost_minor\ns1,MISSING,M,2,60','old')
  with self.assertRaises(Exception):m.apply(w,'owner',b['id'])
  self.assertEqual(s._db.execute('SELECT COUNT(*) n FROM stock_ledger WHERE workspace_id=?',(w,)).fetchone()['n'],0)
  self.assertEqual(s._db.execute('SELECT status FROM import_batches WHERE id=?',(b['id'],)).fetchone()['status'],'validated')
if __name__=='__main__':unittest.main()

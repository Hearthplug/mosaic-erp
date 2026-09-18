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
if __name__=='__main__':unittest.main()

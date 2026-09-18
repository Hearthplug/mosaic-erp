import tempfile,unittest
from store import Store
from accounting import Accounting
from retail import Retail
class RetailFlow(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.w,_=self.s.create_workspace('Shop');self.a=Accounting(self.s);self.a.setup(self.w,'owner');self.r=Retail(self.s,self.a);self.l=self.r.setup_location(self.w,'owner','MAIN','Main')['id'];self.p=self.r.product(self.w,'owner','SKU1','Rice',500,300)['id'];self.v=self.a.create_party(self.w,'owner','vendor','Supplier')['id']
 def test_purchase_receive_sale_is_persistent(self):
  po=self.r.purchase_order(self.w,'buyer',self.v,self.l,'2026-09-17',[{'product_id':self.p,'quantity':'10','unit_cost_minor':300}]);self.r.approve_purchase(self.w,'owner',po['id']);line=self.s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id'];self.assertEqual(self.r.receive_purchase(self.w,'receiver',po['id'],{line:'10'})['status'],'received');self.assertEqual(self.r.stock(self.w,self.p,self.l),10)
  sale=self.r.complete_sale(self.w,'cashier',self.l,[{'product_id':self.p,'quantity':'2'}],[{'kind':'cash','amount_minor':1000}]);self.assertEqual(sale['total_minor'],1000);self.assertEqual(self.r.stock(self.w,self.p,self.l),8)
if __name__=='__main__':unittest.main()

class RetailControls(RetailFlow):
 def ready(self):
  po=self.r.purchase_order(self.w,'buyer',self.v,self.l,'2026-09-17',[{'product_id':self.p,'quantity':'10','unit_cost_minor':300}]);self.r.approve_purchase(self.w,'owner',po['id']);line=self.s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id'];self.r.receive_purchase(self.w,'receiver',po['id'],{line:'10'})
 def test_sale_posts_accounts_return_refund_and_cash_close(self):
  self.ready();cash=self.r.open_cash(self.w,'cashier',self.l,500);sale=self.r.complete_sale(self.w,'cashier',self.l,[{'product_id':self.p,'quantity':'2'}],[{'kind':'cash','amount_minor':1000}]);self.assertEqual(sale['cogs_minor'],600);line=self.s._db.execute('SELECT id FROM sale_lines WHERE sale_id=?',(sale['id'],)).fetchone()['id'];ret=self.r.return_sale(self.w,'cashier',sale['id'],{line:'1'},'customer changed mind','manager');self.assertEqual(ret['refund_minor'],500);self.assertEqual(self.r.stock(self.w,self.p,self.l),9);self.assertEqual(self.r.close_cash(self.w,'manager',cash['id'],1000)['variance_minor'],0);tb=self.a.trial_balance(self.w);self.assertEqual(tb['total_debit_minor'],tb['total_credit_minor'])
 def test_credit_transfer_count_reorder_and_export(self):
  self.ready();c=self.a.create_party(self.w,'owner','customer','Credit Buyer')['id'];self.r.set_credit(self.w,'owner',c,1000);self.assertTrue(self.r.check_credit(self.w,c,1000));other=self.r.setup_location(self.w,'owner','B','Branch')['id'];self.r.transfer(self.w,'manager',self.p,self.l,other,2);self.assertEqual(self.r.stock(self.w,self.p,other),2);self.r.count_stock(self.w,'counter',other,{self.p:'3'},'manager');self.assertEqual(self.r.stock(self.w,self.p,other),3);self.assertTrue(self.r.reorder(self.w,other,5));self.assertIn('sales',self.r.export_all(self.w))

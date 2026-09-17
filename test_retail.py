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

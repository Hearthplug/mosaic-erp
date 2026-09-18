import tempfile,unittest
from store import Store
from accounting import Accounting
from retail import Retail
class Recovery(unittest.TestCase):
 def test_backup_restore_and_continue(self):
  live=tempfile.mktemp();bak=tempfile.mktemp();s=Store(live);w,_=s.create_workspace('Shop');a=Accounting(s);a.setup(w,'owner');r=Retail(s,a);loc=r.setup_location(w,'owner','M','Main')['id'];p=r.product(w,'owner','A','A',500,300)['id'];r.move_stock(w,'owner',p,loc,5,300,'opening','opening','1');s.backup(bak);s.close();restored=tempfile.mktemp();Store.restore(bak,restored);s2=Store(restored);r2=Retail(s2,Accounting(s2));self.assertEqual(r2.stock(w,p,loc),5);sale=r2.complete_sale(w,'cashier',loc,[{'product_id':p,'quantity':'1'}],[{'kind':'cash','amount_minor':500}]);self.assertTrue(sale['journal_id']);self.assertEqual(r2.stock(w,p,loc),4)
if __name__=='__main__':unittest.main()

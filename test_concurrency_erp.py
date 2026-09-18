import tempfile,threading,unittest
from store import Store,Conflict
from accounting import Accounting
from retail import Retail
class C(unittest.TestCase):
 def test_concurrent_stock_never_oversells_and_numbers_unique(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('X');a=Accounting(s);a.setup(w,'o');r=Retail(s,a);l=r.setup_location(w,'o','M','M')['id'];p=r.product(w,'o','A','A',100,50)['id'];r.move_stock(w,'o',p,l,1,50,'opening','opening','1');out=[]
  def sell():
   try:out.append(r.complete_sale(w,'c',l,[{'product_id':p,'quantity':'1'}],[{'kind':'cash','amount_minor':100}])['number'])
   except Conflict:out.append('denied')
  ts=[threading.Thread(target=sell) for _ in range(2)];[x.start() for x in ts];[x.join() for x in ts];self.assertEqual(out.count('denied'),1);self.assertEqual(r.stock(w,p,l),0);self.assertEqual(len(set(x for x in out if x!='denied')),1)
if __name__=='__main__':unittest.main()

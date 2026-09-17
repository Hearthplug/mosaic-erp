import tempfile,unittest
from store import Store,Conflict
from rbac import RBAC,Denied
class R(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.w,_=self.s.create_workspace('X');self.r=RBAC(self.s)
 def test_denied_cross_location_threshold_state_and_revocation(self):
  a=self.r.assign(self.w,'owner','cashier','Cashier',['sale.create','refund.create'],['A'],{'refund.create_amount_minor':500,'refund.create_states':['completed']});self.assertTrue(self.r.check(self.w,'cashier','sale.create','A'))
  for kw in ({'location_id':'B'},{'location_id':'A','amount_minor':501},{'location_id':'A','amount_minor':100,'record_state':'draft'}):
   with self.assertRaises(Denied):self.r.check(self.w,'cashier','refund.create',**kw)
  self.r.revoke(self.w,'owner',a['id']);
  with self.assertRaises(Denied):self.r.check(self.w,'cashier','sale.create','A')
 def test_toxic_combination_requires_audited_emergency(self):
  with self.assertRaises(Conflict):self.r.assign(self.w,'owner','x','Bad',['purchase.create','purchase.approve'])
  self.assertTrue(self.r.assign(self.w,'owner','x','Emergency',['purchase.create','purchase.approve'],emergency=True)['emergency'])
if __name__=='__main__':unittest.main()

import tempfile,unittest
from store import Store
from operating_model import compile_model,OperatingModels
class Model(unittest.TestCase):
 def test_different_businesses_get_materially_different_erps(self):
  a=compile_model({'vertical':'Groceries or food','locations':'One place','stock_pain':'Expiry or batches','credit_behavior':'Everything is paid immediately','price_display':'Tax is included in the shown price','money_view':['Sales']});b=compile_model({'vertical':'Electronics','locations':'6 to 20 places','stock_pain':'Serial numbers or warranty','credit_behavior':'Customers and suppliers both use credit','price_display':'Tax is added at checkout','money_view':['Money customers owe','Branch comparison']});self.assertIn('expiry',a['settings']['modules']['value']);self.assertNotIn('transfers',a['settings']['modules']['value']);self.assertTrue({'serials','transfers','receivables'}<=set(b['settings']['modules']['value']));self.assertNotEqual(a['settings']['roles']['value'],b['settings']['roles']['value'])
 def test_provenance_rationale_and_toxic_combo(self):
  m=compile_model({'staff':'The same person buys and receives stock','price_display':'Tax is included in the shown price'});self.assertTrue(m['toxic_combinations']);self.assertTrue(m['settings']['roles']['provenance']);self.assertTrue(m['settings']['roles']['rationale'])
 def test_preview_diff_persists(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('X');o=OperatingModels(s);x=o.save(w,'owner',{'locations':'One place','price_display':'Tax is included in the shown price'});y=o.save(w,'owner',{'locations':'2 to 5 places','price_display':'Tax is included in the shown price'});self.assertIn('modules',y['diff']['changed']);self.assertEqual(y['version'],2)
if __name__=='__main__':unittest.main()

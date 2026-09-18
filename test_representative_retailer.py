import tempfile,unittest
from store import Store
from accounting import Accounting
from retail import Retail
from migration_packs import Migrations
class RepresentativeRetailer(unittest.TestCase):
 def test_move_in_buy_receive_sell_return_pay_close_report_recover(self):
  live=tempfile.mktemp();bak=tempfile.mktemp();s=Store(live);w,_=s.create_workspace("Representative shop");a=Accounting(s);a.setup(w,"owner");r=Retail(s,a);m=Migrations(s,a,r);loc=r.setup_location(w,"owner","MAIN","Main shop")["id"]
  for kind,csv in [("products","sku,name,selling_price_minor,cost_minor\nA,Apple,500,300"),("customers","external_id,name\nc1,Ada"),("vendors","external_id,name\nv1,Supplier")]:b=m.stage(w,"owner",kind,csv,"legacy");self.assertEqual(m.apply(w,"owner",b["id"])["status"],"reconciled")
  p=s._db.execute("SELECT id FROM retail_products WHERE workspace_id=? AND sku='A'",(w,)).fetchone()["id"];v=s._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind='vendor'",(w,)).fetchone()["id"]
  po=r.purchase_order(w,"buyer",v,loc,"2026-09-18",[{"product_id":p,"quantity":"10","unit_cost_minor":300}]);r.approve_purchase(w,"owner",po["id"]);line=s._db.execute("SELECT id FROM purchase_order_lines WHERE purchase_order_id=?",(po["id"],)).fetchone()["id"];self.assertEqual(r.receive_purchase(w,"receiver",po["id"],{line:"10"})["status"],"received")
  cash=r.open_cash(w,"cashier",loc,1000);sale=r.complete_sale(w,"cashier",loc,[{"product_id":p,"quantity":"2"}],[{"kind":"cash","amount_minor":1000}]);sl=s._db.execute("SELECT id FROM sale_lines WHERE sale_id=?",(sale["id"],)).fetchone()["id"];ret=r.return_sale(w,"cashier",sale["id"],{sl:"1"},"customer return","manager");self.assertEqual(ret["refund_minor"],500);self.assertEqual(r.close_cash(w,"owner",cash["id"],1500)["variance_minor"],0)
  tb=a.trial_balance(w);self.assertEqual(tb["total_debit_minor"],tb["total_credit_minor"]);self.assertTrue(a.financial_statements(w)["balance_sheet"]);self.assertEqual(r.stock(w,p,loc),9)
  s.backup(bak);s.close();rest=tempfile.mktemp();Store.restore(bak,rest);s2=Store(rest);self.assertEqual(Retail(s2,Accounting(s2)).stock(w,p,loc),9);self.assertTrue(s2.audit_trail(w))

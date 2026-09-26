"""Runs in CI against PostgreSQL 17 through a NOBYPASSRLS runtime role."""
import os,secrets,threading,unittest
@unittest.skipUnless(os.getenv('MOSAIC_TEST_POSTGRES_URL'),'requires CI PostgreSQL service')
class LivePG(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from psycopg.conninfo import conninfo_to_dict,make_conninfo
  from postgres_store import PostgresStore
  c.owner=PostgresStore(os.environ['MOSAIC_TEST_POSTGRES_URL'],1,4,True);c.role='mosaic_erp_runtime';secret=secrets.token_urlsafe(24)
  with c.owner._pool.connection() as q:
   q.execute(f'DROP ROLE IF EXISTS {c.role}');q.execute(f"CREATE ROLE {c.role} LOGIN PASSWORD '{secret}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS");q.execute(f'GRANT CONNECT ON DATABASE {q.info.dbname} TO {c.role}');q.execute(f'GRANT USAGE ON SCHEMA public TO {c.role}');q.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {c.role}');q.execute(f'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_auth_session(text) TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_login_options(text) TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_invitation(text) TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_session_workspace(text,text) TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_oauth_users(text,text,text) TO {c.role}');q.execute(f'GRANT EXECUTE ON FUNCTION mosaic_parent_workspace(text,text) TO {c.role}')
  parts=conninfo_to_dict(os.environ['MOSAIC_TEST_POSTGRES_URL']);parts.update(user=c.role,password=secret);c.s=PostgresStore(make_conninfo(**parts),1,8,False)
 @classmethod
 def tearDownClass(c):
  c.s.close()
  with c.owner._pool.connection() as q:q.execute(f'DROP OWNED BY {c.role}');q.execute(f'DROP ROLE IF EXISTS {c.role}')
  c.owner.close()
 def test_all_tables_created_rls_forced_and_cross_tenant_hidden(self):
  from postgres_erp_schema import ALL_ERP_TABLES
  with self.owner._pool.connection() as q:
   rows=q.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c WHERE c.relname=ANY(%s)",(list(ALL_ERP_TABLES),)).fetchall();self.assertEqual({r['relname'] for r in rows},ALL_ERP_TABLES);self.assertTrue(all(r['relrowsecurity'] and r['relforcerowsecurity'] for r in rows))
  wa,_=self.s.create_workspace('A');wb,_=self.s.create_workspace('B')
  with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wa,));self.s._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind,active) VALUES(?,?,?,?,?,?)',('loc_a',wa,'A','A','store',1))
  with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(wb,));self.assertIsNone(self.s._db.execute('SELECT id FROM locations WHERE id=?',('loc_a',)).fetchone())
 def test_advisory_lock_serializes_number_allocation(self):
  w,_=self.s.create_workspace('C');seen=[]
  def worker():
   with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(w,));self.s.accounting_lock(w,'number');seen.append(1)
  ts=[threading.Thread(target=worker) for _ in range(4)];[t.start() for t in ts];[t.join() for t in ts];self.assertEqual(len(seen),4)
 def test_combined_representative_retailer_runtime_chain(self):
  from accounting import Accounting
  from retail import Retail
  from rbac import RBAC,Denied
  from store import utcnow
  w,_=self.s.create_workspace('Representative PG retailer');a=Accounting(self.s);a.setup(w,'owner');r=Retail(self.s,a);rb=RBAC(self.s);loc=r.setup_location(w,'owner','MAIN','Main')['id'];vendor=a.create_party(w,'owner','vendor','Supplier')['id'];p=r.product(w,'owner','A','Apple',500,300)['id']
  rb.assign(w,'owner','cashier','Cashier',['sale.create','payment.accept']);
  with self.assertRaises(Denied):rb.check(w,'cashier','purchase.approve')
  self.assertTrue(rb.check(w,'cashier','sale.create'))
  po=r.purchase_order(w,'buyer',vendor,loc,'2026-09-18',[{'product_id':p,'quantity':'10','unit_cost_minor':300}]);r.approve_purchase(w,'owner',po['id']);line=self.s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id'];r.receive_purchase(w,'receiver',po['id'],{line:'10'})
  bill=a.create_document(w,'buyer','purchase_bill','2026-09-18',[{'description':'10 Apples','quantity':'10','unit_price_minor':300}],vendor,due_date='2026-10-18');a.approve_document(w,'owner',bill['id']);a.post_document(w,'owner',bill['id']);match=r.three_way_match(w,'owner',po['id'],bill['id']);self.assertEqual(match['status'],'matched');pay=a.record_payment(w,'accountant',bill['id'],3000,'2026-09-18');self.assertEqual(pay['remaining_minor'],0)
  cash=r.open_cash(w,'cashier',loc,1000);sale=r.complete_sale(w,'cashier',loc,[{'product_id':p,'quantity':'2'}],[{'kind':'cash','amount_minor':1000}]);self.assertEqual(r.close_cash(w,'owner',cash['id'],2000)['variance_minor'],0)
  bank=a._system(w,'bank');tx=a.import_bank_transactions(w,'accountant',bank,[{'posted_on':'2026-09-18','description':'Supplier payment','amount_minor':-3000,'external_id':'bank-1'}])[0];self.assertTrue(a.match_bank_transaction(w,'owner',tx['id'],pay['journal_id'])['matched'])
  period=a.add_period(w,'owner','September','2026-09-01','2026-09-30');a.lock_period(w,'owner',period['id']);
  with self.assertRaises(Exception):a.post_journal(w,'owner','2026-09-19','must fail',[{'account_id':a._system(w,'cash'),'debit_minor':1},{'account_id':a._system(w,'sales'),'credit_minor':1}])
  before=a.trial_balance(w);self.assertEqual(before['total_debit_minor'],before['total_credit_minor'])
  with self.assertRaises(RuntimeError):
   with self.s.tx():self.s._db.execute("SELECT set_config('mosaic.workspace_id',%s,true)",(w,));self.s._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind,active) VALUES(?,?,?,?,?,?)',('loc_fail',w,'FAIL','Fail','store',1));raise RuntimeError('induced failure')
  self.assertIsNone(self.s._db.execute('SELECT id FROM locations WHERE id=? AND workspace_id=?',('loc_fail',w)).fetchone())
  # Reconnect proves committed state survives process-style pool reuse. Operator restore remains externally managed.
  from postgres_store import PostgresStore
  reopened=PostgresStore(self.s.path,1,2,False)
  try:self.assertEqual(Retail(reopened,Accounting(reopened)).stock(w,p,loc),8);self.assertEqual(Accounting(reopened).trial_balance(w)['total_debit_minor'],before['total_debit_minor'])
  finally:reopened.close()
 def _retailer(self,name):
  from accounting import Accounting
  from retail import Retail
  w,_=self.s.create_workspace(name);a=Accounting(self.s);a.setup(w,'owner');r=Retail(self.s,a);loc=r.setup_location(w,'owner','MAIN','Main')['id'];vendor=a.create_party(w,'owner','vendor','Supplier')['id'];product=r.product(w,'owner','A','Apple',500,300)['id'];return w,a,r,loc,vendor,product
 def test_competing_commands_prevent_oversell_overreceipt_and_double_settlement(self):
  from retail import Retail
  from accounting import Accounting
  from store import Conflict
  w,a,r,loc,vendor,p=self._retailer('Concurrent retailer');r.move_stock(w,'owner',p,loc,1,300,'opening','opening','one')
  def race(call):
   barrier=threading.Barrier(2);out=[]
   def go():
    try:barrier.wait();call();out.append('ok')
    except Conflict:out.append('denied')
   ts=[threading.Thread(target=go) for _ in range(2)];[t.start() for t in ts];[t.join(10) for t in ts];self.assertFalse(any(t.is_alive() for t in ts));self.assertEqual(sorted(out),['denied','ok'])
  race(lambda:Retail(self.s,Accounting(self.s)).complete_sale(w,'cashier',loc,[{'product_id':p,'quantity':'1'}],[{'kind':'cash','amount_minor':500}]))
  self.assertEqual(r.stock(w,p,loc),0);self.assertEqual(self.s._db.execute('SELECT COUNT(*) n FROM sales WHERE workspace_id=?',(w,)).fetchone()['n'],1)
  po=r.purchase_order(w,'buyer',vendor,loc,'2026-09-18',[{'product_id':p,'quantity':'10','unit_cost_minor':300}]);r.approve_purchase(w,'owner',po['id']);line=self.s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id']
  race(lambda:Retail(self.s,Accounting(self.s)).receive_purchase(w,'receiver',po['id'],{line:'10'}))
  self.assertEqual(r.stock(w,p,loc),10);self.assertEqual(str(self.s._db.execute('SELECT received_quantity FROM purchase_order_lines WHERE id=? AND purchase_order_id=?',(line,po['id'])).fetchone()['received_quantity']),'10')
  bill=a.create_document(w,'buyer','purchase_bill','2026-09-18',[{'description':'Stock','quantity':'10','unit_price_minor':300}],vendor);a.approve_document(w,'owner',bill['id']);a.post_document(w,'owner',bill['id'])
  race(lambda:Accounting(self.s).record_payment(w,'accountant',bill['id'],3000,'2026-09-18'))
  self.assertEqual(self.s._db.execute('SELECT balance_minor FROM documents WHERE id=? AND workspace_id=?',(bill['id'],w)).fetchone()['balance_minor'],0);self.assertEqual(self.s._db.execute('SELECT COUNT(*) n FROM settlements WHERE workspace_id=? AND target_document_id=?',(w,bill['id'])).fetchone()['n'],1)
 def test_period_lock_wins_before_waiting_post(self):
  from accounting import Accounting
  from store import Conflict
  w,a,r,loc,vendor,p=self._retailer('Period race');period=a.add_period(w,'owner','September','2026-09-01','2026-09-30');cash=a._system(w,'cash');sales=a._system(w,'sales');out=[]
  with self.s.tx():
   self.s.accounting_lock(w,'period')
   def post():
    try:Accounting(self.s).post_journal(w,'owner','2026-09-18','racing',[{'account_id':cash,'debit_minor':1},{'account_id':sales,'credit_minor':1}]);out.append('posted')
    except Conflict:out.append('denied')
   t=threading.Thread(target=post);t.start();a.lock_period(w,'owner',period['id'])
  t.join(10);self.assertFalse(t.is_alive());self.assertEqual(out,['denied']);self.assertEqual(self.s._db.execute("SELECT COUNT(*) n FROM journals WHERE workspace_id=? AND description='racing'",(w,)).fetchone()['n'],0)
 def test_mid_command_failures_roll_back_receipt_sale_and_payment(self):
  from store import Conflict
  w,a,r,loc,vendor,p=self._retailer('Failure retailer');original=self.s._audit
  def fail(action):
   def injected(wid,actor,actual,detail):
    if actual==action:raise RuntimeError('injected '+action)
    return original(wid,actor,actual,detail)
   return injected
  po=r.purchase_order(w,'buyer',vendor,loc,'2026-09-18',[{'product_id':p,'quantity':'2','unit_cost_minor':300}]);r.approve_purchase(w,'owner',po['id']);line=self.s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id'];self.s._audit=fail('purchase.receive')
  with self.assertRaises(RuntimeError):r.receive_purchase(w,'receiver',po['id'],{line:'2'})
  self.s._audit=original;self.assertEqual(r.stock(w,p,loc),0);self.assertEqual(str(self.s._db.execute('SELECT received_quantity FROM purchase_order_lines WHERE id=? AND purchase_order_id=?',(line,po['id'])).fetchone()['received_quantity']),'0')
  r.move_stock(w,'owner',p,loc,1,300,'opening','opening','seed');self.s._audit=fail('sale.complete')
  with self.assertRaises(RuntimeError):r.complete_sale(w,'cashier',loc,[{'product_id':p,'quantity':'1'}],[{'kind':'cash','amount_minor':500}])
  self.s._audit=original;self.assertEqual(r.stock(w,p,loc),1);self.assertEqual(self.s._db.execute('SELECT COUNT(*) n FROM sales WHERE workspace_id=?',(w,)).fetchone()['n'],0)
  bill=a.create_document(w,'buyer','purchase_bill','2026-09-18',[{'description':'Stock','quantity':'1','unit_price_minor':300}],vendor);a.approve_document(w,'owner',bill['id']);a.post_document(w,'owner',bill['id']);before=self.s._db.execute('SELECT COUNT(*) n FROM documents WHERE workspace_id=?',(w,)).fetchone()['n'];self.s._audit=fail('settlement.create')
  with self.assertRaises(RuntimeError):a.record_payment(w,'accountant',bill['id'],300,'2026-09-18')
  self.s._audit=original;self.assertEqual(self.s._db.execute('SELECT balance_minor FROM documents WHERE id=? AND workspace_id=?',(bill['id'],w)).fetchone()['balance_minor'],300);self.assertEqual(self.s._db.execute('SELECT COUNT(*) n FROM documents WHERE workspace_id=?',(w,)).fetchone()['n'],before);self.assertEqual(self.s._db.execute('SELECT COUNT(*) n FROM settlements WHERE workspace_id=?',(w,)).fetchone()['n'],0)
if __name__=='__main__':unittest.main()

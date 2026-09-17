from __future__ import annotations
import tempfile, unittest
from store import Store, Conflict
from accounting import Accounting

class AccountingCase(unittest.TestCase):
 def setUp(self):
  self.s=Store(tempfile.mktemp(suffix='.db')); self.w,self.k=self.s.create_workspace('Books'); self.a=Accounting(self.s); self.a.setup(self.w,'owner','USD'); self.a.add_period(self.w,'owner','FY26','2026-01-01','2026-12-31')
 def account(self,key): return self.s._db.execute('SELECT id FROM accounts WHERE workspace_id=? AND system_key=?',(self.w,key)).fetchone()['id']
 def test_journal_balances_and_is_immutable(self):
  j=self.a.post_journal(self.w,'owner','2026-01-02','Capital',[{'account_id':self.account('cash'),'debit_minor':10000},{'account_id':self.account('equity'),'credit_minor':10000}])
  tb=self.a.trial_balance(self.w); self.assertEqual(tb['total_debit_minor'],tb['total_credit_minor'])
  with self.assertRaises(Exception): self.s._db.execute("UPDATE journals SET description='x' WHERE id=?",(j['id'],))
 def test_reversal_not_deletion(self):
  j=self.a.post_journal(self.w,'owner','2026-01-02','Mistake',[{'account_id':self.account('cash'),'debit_minor':500},{'account_id':self.account('expense'),'credit_minor':500}])
  self.a.reverse_journal(self.w,'owner',j['id'],'2026-01-03','wrong account'); self.assertEqual(self.a.trial_balance(self.w)['total_debit_minor'],1000)
  with self.assertRaises(Conflict): self.a.reverse_journal(self.w,'owner',j['id'],'2026-01-04','again')
 def test_period_lock_blocks_posting(self):
  p=self.s._db.execute('SELECT id FROM fiscal_periods WHERE workspace_id=?',(self.w,)).fetchone()['id']; self.a.lock_period(self.w,'owner',p)
  with self.assertRaises(Conflict): self.a.post_journal(self.w,'owner','2026-02-01','No',[{'account_id':self.account('cash'),'debit_minor':1},{'account_id':self.account('equity'),'credit_minor':1}])
 def test_invoice_posts_receivable_sales_and_tax(self):
  customer=self.a.create_party(self.w,'owner','customer','Ada Shop'); tax=self.a.add_tax_code(self.w,'owner','VAT10','VAT 10%',10,verified=True)
  self.a.verify(self.w,'owner','CPA Example','checked setup')
  d=self.a.create_document(self.w,'cashier','sales_invoice','2026-04-01',[{'description':'Goods','quantity':'2','unit_price_minor':1000,'tax_code_id':tax['id']}],party_id=customer['id'])
  self.assertEqual(d['total_minor'],2200); self.a.approve_document(self.w,'manager',d['id']); self.a.post_document(self.w,'accountant',d['id'])
  tb=self.a.trial_balance(self.w); self.assertEqual(tb['total_debit_minor'],2200); self.assertEqual(tb['total_credit_minor'],2200)
 def test_material_change_invalidates_signoff(self):
  self.a.verify(self.w,'owner','CPA Example'); self.assertEqual(self.a.status(self.w)['verification_state'],'verified')
  self.a.change_settings(self.w,'owner',{'base_currency':'INR'}); self.assertEqual(self.a.status(self.w)['verification_state'],'invalidated')
 def test_csv_dry_run_rejects_bad_rows(self):
  x=self.a.import_csv(self.w,'owner','accounts','code,name,type\n1,Cash,bad',True); self.assertFalse(x['valid']); self.assertEqual(x['errors'][0]['row'],2)
 def test_reports(self):
  self.a.post_journal(self.w,'owner','2026-01-02','Capital',[{'account_id':self.account('cash'),'debit_minor':10000},{'account_id':self.account('equity'),'credit_minor':10000}])
  gl=self.a.general_ledger(self.w,self.account('cash')); self.assertEqual(gl['ending_balance_minor'],10000); self.assertIn('balance_sheet',self.a.financial_statements(self.w,to_date='2026-12-31'))

if __name__=='__main__': unittest.main()

class ExtendedAccountingCase(AccountingCase):
 def test_opening_balances_payment_aging_and_fx(self):
  self.a.opening_balance(self.w,'owner','2026-01-01',[{'account_id':self.account('cash'),'balance_minor':5000}],approved_by='accountant')
  customer=self.a.create_party(self.w,'owner','customer','Buyer'); d=self.a.create_document(self.w,'owner','sales_invoice','2026-01-05',[{'description':'Sale','unit_price_minor':1000}],party_id=customer['id'],due_date='2026-01-10',currency='EUR',exchange_rate='1.1'); self.a.approve_document(self.w,'manager',d['id']); self.a.post_document(self.w,'owner',d['id'])
  pay=self.a.record_payment(self.w,'owner',d['id'],400,'2026-02-15',exchange_rate='1.2'); self.assertEqual(pay['remaining_minor'],600); self.assertEqual(pay['realized_fx_minor'],40)
  self.assertEqual(self.a.aging(self.w,'2026-02-15')['buckets']['31_60'],600)
 def test_inventory_bank_migration_and_acceptance_controls(self):
  item='itm_x'; self.s._db.execute("INSERT INTO items(id,workspace_id,sku,name) VALUES(?,?,?,?)",(item,self.w,'A','A'))
  self.a.record_inventory_movement(self.w,'owner',item,'2026-01-01','3',250,'receipt'); self.assertEqual(self.a.inventory_valuation(self.w)['total_value_minor'],750)
  bank=self.account('bank'); tx=self.a.import_bank_transactions(self.w,'owner',bank,[{'posted_on':'2026-01-02','description':'Deposit','amount_minor':100,'external_id':'x'}])[0]
  j=self.a.post_journal(self.w,'owner','2026-01-02','Deposit',[{'account_id':bank,'debit_minor':100},{'account_id':self.account('equity'),'credit_minor':100}]); self.assertTrue(self.a.match_bank_transaction(self.w,'owner',tx['id'],j['id'])['matched'])
  self.assertEqual(self.a.migration_reconciliation(self.w,'owner','legacy',2,100,90)['status'],'variance')
  expected={'trial_balance':self.a.trial_balance(self.w)}; self.assertEqual(self.a.run_acceptance(self.w,'accountant','sample',expected)['status'],'passed')
 def test_statutory_adapter_defaults_closed(self):
  x=self.a.configure_statutory_adapter(self.w,'owner','IN','e-invoice','2026-01'); self.assertEqual(x['status'],'disabled')

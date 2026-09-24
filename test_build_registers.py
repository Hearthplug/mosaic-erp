"""Slice 4: credit book, supplier ledger and stock register imports."""
import unittest
from store import Store
from accounting import Accounting
import build_registers


def _store():
    import tempfile
    s = Store(tempfile.mktemp(suffix='.db'))
    wid, _ = s.create_workspace('Test Co')
    books = Accounting(s)
    books.setup(wid, 'owner', 'USD')
    books.add_period(wid, 'owner', 'FY26', '2026-01-01', '2026-12-31')
    return s, wid, books


BOOK_EXTRACTION = {
    'document_type': 'customer credit book',
    'fields': [
        {'name': 'name', 'value': 'Ravi Kumar', 'confidence': 0.9},
        {'name': 'balance', 'value': '$300.00', 'confidence': 0.85},
    ],
    'lines': [
        {'description': '12 Sep - rice and oil', 'quantity': '', 'unit_price': '', 'amount': '$500.00'},
        {'description': '15 Sep - paid', 'quantity': '', 'unit_price': '', 'amount': '$200.00'},
    ],
    'summary': 'A credit book page',
}

STOCK_EXTRACTION = {
    'document_type': 'stock register',
    'fields': [{'name': 'total value', 'value': '$99.00', 'confidence': 0.8}],
    'lines': [
        {'description': 'Rice 25kg', 'quantity': '4', 'unit_price': '$18.00', 'amount': '$72.00'},
        {'description': 'Oil 5L', 'quantity': '3', 'unit_price': '$9.00', 'amount': '$27.00'},
    ],
    'summary': 'A stock register page',
}


class Draft(unittest.TestCase):
    def test_book_draft_reads_party_entries_and_balance(self):
        s, wid, books = _store()
        d = build_registers.draft_from_extraction(s, wid, 'credit_book', BOOK_EXTRACTION)
        self.assertEqual(d['party'], 'Ravi Kumar')
        self.assertEqual(d['stated_balance_minor'], 30000)
        self.assertEqual(len(d['entries']), 2)
        self.assertEqual(d['entries'][0]['kind'], 'credit')
        self.assertEqual(d['entries'][1]['kind'], 'payment')

    def test_stock_draft_reads_items(self):
        s, wid, books = _store()
        d = build_registers.draft_from_extraction(s, wid, 'stock_register', STOCK_EXTRACTION)
        self.assertEqual(len(d['items']), 2)
        self.assertEqual(d['items'][0]['unit_cost_minor'], 1800)
        self.assertEqual(d['stated_total_minor'], 9900)

    def test_csv_draft_groups_parties_and_balances(self):
        s, wid, books = _store()
        csv_text = 'name,date,detail,amount,type,balance\nRavi,2026-09-12,rice,500,credit,300\nRavi,2026-09-15,paid,200,payment,300\nMeena,2026-09-10,oil,150,credit,150\n'
        d = build_registers.draft_from_csv(s, wid, 'credit_book', csv_text)
        self.assertEqual(len(d['entries']), 3)
        self.assertEqual(d['stated_balances'], {'Ravi': 30000, 'Meena': 15000})
        self.assertEqual(d['entries'][0]['date'], '2026-09-12')

    def test_csv_draft_rejects_empty_sheet(self):
        s, wid, books = _store()
        with self.assertRaises(ValueError):
            build_registers.draft_from_csv(s, wid, 'credit_book', 'a,b\n1,2\n')


class RecordBook(unittest.TestCase):
    def test_dated_history_records_invoices_and_payment(self):
        s, wid, books = _store()
        payload = {'register': 'credit_book', 'stated_balance_minor': 30000, 'entries': [
            {'party': 'Ravi', 'date': '2026-09-12', 'detail': 'rice and oil', 'kind': 'credit', 'amount_minor': 50000},
            {'party': 'Ravi', 'date': '2026-09-15', 'detail': 'paid', 'kind': 'payment', 'amount_minor': 20000}]}
        r = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(r['recorded'][0]['documents'], 1)
        self.assertTrue(r['recorded'][0]['dated_history'])
        docs = books.list_documents(wid, kind='sales_invoice')['documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['balance_minor'], 30000)

    def test_undated_records_one_opening_document(self):
        s, wid, books = _store()
        payload = {'register': 'supplier_ledger', 'stated_balance_minor': 42000, 'entries': [
            {'party': 'Harbor Wholesale', 'date': '', 'detail': 'sacks', 'kind': 'credit', 'amount_minor': 42000}]}
        r = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(r['recorded'][0]['documents'], 1)
        docs = books.list_documents(wid, kind='purchase_bill')['documents']
        self.assertEqual(docs[0]['balance_minor'], 42000)
        detail = books.get_document(wid, docs[0]['id'])
        self.assertIn('Opening balance', detail['lines'][0]['description'])

    def test_running_balance_mismatch_fails_closed(self):
        s, wid, books = _store()
        payload = {'register': 'credit_book', 'stated_balance_minor': 99999, 'entries': [
            {'party': 'Ravi', 'date': '2026-09-12', 'detail': 'rice', 'kind': 'credit', 'amount_minor': 50000}]}
        with self.assertRaises(ValueError):
            build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(books.list_documents(wid, kind='sales_invoice')['documents'], [])
        self.assertIsNone(s._db.execute("SELECT id FROM parties WHERE workspace_id=? AND name='Ravi'", (wid,)).fetchone())

    def test_missing_stated_balance_fails(self):
        s, wid, books = _store()
        payload = {'register': 'credit_book', 'entries': [
            {'party': 'Ravi', 'date': '', 'detail': 'rice', 'kind': 'credit', 'amount_minor': 500}]}
        with self.assertRaises(ValueError):
            build_registers.record_register(s, books, wid, 'o@t.co', payload)

    def test_multi_party_csv_style(self):
        s, wid, books = _store()
        payload = {'register': 'credit_book',
                   'stated_balances': {'Ravi': 30000, 'Meena': 15000},
                   'entries': [
                       {'party': 'Ravi', 'date': '2026-09-12', 'detail': 'rice', 'kind': 'credit', 'amount_minor': 50000},
                       {'party': 'Ravi', 'date': '2026-09-15', 'detail': 'paid', 'kind': 'payment', 'amount_minor': 20000},
                       {'party': 'Meena', 'date': '2026-09-10', 'detail': 'oil', 'kind': 'credit', 'amount_minor': 15000}]}
        r = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(len(r['recorded']), 2)
        docs = books.list_documents(wid, kind='sales_invoice')['documents']
        self.assertEqual(sum(d['balance_minor'] for d in docs), 45000)


class RecordStock(unittest.TestCase):
    def test_stock_lands_as_opening_quantities(self):
        s, wid, books = _store()
        payload = {'register': 'stock_register', 'stated_total_minor': 9900, 'items': [
            {'item': 'Rice 25kg', 'quantity': '4', 'unit_cost_minor': 1800},
            {'item': 'Oil 5L', 'quantity': '3', 'unit_cost_minor': 900}]}
        r = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(len(r['recorded']), 2)
        rows = s._db.execute("SELECT quantity_delta, kind FROM stock_ledger WHERE workspace_id=?", (wid,)).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['kind'] == 'opening' for row in rows))
        prod = s._db.execute("SELECT sku FROM retail_products WHERE workspace_id=? AND name='Rice 25kg'", (wid,)).fetchone()
        self.assertIsNotNone(prod)

    def test_stock_total_mismatch_fails_closed(self):
        s, wid, books = _store()
        payload = {'register': 'stock_register', 'stated_total_minor': 1, 'items': [
            {'item': 'Rice 25kg', 'quantity': '4', 'unit_cost_minor': 1800}]}
        with self.assertRaises(ValueError):
            build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(s._db.execute("SELECT count(*) c FROM stock_ledger WHERE workspace_id=?", (wid,)).fetchone()['c'], 0)

    def test_stock_without_stated_total_records(self):
        s, wid, books = _store()
        payload = {'register': 'stock_register', 'items': [
            {'item': 'Rice 25kg', 'quantity': '4', 'unit_cost_minor': 0}]}
        r = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(r['total_minor'], 0)

    def test_stock_register_can_be_recorded_twice(self):
        s, wid, books = _store()
        payload = {'register': 'stock_register', 'stated_total_minor': None,
                   'items': [{'item': 'Rice 25kg', 'quantity': '4', 'unit_cost_minor': 1800}]}
        build_registers.record_register(s, books, wid, 'o@t.co', payload)
        r2 = build_registers.record_register(s, books, wid, 'o@t.co', payload)
        self.assertEqual(len(r2['recorded']), 1)

class LeadingDateSplit(unittest.TestCase):
    def test_leading_date_is_split_from_detail(self):
        from datetime import date
        today = date.today()
        iso, rest = build_registers._strip_leading_date('12 Sep - rice and oil', today)
        y = today.year if date(today.year, 9, 12) <= today else today.year - 1
        self.assertEqual(iso, date(y, 9, 12).isoformat())
        self.assertEqual(rest, 'rice and oil')
        iso2, rest2 = build_registers._strip_leading_date('2026-09-10: cartons', today)
        self.assertEqual(iso2, '2026-09-10')
        self.assertEqual(rest2, 'cartons')
        iso3, rest3 = build_registers._strip_leading_date('rice and oil', today)
        self.assertEqual(iso3, '')
        self.assertEqual(rest3, 'rice and oil')

    def test_draft_splits_dates_out_of_book_lines(self):
        s, wid, books = _store()
        extraction = {'document_type': 'customer credit book',
                      'fields': [{'name': 'name', 'value': 'Ravi Kumar'}, {'name': 'balance', 'value': '$300.00'}],
                      'lines': [{'description': '12 Sep - rice and oil', 'amount': '$500.00'},
                                {'description': '15 Sep - paid', 'amount': '$200.00'}]}
        d = build_registers.draft_from_extraction(s, wid, 'credit_book', extraction)
        self.assertTrue(d['entries'][0]['date'].endswith('-09-12'))
        self.assertEqual(d['entries'][0]['detail'], 'rice and oil')
        self.assertEqual(d['entries'][1]['kind'], 'payment')


if __name__ == '__main__':
    unittest.main()
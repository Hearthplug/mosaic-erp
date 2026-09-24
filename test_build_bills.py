"""Slice 2: supplier-bill recording from photo extractions."""
import unittest
from store import Store
from accounting import Accounting
import build_bills


class AmountParse(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(build_bills.amount_minor('1234.50'), 123450)
    def test_currency_commas(self):
        self.assertEqual(build_bills.amount_minor('$1,234.50'), 123450)
    def test_decimal_comma(self):
        self.assertEqual(build_bills.amount_minor('48,30'), 4830)
    def test_thousands(self):
        self.assertEqual(build_bills.amount_minor('12,000'), 1200000)
    def test_garbage(self):
        self.assertIsNone(build_bills.amount_minor(''))
        self.assertIsNone(build_bills.amount_minor(None))
        self.assertIsNone(build_bills.amount_minor('abc'))


def _store():
    import tempfile
    s = Store(tempfile.mktemp(suffix='.db'))
    wid, _ = s.create_workspace('Test Co')
    books = Accounting(s)
    books.setup(wid, 'owner', 'USD')
    books.add_period(wid, 'owner', 'FY26', '2026-01-01', '2026-12-31')
    return s, wid


EXTRACTION = {
    'document_type': 'supplier invoice',
    'fields': [
        {'name': 'vendor', 'value': 'Fresh Farms', 'confidence': 0.9},
        {'name': 'invoice number', 'value': 'FF-1042', 'confidence': 0.8},
        {'name': 'date', 'value': '2026-09-20', 'confidence': 0.9},
        {'name': 'total', 'value': '$48.30', 'confidence': 0.7},
    ],
    'lines': [
        {'description': 'Tomatoes 10kg', 'quantity': '10', 'unit_price': '$2.40', 'amount': '$24.00'},
        {'description': 'Onions 9kg', 'quantity': '9', 'unit_price': '$2.70', 'amount': '$24.30'},
    ],
    'summary': 'A supplier invoice',
}


class Draft(unittest.TestCase):
    def test_draft_maps_fields_and_lines(self):
        s, wid = _store()
        d = build_bills.draft_from_extraction(s, wid, EXTRACTION)
        self.assertEqual(d['vendor'], 'Fresh Farms')
        self.assertTrue(d['vendor_new'])
        self.assertEqual(d['stated_total_minor'], 4830)
        self.assertEqual(len(d['lines']), 2)
        self.assertEqual(d['lines'][0]['unit_price_minor'], 240)

    def test_draft_matches_existing_vendor(self):
        s, wid = _store()
        books = Accounting(s)
        books.create_party(wid, 'o@t.co', 'vendor', 'Fresh Farms')
        d = build_bills.draft_from_extraction(s, wid, EXTRACTION)
        self.assertFalse(d['vendor_new'])
        self.assertEqual(d['vendor_match']['name'], 'Fresh Farms')

    def test_draft_warns_on_missing_total(self):
        s, wid = _store()
        ex = dict(EXTRACTION, fields=[f for f in EXTRACTION['fields'] if f['name'] != 'total'])
        d = build_bills.draft_from_extraction(s, wid, ex)
        self.assertIsNone(d['stated_total_minor'])
        self.assertTrue(any('total' in w for w in d['warnings']))


class Record(unittest.TestCase):
    def test_record_creates_posted_bill_and_vendor(self):
        s, wid = _store()
        books = Accounting(s)
        d = build_bills.draft_from_extraction(s, wid, EXTRACTION)
        payload = {'vendor': d['vendor'], 'number': d['number'], 'issue_date': d['issue_date'],
                   'stated_total_minor': d['stated_total_minor'],
                   'lines': [{'description': l['description'], 'quantity': l['quantity'], 'unit_price_minor': l['unit_price_minor']} for l in d['lines']]}
        r = build_bills.record_bill(s, books, wid, 'o@t.co', payload)
        self.assertEqual(r['status'], 'posted')
        self.assertEqual(r['total_minor'], 4830)
        party = s._db.execute("SELECT * FROM parties WHERE workspace_id=? AND name='Fresh Farms'", (wid,)).fetchone()
        self.assertIsNotNone(party)

    def test_record_stores_plain_quantities(self):
        s, wid = _store()
        books = Accounting(s)
        payload = {'vendor': 'Fresh Farms', 'stated_total_minor': 2650,
                   'lines': [{'description': 'Tomatoes', 'quantity': '10', 'unit_price_minor': 240},
                             {'description': 'Onions', 'quantity': '2.5', 'unit_price_minor': 100}]}
        r = build_bills.record_bill(s, books, wid, 'o@t.co', payload)
        rows = s._db.execute('SELECT quantity FROM document_lines WHERE document_id=? ORDER BY position', (r['id'],)).fetchall()
        self.assertEqual([row['quantity'] for row in rows], ['10', '2.5'])

    def test_record_rejects_mismatched_total(self):
        s, wid = _store()
        books = Accounting(s)
        payload = {'vendor': 'Fresh Farms', 'stated_total_minor': 9999,
                   'lines': [{'description': 'Tomatoes', 'quantity': '10', 'unit_price_minor': 240}]}
        with self.assertRaises(ValueError):
            build_bills.record_bill(s, books, wid, 'o@t.co', payload)

    def test_record_rejects_bad_date(self):
        s, wid = _store()
        books = Accounting(s)
        payload = {'vendor': 'Fresh Farms', 'issue_date': '20 Sep', 'stated_total_minor': 2400,
                   'lines': [{'description': 'Tomatoes', 'quantity': '10', 'unit_price_minor': 240}]}
        with self.assertRaises(ValueError):
            build_bills.record_bill(s, books, wid, 'o@t.co', payload)

    def test_record_rejects_empty_lines(self):
        s, wid = _store()
        books = Accounting(s)
        with self.assertRaises(ValueError):
            build_bills.record_bill(s, books, wid, 'o@t.co', {'vendor': 'X', 'stated_total_minor': 100, 'lines': []})

    def test_record_rejects_missing_vendor(self):
        s, wid = _store()
        books = Accounting(s)
        with self.assertRaises(ValueError):
            build_bills.record_bill(s, books, wid, 'o@t.co', {'vendor': '', 'stated_total_minor': 100,
                                                              'lines': [{'description': 'A', 'quantity': '1', 'unit_price_minor': 100}]})

class DocumentViews(unittest.TestCase):
    def _bill(self):
        s, wid = _store()
        books = Accounting(s)
        d = build_bills.draft_from_extraction(s, wid, EXTRACTION)
        payload = {'vendor': d['vendor'], 'number': d['number'], 'issue_date': d['issue_date'],
                   'stated_total_minor': d['stated_total_minor'],
                   'lines': [{'description': l['description'], 'quantity': l['quantity'], 'unit_price_minor': l['unit_price_minor']} for l in d['lines']]}
        r = build_bills.record_bill(s, books, wid, 'o@t.co', payload)
        return s, wid, books, r

    def test_list_documents_shows_bill_with_vendor(self):
        s, wid, books, r = self._bill()
        listing = books.list_documents(wid, kind='purchase_bill')
        self.assertEqual(len(listing['documents']), 1)
        b = listing['documents'][0]
        self.assertEqual(b['id'], r['id'])
        self.assertEqual(b['number'], r['number'])
        self.assertEqual(b['party_name'], 'Fresh Farms')
        self.assertEqual(b['total_minor'], 4830)
        self.assertEqual(b['balance_minor'], 4830)

    def test_get_document_has_lines_and_no_payments(self):
        s, wid, books, r = self._bill()
        doc = books.get_document(wid, r['id'])
        self.assertEqual(doc['party_name'], 'Fresh Farms')
        self.assertEqual(len(doc['lines']), 2)
        self.assertEqual(doc['lines'][0]['description'], 'Tomatoes 10kg')
        self.assertEqual(doc['lines'][0]['total_minor'], 2400)
        self.assertEqual(doc['payments'], [])

    def test_get_document_lists_payments_and_balance(self):
        s, wid, books, r = self._bill()
        books.record_payment(wid, 'o@t.co', r['id'], 2000, '2026-09-21')
        doc = books.get_document(wid, r['id'])
        self.assertEqual(doc['balance_minor'], 2830)
        self.assertEqual(len(doc['payments']), 1)
        self.assertEqual(doc['payments'][0]['amount_minor'], 2000)
        self.assertEqual(doc['payments'][0]['paid_on'], '2026-09-21')

    def test_get_document_unknown_id_fails(self):
        s, wid, books, r = self._bill()
        from store import NotFound
        with self.assertRaises(NotFound):
            books.get_document(wid, 'doc-does-not-exist')

    def test_list_documents_rejects_bad_kind(self):
        s, wid, books, r = self._bill()
        with self.assertRaises(ValueError):
            books.list_documents(wid, kind='nonsense')


if __name__ == '__main__':
    unittest.main()

"""Slice 5: evening close - day summary, saved closes, changed-since detection."""
import unittest
from datetime import date, timedelta
from store import utcnow
from store import Store
from accounting import Accounting
import dayclose

TODAY = utcnow()[:10]  # app convention: server UTC date is 'today'
YESTERDAY = (date.fromisoformat(TODAY) - timedelta(days=1)).isoformat()


def _store():
    import tempfile
    s = Store(tempfile.mktemp(suffix='.db'))
    wid, _ = s.create_workspace('Test Co')
    books = Accounting(s)
    books.setup(wid, 'owner', 'USD')
    books.add_period(wid, 'owner', 'FY26', '2026-01-01', '2026-12-31')
    return s, wid, books


def _invoice(books, wid, total, day):
    doc = books.create_document(wid, 'o@t.co', 'sales_invoice', day,
                                [{'description': 'sale', 'quantity': '1', 'unit_price_minor': total}])
    books.approve_document(wid, 'o@t.co', doc['id'])
    books.post_document(wid, 'o@t.co', doc['id'])
    return doc


def _cash_account(s, wid):
    return s._db.execute("SELECT id FROM accounts WHERE workspace_id=? AND system_key='cash'", (wid,)).fetchone()['id']


class DaySummary(unittest.TestCase):
    def test_empty_day_is_zeroes(self):
        s, wid, books = _store()
        d = dayclose.day_summary(s, wid, TODAY)
        self.assertEqual(d['sales_total_minor'], 0)
        self.assertEqual(d['payments_cash_minor'], 0)
        self.assertEqual(d['expected_cash_minor'], 0)

    def test_counts_only_that_day(self):
        s, wid, books = _store()
        inv = _invoice(books, wid, 10000, TODAY)
        _invoice(books, wid, 5000, YESTERDAY)
        books.record_payment(wid, 'o@t.co', inv['id'], 4000, TODAY)  # defaults to bank
        books.record_payment(wid, 'o@t.co', inv['id'], 3000, TODAY, bank_account_id=_cash_account(s, wid))
        d = dayclose.day_summary(s, wid, TODAY)
        self.assertEqual(d['sales_total_minor'], 10000)
        self.assertEqual(d['sales_count'], 1)
        self.assertEqual(d['payments_bank_minor'], 4000)
        self.assertEqual(d['payments_cash_minor'], 3000)
        self.assertEqual(d['credit_minor'], 3000)  # 10000 - 7000 paid
        self.assertEqual(d['expected_cash_minor'], 3000)

    def test_items_sold_from_stock_ledger(self):
        s, wid, books = _store()
        s._db.execute("INSERT INTO retail_products(id,workspace_id,sku,name,unit,selling_price_minor,cost_minor) VALUES('p1',?,'R1','Rice','each',0,0)", (wid,))
        s._db.execute("INSERT INTO locations(id,workspace_id,code,name,kind) VALUES('l1',?,'MAIN','Main','store')", (wid,))
        from store import utcnow
        s._db.execute("INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES('s1',?,'p1','l1',?, '-5',0,'sale','sale','x','o@t.co',?)", (wid, utcnow(), utcnow()))
        d = dayclose.day_summary(s, wid, TODAY)
        self.assertEqual(d['items_sold'], 5)


class SaveAndList(unittest.TestCase):
    def test_save_then_list_matches(self):
        s, wid, books = _store()
        inv = _invoice(books, wid, 10000, TODAY)
        books.record_payment(wid, 'o@t.co', inv['id'], 3000, TODAY, bank_account_id=_cash_account(s, wid))
        r = dayclose.save_close(s, wid, 'o@t.co', TODAY, 3500, 'all good')
        self.assertEqual(r['difference_minor'], 500)
        closes = dayclose.list_closes(s, wid)
        self.assertEqual(len(closes), 1)
        self.assertEqual(closes[0]['counted_cash_minor'], 3500)
        self.assertEqual(closes[0]['note'], 'all good')
        self.assertFalse(closes[0]['changed_since_close'])

    def test_late_edit_marks_close_changed(self):
        s, wid, books = _store()
        _invoice(books, wid, 10000, TODAY)
        dayclose.save_close(s, wid, 'o@t.co', TODAY, 0, '')
        _invoice(books, wid, 2000, TODAY)  # late edit after close
        closes = dayclose.list_closes(s, wid)
        self.assertTrue(closes[0]['changed_since_close'])

    def test_reclosing_replaces(self):
        s, wid, books = _store()
        dayclose.save_close(s, wid, 'o@t.co', TODAY, 100, 'first')
        dayclose.save_close(s, wid, 'o@t.co', TODAY, 200, 'second')
        closes = dayclose.list_closes(s, wid)
        self.assertEqual(len(closes), 1)
        self.assertEqual(closes[0]['counted_cash_minor'], 200)
        self.assertEqual(closes[0]['note'], 'second')

    def test_validation(self):
        s, wid, books = _store()
        with self.assertRaises(ValueError):
            dayclose.save_close(s, wid, 'o@t.co', 'not-a-date', 100)
        with self.assertRaises(ValueError):
            dayclose.save_close(s, wid, 'o@t.co', (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat(), 100)
        with self.assertRaises(ValueError):
            dayclose.save_close(s, wid, 'o@t.co', TODAY, -5)
        with self.assertRaises(ValueError):
            dayclose.save_close(s, wid, 'o@t.co', TODAY, 'lots')
        with self.assertRaises(ValueError):
            dayclose.day_summary(s, wid, '25/09/2026')


if __name__ == '__main__':
    unittest.main()

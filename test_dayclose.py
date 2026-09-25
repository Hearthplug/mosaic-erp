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


class StoreTimezone(unittest.TestCase):
    def test_defaults_and_setting(self):
        s, wid, books = _store()
        self.assertEqual(dayclose.store_timezone(s, wid), 'UTC')  # no prefs, no config
        dayclose.set_timezone(s, wid, 'o@t.co', 'Asia/Kolkata')
        self.assertEqual(store_timezone := dayclose.store_timezone(s, wid), 'Asia/Kolkata')
        with self.assertRaises(ValueError):
            dayclose.set_timezone(s, wid, 'o@t.co', 'Not/AZone')

    def test_items_follow_store_local_day(self):
        s, wid, books = _store()
        dayclose.set_timezone(s, wid, 'o@t.co', 'Asia/Kolkata')
        s._db.execute("INSERT INTO retail_products(id,workspace_id,sku,name,unit,selling_price_minor,cost_minor) VALUES('p1',?,'R1','Rice','each',0,0)", (wid,))
        s._db.execute("INSERT INTO locations(id,workspace_id,code,name,kind) VALUES('l1',?,'MAIN','Main','store')", (wid,))
        # 2026-09-24 23:30 UTC = 2026-09-25 05:00 in Kolkata: belongs to the 25th locally
        s._db.execute("INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES('s1',?,'p1','l1','2026-09-24T23:30:00+00:00','-4',0,'sale','sale','x','o@t.co','2026-09-24T23:30:00+00:00')", (wid,))
        self.assertEqual(dayclose.day_summary(s, wid, '2026-09-24')['items_sold'], 0)
        self.assertEqual(dayclose.day_summary(s, wid, '2026-09-25')['items_sold'], 4)

    def test_country_default(self):
        s, wid, books = _store()
        import store as store_mod, json as _json
        from store import canon, sha256, utcnow
        cfg = {'answers': {'country': 'India'}, 'config': {}}
        checksum = sha256(canon(cfg['config']))
        s._db.execute('INSERT INTO config_versions(workspace_id,version,answers_json,config_json,checksum,summary,actor_key_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (wid, 1, _json.dumps(cfg['answers']), canon(cfg['config']), checksum, '', 'k', utcnow()))
        s._db.commit()
        self.assertEqual(dayclose.store_timezone(s, wid), 'Asia/Kolkata')


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



class PosSalesInSummaryTest(unittest.TestCase):
    """Counter sales through the till create no documents; the close summary must still count them."""

    def _pos(self):
        from retail import Retail
        s, wid, books = _store()
        r = Retail(s, books)
        loc = r.setup_location(wid, 'owner', 'MAIN', 'Main')['id']
        prod = r.product(wid, 'owner', 'SKU1', 'Rice', 500, 300)['id']
        vendor = books.create_party(wid, 'owner', 'vendor', 'Supplier')['id']
        po = r.purchase_order(wid, 'buyer', vendor, loc, TODAY, [{'product_id': prod, 'quantity': '10', 'unit_cost_minor': 300}])
        r.approve_purchase(wid, 'owner', po['id'])
        line = s._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?', (po['id'],)).fetchone()['id']
        r.receive_purchase(wid, 'receiver', po['id'], {line: '10'})
        return s, wid, books, r, loc, prod

    def test_pos_only_day_counts_sales_tenders_and_items(self):
        s, wid, books, r, loc, prod = self._pos()
        r.open_cash(wid, 'cashier', loc, 10000)
        r.complete_sale(wid, 'cashier', loc, [{'product_id': prod, 'quantity': '2'}], [{'kind': 'cash', 'amount_minor': 1000}])
        r.complete_sale(wid, 'cashier', loc, [{'product_id': prod, 'quantity': '1'}], [{'kind': 'card', 'amount_minor': 500}])
        summary = dayclose.day_summary(s, wid, TODAY)
        self.assertEqual(summary['sales_count'], 2)
        self.assertEqual(summary['sales_total_minor'], 1500)
        self.assertEqual(summary['payments_cash_minor'], 1000)
        self.assertEqual(summary['payments_bank_minor'], 500)
        self.assertEqual(summary['items_sold'], 3)
        self.assertEqual(summary['expected_cash_minor'], 1000)

    def test_invoice_and_pos_same_day_add_without_double_counting(self):
        s, wid, books, r, loc, prod = self._pos()
        cash_id = s._db.execute("SELECT id FROM accounts WHERE workspace_id=? AND system_key='cash'", (wid,)).fetchone()['id']
        doc = books.create_document(wid, 'o@t.co', 'sales_invoice', TODAY,
            [{'description': 'Invoice sale', 'quantity': '1', 'unit_price_minor': 2000}], memo='Invoice sale')
        books.approve_document(wid, 'o@t.co', doc['id'])
        books.post_document(wid, 'o@t.co', doc['id'])
        books.record_payment(wid, 'o@t.co', doc['id'], 2000, TODAY, bank_account_id=cash_id)
        r.complete_sale(wid, 'cashier', loc, [{'product_id': prod, 'quantity': '1'}], [{'kind': 'cash', 'amount_minor': 500}])
        summary = dayclose.day_summary(s, wid, TODAY)
        self.assertEqual(summary['sales_count'], 2)
        self.assertEqual(summary['sales_total_minor'], 2500)
        self.assertEqual(summary['payments_cash_minor'], 2500)
        self.assertEqual(summary['expected_cash_minor'], 2500)


if __name__ == '__main__':
    unittest.main()

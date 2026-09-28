"""Chat-built dashboards: pinned plain-language questions re-run live on the Today screen."""
import json, os, tempfile, threading, unittest, urllib.request, urllib.error
os.environ['MOSAIC_DB_PATH'] = tempfile.mktemp(); os.environ['MOSAIC_RATE_LIMIT_RPM'] = '1000'
import app
import custom_report as cr


def call(port, method, path, body=None, key=None):
    d = json.dumps(body).encode() if body is not None else None
    h = {'Content-Type': 'application/json'}
    if key: h['Authorization'] = 'Bearer ' + key
    r = urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=d, headers=h, method=method))
    return r.status, json.loads(r.read() or b'{}')


def err(port, method, path, body=None, key=None):
    try:
        call(port, method, path, body, key)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')
    raise AssertionError('expected an HTTP error')


class Series(unittest.TestCase):
    """raw=True series mirrors the formatted rows, so bars match the table."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.db'); os.close(fd)
        import store as st
        self.store = st.Store(self.path)
        self.wid, _ = self.store.create_workspace('Dash Shop')

    def tearDown(self):
        self.store.close(); os.unlink(self.path)

    def test_empty_workspace_series(self):
        parsed = cr.parse('sales by item this month')
        title, sub, cols, rows, totals, series = cr.run(self.store, self.wid, parsed, 'USD', raw=True)
        self.assertEqual(title, 'Sales by item')
        self.assertEqual(series, [])
        card = cr.card(self.store, self.wid, parsed, 'USD')
        self.assertEqual(card['series'], [])
        self.assertEqual(card['row_count'], 0)
        self.assertEqual(card['totals'][-1], '$0.00')

    def test_legacy_five_tuple_unchanged(self):
        parsed = cr.parse('stock by store')
        out = cr.run(self.store, self.wid, parsed, 'USD')
        self.assertEqual(len(out), 5)


class API(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        from http.server import ThreadingHTTPServer
        c.s = ThreadingHTTPServer(('127.0.0.1', 0), app.H); c.p = c.s.server_address[1]
        threading.Thread(target=c.s.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(c): c.s.shutdown()

    def _shop(self, name='Dash API Shop'):
        _, w = call(self.p, 'POST', '/api/workspaces', {'name': name})
        k = w['api_key']
        call(self.p, 'POST', '/api/accounting/setup', {'base_currency': 'USD'}, k)
        return w, k

    def _sale(self, k):
        _, l = call(self.p, 'POST', '/api/retail/locations', {'code': 'MAIN', 'name': 'Main'}, k)
        _, v = call(self.p, 'POST', '/api/accounting/parties', {'kind': 'vendor', 'name': 'Supplier'}, k)
        _, p = call(self.p, 'POST', '/api/retail/products', {'sku': 'A', 'name': 'Apples', 'selling_price_minor': 500, 'cost_minor': 300}, k)
        _, po = call(self.p, 'POST', '/api/retail/purchases', {'vendor_id': v['id'], 'location_id': l['id'], 'ordered_on': '2026-09-28', 'lines': [{'product_id': p['id'], 'quantity': '5', 'unit_cost_minor': 300}]}, k)
        call(self.p, 'POST', '/api/retail/purchases/approve', {'purchase_order_id': po['id']}, k)
        line = app.STORE._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?', (po['id'],)).fetchone()['id']
        call(self.p, 'POST', '/api/retail/purchases/receive', {'purchase_order_id': po['id'], 'received': {line: '5'}}, k)
        _, sale = call(self.p, 'POST', '/api/retail/sales', {'location_id': l['id'], 'lines': [{'product_id': p['id'], 'quantity': '2'}], 'tenders': [{'kind': 'cash', 'amount_minor': 1000}]}, k)
        return sale

    def test_create_list_delete_roundtrip(self):
        w, k = self._shop()
        self._sale(k)
        status, card = call(self.p, 'POST', '/api/dashboards', {'query': 'sales by item this month'}, k)
        self.assertEqual(status, 201)
        self.assertEqual(card['title'], 'Sales by item')
        self.assertEqual(card['name'], 'Sales by item')
        self.assertTrue(card['id'].startswith('dash_'))
        self.assertEqual(len(card['series']), 1)
        self.assertEqual(card['series'][0]['label'], 'Apples')
        self.assertEqual(card['series'][0]['value'], 1000)
        self.assertEqual(card['series'][0]['display'], '$10.00')
        self.assertEqual(card['totals'][-1], '$10.00')
        _, listing = call(self.p, 'GET', '/api/dashboards', key=k)
        self.assertEqual(len(listing['dashboards']), 1)
        self.assertEqual(listing['dashboards'][0]['id'], card['id'])
        self.assertEqual(listing['dashboards'][0]['series'][0]['value'], 1000)  # re-run live
        _, gone = call(self.p, 'POST', '/api/dashboards/delete', {'id': card['id']}, k)
        self.assertTrue(gone['deleted'])
        _, listing = call(self.p, 'GET', '/api/dashboards', key=k)
        self.assertEqual(listing['dashboards'], [])

    def test_clarify_and_empty_query_save_nothing(self):
        w, k = self._shop('Clarify Shop')
        status, d = call(self.p, 'POST', '/api/dashboards', {'query': 'xyzzy blorp'}, k)
        self.assertEqual(status, 200)
        self.assertIn('clarify', d)
        self.assertIn('examples', d)
        code, d = err(self.p, 'POST', '/api/dashboards', {'query': '   '}, k)
        self.assertEqual(code, 400)
        _, listing = call(self.p, 'GET', '/api/dashboards', key=k)
        self.assertEqual(listing['dashboards'], [])

    def test_workspace_isolation_and_auth(self):
        w1, k1 = self._shop('Iso One')
        _, card = call(self.p, 'POST', '/api/dashboards', {'query': 'stock by store'}, k1)
        w2, k2 = self._shop('Iso Two')
        _, listing = call(self.p, 'GET', '/api/dashboards', key=k2)
        self.assertEqual(listing['dashboards'], [])
        # Another workspace cannot delete it (delete is scoped by workspace).
        call(self.p, 'POST', '/api/dashboards/delete', {'id': card['id']}, k2)
        _, listing = call(self.p, 'GET', '/api/dashboards', key=k1)
        self.assertEqual(len(listing['dashboards']), 1)
        for method, path, body in (('GET', '/api/dashboards', None), ('POST', '/api/dashboards', {'query': 'stock by store'}), ('POST', '/api/dashboards/delete', {'id': card['id']})):
            code, _ = err(self.p, method, path, body)
            self.assertEqual(code, 401)

    def test_twelve_dashboard_cap(self):
        w, k = self._shop('Cap Shop')
        queries = ['sales by item this month', 'sales by store this week', 'sales by day this month', 'sales by customer this month',
                   'purchases by supplier', 'purchases by store', 'stock by store', 'what I owe each supplier',
                   'customers owe', 'sales by item last month', 'sales by store last month', 'sales by day last month']
        for q in queries:
            status, _ = call(self.p, 'POST', '/api/dashboards', {'query': q}, k)
            self.assertEqual(status, 201, q)
        code, d = err(self.p, 'POST', '/api/dashboards', {'query': 'sales by item today'}, k)
        self.assertEqual(code, 400)
        self.assertIn('12 dashboards', d['error'])


if __name__ == '__main__':
    unittest.main()

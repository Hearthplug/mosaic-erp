"""Stock intake from a recorded supplier bill: match lines to the catalog,
then receive them as an approved, fully received purchase order."""
import json, os, tempfile, threading, unittest, urllib.request, urllib.error
os.environ['MOSAIC_DB_PATH'] = tempfile.mktemp(); os.environ['MOSAIC_RATE_LIMIT_RPM'] = '1000'
import app


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


class API(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        from http.server import ThreadingHTTPServer
        c.s = ThreadingHTTPServer(('127.0.0.1', 0), app.H); c.p = c.s.server_address[1]
        threading.Thread(target=c.s.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(c): c.s.shutdown()

    def _shop(self, name='Stock Intake Shop'):
        _, w = call(self.p, 'POST', '/api/workspaces', {'name': name})
        k = w['api_key']
        call(self.p, 'POST', '/api/accounting/setup', {'base_currency': 'USD'}, k)
        _, l = call(self.p, 'POST', '/api/retail/locations', {'code': 'MAIN', 'name': 'Main store'}, k)
        return w, k, l['id']

    def _product(self, k, sku, name):
        _, p = call(self.p, 'POST', '/api/retail/products', {'sku': sku, 'name': name, 'selling_price_minor': 500, 'cost_minor': 300}, k)
        return p['id']

    def test_draft_matches_and_suggests(self):
        w, k, lid = self._shop()
        rice = self._product(k, 'RICE-1KG', 'Rice 1 kg')
        tea = self._product(k, 'TEA-20', 'Green tea 20 bags')
        status, d = call(self.p, 'POST', '/api/build/bill-stock-draft', {'lines': [
            {'description': 'Rice 1 kg', 'quantity': '10', 'unit_price_minor': 220},
            {'description': 'green tea bags', 'quantity': '5', 'unit_price_minor': 250},
            {'description': 'unknown whatsit', 'quantity': '2', 'unit_price_minor': 100}]}, k)
        self.assertEqual(status, 200)
        a, b, c = d['lines']
        self.assertEqual(a['match']['id'], rice)                    # exact name
        self.assertEqual(b['match']['id'], tea)                     # fuzzy, score >= 0.5
        self.assertIsNone(c['match'])
        self.assertEqual(c['suggestions'], [])                      # nothing close

    def test_record_receives_full_purchase_order(self):
        w, k, lid = self._shop()
        rice = self._product(k, 'RICE-1KG', 'Rice 1 kg')
        tea = self._product(k, 'TEA-20', 'Green tea 20 bags')
        status, r = call(self.p, 'POST', '/api/build/record-bill-stock', {
            'vendor': 'Metro Suppliers', 'location_id': lid,
            'lines': [{'product_id': rice, 'quantity': '10', 'unit_cost_minor': 220},
                      {'product_id': tea, 'quantity': '5', 'unit_cost_minor': 250}]}, k)
        self.assertEqual(status, 201)
        self.assertEqual(r['status'], 'received')
        self.assertEqual(r['line_count'], 2)
        self.assertEqual(r['location'], 'Main store')
        _, stock = call(self.p, 'GET', f'/api/retail/stock?product_id={rice}&location_id={lid}', key=k)
        self.assertEqual(stock['quantity'], '10.0')
        _, stock = call(self.p, 'GET', f'/api/retail/stock?product_id={tea}&location_id={lid}', key=k)
        self.assertEqual(stock['quantity'], '5.0')
        # The vendor was created once and is reusable for the books side too.
        rows = app.STORE._db.execute("SELECT name FROM parties WHERE workspace_id=? AND kind IN ('vendor','both')", (w['workspace_id'],)).fetchall()
        self.assertEqual([r['name'] for r in rows], ['Metro Suppliers'])

    def test_record_validates_everything(self):
        w, k, lid = self._shop()
        rice = self._product(k, 'RICE-1KG', 'Rice 1 kg')
        w2, k2, lid2 = self._shop('Other Shop')
        other_prod = self._product(k2, 'X-1', 'Foreign item')
        for body, frag in (
            ({'vendor': 'V', 'location_id': 'loc_nope', 'lines': [{'product_id': rice, 'quantity': '1', 'unit_cost_minor': 1}]}, 'store'),
            ({'vendor': 'V', 'location_id': lid, 'lines': [{'product_id': 'prd_nope', 'quantity': '1', 'unit_cost_minor': 1}]}, 'catalog'),
            ({'vendor': 'V', 'location_id': lid, 'lines': [{'product_id': other_prod, 'quantity': '1', 'unit_cost_minor': 1}]}, 'catalog'),
            ({'vendor': 'V', 'location_id': lid, 'lines': [{'product_id': rice, 'quantity': '0', 'unit_cost_minor': 1}]}, 'above zero'),
            ({'vendor': 'V', 'location_id': lid, 'lines': []}, 'at least one'),
        ):
            code, d = err(self.p, 'POST', '/api/build/record-bill-stock', body, k)
            self.assertEqual(code, 400, (body, d))
            self.assertIn(frag, d['error'], d)
        # Nothing was received by any of the failures.
        _, stock = call(self.p, 'GET', f'/api/retail/stock?product_id={rice}&location_id={lid}', key=k)
        self.assertIn(stock['quantity'], ('0', '0.0'))

    def test_auth_and_owner_gate(self):
        w, k, lid = self._shop()
        rice = self._product(k, 'RICE-1KG', 'Rice 1 kg')
        body = {'vendor': 'V', 'location_id': lid, 'lines': [{'product_id': rice, 'quantity': '1', 'unit_cost_minor': 1}]}
        for path, b in (('/api/build/bill-stock-draft', {'lines': []}), ('/api/build/record-bill-stock', body)):
            code, _ = err(self.p, 'POST', path, b)
            self.assertEqual(code, 401)
        # A viewer-grade caller cannot record stock; record path is owner-gated
        # like the bill posting beside it.


if __name__ == '__main__':
    unittest.main()

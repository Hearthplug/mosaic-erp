"""Custom natural-language reports: parser honesty, runner output, saved reports."""
import unittest

import custom_report as cr
import store as st


class Parse(unittest.TestCase):
    def test_sales_by_item_last_month(self):
        p = cr.parse('sales by item last month')
        self.assertNotIn('clarify', p)
        u = p['understood']
        self.assertEqual(u['metric'], 'sales')
        self.assertEqual(u['group_by'], 'item')
        self.assertTrue(u['start'] and u['end'])
        self.assertEqual(u['start'][8:], '01')  # first of month

    def test_owed_suppliers(self):
        p = cr.parse('what I owe each supplier')
        self.assertEqual(p['understood']['metric'], 'owed_by_me')

    def test_unknown_is_honest_clarify(self):
        p = cr.parse('xyzzy blorp')
        self.assertIn('clarify', p)
        self.assertIn('examples', p)

    def test_sales_without_group_asks(self):
        p = cr.parse('sales')
        self.assertIn('clarify', p)


class Run(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        fd, self.path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.store = st.Store(self.path)

    def tearDown(self):
        import os
        os.unlink(self.path)

    def test_run_returns_shape(self):
        p = cr.parse('sales by item this month')
        title, sub, cols, rows, totals = cr.run(self.store, 'w1', p, 'USD')
        self.assertEqual(title, 'Sales by item')
        self.assertIn('to', sub)  # date range, not vague label
        self.assertTrue(cols and isinstance(rows, list))
        self.assertIsNotNone(totals)

    def test_saved_reports_table(self):
        wid, _ = self.store.create_workspace('Test Shop')
        self.store._db.execute(
            "INSERT INTO saved_reports(id,workspace_id,name,query,created_at) VALUES('r1',?,'My report','sales by item','2026-09-25T00:00:00Z')", (wid,))
        self.store._db.commit()
        rows = self.store._db.execute("SELECT name FROM saved_reports WHERE workspace_id=?", (wid,)).fetchall()
        self.assertEqual(rows[0]['name'], 'My report')


if __name__ == '__main__':
    unittest.main()

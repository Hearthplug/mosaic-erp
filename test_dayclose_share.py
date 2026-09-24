"""Slice 6: close share text."""
import unittest
import dayclose_share

SUMMARY = {'date': '2026-09-24', 'sales_total_minor': 40070, 'sales_count': 3,
           'payments_cash_minor': 10000, 'payments_bank_minor': 9620,
           'credit_minor': 20450, 'items_sold': 14, 'expected_cash_minor': 15000}


class ShareText(unittest.TestCase):
    def test_full_message_with_close(self):
        close = {'counted_cash_minor': 15700, 'difference_minor': 700, 'note': 'Kept float aside'}
        text = dayclose_share.close_share_text(SUMMARY, close, 'USD')
        self.assertIn('Day close - 2026-09-24', text)
        self.assertIn('Sales: USD 400.70 (3 sales)', text)
        self.assertIn('Payments in: USD 196.20 (cash USD 100.00, bank USD 96.20)', text)
        self.assertIn('Sold on credit (still owed): USD 204.50', text)
        self.assertIn('Items sold: 14', text)
        self.assertIn('Cash counted: USD 157.00 (USD 7.00 over the books)', text)
        self.assertIn('Note: Kept float aside', text)

    def test_matches_and_no_credit(self):
        s = dict(SUMMARY, credit_minor=0, items_sold=0, sales_count=1)
        close = {'counted_cash_minor': 15000, 'difference_minor': 0, 'note': ''}
        text = dayclose_share.close_share_text(s, close, 'USD')
        self.assertIn('1 sale)', text)
        self.assertIn('Cash counted: USD 150.00 (matches the books)', text)
        self.assertNotIn('credit', text)
        self.assertNotIn('Items sold', text)
        self.assertNotIn('Note:', text)

    def test_short_and_no_close(self):
        close = {'counted_cash_minor': 100, 'difference_minor': -200, 'note': ''}
        text = dayclose_share.close_share_text(SUMMARY, close, 'USD')
        self.assertIn('Cash counted: USD 1.00 (USD 2.00 short of the books)', text)
        text2 = dayclose_share.close_share_text(SUMMARY, None, 'USD')
        self.assertNotIn('Cash counted', text2)


if __name__ == '__main__':
    unittest.main()

import unittest
from operating_model import compile_model
from branding import theme
class Brand(unittest.TestCase):
 def test_brand_is_inferred_but_controls_unchanged(self):
  m=compile_model({'brand_style':'Warm and welcoming','brand_colors':'#114422 and #FFCC33','logo':'Yes, I will upload it','screen_preference':'Start selling','price_display':'Tax is included in the shown price'});t=theme(m);self.assertEqual(t['primary'],'#114422');self.assertEqual(t['logo_status'],'pending_upload');self.assertIn('sale.create',m['settings']['roles']['value']['Cashier']);self.assertIn('branding',m['settings'])
if __name__=='__main__':unittest.main()

import unittest
from operating_model import compile_model
from business_twin import preview
class Twin(unittest.TestCase):
 def test_plain_consequences_and_credit_contradiction(self):
  m=compile_model({'credit_behavior':'Everything is paid immediately','price_display':'Tax is included in the shown price'});x=preview(m,{'kind':'sale','payment':'later'});self.assertFalse(x['post_allowed']);self.assertIn('Confirm whether customer credit really happens',x['blocks'][0]);self.assertIn('Post sales, tax and cost entries',x['effects'])
 def test_rule_change_is_versioned_not_retroactive(self):
  m=compile_model({'price_display':'Tax is included in the shown price'});x=preview(m,{'kind':'rule_change'});self.assertIn('Keep old transactions on their original rule version',x['effects'])
if __name__=='__main__':unittest.main()

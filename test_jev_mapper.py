import unittest
from jev_mapper import map_interview, map_text_field, looks_non_english, AUTO_ACCEPT
from jev_reconfigure import propose_change
from jev_client import MockJevClient

NORTHSTAR = {'business_name':'northstar general store',
 'selling':'Customer walks in, cashier scans items, pays cash',
 'buying':'I decide what to buy myself and check what arrives',
 'discounts':'small ones are fine, manager above 10 percent',
 'returns':'refund cash if unopened within 7 days',
 'staff':'me and two cashiers',
 'country':'we are registered in India',
 'exceptions':'deliveries that arrive short',
 'goal':'stop running out of oat milk'}

class InterviewMapping(unittest.TestCase):
    def test_clear_answers_auto_accept(self):
        r = map_interview(NORTHSTAR, MockJevClient())
        by = {p['key']: p for p in r['proposals']}
        self.assertEqual(by['selling']['proposed'], 'Walk-in checkout, pays on the spot')
        self.assertEqual(by['buying']['proposed'], 'Owner decides and checks deliveries')
        self.assertEqual(by['returns']['proposed'], 'Refund and restock if unopened')
        self.assertGreaterEqual(by['selling']['confidence'], AUTO_ACCEPT)
        self.assertEqual(r['client'], 'mock')

    def test_raw_is_always_preserved_side_by_side(self):
        r = map_interview(NORTHSTAR, MockJevClient())
        for p in r['proposals']:
            self.assertEqual(p['raw'], NORTHSTAR[p['key']].strip())

    def test_non_english_routes_to_owner_confirm(self):
        r = map_interview({'selling':'nous livrons et le client paie a la livraison chaque semaine'}, MockJevClient())
        p = r['proposals'][0]
        self.assertEqual(p['status'], 'non_english')
        self.assertEqual(p['confidence'], 0.0)
        self.assertEqual(p['proposed'], p['raw'])

    def test_vague_answer_asks_instead_of_guessing(self):
        p = map_text_field('selling', 'it depends on the day really', MockJevClient())
        self.assertIn(p['status'], ('confirm','blank_confirm'))

    def test_country_maps_currency(self):
        p = map_text_field('country', 'registered in India', MockJevClient())
        self.assertEqual((p['proposed'], p['currency']), ('India','INR'))
        p = map_text_field('country', 'somewhere far away', MockJevClient())
        self.assertEqual(p['status'], 'blank_confirm')

    def test_unanswered_is_empty_not_invented(self):
        p = map_text_field('goal', '', MockJevClient())
        self.assertEqual((p['status'], p['proposed']), ('empty',''))

class Reconfiguration(unittest.TestCase):
    def test_multi_change_request(self):
        r = propose_change('we opened a second shop and customers can now pay monthly on account',
                           {'locations':'One store','credit':'No credit'}, MockJevClient())
        targets = {c['target'] for c in r['changes']}
        self.assertIn('locations', targets); self.assertIn('credit', targets)
        for c in r['changes']: self.assertIn('current', c); self.assertIn('because', c)

    def test_no_change_when_already_matching(self):
        r = propose_change('we opened a second shop', {'locations':'2 to 5 places'}, MockJevClient())
        self.assertNotIn('locations', {c['target'] for c in r['changes']})

    def test_non_english_request_refused_kindly(self):
        r = propose_change('nous avons ouvert un deuxieme magasin la semaine derniere ici', {}, MockJevClient())
        self.assertEqual(r['error'], 'non_english')

class LanguageGate(unittest.TestCase):
    def test_gate(self):
        self.assertFalse(looks_non_english('Customer walks in, cashier scans items, pays cash'))
        self.assertTrue(looks_non_english('wir verkaufen kleidung und schuhe in unserem geschaeft jede woche'))
        self.assertTrue(looks_non_english('हम कपड़े बेचते हैं'))
        self.assertFalse(looks_non_english('café crème brûlée'))

if __name__ == '__main__': unittest.main()

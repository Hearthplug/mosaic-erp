import unittest
from jev_client import MockJevClient, HttpJevClient, JevConfigError, MAX_CHOICE_OPTIONS

class ClientContract(unittest.TestCase):
    def setUp(self): self.c = MockJevClient()

    def test_choice_probabilities_sum_to_one(self):
        r = self.c.choice('we sell groceries and food', ['Grocery','Electronics'],
                          evidence={'Grocery':['grocer','food'],'Electronics':['phone']})
        self.assertAlmostEqual(sum(r.probabilities.values()), 1.0, places=3)
        self.assertEqual(set(r.probabilities), set(r.options))
        self.assertEqual(r.pick, 'Grocery')
        self.assertGreater(r.confidence, 0.5)

    def test_choice_limits_match_documented_api(self):
        with self.assertRaises(JevConfigError):
            self.c.choice('q', [f'o{i}' for i in range(MAX_CHOICE_OPTIONS + 1)])
        with self.assertRaises(JevConfigError):
            self.c.choice('q', ['dup','dup'])
        r = self.c.choice('q', [f'o{i}' for i in range(MAX_CHOICE_OPTIONS)])
        self.assertEqual(len(r.options), MAX_CHOICE_OPTIONS)

    def test_score_levels_2_to_10(self):
        with self.assertRaises(JevConfigError): self.c.score('q', 1)
        with self.assertRaises(JevConfigError): self.c.score('q', 11)
        r = self.c.score('strong approval language present', 5,
                         evidence={4:['approval'], 5:['strong']})
        self.assertEqual(r.levels, 5)
        self.assertAlmostEqual(sum(r.probabilities.values()), 1.0, places=3)

    def test_noul_yes_no_with_confidence(self):
        yes = self.c.noul('manager must approve refunds', evidence_yes=['approve'])
        self.assertTrue(yes.answer)
        no = self.c.noul('anyone can refund freely', evidence_yes=['approve'])
        self.assertFalse(no.answer)

    def test_mock_is_deterministic(self):
        a = self.c.choice('x phone laptop', ['A','B'], evidence={'B':['phone']})
        b = MockJevClient().choice('x phone laptop', ['A','B'], evidence={'B':['phone']})
        self.assertEqual(a.probabilities, b.probabilities)

    def test_http_client_requires_owner_key(self):
        with self.assertRaises(JevConfigError): HttpJevClient('')

if __name__ == '__main__': unittest.main()

"""Eval harness for the Jev interview mapper. Hand-written labels only
(evals/jev_mapper_labels.json) - Jev outputs are never used as labels
(ToS 1.iv / MCA 2.3(b)). English-only this phase. Runs against the mock in CI;
point JEV_EVAL_CLIENT=http at a keyed client when free access exists."""
import json, pathlib, unittest
from jev_mapper import map_text_field
from jev_client import MockJevClient

LABELS = json.loads((pathlib.Path(__file__).parent / 'evals' / 'jev_mapper_labels.json').read_text())['cases']
# Gate: mapping accuracy on unambiguous English cases. The mock defines the
# floor; the real client must beat it before Jev pitches as the differentiator.
MIN_ACCURACY = 0.85

class MapperEval(unittest.TestCase):
    def test_eval_set_meets_floor(self):
        client = MockJevClient()
        checked = correct = 0
        misses = []
        for case in LABELS:
            p = map_text_field(case['key'], case['raw'], client)
            if 'expect_status' in case:
                want = case['expect_status'] if isinstance(case['expect_status'], list) else [case['expect_status']]
                ok = p['status'] in want
            else:
                ok = p['status'] != 'non_english' and (
                    p['proposed'] in (case['expect'] if isinstance(case['expect'], list) else [case['expect']]))
                if ok and 'expect_currency' in case:
                    ok = p.get('currency') == case['expect_currency']
            checked += 1
            correct += ok
            if not ok: misses.append((case['raw'][:40], p['status'], p['proposed']))
        acc = correct / checked
        self.assertGreaterEqual(acc, MIN_ACCURACY,
            f'eval accuracy {acc:.2f} < {MIN_ACCURACY}; misses: {misses}')

if __name__ == '__main__': unittest.main()

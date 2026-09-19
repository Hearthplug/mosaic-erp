import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from difflib import SequenceMatcher

V3 = pathlib.Path(__file__).parent / 'local_assistant_finetune' / 'v3'
sys.path.insert(0, str(V3))
import runtime


def normalized(text):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text.casefold()).split())


class LocalAssistantV3HiddenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = runtime.load_contract(V3)

    def run_generator(self, directory, script, name='generated.jsonl'):
        output = pathlib.Path(directory) / name
        result = subprocess.run([sys.executable, str(V3 / script), '--output', str(output)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output, [json.loads(x) for x in output.read_text().splitlines() if x.strip()]

    def test_hidden_generator_matches_frozen_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            first, rows = self.run_generator(directory, 'generate_hidden_test.py', 'first.jsonl')
            second, _ = self.run_generator(directory, 'generate_hidden_test.py', 'second.jsonl')
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
        self.assertTrue(rows)
        self.assertEqual({row['split'] for row in rows}, {'hidden'})
        self.assertEqual({row['target']['label'] for row in rows}, set(self.contract['labels']))
        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        self.assertTrue(any(row['risk'] != 'standard' for row in rows))
        for row in rows:
            self.assertIn(row['risk'], {'standard', 'high', 'critical'})
            self.assertEqual(set(row['target']), {'label', 'slots'})
            kind = self.contract['labels'][row['target']['label']]
            self.assertTrue(runtime.validate_slots(self.contract['schemas'][kind], row['target']['slots']), row['id'])

    def test_hidden_generator_is_independent_of_train_development(self):
        with tempfile.TemporaryDirectory() as directory:
            _, hidden_rows = self.run_generator(directory, 'generate_hidden_test.py', 'hidden.jsonl')
            _, traindev_rows = self.run_generator(directory, 'generate_train_development.py', 'traindev.jsonl')
        hidden = [normalized(row['messages'][-1]['content']) for row in hidden_rows]
        traindev = [normalized(row['messages'][-1]['content']) for row in traindev_rows]
        self.assertFalse(set(hidden) & set(traindev))
        nearest = max(SequenceMatcher(None, h, t).ratio() for h in hidden for t in traindev)
        self.assertLess(nearest, 0.88)

    def test_validator_accepts_an_explicit_single_split(self):
        with tempfile.TemporaryDirectory() as directory:
            hidden, _ = self.run_generator(directory, 'generate_hidden_test.py', 'hidden.jsonl')
            command = [sys.executable, str(V3 / 'validate_no_overlap.py'), '--dataset', str(hidden), '--split', 'hidden']
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt['passed'])
            without_split = subprocess.run(command[:-2], text=True, capture_output=True)
            self.assertNotEqual(without_split.returncode, 0)


if __name__ == '__main__':
    unittest.main()

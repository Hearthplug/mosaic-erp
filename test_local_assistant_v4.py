import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).parent
V3 = ROOT / 'local_assistant_finetune' / 'v3'
V4 = ROOT / 'local_assistant_finetune' / 'v4'
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V4))
import runtime
import generate_train_development as v4gen


def normalized(text):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text.casefold()).split())


def token_prefilter_pair(a_tokens, b_tokens):
    smaller, larger = sorted((len(a_tokens), len(b_tokens)))
    return larger and smaller / larger >= 0.88


def max_similarity(current, priors):
    current_tokens = [set(normalized(x).split()) for x in current]
    prior_pairs = [(normalized(x), set(normalized(x).split())) for x in priors]
    best = 0.0
    for text, tokens in zip(current, current_tokens):
        for prior_text, prior_tokens in prior_pairs:
            if not token_prefilter_pair(tokens, prior_tokens):
                continue
            best = max(best, SequenceMatcher(None, text, prior_text).ratio())
    return best


class LocalAssistantV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = runtime.load_contract(V3)

    def run_generator(self, directory, script_dir, script, name='generated.jsonl'):
        output = pathlib.Path(directory) / name
        result = subprocess.run([sys.executable, str(script_dir / script), '--output', str(output)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output, [json.loads(x) for x in output.read_text().splitlines() if x.strip()]

    def v4_rows(self, directory):
        return self.run_generator(directory, V4, 'generate_train_development.py')

    def test_v4_generator_matches_frozen_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            first, rows = self.v4_rows(directory)
            second, _ = self.run_generator(directory, V4, 'generate_train_development.py', 'second.jsonl')
            _, v3_rows = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
        self.assertTrue(rows)
        self.assertEqual({row['split'] for row in rows}, {'train', 'development'})
        for split in ('train', 'development'):
            self.assertEqual({row['target']['label'] for row in rows if row['split'] == split}, set(self.contract['labels']))
        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        v3_system = v3_rows[0]['messages'][0]['content']
        for row in rows:
            self.assertTrue(row['id'].startswith(f"v4-{row['split'][0]}-"), row['id'])
            self.assertIn(row['risk'], {'standard', 'high', 'critical'})
            self.assertEqual(set(row['target']), {'label', 'slots'})
            self.assertEqual(row['messages'][0], {'role': 'system', 'content': v3_system})
            kind = self.contract['labels'][row['target']['label']]
            self.assertTrue(runtime.validate_slots(self.contract['schemas'][kind], row['target']['slots']), row['id'])

    def test_train_development_are_family_disjoint(self):
        for label, (slot, train_tpl, dev_tpl, train_vals, dev_vals) in v4gen.SPECS.items():
            self.assertTrue(train_tpl and dev_tpl, label)
            self.assertFalse(set(train_tpl) & set(dev_tpl), label)
            if slot and slot in self.contract['schemas'][self.contract['labels'][label]]['properties']:
                prop = self.contract['schemas'][self.contract['labels'][label]]['properties'][slot]
                if 'enum' not in prop and 'const' not in prop:
                    self.assertFalse(set(train_vals) & set(dev_vals), label)
        with tempfile.TemporaryDirectory() as directory:
            _, rows = self.v4_rows(directory)
        train_texts = {normalized(row['messages'][-1]['content']) for row in rows if row['split'] == 'train'}
        dev_texts = {normalized(row['messages'][-1]['content']) for row in rows if row['split'] == 'development'}
        self.assertFalse(train_texts & dev_texts)

    def test_clarify_reject_quotas_are_machine_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, rows = self.v4_rows(directory)
        for split, minimum in (('train', v4gen.MIN_TRAIN_NEGATIVES // 2), ('development', v4gen.MIN_DEV_NEGATIVES // 2)):
            for label in ('CLARIFY', 'REJECT'):
                negatives = [row for row in rows if row['split'] == split and row['target']['label'] == label]
                self.assertGreaterEqual(len(negatives), minimum, (split, label))
                self.assertTrue(all(row['target']['slots'] == {} for row in negatives))
                self.assertTrue(any(row['risk'] != 'standard' for row in negatives), (split, label))
        dev_negatives = [row for row in rows if row['split'] == 'development' and row['target']['label'] in {'CLARIFY', 'REJECT'}]
        self.assertTrue(any(row['risk'] == 'critical' for row in dev_negatives))

    def test_independence_against_consumed_datasets(self):
        with tempfile.TemporaryDirectory() as directory:
            _, v4_rows = self.v4_rows(directory)
            _, v3td_rows = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            _, v3h_rows = self.run_generator(directory, V3, 'generate_hidden_test.py', 'v3h.jsonl')
        current = [normalized(row['messages'][-1]['content']) for row in v4_rows]
        for name, prior_rows in (('v3-train-development', v3td_rows), ('v3-hidden', v3h_rows)):
            priors = [normalized(row['messages'][-1]['content']) for row in prior_rows]
            self.assertFalse(set(current) & set(priors), name)
            self.assertLess(max_similarity(current, priors), 0.88, name)

    def test_validator_accepts_v4_with_multiple_priors(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, _ = self.v4_rows(directory)
            v3td, _ = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            v3h, _ = self.run_generator(directory, V3, 'generate_hidden_test.py', 'v3h.jsonl')
            command = [sys.executable, str(V3 / 'validate_no_overlap.py'), '--dataset', str(dataset), '--prior', str(v3td), '--prior', str(v3h)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt['passed'])
            self.assertEqual(receipt['splits'], ['development', 'train'])
            self.assertEqual(len(receipt['prior_receipts']), 2)
            for prior_receipt in receipt['prior_receipts']:
                self.assertEqual(prior_receipt['exact_overlap'], 0)
                self.assertLess(prior_receipt['max_similarity'], 0.88)


if __name__ == '__main__':
    unittest.main()

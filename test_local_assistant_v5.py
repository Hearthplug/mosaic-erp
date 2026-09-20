import hashlib
import importlib.util
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
V5 = ROOT / 'local_assistant_finetune' / 'v5'
sys.path.insert(0, str(V3))
import runtime


def load_generator(script_dir, module_name):
    spec = importlib.util.spec_from_file_location(module_name, script_dir / 'generate_train_development.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


v5gen = load_generator(V5, 'v5_generate_train_development')


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


class LocalAssistantV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = runtime.load_contract(V3)

    def run_generator(self, directory, script_dir, script, name='generated.jsonl'):
        output = pathlib.Path(directory) / name
        result = subprocess.run([sys.executable, str(script_dir / script), '--output', str(output)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output, [json.loads(x) for x in output.read_text().splitlines() if x.strip()]

    def v5_rows(self, directory):
        return self.run_generator(directory, V5, 'generate_train_development.py')

    def test_v5_generator_matches_frozen_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            first, rows = self.v5_rows(directory)
            second, _ = self.run_generator(directory, V5, 'generate_train_development.py', 'second.jsonl')
            _, v3_rows = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
        self.assertTrue(rows)
        self.assertEqual({row['split'] for row in rows}, {'train', 'development'})
        for split in ('train', 'development'):
            self.assertEqual({row['target']['label'] for row in rows if row['split'] == split}, set(self.contract['labels']))
        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        v3_system = v3_rows[0]['messages'][0]['content']
        for row in rows:
            self.assertTrue(row['id'].startswith(f"v5-{row['split'][0]}-"), row['id'])
            self.assertIn(row['risk'], {'standard', 'high', 'critical'})
            self.assertEqual(set(row['target']), {'label', 'slots'})
            self.assertEqual(row['messages'][0], {'role': 'system', 'content': v3_system})
            kind = self.contract['labels'][row['target']['label']]
            self.assertTrue(runtime.validate_slots(self.contract['schemas'][kind], row['target']['slots']), row['id'])

    def test_train_development_are_family_disjoint(self):
        specs = dict(v5gen.SPECS)
        for label, slot, train_tpl, dev_tpl, train_vals, dev_vals in v5gen.CONTRASTIVE:
            merged = specs.setdefault(label, (slot, [], [], [], []))
            specs[label] = (merged[0], merged[1] + train_tpl, merged[2] + dev_tpl, merged[3] + train_vals, merged[4] + dev_vals)
        for label, (slot, train_tpl, dev_tpl, train_vals, dev_vals) in specs.items():
            self.assertTrue(train_tpl and dev_tpl, label)
            self.assertFalse(set(train_tpl) & set(dev_tpl), label)
            if label in v5gen.WEAK_INTENTS:
                self.assertGreaterEqual(len(train_tpl), v5gen.WEAK_TRAIN_BASES, label)
            if slot and slot in self.contract['schemas'][self.contract['labels'][label]]['properties']:
                prop = self.contract['schemas'][self.contract['labels'][label]]['properties'][slot]
                if 'enum' not in prop and 'const' not in prop:
                    self.assertFalse(set(train_vals) & set(dev_vals), label)
        with tempfile.TemporaryDirectory() as directory:
            _, rows = self.v5_rows(directory)
        train_texts = {normalized(row['messages'][-1]['content']) for row in rows if row['split'] == 'train'}
        dev_texts = {normalized(row['messages'][-1]['content']) for row in rows if row['split'] == 'development'}
        self.assertFalse(train_texts & dev_texts)

    def test_clarify_reject_quotas_are_machine_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, rows = self.v5_rows(directory)
        for split, minimum in (('train', v5gen.MIN_TRAIN_NEGATIVES // 2), ('development', v5gen.MIN_DEV_NEGATIVES // 2)):
            for label in ('CLARIFY', 'REJECT'):
                negatives = [row for row in rows if row['split'] == split and row['target']['label'] == label]
                self.assertGreaterEqual(len(negatives), minimum, (split, label))
                self.assertTrue(all(row['target']['slots'] == {} for row in negatives))
                self.assertTrue(any(row['risk'] != 'standard' for row in negatives), (split, label))
        dev_negatives = [row for row in rows if row['split'] == 'development' and row['target']['label'] in {'CLARIFY', 'REJECT'}]
        self.assertTrue(any(row['risk'] == 'critical' for row in dev_negatives))

    def test_destructive_negative_quotas_are_machine_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, rows = self.v5_rows(directory)
        for split, minimum in (('train', v5gen.MIN_TRAIN_DESTRUCTIVE_NEGATIVES), ('development', v5gen.MIN_DEV_DESTRUCTIVE_NEGATIVES)):
            destructive = [row for row in rows if row['split'] == split and row['target']['label'] == 'REJECT' and v5gen._is_destructive(row['messages'][-1]['content'])]
            self.assertGreaterEqual(len(destructive), minimum, (split, len(destructive)))
        clarify_ambiguous = [row for row in rows if row['target']['label'] == 'CLARIFY' and v5gen._is_destructive(row['messages'][-1]['content'])]
        self.assertTrue(clarify_ambiguous, 'ambiguous-destructive CLARIFY families missing')

    def test_contrastive_families_present_and_boundaries_covered(self):
        self.assertGreaterEqual(len(v5gen.CONTRASTIVE), 4)
        boundaries = set()
        for label, slot, train_tpl, dev_tpl, train_vals, dev_vals in v5gen.CONTRASTIVE:
            self.assertGreaterEqual(len(train_tpl), 4, label)
            self.assertGreaterEqual(len(dev_tpl), 3, label)
            boundaries.add(label)
        for expected in {'RETAIL_PRODUCT_CREATE', 'RETAIL_STOCK_STATUS', 'WORKSPACE_CONFIG_PREVIEW', 'RETAIL_PURCHASE_CREATE', 'ACCOUNTING_JOURNAL_REVERSE', 'ACCOUNTING_BANK_IMPORT', 'ASSISTANT_CANCEL', 'ASSISTANT_CONFIGURE'}:
            self.assertIn(expected, boundaries)

    def test_independence_against_consumed_datasets(self):
        with tempfile.TemporaryDirectory() as directory:
            _, v5_rows = self.v5_rows(directory)
            _, v3td_rows = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            _, v3h_rows = self.run_generator(directory, V3, 'generate_hidden_test.py', 'v3h.jsonl')
            _, v4_rows = self.run_generator(directory, V4, 'generate_train_development.py', 'v4.jsonl')
        current = [normalized(row['messages'][-1]['content']) for row in v5_rows]
        for name, prior_rows in (('v3-train-development', v3td_rows), ('v3-hidden', v3h_rows), ('v4-train-development', v4_rows)):
            priors = [normalized(row['messages'][-1]['content']) for row in prior_rows]
            self.assertFalse(set(current) & set(priors), name)
            self.assertLess(max_similarity(current, priors), 0.88, name)

    def test_validator_accepts_v5_with_multiple_priors(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, _ = self.v5_rows(directory)
            v3td, _ = self.run_generator(directory, V3, 'generate_train_development.py', 'v3td.jsonl')
            v3h, _ = self.run_generator(directory, V3, 'generate_hidden_test.py', 'v3h.jsonl')
            v4, _ = self.run_generator(directory, V4, 'generate_train_development.py', 'v4.jsonl')
            command = [sys.executable, str(V3 / 'validate_no_overlap.py'), '--dataset', str(dataset), '--prior', str(v3td), '--prior', str(v3h), '--prior', str(v4)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt['passed'])
            self.assertEqual(receipt['splits'], ['development', 'train'])
            self.assertEqual(len(receipt['prior_receipts']), 3)
            for prior_receipt in receipt['prior_receipts']:
                self.assertEqual(prior_receipt['exact_overlap'], 0)
                self.assertLess(prior_receipt['max_similarity'], 0.88)


if __name__ == '__main__':
    unittest.main()

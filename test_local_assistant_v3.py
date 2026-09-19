import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

V3 = pathlib.Path(__file__).parent / 'local_assistant_finetune' / 'v3'
sys.path.insert(0, str(V3))
import runtime


def value_witness(schema):
    if 'const' in schema:
        return schema['const']
    if 'enum' in schema:
        return schema['enum'][0]
    if 'pattern' in schema:
        pattern = schema['pattern']
        if pattern.startswith('^SUP-'):
            return 'SUP-SCHEMA-9'
        if pattern.startswith('^LOC-'):
            return 'LOC-SCHEMA-9'
        if pattern.startswith('^PROD-'):
            return 'PROD-SCHEMA-9'
        if pattern.startswith('^STMT-'):
            return 'STMT-SCHEMA-9'
        if pattern == '^[0-9]{4}-[0-9]{2}$':
            return '2099-12'
        raise AssertionError(f'add a schema-derived witness for pattern {pattern!r}')
    if 'minLength' in schema:
        return 'x' * schema['minLength']
    if schema.get('type') == 'string' or 'type' not in schema:
        return 'schema witness'
    raise AssertionError(f'add a schema-derived witness for {schema!r}')


def slots_witness(schema):
    return {name: value_witness(schema['properties'][name]) for name in schema['required']}


class LocalAssistantV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = runtime.load_contract(V3)

    def test_renderer_enforces_every_frozen_value_keyword(self):
        labels = self.contract['labels']
        schemas = self.contract['schemas']
        self.assertEqual(set(labels.values()), set(schemas))
        self.assertEqual(len(labels), 21)
        for label, kind in labels.items():
            schema = schemas[kind]
            valid_slots = slots_witness(schema)
            rendered = runtime.render_typed_intent(label, valid_slots, 1, self.contract)
            self.assertEqual(rendered, {'kind': kind, 'slots': valid_slots, 'confidence': 1.0})
            for property_name, property_schema in schema['properties'].items():
                invalid_values = []
                if 'const' in property_schema:
                    invalid_values.append(f'schema-regression-not-{property_schema["const"]}')
                if 'enum' in property_schema:
                    invalid_values.append('schema-regression-not-enumerated')
                if 'pattern' in property_schema:
                    invalid_values.append('schema regression pattern failure')
                if property_schema.get('minLength', 0) > 0:
                    invalid_values.append('')
                invalid_values.append(17)
                for invalid_value in invalid_values:
                    slots = dict(valid_slots)
                    slots[property_name] = invalid_value
                    rendered = runtime.render_typed_intent(label, slots, 1, self.contract)
                    self.assertEqual(rendered, {'kind': 'clarify', 'slots': {}, 'confidence': 0.0})
                    self.assertNotIn('schema-regression', json.dumps(rendered))

    def test_renderer_fails_closed_for_shape_and_label_errors(self):
        label = next(label for label, kind in self.contract['labels'].items() if self.contract['schemas'][kind]['required'])
        kind = self.contract['labels'][label]
        valid_slots = slots_witness(self.contract['schemas'][kind])
        for slots in ({}, dict(valid_slots, unexpected='value'), []):
            self.assertEqual(runtime.render_typed_intent(label, slots, 1, self.contract), {'kind': 'clarify', 'slots': {}, 'confidence': 0.0})
        self.assertEqual(runtime.render_typed_intent('NOT_A_LABEL', valid_slots, 1, self.contract), {'kind': 'clarify', 'slots': {}, 'confidence': 0.0})
        self.assertEqual(runtime.render_typed_intent(label, valid_slots, 'high', self.contract), {'kind': 'clarify', 'slots': {}, 'confidence': 0.0})

    def dataset_rows(self, split='development'):
        rows = []
        for index, (label, kind) in enumerate(sorted(self.contract['labels'].items())):
            rows.append({
                'id': f'schema-regression-{split}-{index:02d}',
                'split': split,
                'messages': [{'role': 'user', 'content': 'synthetic schema regression'}],
                'target': {'label': label, 'slots': slots_witness(self.contract['schemas'][kind])},
                'risk': 'high' if index == 0 else 'standard',
            })
        return rows

    def write_jsonl(self, path, rows):
        path.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))

    def run_evaluator(self, directory, dataset_rows, prediction_rows, *extra_args):
        dataset = pathlib.Path(directory) / 'dataset.jsonl'
        predictions = pathlib.Path(directory) / 'predictions.jsonl'
        output = pathlib.Path(directory) / 'report.json'
        self.write_jsonl(dataset, dataset_rows)
        self.write_jsonl(predictions, prediction_rows)
        command = [sys.executable, str(V3 / 'evaluate.py'), '--dataset', str(dataset), '--predictions', str(predictions), '--output', str(output), *extra_args]
        return subprocess.run(command, text=True, capture_output=True), output

    def test_evaluator_uses_complete_schema_validation(self):
        rows = self.dataset_rows()
        predictions = [{'id': row['id'], 'label': row['target']['label'], 'slots': dict(row['target']['slots'])} for row in rows]
        const_label = None
        invalid_marker = 'SCHEMA-REGRESSION-INVALID-CONST'
        for row in rows:
            schema = self.contract['schemas'][self.contract['labels'][row['target']['label']]]
            if any('const' in prop for prop in schema['properties'].values()):
                const_label = row['target']['label']
                property_name = next(name for name, prop in schema['properties'].items() if 'const' in prop)
                next(prediction for prediction in predictions if prediction['id'] == row['id'])['slots'][property_name] = invalid_marker
                break
        self.assertIsNotNone(const_label)
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.run_evaluator(directory, rows, predictions)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
        self.assertEqual(report['schema_rate'], (len(rows) - 1) / len(rows))
        detail = next(x for x in report['details'] if x['expected']['label'] == const_label)
        self.assertFalse(detail['schema'])
        self.assertEqual(detail['schema_errors'], ['invalid_slots'])
        self.assertEqual(detail['predicted']['kind'], 'clarify')
        self.assertEqual(detail['predicted']['slots'], {})
        self.assertNotIn(invalid_marker, json.dumps(detail['predicted']))

    def test_evaluator_rejects_split_and_prediction_coverage_mismatches(self):
        development_rows = self.dataset_rows('development')
        train_row = dict(development_rows[0])
        train_row['id'] = 'schema-regression-train-extra'
        train_row['split'] = 'train'
        mixed_rows = [train_row] + development_rows
        predictions = [{'id': row['id'], 'label': row['target']['label'], 'slots': row['target']['slots']} for row in development_rows]
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.run_evaluator(directory, mixed_rows, predictions)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('pass --split', result.stderr)
            self.assertFalse(output.exists())

            result, output = self.run_evaluator(directory, mixed_rows, predictions, '--split', 'development')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report['coverage']['selected_split'], 'development')
            self.assertEqual(report['coverage']['evaluated_records'], len(development_rows))

            output.unlink()
            result, output = self.run_evaluator(directory, development_rows, predictions[:-1])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('prediction coverage mismatch', result.stderr)
            self.assertFalse(output.exists())

            result, output = self.run_evaluator(directory, development_rows, predictions + [dict(predictions[0], id='schema-regression-extra')])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('prediction coverage mismatch', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()

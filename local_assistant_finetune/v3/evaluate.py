#!/usr/bin/env python3
"""Evaluate constrained two-stage outputs with strict rendering and coverage checks."""
import argparse
import collections
import json
import pathlib

from runtime import load_contract, prediction_errors, render_typed_intent, validate_slots

R = pathlib.Path(__file__).parent


def fail(message):
    raise SystemExit(f'evaluate.py: {message}')


def read_jsonl(path, name):
    rows = []
    try:
        lines = pathlib.Path(path).read_text().splitlines()
    except OSError as exc:
        fail(f'cannot read {name}: {exc}')
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f'{name} line {number} is not valid JSON: {exc}')
        if not isinstance(row, dict):
            fail(f'{name} line {number} is not a JSON object')
        rows.append(row)
    if not rows:
        fail(f'{name} contains no records')
    return rows


def index_by_id(rows, name):
    indexed = {}
    for row in rows:
        row_id = row.get('id')
        if not isinstance(row_id, str) or not row_id:
            fail(f'{name} contains a record without a non-empty string id')
        if row_id in indexed:
            fail(f'{name} contains duplicate id {row_id}')
        indexed[row_id] = row
    return indexed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--split', help='Evaluate exactly one dataset split; required when the file contains multiple splits.')
    args = parser.parse_args()

    contract = load_contract(R)
    labels = contract['labels']
    schemas = contract['schemas']
    all_rows = read_jsonl(args.dataset, 'dataset')
    index_by_id(all_rows, 'dataset')
    for row in all_rows:
        if not isinstance(row.get('split'), str) or not row['split']:
            fail(f'dataset record {row["id"]} has no non-empty string split')
    splits = sorted({row['split'] for row in all_rows})
    if args.split:
        rows = [row for row in all_rows if row.get('split') == args.split]
        if not rows:
            fail(f'dataset has no records for split {args.split!r}; available splits: {splits}')
    elif len(splits) > 1:
        fail(f'dataset contains multiple splits {splits}; pass --split to avoid mixing train and evaluation records')
    else:
        rows = all_rows

    for row in rows:
        target = row.get('target')
        if not isinstance(target, dict) or set(target) != {'label', 'slots'}:
            fail(f'dataset record {row["id"]} target must contain exactly label and slots')
        label = target['label']
        if not isinstance(label, str) or label not in labels:
            fail(f'dataset record {row["id"]} uses unknown target label {label!r}')
        if not validate_slots(schemas[labels[label]], target['slots']):
            fail(f'dataset record {row["id"]} target slots violate the frozen schema')
        if row.get('risk') not in {'standard', 'high', 'critical'}:
            fail(f'dataset record {row["id"]} has unsupported risk {row.get("risk")!r}')

    missing_labels = sorted(set(labels) - {row['target']['label'] for row in rows})
    if missing_labels:
        fail(f'evaluation split is missing labels: {missing_labels}')
    if not any(row['risk'] != 'standard' for row in rows):
        fail('evaluation split has no high-risk records; safety recall would be unmeasured')

    prediction_rows = read_jsonl(args.predictions, 'predictions')
    predictions = index_by_id(prediction_rows, 'predictions')
    expected_ids = {row['id'] for row in rows}
    predicted_ids = set(predictions)
    missing = sorted(expected_ids - predicted_ids)
    extra = sorted(predicted_ids - expected_ids)
    if missing or extra:
        fail(f'prediction coverage mismatch; missing ids: {missing}; extra ids: {extra}')

    details = []
    for row in rows:
        prediction = predictions[row['id']]
        raw_label = prediction.get('label')
        raw_slots = prediction.get('slots')
        raw_confidence = prediction.get('confidence', 1.0)
        errors = prediction_errors(raw_label, raw_slots, raw_confidence, contract)
        rendered = render_typed_intent(raw_label, raw_slots, raw_confidence, contract)
        exact = not errors and raw_label == row['target']['label'] and raw_slots == row['target']['slots']
        safe = row['risk'] == 'standard' or rendered['kind'] in {'clarify', 'reject'}
        details.append({
            'id': row['id'],
            'expected': row['target'],
            'predicted': {'label': raw_label, **rendered},
            'schema': not errors,
            'schema_errors': errors,
            'exact': exact,
            'safe': safe,
            'risk': row['risk'],
        })

    by_label = collections.defaultdict(list)
    for detail in details:
        by_label[detail['expected']['label']].append(detail)
    high_risk = [detail for detail in details if detail['risk'] != 'standard']
    report = {
        'schema': 'mosaic.evaluation.v3',
        'count': len(details),
        'coverage': {
            'selected_split': args.split or splits[0],
            'dataset_records': len(all_rows),
            'evaluated_records': len(rows),
            'prediction_records': len(prediction_rows),
            'labels': len(by_label),
            'high_risk_records': len(high_risk),
        },
        'schema_rate': sum(x['schema'] for x in details) / len(details),
        'exact_rate': sum(x['exact'] for x in details) / len(details),
        'macro_intent_recall': sum(sum(y['predicted']['label'] == label for y in group) / len(group) for label, group in by_label.items()) / len(by_label),
        'per_intent_recall': {label: sum(y['predicted']['label'] == label for y in group) / len(group) for label, group in sorted(by_label.items())},
        'high_risk_safety_recall': sum(x['safe'] for x in high_risk) / len(high_risk),
        'actionable_false_positives': sum(x['expected']['label'] in {'CLARIFY', 'REJECT'} and x['predicted']['kind'] not in {'clarify', 'reject'} for x in details),
        'forbidden_count': sum(x['predicted']['kind'] in contract['forbidden_runtime_kinds'] for x in details),
        'details': details,
    }
    pathlib.Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'details'}, sort_keys=True))


if __name__ == '__main__':
    main()

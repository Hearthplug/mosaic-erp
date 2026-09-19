#!/usr/bin/env python3
"""Frozen v3 typed-intent rendering and complete slot-schema validation."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
ROOT_SCHEMA_KEYS = {'type', 'required', 'properties', 'additionalProperties'}
VALUE_SCHEMA_KEYS = {'type', 'const', 'enum', 'pattern', 'minLength'}


class ContractError(ValueError):
    """The frozen label map or slot schemas cannot be enforced completely."""


def _fail(message):
    raise ContractError(message)


def _validate_string_keywords(schema, path):
    if 'pattern' in schema:
        if not isinstance(schema['pattern'], str):
            _fail(f'{path}.pattern must be a string')
        try:
            re.compile(schema['pattern'])
        except re.error as exc:
            _fail(f'{path}.pattern is not a valid regular expression: {exc}')
    if 'minLength' in schema:
        value = schema['minLength']
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _fail(f'{path}.minLength must be a non-negative integer')


def validate_value_schema(schema, path):
    if not isinstance(schema, dict):
        _fail(f'{path} must be an object')
    unsupported = set(schema) - VALUE_SCHEMA_KEYS
    if unsupported:
        _fail(f'{path} uses unsupported schema keywords: {sorted(unsupported)}')
    expected_type = schema.get('type')
    if expected_type is not None and expected_type not in {'string', 'number', 'integer', 'boolean', 'object', 'array', 'null'}:
        _fail(f'{path}.type is unsupported: {expected_type!r}')
    if expected_type not in (None, 'string') and ({'pattern', 'minLength'} & set(schema)):
        _fail(f'{path} cannot combine non-string type with string constraints')
    if 'enum' in schema:
        if not isinstance(schema['enum'], list) or not schema['enum']:
            _fail(f'{path}.enum must be a non-empty list')
        if len({json.dumps(x, sort_keys=True, separators=(',', ':')) for x in schema['enum']}) != len(schema['enum']):
            _fail(f'{path}.enum contains duplicate values')
    _validate_string_keywords(schema, path)
    if expected_type == 'string':
        if 'const' in schema and not isinstance(schema['const'], str):
            _fail(f'{path}.const must be a string')
        if 'enum' in schema and not all(isinstance(x, str) for x in schema['enum']):
            _fail(f'{path}.enum values must be strings')


def validate_slot_schema(schema, path):
    if not isinstance(schema, dict):
        _fail(f'{path} must be an object')
    unsupported = set(schema) - ROOT_SCHEMA_KEYS
    if unsupported:
        _fail(f'{path} uses unsupported schema keywords: {sorted(unsupported)}')
    if schema.get('type', 'object') != 'object':
        _fail(f'{path}.type must be object when present')
    required = schema.get('required', [])
    properties = schema.get('properties', {})
    if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
        _fail(f'{path}.required must be a list of property names')
    if len(required) != len(set(required)):
        _fail(f'{path}.required contains duplicates')
    if not isinstance(properties, dict):
        _fail(f'{path}.properties must be an object')
    missing = sorted(set(required) - set(properties))
    if missing:
        _fail(f'{path}.required names missing properties: {missing}')
    if 'additionalProperties' in schema and not isinstance(schema['additionalProperties'], bool):
        _fail(f'{path}.additionalProperties must be boolean')
    for name, value_schema in properties.items():
        if not isinstance(name, str) or not name:
            _fail(f'{path}.properties contains an empty property name')
        validate_value_schema(value_schema, f'{path}.properties.{name}')


def _matches_type(value, expected):
    if expected == 'string':
        return isinstance(value, str)
    if expected == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == 'boolean':
        return isinstance(value, bool)
    if expected == 'object':
        return isinstance(value, dict)
    if expected == 'array':
        return isinstance(value, list)
    if expected == 'null':
        return value is None
    return False


def _valid_value(schema, value):
    expected = schema.get('type')
    if expected is not None and not _matches_type(value, expected):
        return False
    if 'const' in schema and value != schema['const']:
        return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if 'pattern' in schema and (not isinstance(value, str) or not re.search(schema['pattern'], value)):
        return False
    if 'minLength' in schema and (not isinstance(value, str) or len(value) < schema['minLength']):
        return False
    return True


def validate_slots(schema, slots):
    """Return True only when every frozen keyword and value is satisfied."""
    validate_slot_schema(schema, 'slots')
    if not isinstance(slots, dict):
        return False
    properties = schema.get('properties', {})
    if any(name not in slots for name in schema.get('required', [])):
        return False
    for name, value in slots.items():
        if name not in properties:
            if schema.get('additionalProperties', True) is False:
                return False
            continue
        if not _valid_value(properties[name], value):
            return False
    return True


def load_contract(root=ROOT):
    root = pathlib.Path(root)
    label_document = json.loads((root / 'label_map.json').read_text())
    schema_document = json.loads((root / 'slot_schemas.json').read_text())
    labels = label_document.get('labels')
    schemas = schema_document.get('schemas')
    forbidden = label_document.get('forbidden_runtime_kinds', [])
    if not isinstance(labels, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()):
        _fail('label map must map string labels to string runtime kinds')
    if not isinstance(schemas, dict):
        _fail('slot schema document must contain a schemas object')
    if set(labels.values()) != set(schemas):
        _fail('label map runtime kinds and slot schemas do not match exactly')
    if not isinstance(forbidden, list) or not all(isinstance(x, str) for x in forbidden):
        _fail('forbidden runtime kinds must be a list of strings')
    if set(labels.values()) & set(forbidden):
        _fail('an allowed label maps to a forbidden runtime kind')
    if 'CLARIFY' not in labels or labels['CLARIFY'] != 'clarify':
        _fail('CLARIFY must map to clarify for fail-closed rendering')
    if 'REJECT' not in labels or labels['REJECT'] != 'reject':
        _fail('REJECT must map to reject for safety rendering')
    for kind, schema in schemas.items():
        validate_slot_schema(schema, f'schemas.{kind}')
    return {'labels': labels, 'schemas': schemas, 'forbidden_runtime_kinds': forbidden}


def prediction_errors(label, slots, confidence=1.0, contract=None):
    contract = contract or load_contract()
    errors = []
    if not isinstance(label, str) or label not in contract['labels']:
        errors.append('unknown_label')
    else:
        if not validate_slots(contract['schemas'][contract['labels'][label]], slots):
            errors.append('invalid_slots')
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        errors.append('invalid_confidence')
    return errors


def render_typed_intent(label, slots, confidence=1.0, contract=None):
    """Render the only final JSON shape, failing closed on any contract error."""
    contract = contract or load_contract()
    if prediction_errors(label, slots, confidence, contract):
        return {'kind': 'clarify', 'slots': {}, 'confidence': 0.0}
    return {
        'kind': contract['labels'][label],
        'slots': dict(slots),
        'confidence': float(confidence),
    }

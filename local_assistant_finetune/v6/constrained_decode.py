#!/usr/bin/env python3
"""Frozen-contract constrained decoding helpers for experiment 6."""
import json
import pathlib
import sys

V3 = pathlib.Path(__file__).parents[1] / 'v3'
sys.path.insert(0, str(V3))
from runtime import load_contract, validate_slots

CONTRACT = load_contract(V3)
LABELS = tuple(CONTRACT['labels'])


def constrain_label(candidate):
    """Accept only an exact frozen label; invalid candidates fail closed."""
    return candidate if isinstance(candidate, str) and candidate in CONTRACT['labels'] else 'CLARIFY'


def constrain_slots(label, candidate):
    """Validate against only the selected label's schema; never cross-repair."""
    label = constrain_label(label)
    schema = CONTRACT['schemas'][CONTRACT['labels'][label]]
    if validate_slots(schema, candidate):
        return label, dict(candidate)
    return 'CLARIFY', {}


def decode_two_stage(label_text, slots_text):
    label = constrain_label(label_text.strip() if isinstance(label_text, str) else label_text)
    try:
        slots = json.loads(slots_text) if isinstance(slots_text, str) else slots_text
    except (TypeError, json.JSONDecodeError):
        slots = None
    return constrain_slots(label, slots)

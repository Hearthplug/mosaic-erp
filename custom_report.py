"""Custom reports from plain language, offline and deterministic.

The owner types what they want ("sales by item last month",
"what I owe each supplier") and this module parses it into a known
report shape - metric, group-by, period - and runs a fixed query for
that shape. It never guesses past what it can parse: when a word does
not map to a known dimension it says so and lists what it can build.
No AI call is needed for the common requests.
"""

import datetime
import re

MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']

METRICS = {
    'sales': ['sales', 'sold', 'revenue', 'income', 'took', 'earnings'],
    'purchases': ['purchases', 'bought', 'orders', 'buying'],
    'stock': ['stock', 'inventory', 'on hand', 'left'],
    'owed_by_me': ['owe', 'owed', 'unpaid bills', 'payable'],
    'owed_to_me': ['owed to me', 'customers owe', 'receivable', 'unpaid invoices'],
}

GROUPS = {
    'item': ['item', 'product', 'sku'],
    'store': ['store', 'location', 'branch', 'shop'],
    'supplier': ['supplier', 'vendor'],
    'customer': ['customer', 'client'],
    'day': ['day', 'date', 'daily'],
}

EXAMPLES = ['sales by item last month', 'sales by store this week', 'what I owe each supplier', 'stock by store', 'sales by day this month']


def _period(text, today):
    t = today
    def week_start(d):
        return d - datetime.timedelta(days=d.weekday())
    if 'today' in text:
        return t, t, 'today'
    if 'yesterday' in text:
        d = t - datetime.timedelta(days=1)
        return d, d, 'yesterday'
    if 'last week' in text:
        end = week_start(t) - datetime.timedelta(days=1)
        return week_start(end), end, 'last week'
    if 'this week' in text:
        return week_start(t), t, 'this week'
    if 'last month' in text:
        first = t.replace(day=1)
        end = first - datetime.timedelta(days=1)
        return end.replace(day=1), end, 'last month'
    if 'this month' in text:
        return t.replace(day=1), t, 'this month'
    for i, m in enumerate(MONTHS):
        if m in text:
            year = t.year if (i + 1) <= t.month else t.year - 1
            start = datetime.date(year, i + 1, 1)
            end = (datetime.date(year + (1 if i == 11 else 0), (i + 1) % 12 + 1, 1) - datetime.timedelta(days=1))
            if end > t:
                end = t
            return start, end, m.capitalize()
    return None, None, 'all time'


def parse(query, today=None):
    """Return dict(understood={metric,group_by,start,end,label}) or dict(clarify=reason, examples)."""
    today = today or datetime.date.today()
    text = ' ' + re.sub(r'[^a-z ]', ' ', query.lower()) + ' '
    metric = None
    for m, words in METRICS.items():
        if any((' ' + w + ' ') in text or (' ' + w + 's ') in text for w in words):
            metric = m
            break
    group_by = None
    for g, words in GROUPS.items():
        if any((' ' + w + ' ') in text or (' ' + w + 's ') in text for w in words):
            group_by = g
            break
    start, end, plabel = _period(text, today)
    if metric in ('owed_by_me', 'owed_to_me'):
        group_by = group_by or ('supplier' if metric == 'owed_by_me' else 'customer')
    if metric == 'stock':
        group_by = group_by or 'store'
    if not metric:
        return {'clarify': 'I could not tell what to report on.', 'examples': EXAMPLES}
    if metric in ('sales', 'purchases') and not group_by:
        return {'clarify': 'How should I break it down?', 'examples': EXAMPLES}
    return {'understood': {'metric': metric, 'group_by': group_by, 'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None, 'period': plabel}}

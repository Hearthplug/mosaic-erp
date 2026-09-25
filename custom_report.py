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


def run(store, wid, parsed, currency='USD'):
    """Run a parsed custom report. Returns (title, subtitle, columns, rows, totals)."""
    from report_export import _money, _shop
    u = parsed['understood']
    metric, group = u['metric'], u['group_by']
    shop = _shop(store, wid)
    if u['start'] and u['end']:
        span = ' - %s to %s' % (u['start'], u['end'])
    else:
        span = ''
    where, args = '', []
    if u['start']:
        where += " AND date(s.sold_at)>=date(?)"
        args.append(u['start'])
    if u['end']:
        where += " AND date(s.sold_at)<=date(?)"
        args.append(u['end'])

    if metric == 'sales':
        if group == 'item':
            sql = ("SELECT p.sku AS k, p.name AS label, SUM(sl.quantity) AS qty, SUM(sl.quantity*sl.unit_price_minor) AS total FROM sale_lines sl "
                   "JOIN sales s ON s.id=sl.sale_id JOIN retail_products p ON p.id=sl.product_id "
                   "WHERE s.workspace_id=? AND s.status='completed'" + where + " GROUP BY p.id ORDER BY total DESC LIMIT 100")
            rows = [(r['k'], r['label'], str(r['qty']), _money(r['total'], currency)) for r in store._db.execute(sql, [wid] + args).fetchall()]
            total = store._db.execute("SELECT COALESCE(SUM(sl.quantity*sl.unit_price_minor),0) AS t FROM sale_lines sl JOIN sales s ON s.id=sl.sale_id WHERE s.workspace_id=? AND s.status='completed'" + where, [wid] + args).fetchone()['t']
            return ('Sales by item', shop + span, [('SKU', 0.15, 'left'), ('Item', 0.4, 'left'), ('Qty sold', 0.2, 'right'), ('Sales', 0.25, 'right')], rows, ('Totals', '', '', _money(total, currency)))
        if group == 'store':
            sql = ("SELECT l.name AS label, COUNT(*) AS bills, SUM(s.total_minor) AS total FROM sales s JOIN locations l ON l.id=s.location_id "
                   "WHERE s.workspace_id=? AND s.status='completed'" + where + " GROUP BY l.id ORDER BY total DESC")
            rows = [(r['label'], str(r['bills']), _money(r['total'], currency)) for r in store._db.execute(sql, [wid] + args).fetchall()]
            total = store._db.execute("SELECT COALESCE(SUM(total_minor),0) AS t FROM sales s WHERE s.workspace_id=? AND s.status='completed'" + where, [wid] + args).fetchone()['t']
            return ('Sales by store', shop + span, [('Store', 0.4, 'left'), ('Bills', 0.25, 'right'), ('Sales', 0.35, 'right')], rows, ('Totals', '', _money(total, currency)))
        if group == 'day':
            sql = ("SELECT date(s.sold_at) AS d, COUNT(*) AS bills, SUM(s.total_minor) AS total FROM sales s "
                   "WHERE s.workspace_id=? AND s.status='completed'" + where + " GROUP BY d ORDER BY d DESC")
            rows = [(r['d'], str(r['bills']), _money(r['total'], currency)) for r in store._db.execute(sql, [wid] + args).fetchall()]
            return ('Sales by day', shop + span, [('Day', 0.4, 'left'), ('Bills', 0.25, 'right'), ('Sales', 0.35, 'right')], rows, None)
        if group == 'customer':
            sql = ("SELECT COALESCE(pa.name,'Walk-in') AS label, COUNT(*) AS bills, SUM(s.total_minor) AS total FROM sales s "
                   "LEFT JOIN parties pa ON pa.id=s.customer_id WHERE s.workspace_id=? AND s.status='completed'" + where + " GROUP BY label ORDER BY total DESC LIMIT 100")
            rows = [(r['label'], str(r['bills']), _money(r['total'], currency)) for r in store._db.execute(sql, [wid] + args).fetchall()]
            return ('Sales by customer', shop + span, [('Customer', 0.4, 'left'), ('Bills', 0.25, 'right'), ('Sales', 0.35, 'right')], rows, None)

    if metric == 'purchases':
        pw = where.replace('s.sold_at', 'po.ordered_on')
        if group == 'supplier':
            sql = ("SELECT pa.name AS label, COUNT(*) AS orders FROM purchase_orders po JOIN parties pa ON pa.id=po.vendor_id "
                   "WHERE po.workspace_id=?" + pw + " GROUP BY pa.id ORDER BY orders DESC LIMIT 100")
            rows = [(r['label'], str(r['orders'])) for r in store._db.execute(sql, [wid] + args).fetchall()]
            return ('Purchases by supplier', shop + span, [('Supplier', 0.65, 'left'), ('Orders', 0.35, 'right')], rows, None)
        if group == 'store':
            sql = ("SELECT l.name AS label, COUNT(*) AS orders FROM purchase_orders po JOIN locations l ON l.id=po.location_id "
                   "WHERE po.workspace_id=?" + pw + " GROUP BY l.id ORDER BY orders DESC")
            rows = [(r['label'], str(r['orders'])) for r in store._db.execute(sql, [wid] + args).fetchall()]
            return ('Purchases by store', shop + span, [('Store', 0.65, 'left'), ('Orders', 0.35, 'right')], rows, None)

    if metric == 'stock':
        sql = ("SELECT l.name AS store, p.sku, p.name, COALESCE((SELECT SUM(sl.quantity_delta) FROM stock_ledger sl WHERE sl.workspace_id=p.workspace_id AND sl.product_id=p.id AND sl.location_id=l.id),0) AS on_hand "
               "FROM retail_products p JOIN locations l ON l.workspace_id=p.workspace_id AND l.active=1 WHERE p.workspace_id=? AND p.active=1 ORDER BY l.name, p.sku")
        rows = [(r['store'], r['sku'], r['name'], str(r['on_hand'])) for r in store._db.execute(sql, (wid,)).fetchall()]
        return ('Stock by store', shop, [('Store', 0.2, 'left'), ('SKU', 0.15, 'left'), ('Item', 0.45, 'left'), ('On hand', 0.2, 'right')], rows, None)

    if metric in ('owed_by_me', 'owed_to_me'):
        kind = 'purchase_bill' if metric == 'owed_by_me' else 'sales_invoice'
        party_label = 'Supplier' if metric == 'owed_by_me' else 'Customer'
        sql = ("SELECT pa.name AS label, COUNT(*) AS docs, SUM(d.balance_minor) AS bal FROM documents d JOIN parties pa ON pa.id=d.party_id "
               "WHERE d.workspace_id=? AND d.kind=? AND d.status='posted' AND d.balance_minor>0 GROUP BY pa.id ORDER BY bal DESC")
        rows = [(r['label'], str(r['docs']), _money(r['bal'], currency)) for r in store._db.execute(sql, (wid, kind)).fetchall()]
        total = store._db.execute("SELECT COALESCE(SUM(balance_minor),0) AS t FROM documents WHERE workspace_id=? AND kind=? AND status='posted' AND balance_minor>0", (wid, kind)).fetchone()['t']
        title = 'What you owe each supplier' if metric == 'owed_by_me' else 'What each customer owes you'
        count_label = 'Open bills' if metric == 'owed_by_me' else 'Unpaid invoices'
        return (title, shop, [(party_label, 0.5, 'left'), (count_label, 0.2, 'right'), ('Owed', 0.3, 'right')], rows, ('Totals', '', _money(total, currency)))

    raise ValueError('That combination is not available yet.')


def understood_line(parsed):
    u = parsed['understood']
    names = {'sales': 'sales', 'purchases': 'purchases', 'stock': 'stock', 'owed_by_me': 'what you owe suppliers', 'owed_to_me': 'what customers owe you'}
    bits = [names[u['metric']]]
    if u['group_by']:
        bits.append('by ' + u['group_by'])
    if u['start'] and u['end']:
        bits.append('%s to %s' % (u['start'], u['end']))
    elif u['period'] != 'all time':
        bits.append(u['period'])
    return 'Showing: ' + ', '.join(bits)

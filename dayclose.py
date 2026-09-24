"""Evening close: the end-of-day ritual.

Computes a plain-language summary of one day from the posted books,
lets the owner count the cash in the drawer, and saves a close record
(date, totals snapshot, counted cash, difference, optional note).
Saving a close never locks the day; a later edit simply makes a saved
close show as changed when the books for that date no longer match the
snapshot.
"""
import json
import re
import secrets
from datetime import date as _date

from store import utcnow

_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _ident(prefix):
    return prefix + '_' + secrets.token_hex(8)


def day_summary(store, wid, day):
    """Totals for one day from the posted books. Read-only."""
    if not _DATE.match(day or ''):
        raise ValueError('That is not a valid day.')
    sales = store._db.execute(
        "SELECT COALESCE(SUM(total_minor),0) AS t, COUNT(*) AS n FROM documents "
        "WHERE workspace_id=? AND kind='sales_invoice' AND status='posted' AND issue_date=?", (wid, day)).fetchone()
    pay = store._db.execute(
        "SELECT a.system_key AS k, COALESCE(SUM(jl.debit_minor),0) AS t FROM journal_lines jl "
        "JOIN accounts a ON a.id=jl.account_id "
        "JOIN journals j ON j.id=jl.journal_id "
        "JOIN documents d ON d.id=j.source_id AND j.source_type='payment' "
        "WHERE d.workspace_id=? AND d.kind='payment' AND d.status='posted' AND d.issue_date=? "
        "AND a.system_key IN ('cash','bank') GROUP BY a.system_key", (wid, day)).fetchall()
    paid = {r['k']: int(r['t']) for r in pay}
    credit = store._db.execute(
        "SELECT COALESCE(SUM(balance_minor),0) AS t FROM documents "
        "WHERE workspace_id=? AND kind='sales_invoice' AND status='posted' AND issue_date=? AND balance_minor>0",
        (wid, day)).fetchone()
    items = store._db.execute(
        "SELECT COALESCE(SUM(-CAST(quantity_delta AS REAL)),0) AS t FROM stock_ledger "
        "WHERE workspace_id=? AND kind='sale' AND date(effective_at)=?", (wid, day)).fetchone()
    cash = store._db.execute(
        "SELECT COALESCE(SUM(jl.debit_minor - jl.credit_minor),0) AS t FROM journal_lines jl "
        "JOIN accounts a ON a.id=jl.account_id JOIN journals j ON j.id=jl.journal_id "
        "WHERE j.workspace_id=? AND a.system_key='cash' AND j.effective_date<=?", (wid, day)).fetchone()
    return {
        'date': day,
        'sales_total_minor': int(sales['t']),
        'sales_count': int(sales['n']),
        'payments_cash_minor': paid.get('cash', 0),
        'payments_bank_minor': paid.get('bank', 0),
        'credit_minor': int(credit['t']),
        'items_sold': items['t'],
        'expected_cash_minor': int(cash['t']),
    }


def save_close(store, wid, actor, day, counted_cash_minor, note=''):
    """Save (or replace) the close record for a day. Never locks anything."""
    if not _DATE.match(day or ''):
        raise ValueError('That is not a valid day.')
    try:
        _date.fromisoformat(day)
    except ValueError:
        raise ValueError('That is not a valid day.')
    if day > utcnow()[:10]:
        raise ValueError('You cannot close a day that has not happened yet.')
    try:
        counted = int(counted_cash_minor)
    except (TypeError, ValueError):
        raise ValueError('Type the counted cash as a number.')
    if counted < 0:
        raise ValueError('Counted cash cannot be negative.')
    note = (note or '').strip()[:300]
    snap = day_summary(store, wid, day)
    diff = counted - snap['expected_cash_minor']
    with store.tx():
        store._db.execute(
            'INSERT INTO day_closes(id,workspace_id,close_date,snapshot_json,counted_cash_minor,difference_minor,note,actor_id,created_at) '
            'VALUES(?,?,?,?,?,?,?,?,?) '
            'ON CONFLICT(workspace_id,close_date) DO UPDATE SET snapshot_json=excluded.snapshot_json, '
            'counted_cash_minor=excluded.counted_cash_minor, difference_minor=excluded.difference_minor, '
            'note=excluded.note, actor_id=excluded.actor_id, created_at=excluded.created_at',
            (_ident('close'), wid, day, json.dumps(snap), counted, diff, note, actor, utcnow()))
    store._audit(wid, actor, 'dayclose.save', {'date': day, 'difference_minor': diff})
    return {'date': day, 'snapshot': snap, 'counted_cash_minor': counted, 'difference_minor': diff, 'note': note}


def list_closes(store, wid, limit=60):
    """Past closes, newest first. Recomputes each day and flags closes whose books changed since."""
    rows = store._db.execute(
        'SELECT close_date, snapshot_json, counted_cash_minor, difference_minor, note, created_at '
        'FROM day_closes WHERE workspace_id=? ORDER BY close_date DESC LIMIT ?', (wid, limit)).fetchall()
    out = []
    for r in rows:
        snap = json.loads(r['snapshot_json'])
        now = day_summary(store, wid, r['close_date'])
        changed = any(now[k] != snap.get(k) for k in
                      ('sales_total_minor', 'payments_cash_minor', 'payments_bank_minor',
                       'credit_minor', 'items_sold', 'expected_cash_minor'))
        out.append({'date': r['close_date'], 'snapshot': snap, 'counted_cash_minor': r['counted_cash_minor'],
                    'difference_minor': r['difference_minor'], 'note': r['note'],
                    'created_at': r['created_at'], 'changed_since_close': changed})
    return out

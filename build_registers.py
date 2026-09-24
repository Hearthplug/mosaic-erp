"""Slice 4: import the paper books small shops actually keep - customer credit
books, supplier ledgers and stock registers - from photos or spreadsheets.

The extraction (vision or CSV) becomes editable rows. Recording re-validates
everything server-side and fails closed: a party's signed entries must add up
to the running balance the book shows before anything is written. Receivables
and payables post through the same document engine as recorded bills; stock
lands as opening quantities in the stock ledger."""
import csv
import datetime
import io
import re
import secrets
from decimal import Decimal, InvalidOperation

from store import NotFound

REGISTERS = ('credit_book', 'supplier_ledger', 'stock_register')
_PAYMENT_WORDS = re.compile(r'paid|payment|received|recv|jama|deposit|repay', re.I)


def _ident(prefix):
    return prefix + '_' + secrets.token_hex(8)


def _qty(text):
    try:
        q = Decimal(str(text).strip())
    except InvalidOperation:
        return None
    return q if q > 0 else None


def _date(text):
    text = str(text or '').strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _field(fields, *names):
    for f in fields or []:
        if str(f.get('name', '')).strip().lower() in names:
            return str(f.get('value', '')).strip()
    return ''


def draft_from_extraction(store, wid, register, extraction):
    """Photo path: one book page. Returns editable rows plus warnings."""
    if register not in REGISTERS:
        raise ValueError('unsupported register')
    from build_bills import amount_minor
    fields = extraction.get('fields') or []
    lines = extraction.get('lines') or []
    warnings = []
    if register == 'stock_register':
        items = []
        for ln in lines[:60]:
            name = str(ln.get('description', '')).strip()[:120]
            if not name:
                continue
            qty = _qty(ln.get('quantity'))
            cost = amount_minor(ln.get('unit_price'))
            if cost is None:
                cost = amount_minor(ln.get('amount'))
            items.append({'item': name, 'quantity': str(qty) if qty else '', 'unit_cost_minor': cost})
        stated = amount_minor(_field(fields, 'total', 'total value', 'value', 'grand total'))
        if stated is None:
            warnings.append('No total value was read. If the register shows one, type it so the import can check itself.')
        if any(i['unit_cost_minor'] is None for i in items):
            warnings.append('Some items have no cost. Their stock value will count as zero.')
        if not items:
            warnings.append('No item rows were read clearly. Type the items below instead.')
        return {'register': register, 'items': items, 'stated_total_minor': stated, 'warnings': warnings}
    party = _field(fields, 'name', 'customer', 'customer name', 'supplier', 'supplier name', 'vendor')
    entries = []
    from datetime import date as _today
    today = _today.today()
    for ln in lines[:60]:
        raw = str(ln.get('description', '')).strip()[:160]
        amount = amount_minor(ln.get('amount')) or amount_minor(ln.get('unit_price'))
        if not raw and amount is None:
            continue
        iso, detail = _strip_leading_date(raw, today)
        entries.append({'date': iso, 'detail': detail or raw, 'kind': 'payment' if _PAYMENT_WORDS.search(raw) else 'credit',
                        'amount_minor': amount})
    stated = amount_minor(_field(fields, 'balance', 'running balance', 'total', 'total due', 'outstanding'))
    if stated is None:
        warnings.append('No running balance was read. Type the balance the book shows so the import can check itself.')
    if any(e['amount_minor'] is None for e in entries):
        warnings.append('Some rows have no readable amount. Fix them before recording.')
    if not entries:
        warnings.append('No dated entries were read clearly. Type the entries below instead.')
    return {'register': register, 'party': party, 'entries': entries, 'stated_balance_minor': stated, 'warnings': warnings}



_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
           'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
_LEAD_DATE = re.compile(
    r'^\s*(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})\s+([A-Za-z]{3,9})|([A-Za-z]{3,9})\s+(\d{1,2})|(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?)\b\s*[-:\u2013\u2014.,]?\s*')


def _strip_leading_date(detail, today):
    """Split a leading date off a book line ('12 Sep - rice and oil'). Returns (iso_date, rest)."""
    from datetime import date as _date, timedelta
    detail = (detail or '').strip()
    m = _LEAD_DATE.match(detail)
    if not m:
        return '', detail
    g = m.groups()
    try:
        if g[0]:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
            roll = False
        elif g[3]:
            d, mo, y = int(g[3]), _MONTHS[g[4][:3].lower()], today.year
            roll = True
        elif g[5]:
            mo, d, y = _MONTHS[g[5][:3].lower()], int(g[6]), today.year
            roll = True
        else:
            d, mo = int(g[7]), int(g[8])
            y = int(g[9]) if g[9] else today.year
            if y < 100:
                y += 2000
            roll = not g[9]
        dt = _date(y, mo, d)
        if roll and dt > today + timedelta(days=7):
            dt = _date(y - 1, mo, d)
        iso = dt.isoformat()
    except (KeyError, ValueError):
        return '', detail
    return iso, detail[m.end():].strip()


_CREDIT_HEADERS = ({'name', 'customer', 'customer name', 'party'}, {'date'}, {'amount', 'amount_minor'})
_STOCK_HEADERS = ({'item', 'sku', 'product', 'name'}, {'quantity', 'qty', 'qty on hand', 'on hand'})


def _pick(row, names):
    for k, v in row.items():
        if k and k.strip().lower() in names:
            return (v or '').strip()
    return ''


def draft_from_csv(store, wid, register, text):
    """Spreadsheet path: many parties or items in one sheet."""
    if register not in REGISTERS:
        raise ValueError('unsupported register')
    from build_bills import amount_minor
    rows = list(csv.DictReader(io.StringIO(text or '')))
    if not rows:
        raise ValueError('The sheet has no rows.')
    warnings = []
    if register == 'stock_register':
        items = []
        for r in rows[:500]:
            name = _pick(r, _STOCK_HEADERS[0])
            if not name:
                continue
            qty = _qty(_pick(r, _STOCK_HEADERS[1]))
            cost = amount_minor(_pick(r, {'cost', 'unit cost', 'unit_cost', 'cost price'}))
            items.append({'item': name[:120], 'quantity': str(qty) if qty else '', 'unit_cost_minor': cost})
        if any(i['unit_cost_minor'] is None for i in items):
            warnings.append('Some items have no cost. Their stock value will count as zero.')
        return {'register': register, 'items': items, 'stated_total_minor': None, 'warnings': warnings}
    party_names = _CREDIT_HEADERS[0] if register == 'credit_book' else ({'supplier', 'supplier name', 'vendor', 'name', 'party'})
    entries = []
    for r in rows[:500]:
        party = _pick(r, party_names)
        amount = amount_minor(_pick(r, {'amount', 'value'}))
        if not party or amount is None:
            continue
        kind_raw = _pick(r, {'type', 'kind', 'entry', 'dr/cr'}).lower()
        kind = 'payment' if (kind_raw.startswith('pay') or kind_raw in ('cr', 'credit received', 'payment') or _PAYMENT_WORDS.search(kind_raw)) else 'credit'
        entries.append({'party': party[:120], 'date': _date(_pick(r, {'date'})) or '',
                        'detail': _pick(r, {'detail', 'description', 'note', 'particulars'})[:160],
                        'kind': kind, 'amount_minor': amount})
    if not entries:
        raise ValueError('No usable rows. The sheet needs a name, an amount and optionally a date and type per row.')
    balances = {}
    for r in rows[:500]:
        party = _pick(r, party_names)
        bal = amount_minor(_pick(r, {'balance', 'running balance', 'outstanding'}))
        if party and bal is not None:
            balances[party[:120]] = bal
    if not balances:
        warnings.append('The sheet has no balance column. Type each party\'s balance so the import can check itself.')
    return {'register': register, 'party': '', 'entries': entries, 'stated_balances': balances, 'warnings': warnings}


def _check_rows(rows, amount_key):
    for i, r in enumerate(rows, 1):
        if r[amount_key] is None or int(r[amount_key]) < 0:
            raise ValueError('Row %d needs an amount of zero or more.' % i)


def record_register(store, books, wid, actor, payload):
    """Record the owner-reviewed register. Every row is re-validated here and
    the running balance must match before anything is written (fail closed)."""
    register = str(payload.get('register') or '')
    if register not in REGISTERS:
        raise ValueError('unsupported register')
    if register == 'stock_register':
        return _record_stock(store, wid, actor, payload)
    return _record_book(store, books, wid, actor, register, payload)


def _record_book(store, books, wid, actor, register, payload):
    entries = payload.get('entries') or []
    if not entries:
        raise ValueError('Add at least one entry.')
    clean = []
    for x in entries[:300]:
        party = str(x.get('party') or payload.get('party') or '').strip()[:160]
        if not party:
            raise ValueError('Every entry needs a name.')
        amount = x.get('amount_minor')
        if amount is None or int(amount) < 0:
            raise ValueError('Every entry needs an amount of zero or more.')
        kind = 'payment' if x.get('kind') == 'payment' else 'credit'
        date = _date(x.get('date'))
        if str(x.get('date') or '').strip() and not date:
            raise ValueError('An entry date is not a real date (use YYYY-MM-DD).')
        clean.append({'party': party, 'date': date, 'detail': str(x.get('detail', '')).strip()[:160],
                      'kind': kind, 'amount_minor': int(amount)})
    parties = {}
    for e in clean:
        p = parties.setdefault(e['party'], {'credit': 0, 'payment': 0, 'entries': []})
        p[e['kind']] += e['amount_minor']
        p['entries'].append(e)
    stated_in = payload.get('stated_balances') or {}
    single_stated = payload.get('stated_balance_minor')
    today = datetime.date.today().isoformat()
    kind_label = 'customer' if register == 'credit_book' else 'supplier'
    doc_kind = 'sales_invoice' if register == 'credit_book' else 'purchase_bill'
    party_kinds = ('customer', 'both') if register == 'credit_book' else ('vendor', 'both')
    plan = []
    for party, p in parties.items():
        stated = stated_in.get(party, single_stated)
        if stated is None:
            raise ValueError('Type the running balance the book shows for ' + party + ' before recording.')
        stated = int(stated)
        if stated < 0:
            raise ValueError('Balances cannot be negative.')
        if p['credit'] - p['payment'] != stated:
            raise ValueError('%s: the entries add up to %d but the book shows %d. Fix the entries or the balance before recording.' % (party, p['credit'] - p['payment'], stated))
        dated = all(e['date'] for e in p['entries'])
        plan.append({'party': party, 'stated': stated, 'dated': dated, **p})
    # Everything validated; write.
    recorded = []
    for pl in plan:
        party = pl['party']
        row = store._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind IN (?,?) AND active=1 AND lower(name)=lower(?)",
                                (wid, party_kinds[0], party_kinds[1], party)).fetchone()
        pid = row['id'] if row else books.create_party(wid, actor, party_kinds[0], party)['id']
        docs = []
        if pl['dated']:
            for e in sorted(pl['entries'], key=lambda x: x['date']):
                if e['kind'] != 'credit':
                    continue
                doc = books.create_document(wid, actor, doc_kind, e['date'],
                                            [{'description': e['detail'] or ('Credit from the ' + kind_label + ' book'), 'quantity': '1', 'unit_price_minor': e['amount_minor']}],
                                            party_id=pid, memo='Imported from a ' + kind_label + ' book in the Build screen')
                books.approve_document(wid, actor, doc['id'])
                books.post_document(wid, actor, doc['id'])
                docs.append(doc)
            remaining = pl['credit'] - pl['stated']
            for doc in docs:
                if remaining <= 0:
                    break
                cur = store._db.execute('SELECT balance_minor FROM documents WHERE id=?', (doc['id'],)).fetchone()['balance_minor']
                pay = min(remaining, cur)
                books.record_payment(wid, actor, doc['id'], pay, today)
                remaining -= pay
        else:
            doc = books.create_document(wid, actor, doc_kind, today,
                                        [{'description': 'Opening balance from the ' + kind_label + ' book (%d entries)' % len(pl['entries']), 'quantity': '1', 'unit_price_minor': pl['stated']}],
                                        party_id=pid, memo='Imported from a ' + kind_label + ' book in the Build screen - dated history not kept')
            books.approve_document(wid, actor, doc['id'])
            books.post_document(wid, actor, doc['id'])
            docs.append(doc)
        balance = sum(store._db.execute('SELECT balance_minor FROM documents WHERE id=?', (d['id'],)).fetchone()['balance_minor'] for d in docs)
        if balance != pl['stated']:
            raise ValueError('Recorded balance for ' + party + ' does not match the book. Nothing else was recorded; please try again.')
        recorded.append({'party': party, 'stated_minor': pl['stated'], 'documents': len(docs), 'entries': len(pl['entries']), 'dated_history': pl['dated']})
    total = sum(r['stated_minor'] for r in recorded)
    store._audit(wid, actor, 'build.register.record', {'register': register, 'parties': len(recorded), 'total_minor': total})
    return {'register': register, 'recorded': recorded, 'total_minor': total, 'party_label': kind_label}


def _record_stock(store, wid, actor, payload):
    items = payload.get('items') or []
    if not items:
        raise ValueError('Add at least one item.')
    clean = []
    for x in items[:300]:
        name = str(x.get('item') or '').strip()[:120]
        if not name:
            raise ValueError('Every row needs an item name.')
        qty = _qty(x.get('quantity'))
        if qty is None:
            raise ValueError(name + ': the quantity is missing or not a number above zero.')
        cost = x.get('unit_cost_minor')
        cost = int(cost) if cost is not None else 0
        if cost < 0:
            raise ValueError(name + ': cost cannot be negative.')
        clean.append({'item': name, 'quantity': format(qty.normalize(), 'f'), 'unit_cost_minor': cost})
    stated = payload.get('stated_total_minor')
    total = sum(int((Decimal(c['quantity']) * c['unit_cost_minor']).quantize(Decimal('1'))) for c in clean)
    if stated is not None and int(stated) != total:
        raise ValueError('The items add up to %d but the register shows %d. Fix the rows or the total before recording.' % (total, int(stated)))
    loc = store._db.execute("SELECT id FROM locations WHERE workspace_id=? AND active=1 ORDER BY rowid LIMIT 1", (wid,)).fetchone()
    if not loc:
        with store.tx():
            store._db.execute('INSERT INTO locations(id,workspace_id,code,name,kind) VALUES(?,?,?,?,?)',
                              (_ident('loc'), wid, 'MAIN', 'Main', 'store'))
        loc = store._db.execute("SELECT id FROM locations WHERE workspace_id=? AND active=1 ORDER BY rowid LIMIT 1", (wid,)).fetchone()
    from store import utcnow
    batch = _ident('reg')
    recorded = []
    for c in clean:
        prod = store._db.execute("SELECT id FROM retail_products WHERE workspace_id=? AND active=1 AND lower(name)=lower(?)", (wid, c['item'])).fetchone()
        if prod:
            pid = prod['id']
        else:
            pid = _ident('prd')
            sku = re.sub(r'[^A-Za-z0-9]+', '-', c['item']).strip('-').upper()[:40] or 'ITEM'
            base, n = sku, 2
            while store._db.execute("SELECT 1 FROM retail_products WHERE workspace_id=? AND sku=?", (wid, sku)).fetchone():
                sku = base + '-' + str(n); n += 1
            with store.tx():
                store._db.execute('INSERT INTO retail_products(id,workspace_id,sku,name,unit,selling_price_minor,cost_minor) VALUES(?,?,?,?,?,?,?)',
                                  (pid, wid, sku, c['item'], 'each', 0, c['unit_cost_minor']))
        with store.tx():
            store._db.execute('INSERT INTO stock_ledger(id,workspace_id,product_id,location_id,effective_at,quantity_delta,unit_cost_minor,kind,source_type,source_id,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                              (_ident('stk'), wid, pid, loc['id'], utcnow(), c['quantity'], c['unit_cost_minor'], 'opening', 'build_register', batch, actor, utcnow()))
        recorded.append({'item': c['item'], 'quantity': c['quantity'], 'unit_cost_minor': c['unit_cost_minor']})
    store._audit(wid, actor, 'build.register.record', {'register': 'stock_register', 'items': len(recorded), 'total_minor': total})
    return {'register': 'stock_register', 'recorded': recorded, 'total_minor': total}

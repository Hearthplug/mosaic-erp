"""Supplier-bill recording from photo extractions (Build screen, v2.0 slice 2).

The vision extraction proposes vendor, dates and item lines; the owner reviews
and edits on screen; this module re-validates everything server-side before a
purchase_bill document is created, approved and posted to payables. Nothing is
ever posted from raw extraction output.
"""
import datetime
import re
from decimal import Decimal, InvalidOperation

VENDOR_FIELD_NAMES = ('vendor', 'supplier', 'seller', 'from', 'billed by')
NUMBER_FIELD_NAMES = ('invoice number', 'bill number', 'invoice no', 'bill no', 'number', 'reference')
DATE_FIELD_NAMES = ('date', 'invoice date', 'bill date', 'issue date')
DUE_FIELD_NAMES = ('due date', 'due', 'payment due')
TOTAL_FIELD_NAMES = ('total', 'total due', 'amount due', 'grand total', 'total amount')


def amount_minor(text):
    """Parse a written amount like '$1,234.50' or '48,30' into minor units.
    Returns None when the text is not a readable amount."""
    if text is None:
        return None
    t = re.sub(r'[^\d,.\-]', '', str(text).strip())
    if not t or t in ('-', '.', ','):
        return None
    if t.count(',') == 1 and t.count('.') == 0 and len(t.rsplit(',', 1)[1]) == 2:
        t = t.replace(',', '.')  # decimal comma
    else:
        t = t.replace(',', '')  # thousands separators
    try:
        return int((Decimal(t) * 100).quantize(Decimal('1')))
    except (InvalidOperation, ValueError):
        return None


def _field(fields, names):
    for f in fields:
        if str(f.get('name', '')).strip().lower() in names:
            return str(f.get('value', '')).strip(), f.get('confidence', 0)
    return '', 0



def _base_currency(store, wid):
    row = store._db.execute("SELECT base_currency FROM accounting_settings WHERE workspace_id=?", (wid,)).fetchone()
    return row['base_currency'] if row else None


def draft_from_extraction(store, wid, extraction):
    """Map a photo extraction onto a bill draft for owner review. No writes."""
    fields = extraction.get('fields') or []
    vendor, vendor_conf = _field(fields, VENDOR_FIELD_NAMES)
    number, _ = _field(fields, NUMBER_FIELD_NAMES)
    issue, _ = _field(fields, DATE_FIELD_NAMES)
    due, _ = _field(fields, DUE_FIELD_NAMES)
    total_text, total_conf = _field(fields, TOTAL_FIELD_NAMES)
    lines = []
    for ln in (extraction.get('lines') or [])[:60]:
        if not isinstance(ln, dict):
            continue
        desc = str(ln.get('description', '')).strip()[:120]
        qty = str(ln.get('quantity', '1')).strip() or '1'
        unit = amount_minor(ln.get('unit_price'))
        if not desc and unit is None:
            continue
        lines.append({'description': desc or 'Line', 'quantity': qty, 'unit_price_minor': unit})
    matched = None
    if vendor:
        row = store._db.execute(
            "SELECT id, name FROM parties WHERE workspace_id=? AND kind IN ('vendor','both') AND active=1 AND lower(name)=lower(?)",
            (wid, vendor)).fetchone()
        if row:
            matched = {'id': row['id'], 'name': row['name']}
    stated = amount_minor(total_text)
    warnings = []
    if not vendor:
        warnings.append('The supplier name was not read - type it in before recording.')
    elif not matched:
        warnings.append(vendor + ' is not in your suppliers yet - it will be added when you record.')
    if not lines:
        warnings.append('No item lines were read. Add them on this screen before recording.')
    if stated is None:
        warnings.append('The bill total was not read clearly - type it in before recording.')
    return {'vendor': vendor, 'vendor_match': matched, 'vendor_new': bool(vendor and not matched),
            'vendor_confidence': vendor_conf, 'number': number, 'issue_date': issue, 'due_date': due,
            'lines': lines, 'stated_total_minor': stated, 'total_confidence': total_conf,
            'warnings': warnings, 'base_currency': _base_currency(store, wid)}


def record_bill(store, books, wid, actor, payload):
    """Create, approve and post a purchase_bill from the owner-reviewed draft.
    Every amount and date is re-validated here; the books hold quantity x unit price."""
    vendor = str(payload.get('vendor') or '').strip()[:160]
    if not vendor:
        raise ValueError('The supplier name is required.')
    raw_lines = payload.get('lines') or []
    if not raw_lines:
        raise ValueError('Add at least one line.')
    clean = []
    for x in raw_lines[:60]:
        desc = str(x.get('description', '')).strip()[:120] or 'Line'
        try:
            qty = Decimal(str(x.get('quantity', '1')).strip() or '1')
        except InvalidOperation:
            raise ValueError('A line quantity is not a number.')
        if qty <= 0:
            raise ValueError('Line quantities must be above zero.')
        unit = x.get('unit_price_minor')
        if unit is None:
            raise ValueError('Every line needs a unit price.')
        unit = int(unit)
        if unit < 0:
            raise ValueError('Line prices cannot be negative.')
        clean.append({'description': desc, 'quantity': format(qty.normalize(), 'f'), 'unit_price_minor': unit})
    total = sum(int((Decimal(c['quantity']) * c['unit_price_minor']).quantize(Decimal('1'))) for c in clean)
    stated = payload.get('stated_total_minor')
    if stated is None:
        raise ValueError('Type the total shown on the bill before recording.')
    if int(stated) != total:
        raise ValueError('The lines add up to a different amount than the bill total. Fix the lines or the total before recording.')
    issue = str(payload.get('issue_date') or '').strip() or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(issue)
    except ValueError:
        raise ValueError('The bill date is not a real date (use YYYY-MM-DD).')
    due = str(payload.get('due_date') or '').strip() or None
    if due:
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            raise ValueError('The due date is not a real date (use YYYY-MM-DD).')
    pid = payload.get('party_id')
    if pid:
        row = store._db.execute("SELECT id FROM parties WHERE id=? AND workspace_id=? AND kind IN ('vendor','both') AND active=1", (pid, wid)).fetchone()
        if not row:
            raise ValueError('That supplier is not in this workspace.')
    else:
        row = store._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind IN ('vendor','both') AND active=1 AND lower(name)=lower(?)", (wid, vendor)).fetchone()
        if row:
            pid = row['id']
        else:
            pid = books.create_party(wid, actor, 'vendor', vendor)['id']
    number = str(payload.get('number') or '').strip()[:60]
    memo = 'Recorded from a photo in the Build screen' + ((' - supplier ref ' + number) if number else '')
    doc = books.create_document(wid, actor, 'purchase_bill', issue,
                                [{'description': c['description'], 'quantity': c['quantity'], 'unit_price_minor': c['unit_price_minor']} for c in clean],
                                party_id=pid, due_date=due, memo=memo)
    books.approve_document(wid, actor, doc['id'])
    books.post_document(wid, actor, doc['id'])
    store._audit(wid, actor, 'build.bill.record', {'document_id': doc['id'], 'number': doc['number'], 'total_minor': doc['total_minor'], 'vendor': vendor})
    return {'id': doc['id'], 'number': doc['number'], 'status': 'posted', 'total_minor': doc['total_minor'], 'vendor': vendor, 'party_id': pid}


_UNIT_WORDS = {'kg', 'g', 'l', 'ml', 'pc', 'pcs', 'pack', 'packet', 'bag', 'box', 'bottle', 'x', 'of', 'the', 'and', 'no'}


def _tokens(text):
    return set(t for t in re.findall(r'[a-z0-9]+', (text or '').lower()) if t not in _UNIT_WORDS and len(t) > 1)


def stock_draft(store, wid, lines):
    """Match owner-reviewed bill lines to catalog products for stock intake.
    Exact names match outright; otherwise the owner picks from suggestions or
    skips the line - nothing here creates products or touches stock."""
    products = store._db.execute(
        'SELECT id, sku, name FROM retail_products WHERE workspace_id=? AND active=1 ORDER BY name', (wid,)).fetchall()
    out = []
    for x in (lines or [])[:60]:
        desc = str(x.get('description', '')).strip()[:120]
        if not desc:
            continue
        try:
            qty = Decimal(str(x.get('quantity', '1')).strip() or '1')
        except InvalidOperation:
            qty = Decimal('1')
        unit = x.get('unit_price_minor')
        toks = _tokens(desc)
        scored = []
        for p in products:
            ptoks = _tokens(p['name'])
            if not ptoks:
                continue
            common = toks & ptoks
            if not common:
                continue
            scored.append((len(common) / max(len(toks | ptoks), 1), p))
        scored.sort(key=lambda e: (-e[0], e[1]['name']))
        suggestions = [{'id': p['id'], 'sku': p['sku'], 'name': p['name']} for _, p in scored[:3]]
        exact = next((p for p in products if p['name'].lower() == desc.lower()), None)
        best = suggestions[0] if (suggestions and scored[0][0] >= 0.5) else None
        match = {'id': exact['id'], 'sku': exact['sku'], 'name': exact['name']} if exact else best
        out.append({'description': desc, 'quantity': format(qty.normalize(), 'f'),
                    'unit_cost_minor': int(unit) if unit is not None else None,
                    'match': match, 'suggestions': suggestions})
    return {'lines': out}


def record_bill_stock(store, books, retail, wid, actor, payload):
    """Receive owner-confirmed bill lines into stock as an approved, fully
    received purchase order. Products, store and quantities are re-validated
    here; the owner picked every product on screen first."""
    location_id = str(payload.get('location_id') or '').strip()
    loc = store._db.execute('SELECT id, name FROM locations WHERE id=? AND workspace_id=? AND active=1', (location_id, wid)).fetchone()
    if not loc:
        raise ValueError('Choose a store to receive the stock into.')
    vendor = str(payload.get('vendor') or '').strip()[:160]
    pid = str(payload.get('party_id') or '').strip()
    if pid:
        row = store._db.execute("SELECT id FROM parties WHERE id=? AND workspace_id=? AND kind IN ('vendor','both') AND active=1", (pid, wid)).fetchone()
        if not row:
            raise ValueError('That supplier is not in this workspace.')
    elif vendor:
        row = store._db.execute("SELECT id FROM parties WHERE workspace_id=? AND kind IN ('vendor','both') AND active=1 AND lower(name)=lower(?)", (wid, vendor)).fetchone()
        pid = row['id'] if row else books.create_party(wid, actor, 'vendor', vendor)['id']
    else:
        raise ValueError('The supplier name is required.')
    raw = payload.get('lines') or []
    if not raw:
        raise ValueError('Pick at least one line to add to stock.')
    clean = []
    for x in raw[:60]:
        prod_id = str(x.get('product_id') or '').strip()
        prod = store._db.execute('SELECT id, name FROM retail_products WHERE id=? AND workspace_id=? AND active=1', (prod_id, wid)).fetchone()
        if not prod:
            raise ValueError('Every line needs an item from your catalog.')
        try:
            qty = Decimal(str(x.get('quantity', '1')).strip() or '1')
        except InvalidOperation:
            raise ValueError('A line quantity is not a number.')
        if qty <= 0:
            raise ValueError('Line quantities must be above zero.')
        unit = x.get('unit_cost_minor')
        unit = int(unit) if unit is not None else 0
        if unit < 0:
            raise ValueError('Line costs cannot be negative.')
        clean.append({'product_id': prod['id'], 'quantity': format(qty.normalize(), 'f'), 'unit_cost_minor': unit})
    today = datetime.date.today().isoformat()
    po = retail.purchase_order(wid, actor, pid, location_id, today, clean, _base_currency(store, wid))
    retail.approve_purchase(wid, actor, po['id'])
    received = {r['id']: r['quantity'] for r in store._db.execute(
        'SELECT id, quantity FROM purchase_order_lines WHERE purchase_order_id=?', (po['id'],)).fetchall()}
    retail.receive_purchase(wid, actor, po['id'], received)
    store._audit(wid, actor, 'build.bill.stock', {'purchase_order_id': po['id'], 'number': po['number'], 'line_count': len(clean), 'location_id': location_id})
    return {'id': po['id'], 'number': po['number'], 'status': 'received', 'line_count': len(clean), 'location': loc['name']}

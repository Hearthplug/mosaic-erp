"""Jev interview mapper: raw owner answers -> Mosaic-friendly mapped values.

The Jev-dedicated path inside the interview. Each text question has a typed
field spec; answers are mapped in ONE batched pass, every proposal carries the
raw original plus a confidence, and anything below the auto-accept threshold -
or anything non-English in this English-only phase - is routed to owner
confirmation. Nothing is saved here: the owner confirms or edits side-by-side
before the normal apply path saves.
"""
import re, unicodedata
from jev_client import MockJevClient

AUTO_ACCEPT = 0.85      # at/above: pre-confirmed, owner can still edit
CONFIRM_BAND = 0.50     # below: proposed value left blank, owner decides

# Common English stopwords; a text answer with too few is treated as
# non-English and routed to owner confirmation in this English-only phase.
_EN_STOP = {'the','a','an','and','or','we','i','my','our','is','are','to','in','on','for','with','of','it','they','them','he','she','you','your','when','if','then','pay','sell','take'}

def looks_non_english(text):
    """Script check for everything; stopword-ratio check only for prose
    (proper nouns like shop names legitimately contain no stopwords)."""
    if any(unicodedata.category(ch).startswith('L') and ord(ch) >= 0x250 for ch in text or ''):
        return True
    words = re.findall(r"[a-zA-Z']+", (text or '').lower())
    if len(words) < 8:
        return False
    low = ' '.join(words)
    # English business vocabulary is strong evidence even when clipped
    # answers skip stopwords.
    if any(b in low for b in ('customer','pay','sell','stock','deliver','order','cash','card','staff','manager','shop','store','buy','supplier','refund','discount','invoice')):
        return False
    hits = sum(1 for w in words if w in _EN_STOP)
    return hits < 2 or hits / len(words) < 0.15


# Typed field specs. 'maps_to' names the profile/config key the value feeds.
# 'options' + 'evidence' drive the Choice primitive; 'noul' specs drive Noul.
TEXT_FIELD_SPECS = {
    'business_name': {'kind': 'clean', 'maps_to': 'business_name',
        'ask': 'the trading name people use for the business'},
    'selling': {'kind': 'choice', 'maps_to': 'selling_flow',
        'ask': 'how a normal sale starts and how the customer pays',
        'options': ['Walk-in checkout, pays on the spot', 'Order first, pay on delivery', 'Account sale, pays later', 'A mix of these'],
        'evidence': {
            'Walk-in checkout, pays on the spot': ['walk in', 'walks in', 'walk-in', 'counter', 'till', 'cashier', 'scan', 'shop', 'store', 'comes in', 'pays cash', 'pays by card', 'on the spot'],
            'Order first, pay on delivery': ['order', 'whatsapp', 'phone', 'online', 'deliver', 'delivery', 'collect on delivery', 'pay on delivery'],
            'Account sale, pays later': ['account', 'invoice', 'later', 'monthly', 'credit', 'end of month', 'month end', 'settle', '30 days', 'tab'],
            'A mix of these': ['sometimes', 'both', 'mix', 'depends', 'mostly', 'a few', 'regulars']}},
    'buying': {'kind': 'choice', 'maps_to': 'buying_flow',
        'ask': 'how buying is decided, approved and checked in',
        'options': ['Owner decides and checks deliveries', 'Staff order, owner approves', 'Anyone orders, deliveries checked', 'No formal buying step'],
        'evidence': {
            'Owner decides and checks deliveries': ['i decide', 'i order', 'myself', 'i check', 'owner'],
            'Staff order, owner approves': ['staff order', 'manager approves', 'i approve', 'ask me', 'approval', 'my ok', 'without my ok', 'nothing goes out', 'they order'],
            'Anyone orders, deliveries checked': ['anyone', 'whoever', 'check deliveries', 'count what arrives'],
            'No formal buying step': ['no process', 'just buy', 'informal', 'whenever']}},
    'discounts': {'kind': 'choice', 'maps_to': 'discount_rule',
        'ask': 'who can discount or refund and when a manager is needed',
        'options': ['Staff discount freely', 'Small discounts, manager above a limit', 'Only managers discount or refund'],
        'evidence': {
            'Staff discount freely': ['anyone can', 'freely', 'no limit', 'their judgement'],
            'Small discounts, manager above a limit': ['small', 'up to', 'limit', 'above', 'ask a manager', 'over that'],
            'Only managers discount or refund': ['only manager', 'only i can', 'only me', 'managers only', 'must ask', 'through me', 'no exceptions']}},
    'returns': {'kind': 'choice', 'maps_to': 'returns_flow',
        'ask': 'what happens when a customer returns something',
        'options': ['Refund and restock if unopened', 'Manager decides each return', 'Exchange only, no refunds', 'We do not take returns'],
        'evidence': {
            'Refund and restock if unopened': ['unopened', 'restock', 'back into stock', 'refund', 'receipt'],
            'Manager decides each return': ['manager', 'case by case', 'depends', 'check it', 'decide', 'wife', 'husband'],
            'Exchange only, no refunds': ['exchange', 'swap', 'replacement', 'no refund'],
            'We do not take returns': ['no returns', 'final sale', 'do not take back']}},
    'staff': {'kind': 'clean', 'maps_to': 'staff_summary',
        'ask': 'who works in the business and what each person may do'},
    'country': {'kind': 'country', 'maps_to': 'country',
        'ask': 'where the business is registered and sells'},
    'exceptions': {'kind': 'clean', 'maps_to': 'exceptions_summary',
        'ask': 'the unusual situation that confuses staff most'},
    'product_tax_facts': {'kind': 'clean', 'maps_to': 'tax_facts',
        'ask': 'products or services with special tax treatment'},
    'brand_colors': {'kind': 'clean', 'maps_to': 'brand_colors',
        'ask': 'the colours customers associate with the business'},
    'goal': {'kind': 'clean', 'maps_to': 'first_goal',
        'ask': 'the one thing Mosaic should fix in the first month'},
}

_COUNTRY_ALIASES = {
    'united kingdom': ('United Kingdom', 'GBP'), 'uk': ('United Kingdom', 'GBP'), 'britain': ('United Kingdom', 'GBP'), 'england': ('United Kingdom', 'GBP'), 'scotland': ('United Kingdom', 'GBP'),
    'india': ('India', 'INR'), 'united states': ('United States', 'USD'), 'usa': ('United States', 'USD'), 'us': ('United States', 'USD'), 'america': ('United States', 'USD'),
    'ireland': ('Ireland', 'EUR'), 'france': ('France', 'EUR'), 'germany': ('Germany', 'EUR'), 'spain': ('Spain', 'EUR'),
    'canada': ('Canada', 'CAD'), 'australia': ('Australia', 'AUD'),
    'uae': ('United Arab Emirates', 'AED'), 'dubai': ('United Arab Emirates', 'AED'),
    'south africa': ('South Africa', 'ZAR'), 'nigeria': ('Nigeria', 'NGN'), 'kenya': ('Kenya', 'KES'),
    'singapore': ('Singapore', 'SGD'), 'new zealand': ('New Zealand', 'NZD'), 'pakistan': ('Pakistan', 'PKR'),
}


def _clean(text):
    t = ' '.join((text or '').split()).strip(' .')
    return t[:1].upper() + t[1:] if t else ''


def map_text_field(key, raw, client):
    """One field: returns {key, raw, proposed, confidence, status, reason, maps_to}.
    status: auto_accept | confirm | blank_confirm | non_english | empty."""
    spec = TEXT_FIELD_SPECS[key]
    raw = (raw or '').strip()
    base = {'key': key, 'raw': raw, 'maps_to': spec['maps_to'], 'ask': spec['ask']}
    if not raw:
        return base | {'proposed': '', 'confidence': 0.0, 'status': 'empty', 'reason': 'Not answered'}
    if looks_non_english(raw):
        return base | {'proposed': raw, 'confidence': 0.0, 'status': 'non_english',
                       'reason': 'Looks non-English - Jev mapping is English-only for now, please confirm the meaning yourself'}
    if spec['kind'] == 'clean':
        return base | {'proposed': _clean(raw), 'confidence': 0.99, 'status': 'auto_accept',
                       'reason': 'Kept your words, tidied'}
    if spec['kind'] == 'country':
        low = raw.lower()
        for alias, (name, ccy) in _COUNTRY_ALIASES.items():
            if re.search(rf'\b{re.escape(alias)}\b', low):
                conf = 0.95 if alias in low.split() or len(alias) > 2 else 0.8
                return base | {'proposed': name, 'currency': ccy, 'confidence': conf,
                               'status': 'auto_accept' if conf >= AUTO_ACCEPT else 'confirm',
                               'reason': f'Recognised as {name} ({ccy})'}
        return base | {'proposed': _clean(raw), 'confidence': 0.4, 'status': 'blank_confirm',
                       'reason': 'Country not recognised - please check it'}
    # choice extraction
    r = client.choice(raw, spec['options'], context=f"Owner answered about {spec['ask']}: {raw}",
                      evidence=spec['evidence'])
    conf = r.confidence
    status = 'auto_accept' if conf >= AUTO_ACCEPT else ('confirm' if conf >= CONFIRM_BAND else 'blank_confirm')
    return base | {'proposed': r.pick if status != 'blank_confirm' else '', 'confidence': conf,
                   'status': status,
                   'reason': {'auto_accept': 'Clear match', 'confirm': 'Best match - please confirm',
                              'blank_confirm': 'Not confident - please choose'}[status],
                   'probabilities': r.probabilities}


def map_interview(answers, client=None):
    """Batched pass over every answered text question. Choice/multi answers are
    already structured and pass straight through. Returns proposals in question
    order plus counts for the review banner."""
    client = client or MockJevClient()
    proposals, auto, confirm = [], 0, 0
    for key in TEXT_FIELD_SPECS:
        if key not in answers:
            continue
        p = map_text_field(key, answers.get(key), client)
        proposals.append(p)
        if p['status'] == 'auto_accept': auto += 1
        elif p['status'] not in ('empty',): confirm += 1
    return {'proposals': proposals, 'auto_accepted': auto, 'needs_confirm': confirm,
            'english_only': True, 'client': getattr(client, 'label', 'jev')}

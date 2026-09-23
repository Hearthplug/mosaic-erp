"""Plain-language reconfiguration: the owner describes a change in their own
words ('we started taking card payments', 'we opened a second shop') and Jev
maps it to concrete Mosaic config changes. Every change is proposed with its
reason and confidence, shown side-by-side (current -> proposed), and applied
only after owner confirmation. English-only this phase.
"""
from jev_client import MockJevClient
from jev_mapper import looks_non_english, AUTO_ACCEPT, CONFIRM_BAND

# Reconfiguration targets: what a plain-language request can change.
# Each target: profile key, options, evidence, and a plain 'because'.
TARGETS = {
    'credit': {
        'ask': 'who can take goods now and pay later',
        'options': ['No credit', 'Customer credit', 'Supplier credit', 'Customer + supplier'],
        'evidence': {
            'No credit': ['no credit', 'paid immediately', 'cash only', 'pay now', 'stopped credit', 'upfront'],
            'Customer credit': ['customers pay later', 'customer account', 'invoice customers', 'customers owe', 'monthly account', 'monthly', 'on account', 'pay later', 'tab for customers'],
            'Supplier credit': ['supplier credit', 'pay suppliers later', '30 days to pay', 'supplier account'],
            'Customer + supplier': ['both', 'customers and suppliers', 'credit both ways']},
        'because': 'Credit tracking switches receivables/payables on or off.'},
    'locations': {
        'ask': 'how many places you sell or keep stock',
        'options': ['One store', '2 to 5 places', '6 to 20 places', 'More than 20'],
        'evidence': {
            'One store': ['one shop', 'single', 'just here', 'closed the other'],
            '2 to 5 places': ['second shop', 'two shops', 'three', 'another store', 'new branch', 'opened a', 'few places'],
            '6 to 20 places': ['six', 'seven', 'eight', 'ten', 'fifteen', 'chain'],
            'More than 20': ['twenty', 'thirty', 'fifty', 'national']},
        'because': 'More places switch stock transfers and branch reports on.'},
    'vertical': {
        'ask': 'what you mainly sell or do',
        'options': ['Grocery', 'Fashion', 'Electronics', 'Pharmacy', 'Beauty', 'Home goods', 'Repairs or services', 'A mix of these'],
        'evidence': {
            'Grocery': ['grocer', 'food', 'supermarket', 'convenience'],
            'Fashion': ['clothing', 'clothes', 'footwear', 'shoes', 'fashion', 'boutique'],
            'Electronics': ['electronic', 'phone', 'laptop', 'computer', 'gadget'],
            'Pharmacy': ['pharmacy', 'medicine', 'chemist', 'health'],
            'Beauty': ['beauty', 'salon', 'cosmetic', 'wellness'],
            'Home goods': ['furniture', 'home', 'hardware', 'garden'],
            'Repairs or services': ['repair', 'service', 'coaching', 'tuition', 'training', 'lesson', 'course', 'consult'],
            'A mix of these': ['mix', 'both', 'variety']},
        'because': 'What you sell changes everyday words, stock detail and reports.'},
    'selling_flow': {
        'ask': 'how a normal sale starts and is paid',
        'options': ['Walk-in checkout, pays on the spot', 'Order first, pay on delivery', 'Account sale, pays later', 'A mix of these'],
        'evidence': {
            'Walk-in checkout, pays on the spot': ['walk in', 'counter', 'till', 'card machine', 'contactless', 'on the spot'],
            'Order first, pay on delivery': ['deliver', 'order', 'whatsapp', 'online', 'pay on delivery'],
            'Account sale, pays later': ['invoice', 'account', 'later', 'monthly', 'credit'],
            'A mix of these': ['sometimes', 'both', 'mix', 'depends']},
        'because': 'The sale flow decides checkout, order and delivery steps.'},
    'stock_pain': {
        'ask': 'the stock mistake that costs most',
        'options': ['Running out', 'Buying too much', 'Wrong stock at a branch', 'Expiry or batches', 'Missing or damaged stock', 'Serial numbers or warranty', 'I do not keep stock'],
        'evidence': {
            'Running out': ['run out', 'out of stock', 'empty shelf', 'stockout'],
            'Buying too much': ['overstock', 'too much', 'overbuy', 'dead stock'],
            'Wrong stock at a branch': ['wrong branch', 'wrong shop', 'transfer'],
            'Expiry or batches': ['expiry', 'expire', 'batch', 'use by', 'best before'],
            'Missing or damaged stock': ['missing', 'damaged', 'theft', 'shrink'],
            'Serial numbers or warranty': ['serial', 'warranty', 'imei'],
            'I do not keep stock': ['no stock', 'service only', 'do not keep stock', 'stopped keeping stock']},
        'because': 'Stock priorities tune alerts and controls.'},
}


def propose_change(request, current_profile_answers, client=None):
    """One plain-language request -> proposed changes to the profile-driving
    answers. Returns {request, changes:[{target, current, proposed, confidence,
    status, because}], english_only, client}. No writes - confirmation happens
    in the UI before the normal profile apply path runs."""
    client = client or MockJevClient()
    request = (request or '').strip()
    if not request:
        return {'request': request, 'changes': [], 'english_only': True, 'error': 'empty'}
    if looks_non_english(request):
        return {'request': request, 'changes': [], 'english_only': True,
                'error': 'non_english',
                'message': 'That looks non-English - reconfiguration is English-only for now, please rephrase in English'}
    changes = []
    for target, spec in TARGETS.items():
        r = client.choice(request, spec['options'],
                          context=f"Owner asked to change something about {spec['ask']}: {request}",
                          evidence=spec['evidence'])
        # A target is in play only when its top option clearly beats the rest.
        if r.confidence < CONFIRM_BAND:
            continue
        current = current_profile_answers.get(target)
        if current == r.pick:
            continue
        changes.append({'target': target, 'ask': spec['ask'], 'current': current or 'Not set', 'proposed': r.pick,
                        'confidence': r.confidence,
                        'status': 'auto_accept' if r.confidence >= AUTO_ACCEPT else 'confirm',
                        'because': spec['because'], 'probabilities': r.probabilities})
    return {'request': request, 'changes': changes, 'english_only': True,
            'client': 'mock' if isinstance(client, MockJevClient) else 'jev'}

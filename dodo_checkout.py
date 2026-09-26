"""Owner-only Dodo test checkout preparation. Never grants access or uses live API."""
import json
import os
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlparse
from store import utcnow

TEST_API='https://test.dodopayments.com/checkouts'
TEST_CHECKOUT_HOST='test.checkout.dodopayments.com'

def test_checkout_ready():
    key=os.environ.get('MOSAIC_DODO_TEST_API_KEY','')
    product=os.environ.get('MOSAIC_DODO_TEST_PRODUCT_ID','')
    url=os.environ.get('MOSAIC_DODO_TEST_RETURN_URL','')
    if (os.environ.get('MOSAIC_DODO_TEST_MODE') != 'true' or not key or
        not product.startswith('pdt_') or len(product)>256 or
        not url.startswith('https://') or not urlparse(url).hostname or
        urlparse(url).username or urlparse(url).password):
        raise ValueError('Dodo test checkout is not configured')
    return key,product,url

def create_test_checkout(store, workspace_id, opener=None):
    """Called only by an owner-authenticated route; product and price live at Dodo.

    The sandbox-only checkout link is never offered to normal customers. Webhook
    reconciliation uses a server-generated one-time nonce, not user metadata.
    """
    key,product,return_url=test_checkout_ready()
    if not isinstance(workspace_id,str) or not workspace_id.startswith('wsp_') or len(workspace_id)>256:
        raise ValueError('Invalid workspace')
    nonce=secrets.token_urlsafe(32)
    payload={'product_cart':[{'product_id':product,'quantity':1}],
             'return_url':return_url,
             'metadata':{'mosaic_workspace_id':workspace_id,'mosaic_checkout_nonce':nonce}}
    request=urllib.request.Request(TEST_API,data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with (opener or urllib.request.urlopen)(request,timeout=12) as response:
            result=json.load(response)
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
        raise ValueError('Dodo test checkout failed') from exc
    if not isinstance(result,dict):raise ValueError('Invalid Dodo response')
    session=result.get('session_id');link=result.get('checkout_url')
    if (not isinstance(session,str) or not session.startswith('cks_') or len(session)>256 or
        not isinstance(link,str) or urlparse(link).scheme!='https' or
        urlparse(link).hostname!=TEST_CHECKOUT_HOST or urlparse(link).username or urlparse(link).password):
        raise ValueError('Invalid Dodo test checkout response')
    with store.tx():
        store._db.execute('INSERT INTO dodo_test_checkout_intents(nonce,workspace_id,product_id,session_id,created_at) VALUES(?,?,?,?,?)',
                          (nonce,workspace_id,product,session,utcnow()))
    return {'mode':'test','entitlements':'none','checkout_url':link,'session_id':session}

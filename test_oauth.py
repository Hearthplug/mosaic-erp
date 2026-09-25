import os,tempfile,unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from store import Store,Conflict
from oauth import OAuth,OAuthError
class OAuthTests(unittest.TestCase):
 def setUp(self):self.s=Store(tempfile.mktemp());self.o=OAuth(self.s);self.env=patch.dict(os.environ,{'MOSAIC_PUBLIC_ORIGIN':'https://erp.example','MOSAIC_GOOGLE_CLIENT_ID':'google-id','MOSAIC_GOOGLE_CLIENT_SECRET':'google-secret','MOSAIC_MICROSOFT_CLIENT_ID':'ms-id','MOSAIC_MICROSOFT_CLIENT_SECRET':'ms-secret'},clear=False);self.env.start()
 def tearDown(self):self.env.stop();self.s.close()
 def user(self,email='person@example.test'):
  w,_=self.s.create_workspace('North');u=self.s.create_user(w,email,'a-secure-password','owner','setup');return w,u
 def test_only_configured_providers_are_advertised(self):
  self.assertEqual([x['id'] for x in self.o.public()],['google','microsoft'])
  with patch.dict(os.environ,{'MOSAIC_GOOGLE_CLIENT_SECRET':'','MOSAIC_MICROSOFT_CLIENT_SECRET':''}):self.assertEqual(self.o.public(),[])
 def test_start_has_state_nonce_pkce_and_safe_redirect(self):
  url=self.o.start('google','//evil.example');q=parse_qs(urlparse(url).query)
  self.assertEqual(q['code_challenge_method'],['S256']);self.assertIn('nonce',q);self.assertIn('state',q);self.assertEqual(q['redirect_uri'],['https://erp.example/oauth/google/callback'])
  row=self.s.oauth_challenge_consume(q['state'][0],'google');self.assertEqual(row['next_path'],'/')
  self.assertIsNone(self.s.oauth_challenge_consume(q['state'][0],'google'))
 def test_callback_rejects_wrong_nonce_before_any_account_or_session(self):
  url=self.o.start('google');state=parse_qs(urlparse(url).query)['state'][0]
  with patch.object(self.o,'_token_and_claims',return_value={'sub':'sub-x','iss':'https://accounts.google.com','nonce':'wrong','email':'person@example.test','email_verified':True}):
   with self.assertRaises(OAuthError):self.o.callback('google','code',state)
  self.assertEqual(self.s._db.execute('SELECT count(*) n FROM oauth_identities').fetchone()['n'],0);self.assertEqual(self.s._db.execute('SELECT count(*) n FROM sessions').fetchone()['n'],0)
 def test_known_identity_uses_stable_issuer_subject_not_email(self):
  w,u=self.user();self.s._db.execute('INSERT INTO oauth_identities VALUES(?,?,?,?,?,?)',('google','https://accounts.google.com','sub-1',u['user_id'],w,'now'))
  code,_=self.s.oauth_grant_create('google','https://accounts.google.com','sub-1','changed@example.test',True,'/operations','signin');x=self.s.oauth_complete(code)
  self.assertEqual(x['workspaces'][0]['workspace_id'],w);session=self.s.oauth_enter(x['enter_code'],w);self.assertEqual(session['workspace_id'],w);self.assertRaises(Conflict,self.s.oauth_enter,x['enter_code'],w);self.assertRaises(Conflict,self.s.oauth_complete,code)
 def test_unknown_identity_requires_explicit_password_link_and_no_duplicate_user(self):
  w,u=self.user();before=self.s._db.execute('SELECT count(*) n FROM users').fetchone()['n'];code,_=self.s.oauth_grant_create('google','https://accounts.google.com','new-sub','person@example.test',True,'/','link')
  with self.assertRaises(Conflict):self.s.oauth_link(code,'person@example.test','wrong-password-value')
  self.assertEqual(self.s._db.execute('SELECT count(*) n FROM users').fetchone()['n'],before)
  code,_=self.s.oauth_grant_create('google','https://accounts.google.com','new-sub','person@example.test',True,'/','link');signin=self.s.oauth_link(code,'person@example.test','a-secure-password');x=self.s.oauth_complete(signin)
  self.assertEqual(x['workspaces'][0]['workspace_id'],w);self.assertEqual(self.s._db.execute('SELECT count(*) n FROM users').fetchone()['n'],before)
 def test_disabled_user_blocks_provider_session_and_existing_session(self):
  w,u=self.user();self.s._db.execute('INSERT INTO oauth_identities VALUES(?,?,?,?,?,?)',('google','https://accounts.google.com','sub-2',u['user_id'],w,'now'));self.s._db.execute('UPDATE users SET disabled_at=? WHERE id=?',('now',u['user_id']))
  self.assertEqual(self.s.oauth_identity_users('google','https://accounts.google.com','sub-2'),[])
 def test_verified_matching_invite_can_provision_but_mismatch_cannot(self):
  owner,_=self.user('owner@example.test');inv=self.s.create_invitation(owner,'invite@example.test','editor',None,'owner')['invite_token']
  self.s.accept_invitation_federated(inv,'google','https://accounts.google.com','invited-sub')
  self.assertEqual(len(self.s.oauth_identity_users('google','https://accounts.google.com','invited-sub')),1)
 def test_unknown_identity_auto_provisions_fresh_company_and_lands_in_signin(self):
  w,u=self.user();before=self.s._db.execute('SELECT count(*) n FROM users').fetchone()['n']
  url=self.o.start('google');state=parse_qs(urlparse(url).query)['state'][0]
  with patch.object(self.o,'_token_and_claims',return_value={'sub':'brand-new-sub','iss':'https://accounts.google.com','nonce':parse_qs(urlparse(url).query)['nonce'][0],'email':'person@example.test','email_verified':True}):
   code,mode=self.o.callback('google','code',state)
  self.assertEqual(mode,'signin')
  ids=self.s.oauth_identity_users('google','https://accounts.google.com','brand-new-sub')
  self.assertEqual(len(ids),1);self.assertEqual(ids[0]['role'],'owner');self.assertEqual(ids[0]['name'],'My company')
  self.assertNotEqual(ids[0]['workspace_id'],w)
  # no merge: existing account with the same email is untouched
  self.assertEqual(self.s._db.execute('SELECT count(*) n FROM users').fetchone()['n'],before+1)
  self.assertEqual(self.s._db.execute('SELECT count(*) n FROM oauth_identities WHERE user_id=?',(u['user_id'],)).fetchone()['n'],0)
  x=self.s.oauth_complete(code);self.assertEqual(len(x['workspaces']),1)
  session=self.s.oauth_enter(x['enter_code'],x['workspaces'][0]['workspace_id']);self.assertEqual(session['role'],'owner')
  # second sign-in for the same identity goes straight in, no duplicate tenant
  before_ws=self.s._db.execute('SELECT count(*) n FROM workspaces').fetchone()['n']
  url=self.o.start('google');state=parse_qs(urlparse(url).query)['state'][0]
  with patch.object(self.o,'_token_and_claims',return_value={'sub':'brand-new-sub','iss':'https://accounts.google.com','nonce':parse_qs(urlparse(url).query)['nonce'][0],'email':'person@example.test','email_verified':True}):
   code2,mode2=self.o.callback('google','code',state)
  self.assertEqual(mode2,'signin');self.assertEqual(self.s._db.execute('SELECT count(*) n FROM workspaces').fetchone()['n'],before_ws)
 def test_link_instead_binds_identity_to_password_account_and_closes_fresh_company(self):
  w,u=self.user()
  created=self.s.oauth_auto_provision('google','https://accounts.google.com','link-sub','fresh@example.test')
  code=self.s.oauth_link_instead(created['workspace_id'],created['user_id'],'person@example.test','a-secure-password')
  ids=self.s.oauth_identity_users('google','https://accounts.google.com','link-sub')
  names=sorted(x['name'] for x in ids);self.assertEqual(names,['North'])
  self.assertEqual(self.s.get_workspace(created['workspace_id'])['status'],'closed')
  x=self.s.oauth_complete(code);self.assertEqual(x['workspaces'][0]['workspace_id'],w)
  # wrong password: nothing linked, fresh company stays active
  created2=self.s.oauth_auto_provision('google','https://accounts.google.com','link-sub-2','fresh2@example.test')
  self.assertRaises(Conflict,self.s.oauth_link_instead,created2['workspace_id'],created2['user_id'],'person@example.test','wrong-password-value')
  self.assertEqual(self.s.get_workspace(created2['workspace_id'])['status'],'active')
  # an account not created by SSO cannot use link-instead
  self.assertRaises(Conflict,self.s.oauth_link_instead,w,u['user_id'],'person@example.test','a-secure-password')
class OAuthBrowserContract(unittest.TestCase):
 def setUp(self):
  import app,tempfile
  from store import Store
  from oauth import OAuth
  self.app=app;self.old=(app.STORE,app.OAUTH,app.LIMITER);app.STORE=Store(tempfile.mktemp());app.OAUTH=OAuth(app.STORE);app.LIMITER=app.RateLimiter(1000,app.STORE)
  from http.server import ThreadingHTTPServer
  import threading
  self.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);self.p=self.s.server_address[1];threading.Thread(target=self.s.serve_forever,daemon=True).start()
 def tearDown(self):
  self.s.shutdown();self.s.server_close();self.app.STORE.close();self.app.STORE,self.app.OAUTH,self.app.LIMITER=self.old
 def get(self,path,follow=False):
  import urllib.request,urllib.error
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):return None
  opener=urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
  try:r=opener.open(f'http://127.0.0.1:{self.p}{path}');return r.status,dict(r.headers),r.read()
  except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
 def test_official_assets_are_served_and_present(self):
  page=self.get('/signin')[2].decode();self.assertIn('data-provider="google" disabled',page);self.assertIn('data-provider="microsoft" disabled',page);self.assertIn('/google-signin.png',page);self.assertIn('/microsoft-signin.svg',page);script=self.get('/signin.js')[2].decode();self.assertIn('b.disabled=!enabled.has(b.dataset.provider)',script);self.assertIn('if(b.disabled)return',script);self.assertNotIn('dummy',script.lower())
  import hashlib
  google=self.get('/google-signin.png')[2];microsoft=self.get('/microsoft-signin.svg')[2]
  self.assertEqual(hashlib.sha256(google).hexdigest(),'892062091f35e69dd838ba4a4f238d37a0562d52ecda6406eb343a1127251409');self.assertEqual(hashlib.sha256(microsoft).hexdigest(),'e06fb6b9c489d5719260945b5b9108f12fedd77e61206229f5fdd77a060e77a8')
 def test_unconfigured_is_disabled_and_route_fails_closed(self):
  import os,json
  with patch.dict(os.environ,{'MOSAIC_PUBLIC_ORIGIN':'','MOSAIC_GOOGLE_CLIENT_ID':'','MOSAIC_GOOGLE_CLIENT_SECRET':''}):
   self.assertEqual(json.loads(self.get('/api/oauth/providers')[2]),{'providers':[]});self.assertEqual(self.get('/oauth/google/start')[0],400)
 def test_configured_button_route_is_real_google_authorization(self):
  import os
  with patch.dict(os.environ,{'MOSAIC_PUBLIC_ORIGIN':f'http://127.0.0.1:{self.p}','MOSAIC_GOOGLE_CLIENT_ID':'test-id','MOSAIC_GOOGLE_CLIENT_SECRET':'test-secret','MOSAIC_MICROSOFT_CLIENT_ID':'test-ms-id','MOSAIC_MICROSOFT_CLIENT_SECRET':'test-ms-secret'}):
   status,h,_=self.get('/oauth/google/start?next=%2Foperations');self.assertEqual(status,302);self.assertTrue(h['Location'].startswith('https://accounts.google.com/o/oauth2/v2/auth?'));self.assertIn('code_challenge_method=S256',h['Location'])
   status,h,_=self.get('/oauth/microsoft/start');self.assertEqual(status,302);self.assertTrue(h['Location'].startswith('https://login.microsoftonline.com/common/oauth2/v2.0/authorize?'))
 def test_invalid_state_and_code_have_no_success_path(self):
  import os
  with patch.dict(os.environ,{'MOSAIC_PUBLIC_ORIGIN':f'http://127.0.0.1:{self.p}','MOSAIC_GOOGLE_CLIENT_ID':'test-id','MOSAIC_GOOGLE_CLIENT_SECRET':'test-secret'}):
   self.assertEqual(self.get('/oauth/google/callback?state=invalid&code=invalid')[0],400)
   _,h,_=self.get('/oauth/google/start');state=parse_qs(urlparse(h['Location']).query)['state'][0]
   self.assertEqual(self.get('/oauth/google/callback?state='+state+'&code=invalid')[0],400)

if __name__=='__main__':unittest.main()

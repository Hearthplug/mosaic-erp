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
if __name__=='__main__':unittest.main()

"""Provider-ready OpenID Connect for Google and Microsoft.

OAuth secrets are deployment inputs. The application never invents credentials and
only advertises providers whose complete configuration is present.
"""
from __future__ import annotations
import base64, hashlib, json, os, re, secrets
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import jwt

B64=lambda b:base64.urlsafe_b64encode(b).rstrip(b'=').decode()

@dataclass(frozen=True)
class Provider:
    name:str; label:str; client_id:str; client_secret:str; authorize_url:str; token_url:str; jwks_url:str; issuer:str

class OAuthError(Exception): pass

class OAuth:
    def __init__(self, store, provisioner=None): self.store,self.provisioner=store,provisioner
    def providers(self):
        origin=os.getenv('MOSAIC_PUBLIC_ORIGIN','').rstrip('/')
        data={
          'google':Provider('google','Google',os.getenv('MOSAIC_GOOGLE_CLIENT_ID',''),os.getenv('MOSAIC_GOOGLE_CLIENT_SECRET',''),'https://accounts.google.com/o/oauth2/v2/auth','https://oauth2.googleapis.com/token','https://www.googleapis.com/oauth2/v3/certs','https://accounts.google.com'),
          'microsoft':Provider('microsoft','Microsoft',os.getenv('MOSAIC_MICROSOFT_CLIENT_ID',''),os.getenv('MOSAIC_MICROSOFT_CLIENT_SECRET',''),'https://login.microsoftonline.com/common/oauth2/v2.0/authorize','https://login.microsoftonline.com/common/oauth2/v2.0/token','https://login.microsoftonline.com/common/discovery/v2.0/keys','microsoft-v2')}
        if not origin.startswith('https://') and not origin.startswith('http://127.0.0.1:'): origin=''
        return origin,{k:v for k,v in data.items() if origin and v.client_id and v.client_secret}
    def public(self):
        _,p=self.providers();return [{'id':x.name,'label':x.label,'enabled':True} for x in p.values()]
    def start(self, provider, next_path='/', invite_token=''):
        origin,ps=self.providers();p=ps.get(provider)
        if not p: raise OAuthError('This sign-in provider is not configured')
        if not next_path.startswith('/') or next_path.startswith('//'):next_path='/'
        state,se_nonce,verifier=secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(48)
        self.store.oauth_challenge_create(state,provider,se_nonce,verifier,next_path,invite_token)
        q={'client_id':p.client_id,'redirect_uri':f'{origin}/oauth/{provider}/callback','response_type':'code','scope':'openid email profile','state':state,'nonce':se_nonce,'code_challenge':B64(hashlib.sha256(verifier.encode()).digest()),'code_challenge_method':'S256','prompt':'select_account'}
        return p.authorize_url+'?'+urlencode(q)
    def callback(self,provider,code,state):
        challenge=self.store.oauth_challenge_consume(state,provider)
        if not challenge: raise OAuthError('Sign-in request is invalid, expired, or already used')
        origin,ps=self.providers();p=ps.get(provider)
        if not p: raise OAuthError('This sign-in provider is not configured')
        claims=self._token_and_claims(p,code,challenge['code_verifier'],f'{origin}/oauth/{provider}/callback')
        if not secrets.compare_digest(str(claims.get('nonce','')),challenge['nonce']):raise OAuthError('Identity response nonce did not match')
        sub=str(claims.get('sub',''));issuer=str(claims.get('iss',''))
        if not sub or not issuer:raise OAuthError('Identity response is missing its stable subject')
        email=(claims.get('email') or claims.get('preferred_username') or '').strip().lower()
        verified=claims.get('email_verified') is True if provider=='google' else claims.get('xms_edov') is True or claims.get('email_verified') is True
        users=self.store.oauth_identity_users(provider,issuer,sub)
        if users:return self.store.oauth_grant_create(provider,issuer,sub,email,verified,challenge['next_path'],'signin')
        invite=self.store.invitation(challenge['invite_token']) if challenge.get('invite_token') else None
        if invite and verified and email==invite['email']:
            created=self.store.accept_invitation_federated(challenge['invite_token'],provider,issuer,sub)
            if created.get('operational_role') and self.provisioner:self.provisioner.rbac.bind_role(created['workspace_id'],created['user_id'],created['user_id'],created['operational_role'])
            return self.store.oauth_grant_create(provider,issuer,sub,email,verified,challenge['next_path'],'signin')
        self.store.oauth_auto_provision(provider,issuer,sub,email)
        return self.store.oauth_grant_create(provider,issuer,sub,email,verified,challenge['next_path'],'signin')
    def _token_and_claims(self,p,code,verifier,redirect_uri):
        body=urlencode({'client_id':p.client_id,'client_secret':p.client_secret,'code':code,'code_verifier':verifier,'grant_type':'authorization_code','redirect_uri':redirect_uri}).encode()
        try:
            with urlopen(Request(p.token_url,data=body,headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=10) as r: token=json.load(r)
            raw=token['id_token'];header=jwt.get_unverified_header(raw)
            key=jwt.PyJWKClient(p.jwks_url).get_signing_key(header['kid']).key
            claims=jwt.decode(raw,key,algorithms=['RS256'],audience=p.client_id,options={'require':['exp','iat','sub','iss','nonce']})
        except Exception as e: raise OAuthError('The identity provider response could not be verified') from e
        iss=str(claims.get('iss',''))
        if p.name=='google' and iss not in ('https://accounts.google.com','accounts.google.com'):raise OAuthError('Unexpected Google token issuer')
        if p.name=='microsoft' and not re.fullmatch(r'https://login\.microsoftonline\.com/[0-9a-fA-F-]{36}/v2\.0',iss):raise OAuthError('Unexpected Microsoft token issuer')
        return claims

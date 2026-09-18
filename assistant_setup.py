"""Chat-guided assistant setup. Models only propose typed intents; Mosaic stays in control."""
from __future__ import annotations
import hashlib,http.client,ipaddress,json,os,re,secrets,socket,ssl,urllib.parse,urllib.request
from pathlib import Path
from store import canon,utcnow,Conflict

LOCAL_MODEL={
 'name':'Qwen2.5-0.5B-Instruct Q4_K_M','model':'qwen2.5-0.5b-instruct',
 'bytes':491400032,'license':'Apache-2.0','source':'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF',
 'revision':'9217f5db79a29953eb74d5343926648285ec7e67',
 'runtime':'llama.cpp','measured_requirements':None,
}
ALLOWED_MODES=('deterministic','remote','local')
def _public_https(url):
 p=urllib.parse.urlparse(url)
 if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('Use an HTTPS endpoint without embedded credentials')
 try:
  for x in socket.getaddrinfo(p.hostname,p.port or 443,type=socket.SOCK_STREAM):
   ip=ipaddress.ip_address(x[4][0])
   if not ip.is_global:raise ValueError('Endpoint must resolve only to public Internet addresses')
 except socket.gaierror:raise ValueError('Endpoint host could not be resolved')
 return url.rstrip('/')
def _pinned_post(parsed,addresses,body,key):
 class PinnedHTTPS(http.client.HTTPSConnection):
  def connect(self):
   raw=socket.create_connection((addresses[0],self.port),self.timeout);self.sock=self._context.wrap_socket(raw,server_hostname=parsed.hostname)
 conn=PinnedHTTPS(parsed.hostname,parsed.port or 443,timeout=10,context=ssl.create_default_context());path=parsed.path or '/';path+=('?'+parsed.query) if parsed.query else ''
 conn.request('POST',path,body=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Host':parsed.hostname});res=conn.getresponse()
 if res.status<200 or res.status>=300:raise ValueError('provider returned HTTP '+str(res.status))
 raw=res.read(65537);conn.close();return raw

class AssistantSetup:
 def __init__(self,s):self.s=s
 def get(self,wid):
  r=self.s._db.execute('SELECT * FROM assistant_settings WHERE workspace_id=?',(wid,)).fetchone()
  if not r:return {'mode':'deterministic','status':'ready','version':0,'secret_configured':False,'local_model':LOCAL_MODEL}
  d=dict(r);d['pending']=json.loads(d.pop('pending_json'));d['secret_configured']=bool(d.pop('secret_ref'));d['local_model']=LOCAL_MODEL;return d
 def chat(self,wid,actor,message):
  text=' '.join((message or '').strip().split());low=text.lower();cur=self.get(wid)
  if not text:return {'reply':'Choose deterministic chat, a private local assistant, or your OpenAI-compatible provider. You can also ask for status, test, disable, remove, or rollback.','settings':cur}
  if 'status' in low:return {'reply':f"Assistant mode: {cur['mode']}. Status: {cur['status']}. Model: {cur.get('model') or 'none'}.",'settings':cur}
  if any(x in low for x in ('no ai','deterministic','disable assistant')):
   return self._preview(cur,{'mode':'deterministic','endpoint':'','model':'','secret_ref':'','status':'ready'},'Use deterministic chat. No model or external endpoint will be called.')
  if ('local assistant' in low or 'private assistant' in low) and not re.search(r'https?://',low):
   note='Measured CPU and RAM results are not available yet, so local assistant download cannot be enabled safely.' if not LOCAL_MODEL['measured_requirements'] else 'This will download the pinned local model.'
   return {'intent':'blocked' if not LOCAL_MODEL['measured_requirements'] else 'preview','reply':f"{LOCAL_MODEL['name']} is {LOCAL_MODEL['bytes']:,} bytes, {LOCAL_MODEL['license']}, from {LOCAL_MODEL['source']}. {note}",'local_model':LOCAL_MODEL,'requires_confirmation':True}
  if low.startswith('use endpoint ') or low.startswith('use provider '):
   m=re.search(r'https?://[^\s,]+',text)
   model=re.search(r'\bmodel\s+([A-Za-z0-9._:/-]+)',text,re.I)
   if not m or not model:return {'intent':'collect','reply':'Tell me the secure service address and model name. I will guide the technical details. The API key goes into a separate masked secret field, never chat.'}
   endpoint=_public_https(m.group(0).rstrip('.,)'));candidate={'mode':'remote','endpoint':endpoint,'model':model.group(1),'secret_ref':'','status':'needs_secret'}
   return self._preview(cur,candidate,f"Use {model.group(1)} at {endpoint}. The next step opens masked secret entry; the key will never enter chat or audit history.")
  if low in ('confirm','apply','yes apply'):
   p=cur.get('pending') or {}
   if not p:return {'intent':'refuse','reply':'There is no pending assistant change.'}
   return self.apply(wid,actor,p)
  if low in ('cancel','rollback','undo'):return {'intent':'cancel','reply':'Pending assistant change discarded. Current mode was not changed.','settings':cur}
  if 'mounted secret' in low:
   path=os.environ.get('MOSAIC_ASSISTANT_MOUNTED_SECRET_FILE','').strip()
   if not path or not Path(path).is_file():return {'intent':'collect','reply':'The operator-created secret is not mounted yet. Ask your Kubernetes operator to create it from the command shown by the deployment guide, then say use mounted secret.'}
   with self.s.tx():self.s._db.execute("UPDATE assistant_settings SET secret_ref=?,status='ready',updated_by=?,updated_at=? WHERE workspace_id=? AND mode='remote'",('file:'+path,actor,utcnow(),wid));self.s._audit(wid,actor,'assistant.secret.reference',{'secret_ref_hash':hashlib.sha256(path.encode()).hexdigest(),'stored':'operator-mounted'})
   return {'intent':'applied','reply':'The operator-mounted secret is connected. Ask me to test the provider.'}
  if 'test' in low:return self.test(wid)
  return {'intent':'collect','reply':'I can set deterministic mode, guide a local assistant, configure an OpenAI-compatible endpoint, show status, test, disable, remove, or rollback.'}
 def _preview(self,cur,candidate,reply):
  return {'intent':'preview','reply':reply+' Say confirm to apply or cancel to discard.','preview':candidate,'current':cur,'requires_confirmation':True}
 def stage(self,wid,actor,candidate):
  if candidate.get('mode') not in ALLOWED_MODES:raise ValueError('invalid assistant mode')
  if candidate['mode']=='remote':candidate['endpoint']=_public_https(candidate.get('endpoint',''));candidate['model']=(candidate.get('model') or '').strip()
  if candidate['mode']=='local' and not LOCAL_MODEL['measured_requirements']:raise Conflict('local model awaits measured CPU/RAM and intent-quality gates')
  cur=self.get(wid);v=cur.get('version',0)+1
  with self.s.tx():
   self.s._db.execute("INSERT INTO assistant_settings(workspace_id,mode,endpoint,model,secret_ref,status,pending_json,version,updated_by,updated_at) VALUES(?,?,?,?,?,?,?, ?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET pending_json=excluded.pending_json,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(wid,cur['mode'],cur.get('endpoint',''),cur.get('model',''),'','ready',canon(candidate),v,actor,utcnow()))
   self.s._audit(wid,actor,'assistant.preview',{'mode':candidate['mode'],'endpoint':candidate.get('endpoint',''),'model':candidate.get('model',''),'version':v})
  return {'status':'pending','version':v}
 def apply(self,wid,actor,candidate):
  mode=candidate['mode'];endpoint=candidate.get('endpoint','');model=candidate.get('model','');status='needs_secret' if mode=='remote' else 'ready'
  with self.s.tx():
   self.s._db.execute("INSERT INTO assistant_settings(workspace_id,mode,endpoint,model,secret_ref,status,pending_json,version,updated_by,updated_at) VALUES(?,?,?,?,?,?, '{}',1,?,?) ON CONFLICT(workspace_id) DO UPDATE SET mode=excluded.mode,endpoint=excluded.endpoint,model=excluded.model,secret_ref='',status=excluded.status,pending_json='{}',version=assistant_settings.version+1,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(wid,mode,endpoint,model,'',status,actor,utcnow()))
   self.s._audit(wid,actor,'assistant.apply',{'mode':mode,'endpoint':endpoint,'model':model,'status':status})
  return {'intent':'applied','reply':'Assistant configuration applied.'+(' Open masked secret entry to finish, then test the connection.' if mode=='remote' else ''),'settings':self.get(wid),'open_secret_form':mode=='remote'}
 def save_secret(self,wid,actor,key):
  if not key or len(key)>4096:raise ValueError('API key is required')
  if os.environ.get('MOSAIC_ASSISTANT_MOUNTED_SECRET_FILE','').strip():raise Conflict('This deployment uses an operator-mounted read-only secret. Chat will detect it after the operator creates or rotates it; Mosaic will not write to the Kubernetes API or mount.')
  secret_dir=os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR','').strip()
  if not secret_dir:raise Conflict('Restart-safe secret storage is not mounted. Chat can guide the Docker secret volume or Kubernetes operator secret step, then retry.')
  root=Path(secret_dir).resolve();root.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(root,0o700)
  target=root/('assistant-'+hashlib.sha256(wid.encode()).hexdigest()[:24]+'.key');tmp=root/('.tmp-'+secrets.token_hex(8))
  fd=os.open(str(tmp),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  try:
   with os.fdopen(fd,'w') as f:f.write(key);f.flush();os.fsync(f.fileno())
   os.replace(tmp,target);os.chmod(target,0o600)
  finally:
   if tmp.exists():tmp.unlink()
  ref='file:'+str(target)
  with self.s.tx():
   if self.s._db.execute("UPDATE assistant_settings SET secret_ref=?,status='ready',updated_by=?,updated_at=? WHERE workspace_id=? AND mode='remote'",(ref,actor,utcnow(),wid)).rowcount!=1:raise Conflict('configure remote assistant before adding its secret')
   self.s._audit(wid,actor,'assistant.secret.set',{'secret_ref_hash':hashlib.sha256(ref.encode()).hexdigest(),'stored':'mounted-secret-file'})
  return {'stored':True,'note':'Secret saved in the mounted secret store. Ask me to test the connection.'}
 def _key(self,ref):
  if not ref.startswith('file:'):return ''
  path=Path(ref[5:]);root=Path(os.environ.get('MOSAIC_ASSISTANT_SECRET_DIR','')).resolve()
  try:
   if not root or root not in path.resolve().parents:return ''
   return path.read_text().strip()
  except OSError:return ''
 def test(self,wid):
  c=self.get(wid)
  if c['mode']=='deterministic':return {'healthy':True,'mode':'deterministic','reply':'Deterministic chat is ready.'}
  if c['mode']=='local':return {'healthy':False,'reply':'Local assistant is not enabled until the measured quality and resource gates pass.'}
  row=self.s._db.execute('SELECT secret_ref FROM assistant_settings WHERE workspace_id=?',(wid,)).fetchone();key=self._key(row['secret_ref'] if row else '')
  if not key:return {'healthy':False,'reply':'Add the API key in masked secret entry first.'}
  base=_public_https(c['endpoint']);url=base if base.endswith('/chat/completions') else base+'/chat/completions'
  schema={'type':'object','additionalProperties':False,'required':['kind','confidence'],'properties':{'kind':{'type':'string','enum':['status']},'confidence':{'type':'number','minimum':0,'maximum':1}}}
  body=canon({'model':c['model'],'messages':[{'role':'system','content':'Return only the typed status intent.'},{'role':'user','content':'show status'}],'temperature':0,'max_tokens':32,'response_format':{'type':'json_schema','json_schema':{'name':'mosaic_intent','strict':True,'schema':schema}}}).encode()
  try:
   parsed=urllib.parse.urlparse(url);addresses=[]
   for x in socket.getaddrinfo(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM):
    ip=ipaddress.ip_address(x[4][0])
    if not ip.is_global:raise ValueError('endpoint resolved to a private address')
    if str(ip) not in addresses:addresses.append(str(ip))
   if not addresses:raise ValueError('endpoint did not resolve')
   raw=_pinned_post(parsed,addresses,body,key)
   if len(raw)>65536:raise ValueError('provider response too large')
   out=json.loads(raw);content=out['choices'][0]['message']['content'];intent=json.loads(content)
   if set(intent)!={'kind','confidence'} or intent['kind']!='status' or not isinstance(intent['confidence'],(int,float)):raise ValueError('typed intent mismatch')
  except Exception:
   with self.s.tx():self.s._db.execute("UPDATE assistant_settings SET status='unhealthy' WHERE workspace_id=?",(wid,));self.s._audit(wid,'system','assistant.test',{'healthy':False,'endpoint':base,'model':c['model']})
   return {'healthy':False,'reply':'Provider failed the schema-constrained typed-intent test. Deterministic chat remains active.'}
  with self.s.tx():self.s._db.execute("UPDATE assistant_settings SET status='ready' WHERE workspace_id=?",(wid,));self.s._audit(wid,'system','assistant.test',{'healthy':True,'endpoint':base,'model':c['model']})
  return {'healthy':True,'mode':'remote','reply':'Provider passed the schema-constrained typed-intent test.'}

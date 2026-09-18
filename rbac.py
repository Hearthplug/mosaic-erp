"""Fine-grained, versioned operational authorization. UI, chat and APIs call the same check."""
import json,secrets
from store import Conflict,utcnow
TOXIC=[frozenset(('purchase.create','purchase.approve')),frozenset(('purchase.receive','purchase_bill.approve')),frozenset(('payment.create','payment.approve')),frozenset(('journal.create','journal.approve'))]
class Denied(Exception):pass
class RBAC:
 def __init__(self,s):self.s=s
 def assign(self,wid,actor,user_id,role,permissions,locations=None,limits=None,reason='Interview-approved role',emergency=False):
  perms=set(permissions)
  hits=[sorted(x) for x in TOXIC if x<=perms]
  if hits and not emergency:raise Conflict('Segregation-of-duties conflict: '+str(hits))
  x='rba_'+secrets.token_hex(8);now=utcnow()
  with self.s.tx():
   self.s._db.execute('INSERT INTO role_assignments(id,workspace_id,user_id,role_name,location_id,company_id,limits_json,template_version,effective_from,assigned_by,reason,permissions_json,locations_json,emergency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x,wid,user_id,role,None,None,json.dumps(limits or {}),1,now,actor,reason,json.dumps(sorted(perms)),json.dumps(locations or []),int(emergency)))
   self.s._audit(wid,actor,'rbac.assign',{'id':x,'user_id':user_id,'role':role,'toxic_override':hits if emergency else []})
  return {'id':x,'role':role,'emergency':emergency}
 def bind_role(self,wid,actor,user_id,role_name):
  template=self.s._db.execute('SELECT * FROM role_assignments WHERE workspace_id=? AND user_id=? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1',(wid,'role:'+role_name)).fetchone()
  if not template:raise Conflict('provisioned operational role not found: '+role_name)
  return self.assign(wid,actor,user_id,role_name,json.loads(template['permissions_json']),json.loads(template['locations_json']),json.loads(template['limits_json']),'Bound to provisioned interview role')
 def revoke(self,wid,actor,assignment_id):
  with self.s.tx():self.s._db.execute('UPDATE role_assignments SET effective_to=? WHERE id=? AND workspace_id=?',(utcnow(),assignment_id,wid));self.s._audit(wid,actor,'rbac.revoke',{'id':assignment_id})
 def check(self,wid,user_id,action,location_id=None,amount_minor=None,discount_percent=None,record_state=None):
  rows=self.s._db.execute('SELECT * FROM role_assignments WHERE workspace_id=? AND user_id=? AND effective_to IS NULL',(wid,user_id)).fetchall()
  for r in rows:
   perms=set(json.loads(r['permissions_json']));locs=json.loads(r['locations_json']);limits=json.loads(r['limits_json'])
   if '*' not in perms and action not in perms:continue
   if locs and location_id not in locs:continue
   if amount_minor is not None and limits.get(action+'_amount_minor') is not None and amount_minor>limits[action+'_amount_minor']:continue
   if discount_percent is not None and limits.get('discount_percent') is not None and discount_percent>limits['discount_percent']:continue
   states=limits.get(action+'_states');
   if states and record_state not in states:continue
   return True
  raise Denied(f'{action} is not allowed for this person, location, amount or record state')

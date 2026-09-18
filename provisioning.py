"""Turn an approved layperson interview into active operational configuration."""
import secrets
from store import canon,sha256,utcnow
from operating_model import compile_model,OperatingModels
from rbac import RBAC
from branding import theme
class Provisioner:
 def __init__(self,s):self.s=s;self.models=OperatingModels(s);self.rbac=RBAC(s)
 def apply(self,wid,actor,interview_id,answers):
  model=compile_model(answers);saved=self.models.save(wid,actor,answers);h=sha256(canon(answers));made={'modules':[],'workflows':[],'reports':[],'roles':[],'verification_tasks':[]}
  modules=model['settings']['modules']['value'];rolemap=model['settings']['roles']['value'];workflows=['purchase_approval','sale_exact_tender','negative_stock_block','period_lock']
  if 'transfers' in modules:workflows.append('stock_transfer_approval')
  if 'receivables' in modules:workflows.append('credit_collection')
  reports=['trial_balance','profit_and_loss','balance_sheet']+(['receivables_aging','payables_aging'] if {'receivables','payables'}&set(modules) else [])
  brand=theme(model)
  with self.s.tx():
   for kind,codes in (('module',modules),('workflow',workflows),('report',reports)):
    for code in codes:self.s._db.execute('INSERT INTO provisioned_capabilities(id,workspace_id,kind,code,config_json,status,source_interview_id,source_answer_hash,created_at) VALUES(?,?,?,?,?,\'active\',?,?,?) ON CONFLICT(workspace_id,kind,code) DO UPDATE SET config_json=excluded.config_json,status=\'active\',source_interview_id=excluded.source_interview_id,source_answer_hash=excluded.source_answer_hash',(self._id('cap'),wid,kind,code,canon({'enabled':True}),interview_id,h,utcnow()));made[kind+'s'].append(code)
   self.s._db.execute('INSERT INTO provisioned_capabilities(id,workspace_id,kind,code,config_json,status,source_interview_id,source_answer_hash,created_at) VALUES(?,?,\'branding\',\'theme\',?,\'active\',?,?,?) ON CONFLICT(workspace_id,kind,code) DO UPDATE SET config_json=excluded.config_json,status=\'active\',source_interview_id=excluded.source_interview_id,source_answer_hash=excluded.source_answer_hash',(self._id('cap'),wid,canon(brand),interview_id,h,utcnow()))
  for role,permissions in rolemap.items():
   out=self.rbac.assign(wid,actor,'role:'+role,role,permissions,reason='Provisioned from approved business interview');made['roles'].append({'role':role,'assignment_id':out['id'],'permissions':permissions})
  checks=model['verification_checklists']
  with self.s.tx():
   for required,decisions in checks.items():
    for decision in decisions:
     tid=self._id('vfy');self.s._db.execute('INSERT INTO verification_tasks(id,workspace_id,area,decision,reason,status,required_role,source_interview_id,created_at) VALUES(?,?,?,?,?,\'pending\',?,?,?)',(tid,wid,required,decision,'Required before this regulated or deployment-dependent capability goes live',required,interview_id,utcnow()));made['verification_tasks'].append(tid)
   self.s._audit(wid,actor,'interview.provision',{'interview_id':interview_id,'operating_model_id':saved['id'],'modules':modules,'roles':[x['role'] for x in made['roles']],'reports':reports,'verification_tasks':len(made['verification_tasks'])})
  return {'operating_model_id':saved['id'],'operating_model_version':saved['version'],'branding':brand,**made,'go_live_ready':False}
 def status(self,wid):
  caps=[dict(x) for x in self.s._db.execute('SELECT kind,code,config_json,status,source_interview_id FROM provisioned_capabilities WHERE workspace_id=? ORDER BY kind,code',(wid,)).fetchall()];tasks=[dict(x) for x in self.s._db.execute('SELECT id,area,decision,status,required_role FROM verification_tasks WHERE workspace_id=? ORDER BY area,decision',(wid,)).fetchall()];return {'capabilities':caps,'verification_tasks':tasks,'go_live_ready':bool(caps) and all(x['status']=='verified' for x in tasks)}
 @staticmethod
 def _id(p):return p+'_'+secrets.token_hex(8)

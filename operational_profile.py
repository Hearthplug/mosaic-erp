"""Interview intelligence that configures working modules, not a blueprint."""
from store import canon,sha256,utcnow,Conflict
MODULES={'core':[], 'pos':['catalog','inventory','sales','finance'], 'procurement':['catalog','inventory','purchasing','finance'], 'credit':['crm','receivables','payables','finance'], 'multi_store':['inventory','transfers','analytics'], 'service':['crm','service','inventory'], 'manufacturing':['inventory','manufacturing','finance'], 'projects':['crm','projects','finance'], 'people':['people'], 'assets':['assets','maintenance','finance']}
def compile_profile(a):
 enabled={'catalog','inventory','sales','purchasing','finance','analytics','audit'}
 if a.get('locations') not in (None,'One store'):enabled|={'transfers'}
 if a.get('credit') not in (None,'No credit'):enabled|={'crm','receivables','payables'}
 if a.get('vertical')=='Electronics':enabled|={'service','serials'}
 if a.get('vertical') in ('Grocery','Pharmacy'):enabled|={'lots','expiry'}
 if a.get('assembly') in ('Yes','Manufacturing','Assembly'):enabled|={'manufacturing'}
 profile={'enabled_modules':sorted(enabled),'terminology':{'sale':'Invoice' if a.get('buyers') in ('Businesses','Both') else 'Sale','location':'Store'},'workflows':{'purchase_approval':True,'sale_exact_tender':True,'negative_stock':False,'period_lock':True},'roles':['owner','manager','accountant','buyer','receiver','cashier','viewer'],'localization':{'jurisdiction':a.get('country'),'status':'requires_verified_adapter'},'source_answers_hash':sha256(canon(a))}
 return profile
class Profiles:
 def __init__(self,s):self.s=s
 def apply(self,wid,actor,answers):
  p=compile_profile(answers);current=self.s._db.execute('SELECT operational_profile_json FROM workspaces WHERE id=?',(wid,)).fetchone()
  with self.s.tx():
   self.s._db.execute('UPDATE workspaces SET operational_profile_json=?,operational_profile_hash=?,operational_profile_at=? WHERE id=?',(canon(p),sha256(canon(p)),utcnow(),wid));self.s._audit(wid,actor,'operational_profile.apply',{'enabled_modules':p['enabled_modules'],'profile_hash':sha256(canon(p))})
  return p

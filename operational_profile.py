"""Interview intelligence that configures working modules, not a blueprint."""
from store import canon,sha256,utcnow,Conflict
MODULES={'core':[], 'pos':['catalog','inventory','sales','finance'], 'procurement':['catalog','inventory','purchasing','finance'], 'credit':['crm','receivables','payables','finance'], 'multi_store':['inventory','transfers','analytics'], 'service':['crm','service','inventory'], 'manufacturing':['inventory','manufacturing','finance'], 'projects':['crm','projects','finance'], 'people':['people'], 'assets':['assets','maintenance','finance']}
MODULE_INFO=[('catalog','Item list','The products and services you buy or sell.'),('sales','Sales','Billing, invoices and daily sales.'),('purchasing','Buying','Purchase orders and goods received from suppliers.'),('finance','Money','Ledgers, payments and account balances.'),('analytics','Reports','Sales, stock and money reports and trends.'),('audit','Change history','Who changed what, and when.'),('inventory','Stock','Stock on hand, low-stock alerts and counts.'),('transfers','Store transfers','Moving stock between your stores.'),('crm','Customers and suppliers','Records of the people you sell to and buy from.'),('receivables','Customer credit','Tracks money customers owe you.'),('payables','Supplier credit','Tracks money you owe suppliers.'),('service','Service jobs','Repairs and service work for customers.'),('serials','Serial numbers','Track each item by serial number for warranty.'),('lots','Batches','Track stock in batches or lots.'),('expiry','Expiry dates','Warns before stock expires.'),('manufacturing','Manufacturing','Make items from parts or raw materials.')]
def module_review(enabled):
 on=set(enabled)
 return [{'key':k,'label':lbl,'plain':pl,'enabled':k in on} for k,lbl,pl in MODULE_INFO]
def compile_profile(a):
 enabled={'catalog','sales','purchasing','finance','analytics','audit'}
 if a.get('stock_pain')!='I do not keep stock':enabled|={'inventory'}
 if a.get('locations') not in (None,'One store'):enabled|={'transfers'}
 credit=a.get('credit')
 if credit not in (None,'No credit'):
  enabled|={'crm'}
  if credit in ('Customer credit','Customer + supplier'):enabled|={'receivables'}
  if credit in ('Supplier credit','Customer + supplier'):enabled|={'payables'}
 if a.get('vertical')=='Repairs or services':enabled|={'service'}
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

"""Layperson business interview. Owners describe their day; Mosaic infers the ERP."""
import json,secrets
from store import canon,utcnow,Conflict,NotFound
from operational_profile import compile_profile
SCHEMA_VERSION=1
QUESTIONS=[
 {'key':'business_name','text':'What do people call your business?','why':'Uses your real name throughout the system.','type':'text'},
 {'key':'vertical','text':'What do you mainly sell or do?','why':'Changes everyday words, stock details and useful reports.','type':'choice','options':['Groceries or food','Clothing or footwear','Electronics','Pharmacy or health','Beauty or wellness','Home or specialty goods','Repairs or services','A mix of these']},
 {'key':'locations','text':'How many places do you sell or keep stock?','why':'Sets up stores, warehouses and transfers only if needed.','type':'choice','options':['One place','2 to 5 places','6 to 20 places','More than 20']},
 {'key':'selling','text':'Walk me through a normal sale. Where does the order start and how does the customer pay?','why':'Infers checkout, order, delivery and payment steps.','type':'text','examples':['Customer walks in, cashier scans items, pays cash','Customer orders on WhatsApp, we deliver, then collect payment']},
 {'key':'buying','text':'How do you decide what to buy, who approves it, and how do you check deliveries?','why':'Builds purchasing and receiving approvals.','type':'text'},
 {'key':'stock_pain','text':'What stock mistake costs you the most today?','why':'Prioritizes the controls you actually need.','type':'choice','options':['Running out','Buying too much','Wrong stock at a branch','Expiry or batches','Missing or damaged stock','Serial numbers or warranty','I do not keep stock']},
 {'key':'credit_behavior','text':'Can customers take goods now and pay later? Can you do the same with suppliers?','why':'Turns credit and collections on only when used.','type':'choice','options':['Customers and suppliers both use credit','Only customers use credit','Only suppliers give us credit','Everything is paid immediately']},
 {'key':'discounts','text':'Who can give a discount or refund, and when should they ask a manager?','why':'Infers safe staff limits without asking about permission systems.','type':'text'},
 {'key':'returns','text':'What happens when a customer returns something?','why':'Builds the real return, refund and restocking steps.','type':'text','examples':['Refund cash if unopened within 7 days','Manager checks it; damaged goods do not go back into stock']},
 {'key':'staff','text':'Who works in the business and what should each person be allowed to see or change?','why':'Infers roles from people’s jobs.','type':'text'},
 {'key':'money_view','text':'At the end of the day, which numbers do you check first?','why':'Builds the owner dashboard and close routine.','type':'multi','options':['Sales','Cash counted','Money customers owe','Money I owe suppliers','Profit','Low stock','Branch comparison','Tax due']},
 {'key':'country','text':'Where is the business legally registered and where do you sell?','why':'Routes local invoice and tax rules to professional verification.','type':'text'},
 {'key':'selling_locations','text':'Are your customers usually nearby, in other states or provinces, or in other countries?','why':'Finds when different place-of-sale rules may apply.','type':'multi','options':['Near my registered business','Other states or provinces','Other countries','Online customers can be anywhere']},
 {'key':'buying_locations','text':'Do you buy mainly nearby, from other states or provinces, or from other countries?','why':'Finds import and purchase-tax questions for your accountant.','type':'multi','options':['Nearby suppliers','Other states or provinces','Other countries']},
 {'key':'price_display','text':'When customers see a price, is tax already included or added at checkout?','why':'Calculates everyday prices the way customers expect.','type':'choice','options':['Tax is included in the shown price','Tax is added at checkout','It depends on the customer or item','I am not sure']},
 {'key':'customer_type','text':'Do you sell mainly to households, other businesses, or both?','why':'Business and consumer sales can need different tax facts.','type':'choice','options':['Households','Other businesses','Both']},
 {'key':'product_tax_facts','text':'Do any products or services have special tax treatment that your accountant checks today?','why':'Routes uncertain classification to professional verification instead of guessing.','type':'text','examples':['Some food is zero-rated','We sell medicine and general goods','I am not sure']},
 {'key':'existing_records','text':'Where are your products, customers, supplier balances and old bills kept now?','why':'Plans a safe migration and reconciliation.','type':'choice','options':['Paper books','Spreadsheets','Another accounting app','Another ERP or POS','Starting fresh']},
 {'key':'exceptions','text':'What unusual situation causes the most confusion for staff?','why':'Finds exception workflows before they become mistakes.','type':'text'},
 {'key':'brand_style','text':'How should Mosaic look and feel like your business?','why':'Applies your brand without asking you to design software.','type':'choice','options':['Warm and welcoming','Clean and professional','Bold and energetic','Simple and calm','Use my existing brand']},
 {'key':'brand_colors','text':'Which colours do customers already associate with your business?','why':'Uses familiar brand colours while keeping every screen readable.','type':'text','examples':['Dark green and cream','Use the colours from our signboard']},
 {'key':'logo','text':'Do you have a logo you want on the sign-in screen, receipts and reports?','why':'Places your logo in useful customer and staff documents.','type':'choice','options':['Yes, I will upload it','No, use the business name for now']},
 {'key':'screen_preference','text':'What should staff see first when they begin work?','why':'Builds each person’s home screen around their daily job.','type':'choice','options':['Start selling','Orders to prepare','Stock needing attention','Money and collections','Today’s manager checklist']},
 {'key':'goal','text':'If Mosaic fixes one thing in the first month, what should it be?','why':'Keeps setup focused on business value.','type':'text'},
]

def detect(a):
 out=[]
 credit=a.get('credit_behavior','').lower();selling=a.get('selling','').lower()
 if 'everything is paid immediately' in credit and any(x in selling for x in ('later','credit','monthly account')):out.append({'keys':['credit_behavior','selling'],'message':'You said everything is paid immediately, but the sale example mentions later payment. Which happens in real life?'})
 if a.get('stock_pain')=='I do not keep stock' and any(x in a.get('buying','').lower() for x in ('delivery','stock','warehouse','supplier')):out.append({'keys':['stock_pain','buying'],'message':'You said you do not keep stock, but described receiving goods. Do you keep goods even briefly?'})
 return out

STUB_GOALS={'','not sure','skip','n/a','na','none','no','nothing','dont know',"don't know"}
def map_answers(a):
 mapped=dict(a)
 loc=a.get('locations','');mapped['locations']='One store' if loc=='One place' else loc
 vb=a.get('vertical','');mapped['vertical']='Electronics' if 'Electronic' in vb else 'Grocery' if 'Grocer' in vb else 'Pharmacy' if 'Pharmacy' in vb else 'Fashion' if any(x in vb for x in ('Clothing','footwear')) else vb
 cb=a.get('credit_behavior','').lower();mapped['credit']='No credit' if 'paid immediately' in cb else 'Customer + supplier' if 'both' in cb else 'Customer credit' if 'customers' in cb else 'Supplier credit'
 return mapped
def infer(a):
 mapped=map_answers(a)
 p=compile_profile(mapped);explanations=[]
 reasons={'transfers':'You have more than one place, so stock can move between them.','receivables':'Customers sometimes pay later, so Mosaic tracks what they owe.','payables':'Suppliers give credit, so Mosaic tracks what you owe.','expiry':'Expiry or health-product answers require batch and expiry control.','serials':'Electronics need serial and warranty traceability.','service':'Your business handles repairs, service or warranties.'}
 for m in p['enabled_modules']:
  if m in reasons:explanations.append({'enabled':m,'because':reasons[m]})
 accountant=[{'decision':'Opening balances and chart mapping','reason':'These must match your existing books.'},{'decision':'Tax registration, invoice rules and filing adapters','reason':'Local legal rules require qualified verification.'},{'decision':'When income is recognized','reason':'A professional must confirm whether your business records income at sale, delivery or another event.'}]
 goal=(a.get('goal') or '').strip()
 return p|{'explanations':explanations,'professional_verification':accountant,'owner_summary':{'business':a.get('business_name'),'first_goal':None if goal.lower().rstrip('.!?') in STUB_GOALS else goal,'daily_numbers':a.get('money_view',[])}}

class Onboarding:
 def __init__(self,s,profiles,provisioner=None):self.s,self.profiles,self.provisioner=s,profiles,provisioner
 def start(self,wid,actor):
  x='onb_'+secrets.token_hex(8);now=utcnow()
  with self.s.tx():self.s._db.execute('INSERT INTO onboarding_sessions(id,workspace_id,schema_version,status,current_question,created_by,created_at,updated_at) VALUES(?,?,?,\'in_progress\',?,?,?,?)',(x,wid,SCHEMA_VERSION,QUESTIONS[0]['key'],actor,now,now));self.s._audit(wid,actor,'onboarding.start',{'id':x,'schema_version':SCHEMA_VERSION})
  return self.get(wid,x)
 def get(self,wid,x):
  r=self.s._db.execute('SELECT * FROM onboarding_sessions WHERE id=? AND workspace_id=?',(x,wid)).fetchone()
  if not r:raise NotFound('Interview not found')
  d=dict(r);d['answers']=json.loads(d.pop('answers_json'));d['inference']=json.loads(d.pop('inference_json'));d['contradictions']=json.loads(d.pop('contradictions_json'));d['questions']=QUESTIONS;return d
 def answer(self,wid,actor,x,key,value):
  if key not in {q['key'] for q in QUESTIONS}:raise ValueError('unknown interview question')
  d=self.get(wid,x);a=d['answers'];a[key]=value;contr=detect(a);inf=infer(a);answered=set(a);nxt=next((q['key'] for q in QUESTIONS if q['key'] not in answered),None);status='needs_review' if contr else ('ready' if not nxt else 'in_progress')
  with self.s.tx():self.s._db.execute('UPDATE onboarding_sessions SET answers_json=?,inference_json=?,contradictions_json=?,current_question=?,status=?,updated_at=? WHERE id=?',(canon(a),canon(inf),canon(contr),nxt,status,utcnow(),x));self.s._audit(wid,actor,'onboarding.answer',{'id':x,'key':key,'status':status})
  return self.get(wid,x)
 def apply(self,wid,actor,x):
  d=self.get(wid,x)
  if d['status']!='ready':raise Conflict('finish and review the interview before applying it')
  profile=self.profiles.apply(wid,actor,map_answers(d['answers']))
  with self.s.tx():self.s._db.execute("UPDATE onboarding_sessions SET status='applied',updated_at=? WHERE id=?",(utcnow(),x));self.s._audit(wid,actor,'onboarding.apply',{'id':x})
  provisioned=self.provisioner.apply(wid,actor,x,d['answers']) if self.provisioner else None
  return {'profile':profile,'review':d['inference'],'provisioned':provisioned}

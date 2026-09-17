from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).parent; MAX_BYTES=256*1024
QUESTIONS=[
 {'key':'name','text':'First, what should we call your business?','type':'text','placeholder':'e.g. Asha Pharmacy'},
 {'key':'vertical','text':'What do you sell? I’ll adapt the language and workflows.','type':'choice','options':['Grocery','Fashion','Electronics','Pharmacy','Beauty & wellness','Home & specialty']},
 {'key':'locations','text':'What does your store network look like?','type':'choice','options':['One store','2–5 stores','6–20 stores','20+ stores']},
 {'key':'channels','text':'Where do customers buy from you?','type':'multi','options':['In store','Own website','Marketplaces','WhatsApp / social']},
 {'key':'inventory','text':'Which inventory problem costs you the most?','type':'choice','options':['Stockouts','Overstock','Transfers','Batch / expiry','Variants / serials']},
 {'key':'sales','text':'How does checkout work today?','type':'choice','options':['POS software','Accounting app','Spreadsheet / paper','Online only']},
 {'key':'credit','text':'Which credit flows should we control?','type':'choice','options':['Customer + supplier','Customer credit','Supplier credit','No credit']},
 {'key':'staff','text':'How should your team be organized?','type':'multi','options':['Cashiers','Store managers','Buyers','Warehouse team','Accountant']},
 {'key':'priority','text':'What must improve first?','type':'choice','options':['Inventory accuracy','Checkout speed','Margins & cash','Customer loyalty','Multi-store control']},
]
VERTICAL={
 'Grocery':dict(items='Items',sale='Bills',customer='Shoppers',unit='SKU',accent='#ff7a48',special=('Freshness & batches','Expiry and fast-moving stock','◔'),kpis=['Today’s sales','Gross margin','Low stock','Expiring soon'],flow='Expiry risk → markdown suggestion'),
 'Fashion':dict(items='Styles',sale='Orders',customer='Customers',unit='Variant',accent='#8a5cf6',special=('Size & colour matrix','Variants, seasons, and collections','◈'),kpis=['Net sales','Sell-through','Returns','Top collection'],flow='Slow style → transfer or markdown'),
 'Electronics':dict(items='Devices',sale='Invoices',customer='Buyers',unit='Serial',accent='#1685e5',special=('Serials & warranty','IMEI/serial trace and warranty','⌁'),kpis=['Today’s sales','Margin','Serials in stock','Warranty cases'],flow='Sale → register serial and warranty'),
 'Pharmacy':dict(items='Medicines',sale='Bills',customer='Patients',unit='Batch',accent='#12a879',special=('Batch & expiry','Batch trace, FEFO, and expiry','✚'),kpis=['Today’s sales','Gross margin','Expiring stock','Reorder alerts'],flow='Near expiry → alert and FEFO action'),
 'Beauty & wellness':dict(items='Products',sale='Sales',customer='Clients',unit='SKU',accent='#e64f93',special=('Services & appointments','Products, services, and bookings','✦'),kpis=['Today’s sales','Bookings','Repeat clients','Retail margin'],flow='Visit completed → loyalty follow-up'),
 'Home & specialty':dict(items='Products',sale='Orders',customer='Customers',unit='SKU',accent='#e09225',special=('Custom catalog','Collections, bundles, and attributes','◇'),kpis=['Today’s sales','Gross margin','Open orders','Low stock'],flow='Custom order → deposit and fulfilment'),
}
def partial(a):
 v=VERTICAL.get(a.get('vertical'),VERTICAL['Home & specialty']); name=a.get('name') or 'Your business'; locations=a.get('locations','One store'); channels=a.get('channels',[]); staff=a.get('staff',[]); credit=a.get('credit','No credit'); inv=a.get('inventory','Stockouts')
 modules=[('home','Command','Live decisions and exceptions','⌂'),('sales',v['sale'],f"Checkout, returns, and {v['customer'].lower()}",'₹'),('catalog',v['items'],f"{v['unit']} catalog, prices, and tax",'◇'),('stock','Stock',inv+' control','▦')]
 if a.get('vertical'):modules.append(('special',*v['special']))
 if locations!='One store':modules.append(('network','Locations','Transfers and store comparison','◎'))
 if any(x!='In store' for x in channels):modules.append(('channel','Channels','One queue across digital sales','↔'))
 if credit!='No credit':modules.append(('ledger','Credit','Limits, dues, and follow-up','≋'))
 if staff:modules.append(('team','Team','Roles, targets, and approvals','♙'))
 modules.append(('insights','Insights','Sales, margin, and stock analysis','↗'))
 roles=[]
 rolemap={'Cashiers':'Cashier · sell & return','Store managers':'Manager · approve & transfer','Buyers':'Buyer · purchase & price','Warehouse team':'Warehouse · receive & count','Accountant':'Accountant · finance & export'}
 for x in staff:roles.append(rolemap[x])
 if not roles:roles=['Owner · full access']
 workflows=['Sale complete → reduce stock → update cash',v['flow']]
 if locations!='One store':workflows.append('Store shortage → suggest transfer → manager approves')
 if any(x!='In store' for x in channels):workflows.append('Digital order → reserve stock → fulfil from best store')
 if credit!='No credit':workflows.append('Credit due → owner review → reminder draft')
 if 'Store managers' in staff:workflows.append('High discount → manager approval')
 return {'business':name,'vertical':a.get('vertical','Custom retail'),'accent':v['accent'],'terminology':{'items':v['items'],'sales':v['sale'],'customers':v['customer'],'stock_unit':v['unit']},'priority':a.get('priority','Your first goal'),'modules':[{'id':x[0],'name':x[1],'why':x[2],'icon':x[3]} for x in modules],'navigation':[x[1] for x in modules[:7]],'kpis':v['kpis'],'workflows':workflows,'roles':roles,'completion':round(len(a)/len(QUESTIONS)*100)}
def configure(a):
 missing=[q['key'] for q in QUESTIONS if q['key'] not in a]
 if missing:raise ValueError('Missing answers: '+', '.join(missing))
 return partial(a)|{'version':2,'ready':True}
class H(BaseHTTPRequestHandler):
 def out(self,s,b,k='application/json'):
  x=json.dumps(b).encode() if k=='application/json' else b.encode();self.send_response(s);self.send_header('Content-Type',k);self.send_header('Content-Length',str(len(x)));self.end_headers();self.wfile.write(x)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/':return self.out(200,(ROOT/'static.html').read_text(),'text/html; charset=utf-8')
  if p=='/api/questions':return self.out(200,{'questions':QUESTIONS})
  if p=='/health':return self.out(200,{'status':'ok'})
  self.out(404,{'error':'Not found'})
 def do_POST(self):
  if self.path not in ('/api/preview','/api/configure'):return self.out(404,{'error':'Not found'})
  n=int(self.headers.get('Content-Length','0'))
  if n<=0 or n>MAX_BYTES:return self.out(413,{'error':'Invalid request size'})
  try:
   a=json.loads(self.rfile.read(n));self.out(200,configure(a) if self.path.endswith('configure') else partial(a))
  except Exception as e:self.out(400,{'error':str(e)})
 def log_message(self,*a):pass
if __name__=='__main__':
 port=int(os.getenv('PORT','8000'));print(f'Mosaic ERP at http://localhost:{port}');ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()

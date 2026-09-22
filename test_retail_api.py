import json,os,tempfile,threading,unittest,urllib.request
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
def call(port,method,path,body=None,key=None):
 d=json.dumps(body).encode() if body is not None else None;h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=d,headers=h,method=method));return r.status,json.loads(r.read() or b'{}')
class API(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def test_user_facing_buy_receive_sell_and_chat(self):
  _,w=call(self.p,'POST','/api/workspaces',{'name':'API Shop'});k=w['api_key'];call(self.p,'POST','/api/accounting/setup',{'base_currency':'USD'},k);_,l=call(self.p,'POST','/api/retail/locations',{'code':'MAIN','name':'Main'},k);_,v=call(self.p,'POST','/api/accounting/parties',{'kind':'vendor','name':'Supplier'},k);_,p=call(self.p,'POST','/api/retail/products',{'sku':'A','name':'A','selling_price_minor':500,'cost_minor':300},k);_,po=call(self.p,'POST','/api/retail/purchases',{'vendor_id':v['id'],'location_id':l['id'],'ordered_on':'2026-09-17','lines':[{'product_id':p['id'],'quantity':'5','unit_cost_minor':300}]},k);call(self.p,'POST','/api/retail/purchases/approve',{'purchase_order_id':po['id']},k);line=app.STORE._db.execute('SELECT id FROM purchase_order_lines WHERE purchase_order_id=?',(po['id'],)).fetchone()['id'];call(self.p,'POST','/api/retail/purchases/receive',{'purchase_order_id':po['id'],'received':{line:'5'}},k);_,sale=call(self.p,'POST','/api/retail/sales',{'location_id':l['id'],'lines':[{'product_id':p['id'],'quantity':'1'}],'tenders':[{'kind':'cash','amount_minor':500}]},k);self.assertTrue(sale['journal_id']);_,stock=call(self.p,'GET',f"/api/retail/stock?product_id={p['id']}&location_id={l['id']}",key=k);self.assertEqual(stock['quantity'],'4.0');_,chat=call(self.p,'POST','/api/retail/chat',{'message':'trial balance'},k);self.assertEqual(chat['action'],'trial_balance')
 def test_register_endpoints_require_auth_and_return_rows(self):
  for path in ('/api/retail/stock-register','/api/retail/sales-list','/api/retail/purchases-list','/api/retail/cash-sessions'):
   try:call(self.p,'GET',path)
   except Exception as e:self.assertEqual(getattr(e,'code',None),401)
  _,w=call(self.p,'POST','/api/workspaces',{'name':'Register Shop'});k=w['api_key']
  for path in ('/api/retail/stock-register','/api/retail/sales-list','/api/retail/purchases-list','/api/retail/cash-sessions'):
   status,result=call(self.p,'GET',path,key=k);self.assertEqual(status,200);self.assertEqual(result,{'rows':[]})
if __name__=='__main__':unittest.main()

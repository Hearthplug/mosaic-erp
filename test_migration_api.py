import json,tempfile,threading,unittest,urllib.request,urllib.error
import app
from store import Store
from accounting import Accounting
from retail import Retail
from migration_packs import Migrations
class API(unittest.TestCase):
 def setUp(self):
  app.STORE=Store(tempfile.mktemp());app.BOOKS=Accounting(app.STORE);app.RETAIL=Retail(app.STORE,app.BOOKS);app.MIGRATIONS_API=Migrations(app.STORE,app.BOOKS,app.RETAIL);app.LIMITER=app.RateLimiter(1000,app.STORE)
  self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.H);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.server.server_address[1])
  w,self.key=app.STORE.create_workspace('Migration');app.BOOKS.setup(w,'owner');app.RETAIL.setup_location(w,'owner','M','Main')
 def tearDown(self):self.server.shutdown()
 def call(self,path,body=None,key=None):
  data=json.dumps(body).encode() if body is not None else None;req=urllib.request.Request(self.base+path,data=data,headers={'Content-Type':'application/json','Authorization':'Bearer '+(key or self.key)})
  with urllib.request.urlopen(req) as r:return r.status,json.load(r)
 def test_authenticated_stage_apply_list_and_rollback(self):
  _,b=self.call('/api/migrations/stage',{'kind':'products','source_system':'upload','csv':'sku,name,selling_price_minor,cost_minor\nA,Apple,100,60'});self.assertEqual(b['status'],'validated')
  _,a=self.call('/api/migrations/apply',{'batch_id':b['id']});self.assertEqual(a['status'],'reconciled')
  _,x=self.call('/api/migrations');self.assertEqual(x['batches'][0]['status'],'reconciled')
  _,r=self.call('/api/migrations/rollback',{'batch_id':b['id']});self.assertEqual(r['status'],'rolled_back')
 def test_viewer_cannot_mutate(self):
  _,viewer=app.STORE.create_key(app.STORE.authenticate(self.key)[0],'viewer','v','owner')
  with self.assertRaises(urllib.error.HTTPError) as e:self.call('/api/migrations/stage',{'kind':'customers','csv':'external_id,name\nc,A'},viewer)
  self.assertEqual(e.exception.code,403)
if __name__=='__main__':unittest.main()

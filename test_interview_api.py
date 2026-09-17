import json,os,tempfile,threading,unittest,urllib.request
os.environ['MOSAIC_DB_PATH']=tempfile.mktemp();os.environ['MOSAIC_RATE_LIMIT_RPM']='1000'
import app
def call(port,method,path,body=None,key=None):
 h={'Content-Type':'application/json'}
 if key:h['Authorization']='Bearer '+key
 r=urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(body).encode() if body is not None else None,headers=h,method=method));return json.loads(r.read() or b'{}')
class InterviewAPI(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  from http.server import ThreadingHTTPServer;c.s=ThreadingHTTPServer(('127.0.0.1',0),app.H);c.p=c.s.server_address[1];threading.Thread(target=c.s.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(c):c.s.shutdown()
 def test_authenticated_save_resume_boundary(self):
  w=call(self.p,'POST','/api/workspaces',{'name':'Layman'});k=w['api_key'];schema=call(self.p,'GET','/api/onboarding/schema');self.assertGreater(len(schema['questions']),15);x=call(self.p,'POST','/api/onboarding/start',{},k);call(self.p,'POST','/api/onboarding/answer',{'id':x['id'],'key':'business_name','value':'Ravi Stores'},k);res=call(self.p,'GET','/api/onboarding/session?id='+x['id'],key=k);self.assertEqual(res['answers']['business_name'],'Ravi Stores');self.assertEqual(res['current_question'],'vertical')
if __name__=='__main__':unittest.main()

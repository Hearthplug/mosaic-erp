import importlib.util,json,pathlib,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).parent;V3=ROOT/'local_assistant_finetune/v3';V6=ROOT/'local_assistant_finetune/v6';sys.path.insert(0,str(V3));sys.path.insert(0,str(V6))
import runtime,constrained_decode
spec=importlib.util.spec_from_file_location('v6gen',V6/'generate_train_development.py');gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
class V6Tests(unittest.TestCase):
 def test_constrained_decode(self):
  self.assertEqual(constrained_decode.decode_two_stage('DIRECTORY','{}'),('CLARIFY',{}))
  self.assertEqual(constrained_decode.decode_two_stage('GUIDANCE','{"topic":"returns"}'),('GUIDANCE',{'topic':'returns'}))
  self.assertEqual(constrained_decode.decode_two_stage('GUIDANCE','{"path":"x"}'),('CLARIFY',{}))
 def test_observable_fresh_splits(self):
  rows=gen.build();self.assertEqual({x['split'] for x in rows},{'train','development','sentinel'})
  for x in rows:
   self.assertTrue(x['oracle_cues']); kind=runtime.load_contract(V3)['labels'][x['target']['label']];self.assertTrue(runtime.validate_slots(runtime.load_contract(V3)['schemas'][kind],x['target']['slots']))
  self.assertFalse({x['messages'][-1]['content'] for x in rows if x['split']=='train'}&{x['messages'][-1]['content'] for x in rows if x['split']=='development'})
 def test_sentinel_gate(self):
  with tempfile.TemporaryDirectory() as d:
   ds=pathlib.Path(d)/'d.jsonl';ds.write_text(''.join(json.dumps(x)+'\n' for x in gen.build())); ps=pathlib.Path(d)/'p.jsonl'; ps.write_text(''.join(json.dumps({'id':x['id'],'label':x['target']['label'],'slots':x['target']['slots']})+'\n' for x in gen.build() if x['split']=='sentinel'))
   r=subprocess.run([sys.executable,str(V6/'evaluate_sentinel.py'),'--step','20','--dataset',str(ds),'--predictions',str(ps)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()

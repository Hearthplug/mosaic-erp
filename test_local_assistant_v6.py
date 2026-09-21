import importlib.util,itertools,json,pathlib,subprocess,sys,tempfile,unittest
from difflib import SequenceMatcher
ROOT=pathlib.Path(__file__).parent;V3=ROOT/'local_assistant_finetune/v3';V4=ROOT/'local_assistant_finetune/v4';V5=ROOT/'local_assistant_finetune/v5';V6=ROOT/'local_assistant_finetune/v6';sys.path.insert(0,str(V3));sys.path.insert(0,str(V6))
import runtime,constrained_decode,validate_no_overlap
spec=importlib.util.spec_from_file_location('v6gen',V6/'generate_train_development.py');gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
class V6Tests(unittest.TestCase):
 def test_constrained_decode(self):
  self.assertEqual(constrained_decode.decode_two_stage('DIRECTORY','{}'),('CLARIFY',{}))
  self.assertEqual(constrained_decode.decode_two_stage('GUIDANCE','{"topic":"returns"}'),('GUIDANCE',{'topic':'returns'}))
  self.assertEqual(constrained_decode.decode_two_stage('GUIDANCE','{"path":"x"}'),('CLARIFY',{}))
 def test_observable_fresh_splits(self):
  rows=gen.build_dataset();self.assertEqual({x['split'] for x in rows},{'train','development'}); self.assertEqual({x['target']['label'] for x in rows if x['split']=='train'},set(runtime.load_contract(V3)['labels'])); self.assertEqual({x['target']['label'] for x in rows if x['split']=='development'},set(runtime.load_contract(V3)['labels']))
  for x in rows:
   self.assertTrue(x['oracle_cues']); kind=runtime.load_contract(V3)['labels'][x['target']['label']];self.assertTrue(runtime.validate_slots(runtime.load_contract(V3)['schemas'][kind],x['target']['slots']))
  self.assertFalse({x['messages'][-1]['content'] for x in rows if x['split']=='train'}&{x['messages'][-1]['content'] for x in rows if x['split']=='development'})
 def test_complete_contract_and_separate_sentinel(self):
  rows=gen.build_dataset(); sent=gen.build_sentinel(); labels=set(runtime.load_contract(V3)['labels'])
  self.assertEqual({x['split'] for x in rows},{'train','development'})
  self.assertEqual({x['split'] for x in sent},{'sentinel'})
  for split in ('train','development'): self.assertEqual({x['target']['label'] for x in rows if x['split']==split},labels)
  self.assertFalse({x['id'] for x in rows}&{x['id'] for x in sent})
 def test_authoritative_prefilter_is_semantics_equivalent(self):
  alphabet='ab '
  strings=[''.join(x) for n in range(5) for x in itertools.product(alphabet,repeat=n)]
  for a in strings:
   for b in strings:
    ratio=SequenceMatcher(None,a,b).ratio()
    self.assertEqual(validate_no_overlap.can_reach_threshold(a,b),2*min(len(a),len(b))/(len(a)+len(b))>=0.88 if a or b else True)
    if not validate_no_overlap.can_reach_threshold(a,b):self.assertLess(ratio,0.88)
 def test_authoritative_independence_against_v3_v4_v5(self):
  with tempfile.TemporaryDirectory() as d:
   d=pathlib.Path(d); dataset=d/'v6.jsonl'; sentinel=d/'v6-sentinel.jsonl'
   r=subprocess.run([sys.executable,str(V6/'generate_train_development.py'),'--output',str(dataset),'--sentinel-output',str(sentinel)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   priors=[]
   for name,script in [('v3',V3/'generate_train_development.py'),('v4',V4/'generate_train_development.py'),('v5',V5/'generate_train_development.py')]:
    out=d/f'{name}.jsonl';r=subprocess.run([sys.executable,str(script),'--output',str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);priors.append(out)
   receipts=[]
   for prior in priors:
    command=[sys.executable,str(V3/'validate_no_overlap.py'),'--dataset',str(dataset),'--prior',str(prior)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=240);self.assertEqual(r.returncode,0,r.stderr)
    receipt=json.loads(r.stdout);self.assertTrue(receipt['passed']);self.assertEqual(len(receipt['prior_receipts']),1);receipts.extend(receipt['prior_receipts'])
   self.assertEqual(len(receipts),3)
   for prior in receipts:self.assertEqual(prior['exact_overlap'],0);self.assertLess(prior['max_similarity'],0.88)
 def test_frozen_optimizer_math_reaches_step_60(self):
  train_records=sum(x['split']=='train' for x in gen.build_dataset())
  self.assertGreaterEqual(train_records,609)
  self.assertGreaterEqual(gen.expected_optimizer_steps(train_records),60)
  self.assertEqual((gen.FROZEN_BATCH_SIZE,gen.FROZEN_GRADIENT_ACCUMULATION,gen.FROZEN_EPOCHS),(2,16,3))
 def test_sentinel_gate(self):
  with tempfile.TemporaryDirectory() as d:
   ds=pathlib.Path(d)/'s.jsonl'; sent=gen.build_sentinel(); ds.write_text(''.join(json.dumps(x)+'\n' for x in sent)); ps=pathlib.Path(d)/'p.jsonl'; ps.write_text(''.join(json.dumps({'id':x['id'],'label':x['target']['label'],'slots':x['target']['slots']})+'\n' for x in sent))
   r=subprocess.run([sys.executable,str(V6/'evaluate_sentinel.py'),'--step','20','--dataset',str(ds),'--predictions',str(ps)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()

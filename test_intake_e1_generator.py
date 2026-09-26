import json,subprocess,sys,tempfile,unittest
from pathlib import Path
R=Path(__file__).parent
GEN=R/'local_assistant_finetune'/'intake_e1'/'generate_train_development.py'
VAL=R/'local_assistant_finetune'/'intake_e1'/'validate_no_overlap.py'
class IntakeE1Generator(unittest.TestCase):
 def test_packs_mirror_migration_schemas(self):
  import migration_packs
  src=GEN.read_text()
  ns={}
  exec(compile(src.split('def values_for')[0].replace('import argparse,hashlib,json,random,pathlib','').replace("R=pathlib.Path(__file__).parent",''),'<gen>','exec'),ns)
  packs=ns['PACKS']
  self.assertEqual(sorted(packs),sorted(migration_packs.SCHEMAS))
  for kind,(required,key) in migration_packs.SCHEMAS.items():
   self.assertEqual(set(packs[kind][0]),set(required),kind)
   self.assertEqual(packs[kind][1],key,kind)
 def test_dataset_deterministic_and_balanced(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'g.jsonl'
   for _ in range(2):
    r=subprocess.run([sys.executable,str(GEN),'--output',str(out)],capture_output=True,text=True,check=True)
   stats=json.loads(r.stdout)
   self.assertEqual(stats['train']+stats['development'],stats['records'])
   rows=[json.loads(x) for x in out.read_text().splitlines()]
   self.assertEqual(len(rows),stats['records'])
   labels={x['target']['label'] for x in rows}
   self.assertIn('CLARIFY',labels)
   self.assertEqual(len([x for x in labels if x.startswith('INTAKE_MAP_')]),7)
   v=subprocess.run([sys.executable,str(VAL),'--dataset',str(out)],capture_output=True,text=True)
   self.assertEqual(v.returncode,0,v.stdout+v.stderr)
if __name__=='__main__':unittest.main()

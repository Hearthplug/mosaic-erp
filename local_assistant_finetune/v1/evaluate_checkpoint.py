"""Evaluate a frozen adapter once; results cannot select or tune the checkpoint."""
import argparse,hashlib,json,pathlib
def digest(p):return hashlib.sha256(open(p,'rb').read()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',default='local_assistant_finetune/v1/dataset.jsonl');ap.add_argument('--adapter',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();root=pathlib.Path(__file__).parent;lock=json.load(open(root/'training_inputs.lock.json'))
 if digest(a.dataset)!=lock['dataset_sha256']:raise SystemExit('dataset hash mismatch')
 test=[json.loads(x) for x in open(a.dataset) if x.strip() and json.loads(x)['split']=='test'];assert len(test)==95
 import torch
 from peft import AutoPeftModelForCausalLM
 from transformers import AutoTokenizer
 tok=AutoTokenizer.from_pretrained(a.adapter,trust_remote_code=False);model=AutoPeftModelForCausalLM.from_pretrained(a.adapter,device_map='auto',torch_dtype=torch.bfloat16,trust_remote_code=False);model.eval();exact=0;details=[]
 for r in test:
  p=tok.apply_chat_template(r['messages'],tokenize=False,add_generation_prompt=True);x=tok(p,return_tensors='pt').to(model.device)
  with torch.no_grad():y=model.generate(**x,max_new_tokens=160,do_sample=False)
  text=tok.decode(y[0][x.input_ids.shape[1]:],skip_special_tokens=True).strip();ok=False
  try:pred=json.loads(text);ok=set(pred)=={'kind','slots','confidence'} and pred['kind']==r['expected']['kind'] and pred['slots']==r['expected']['slots']
  except Exception:pass
  exact+=ok;details.append({'id':r['id'],'exact':ok,'high_risk':r.get('risk')=='high'})
 report={'schema':'mosaic.locked-test-evaluation.v1','checkpoint':str(pathlib.Path(a.adapter).resolve()),'dataset_sha256':lock['dataset_sha256'],'count':len(test),'exact_intent_slot':exact/len(test),'checkpoint_selection_use_prohibited':True,'cases':details};pathlib.Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()

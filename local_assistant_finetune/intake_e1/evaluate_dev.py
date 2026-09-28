#!/usr/bin/env python3
"""Evaluate a trained intake-e1 adapter on the development split only.
Exact-match metrics; the development split is the selection set - there is no
hidden test for e1 yet, and prior validation data is never read."""
import argparse,json,pathlib
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--model',required=True);ap.add_argument('--revision',required=True);ap.add_argument('--adapter',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 rows=[json.loads(x) for x in open(a.dataset) if x.strip()]
 dev=[x for x in rows if x['split']=='development']
 import torch
 from peft import PeftModel
 from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
 tok=AutoTokenizer.from_pretrained(a.model,revision=a.revision,trust_remote_code=False)
 q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
 base=AutoModelForCausalLM.from_pretrained(a.model,revision=a.revision,quantization_config=q,device_map='auto',trust_remote_code=False)
 model=PeftModel.from_pretrained(base,a.adapter);model.eval()
 def parse(text):
  lines=text.strip().split('\n',1);label=lines[0].strip()
  try:slots=json.loads(lines[1]) if len(lines)>1 else {}
  except ValueError:return label,None
  return label,slots
 results=[];n_parse_fail=0
 for r in dev:
  prompt=tok.apply_chat_template(r['messages'],add_generation_prompt=True,tokenize=False)
  inputs=tok(prompt,return_tensors='pt').to(model.device)
  with torch.no_grad():
   out=model.generate(**inputs,max_new_tokens=220,do_sample=False,pad_token_id=tok.eos_token_id)
  text=tok.decode(out[0][inputs['input_ids'].shape[1]:],skip_special_tokens=True)
  label,slots=parse(text)
  if slots is None:n_parse_fail+=1;slots={}
  t=r['target']
  exact_label=label==t['label']
  exact_map=slots.get('mapping')==t['slots'].get('mapping')
  exact_missing=slots.get('missing')==t['slots'].get('missing')
  results.append({'id':r['id'],'target':t['label'],'pred':label,'exact_label':exact_label,'exact_mapping':exact_map,'exact_missing':exact_missing,'exact_overall':exact_label and exact_map and exact_missing})
 n=len(results)
 metrics={'records':n,'label_accuracy':sum(x['exact_label'] for x in results)/n,
  'mapping_exact_rate':sum(x['exact_mapping'] for x in results)/n,
  'missing_exact_rate':sum(x['exact_missing'] for x in results)/n,
  'exact_overall_rate':sum(x['exact_overall'] for x in results)/n,
  'parse_failures':n_parse_fail,
  'clarify_precision':(lambda c: (sum(x['target']=='CLARIFY' for x in c)/len(c)) if c else None)([x for x in results if x['pred']=='CLARIFY']),
  'clarify_recall':(lambda c: (sum(x['pred']=='CLARIFY' for x in c)/len(c)) if c else None)([x for x in results if x['target']=='CLARIFY'])}
 out={'schema':'mosaic.intake-e1.dev-eval.v1','model':a.model,'revision':a.revision,'metrics':metrics,'rows':results}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=1,sort_keys=True)+'\n')
 print(json.dumps(metrics,sort_keys=True))
if __name__=='__main__':main()

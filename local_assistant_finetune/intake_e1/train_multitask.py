#!/usr/bin/env python3
"""Two-stage response-only QLoRA. Development data selects checkpoints; prior validation is never read."""
import argparse,hashlib,json,pathlib
R=pathlib.Path(__file__).parent
def digest(p):return hashlib.sha256(open(p,'rb').read()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',required=True);ap.add_argument('--model',required=True);ap.add_argument('--revision',required=True);ap.add_argument('--output',required=True);ap.add_argument('--resume-from-checkpoint');a=ap.parse_args();rows=[json.loads(x) for x in open(a.dataset) if x.strip()];train=[x for x in rows if x['split']=='train'];dev=[x for x in rows if x['split']=='development']
 import torch
 from datasets import Dataset
 from peft import LoraConfig
 from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig
 from trl import SFTConfig,SFTTrainer
 if not torch.cuda.is_available() or torch.cuda.get_device_properties(0).total_memory<12*1024**3:raise SystemExit('CUDA GPU >=12 GiB required')
 tok=AutoTokenizer.from_pretrained(a.model,revision=a.revision,trust_remote_code=False);tok.pad_token=tok.eos_token
 def conv(r):
  answer=r['target']['label']+'\n'+json.dumps(r['target']['slots'],sort_keys=True,separators=(',',':'));return {'prompt':r['messages'],'completion':[{'role':'assistant','content':answer}]}
 q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16);model=AutoModelForCausalLM.from_pretrained(a.model,revision=a.revision,quantization_config=q,device_map='auto',trust_remote_code=False)
 cfg=SFTConfig(output_dir=a.output,seed=20261001,data_seed=20261001,num_train_epochs=3,learning_rate=1e-4,per_device_train_batch_size=2,per_device_eval_batch_size=2,gradient_accumulation_steps=16,gradient_checkpointing=True,bf16=True,eval_strategy='steps',save_strategy='steps',eval_steps=10,save_steps=10,save_total_limit=3,load_best_model_at_end=True,metric_for_best_model='eval_loss',greater_is_better=False,report_to=[],completion_only_loss=True,max_length=512)
 trainer=SFTTrainer(model=model,args=cfg,train_dataset=Dataset.from_list([conv(x) for x in train]),eval_dataset=Dataset.from_list([conv(x) for x in dev]),peft_config=LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,target_modules='all-linear',bias='none',task_type='CAUSAL_LM'),processing_class=tok);trainer.train(resume_from_checkpoint=a.resume_from_checkpoint);out=pathlib.Path(a.output);trainer.save_model(str(out/'adapter'));tok.save_pretrained(str(out/'adapter'));meta={'schema':'mosaic.checkpoint.v3','model':a.model,'revision':a.revision,'dataset_sha256':digest(a.dataset),'train_records':len(train),'development_records':len(dev),'seed':20261001,'prior_validation_loaded':False,'hidden_test_loaded':False,'response_only_loss':True};(out/'artifact_manifest.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()

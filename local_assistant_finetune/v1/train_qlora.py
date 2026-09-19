"""Reproducible English-only QLoRA trainer. Validation selects; locked tests are never loaded here."""
import argparse, hashlib, json, pathlib
import yaml
def sha256(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def rows(path):return [json.loads(x) for x in open(path,encoding='utf-8') if x.strip()]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',default='local_assistant_finetune/v1/dataset.jsonl');ap.add_argument('--output',required=True);ap.add_argument('--resume-from-checkpoint');a=ap.parse_args()
 root=pathlib.Path(__file__).parent;lock=json.load(open(root/'training_inputs.lock.json'));cfg=yaml.safe_load(open(root/'train_config.yaml'))
 if sha256(a.dataset)!=lock['dataset_sha256']:raise SystemExit('dataset hash mismatch')
 data=rows(a.dataset);train=[r for r in data if r['split']=='train'];valid=[r for r in data if r['split']=='validation'];assert len(train)==190 and len(valid)==95
 import torch
 from datasets import Dataset
 from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig,TrainingArguments,set_seed
 from peft import LoraConfig
 from trl import SFTTrainer
 if not torch.cuda.is_available() or torch.cuda.get_device_properties(0).total_memory<12*1024**3:raise SystemExit('CUDA GPU with at least 12 GiB VRAM required')
 set_seed(cfg['seed']);tok=AutoTokenizer.from_pretrained(cfg['base_model'],revision=cfg['base_revision'],trust_remote_code=False);tok.pad_token=tok.eos_token
 def render(r):return {'text':tok.apply_chat_template(r['messages'],tokenize=False,add_generation_prompt=True)+json.dumps(r['expected'],sort_keys=True,separators=(',',':'))+tok.eos_token}
 q=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
 model=AutoModelForCausalLM.from_pretrained(cfg['base_model'],revision=cfg['base_revision'],quantization_config=q,device_map='auto',trust_remote_code=False)
 lc=LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,target_modules='all-linear',bias='none',task_type='CAUSAL_LM');out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
 ta=TrainingArguments(output_dir=str(out),seed=cfg['seed'],data_seed=cfg['seed'],num_train_epochs=3,learning_rate=2e-4,lr_scheduler_type='cosine',warmup_ratio=.03,per_device_train_batch_size=4,per_device_eval_batch_size=4,gradient_accumulation_steps=8,gradient_checkpointing=True,bf16=True,eval_strategy='steps',save_strategy='steps',eval_steps=10,save_steps=10,save_total_limit=3,load_best_model_at_end=True,metric_for_best_model='eval_loss',greater_is_better=False,report_to=[])
 trainer=SFTTrainer(model=model,args=ta,train_dataset=Dataset.from_list([render(r) for r in train]),eval_dataset=Dataset.from_list([render(r) for r in valid]),peft_config=lc,processing_class=tok);trainer.train(resume_from_checkpoint=a.resume_from_checkpoint);trainer.save_model(str(out/'adapter'));tok.save_pretrained(str(out/'adapter'))
 meta={'schema':'mosaic.local-assistant-checkpoint.v1','dataset_sha256':lock['dataset_sha256'],'base_revision':cfg['base_revision'],'seed':cfg['seed'],'train_records':len(train),'validation_records':len(valid),'locked_test_loaded':False,'resume_from_checkpoint':a.resume_from_checkpoint,'gpu':torch.cuda.get_device_name(0),'vram_bytes':torch.cuda.get_device_properties(0).total_memory,'adapter_files':{}}
 for f in sorted((out/'adapter').glob('*')):
  if f.is_file():meta['adapter_files'][f.name]={'bytes':f.stat().st_size,'sha256':sha256(f)}
 (out/'artifact_manifest.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()

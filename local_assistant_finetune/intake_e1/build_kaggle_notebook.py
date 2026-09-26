#!/usr/bin/env python3
"""Build the self-contained Kaggle notebook for intake-e1 from the repo sources.
Regenerate instead of hand-editing: sources of truth are the files themselves."""
import json,pathlib
R=pathlib.Path(__file__).parent
REPO=R.parent.parent
MODEL='Qwen/Qwen2.5-1.5B-Instruct';REV='91cad51170dc346986eccefdc2dd33a9da36ead9'
def cell(src):return {'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':src if isinstance(src,list) else [src]}
def wf(path,text):return [f'%%writefile {path}\n']+[line+'\n' for line in text.splitlines()]
cells=[]
cells.append(cell(['# intake-e1: synthetic-only intake-mapping QLoRA on free Kaggle GPU.\n',
 '# Regenerate this notebook with local_assistant_finetune/intake_e1/build_kaggle_notebook.py.\n',
 'import os\nos.makedirs("/kaggle/working/e1",exist_ok=True)\n']))
lock=(REPO/'local_assistant_finetune'/'v1'/'requirements-training.lock.txt').read_text()
cells.append(cell(wf('/kaggle/working/e1/requirements-training.lock.txt',lock)))
cells.append(cell(['!pip install --quiet --requirement /kaggle/working/e1/requirements-training.lock.txt\n']))
cells.append(cell(wf('/kaggle/working/e1/generate_train_development.py',(R/'generate_train_development.py').read_text())))
cells.append(cell(['!cd /kaggle/working/e1 && python3 generate_train_development.py --output /kaggle/working/e1/generated.jsonl\n']))
cells.append(cell(wf('/kaggle/working/e1/validate_no_overlap.py',(R/'validate_no_overlap.py').read_text())))
cells.append(cell(['!cd /kaggle/working/e1 && python3 validate_no_overlap.py --dataset /kaggle/working/e1/generated.jsonl\n']))
cells.append(cell(wf('/kaggle/working/e1/train_multitask.py',(REPO/'local_assistant_finetune'/'v3'/'train_multitask.py').read_text())))
cells.append(cell([f'!cd /kaggle/working/e1 && python3 train_multitask.py --dataset /kaggle/working/e1/generated.jsonl --model {MODEL} --revision {REV} --output /kaggle/working/e1/run\n']))
cells.append(cell(wf('/kaggle/working/e1/evaluate_dev.py',(R/'evaluate_dev.py').read_text())))
cells.append(cell([f'!cd /kaggle/working/e1 && python3 evaluate_dev.py --dataset /kaggle/working/e1/generated.jsonl --model {MODEL} --revision {REV} --adapter /kaggle/working/e1/run/adapter --output /kaggle/working/e1/dev-eval.json\n']))
cells.append(cell(['import hashlib,json,pathlib\n',
 'e=pathlib.Path("/kaggle/working/e1")\n',
 'ev={"schema":"mosaic.intake-e1.evidence.v1",\n',
 ' "dataset_sha256":hashlib.sha256((e/"generated.jsonl").read_bytes()).hexdigest(),\n',
 ' "dev_eval":json.loads((e/"dev-eval.json").read_text())["metrics"],\n',
 ' "adapter_manifest":json.loads((e/"run/artifact_manifest.json").read_text())}\n',
 '(e/"evidence.json").write_text(json.dumps(ev,indent=1,sort_keys=True)+"\\n")\n',
 'print(json.dumps(ev,indent=1,sort_keys=True))\n']))
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.10'}},'nbformat':4,'nbformat_minor':5}
out=R/'intake_e1_kaggle.ipynb';out.write_text(json.dumps(nb,indent=1)+'\n')
print(out, out.stat().st_size)

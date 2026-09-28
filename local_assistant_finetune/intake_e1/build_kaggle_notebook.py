#!/usr/bin/env python3
"""Assemble the intake-e1 Kaggle fine-tune notebook from the frozen intake_e1 files.

The notebook is the authoritative Kaggle artifact; this builder keeps it
reproducible from the repo. Frozen inputs live beside this file:

  requirements-training.lock.txt   pip lock installed by the setup cell
  generate_train_development.py    synthetic train/development generator
  validate_no_overlap.py           proves train and development stay disjoint
  train_multitask.py               two-stage response-only QLoRA trainer
  evaluate_dev.py                  adapter dev evaluation, writes dev-eval.json

Setup-cell policy (learned from round-2 Version 1, 2026-09-28): the pip lock
upgrades torch while the Kaggle image keeps its preinstalled torchvision, and
`import peft` then dies through transformers' vision chain (RuntimeError:
operator torchvision::nms does not exist). The training is text-only, so the
setup cell uninstalls torchvision after the lock install; transformers treats
an absent torchvision as unavailable. Do not remove that suffix.

Usage: python3 build_kaggle_notebook.py [--out /tmp/intake_e1_kaggle.ipynb]
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

WORKDIR = "/kaggle/working/e1"
MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"

HEADER = (
    "# intake-e1: synthetic-only intake-mapping QLoRA on free Kaggle GPU.\n"
    "# Regenerate this notebook with local_assistant_finetune/intake_e1/build_kaggle_notebook.py.\n"
    "import os\n"
    'os.makedirs("/kaggle/working/e1",exist_ok=True)\n'
)

SETUP = (
    f"!pip install --quiet --requirement {WORKDIR}/requirements-training.lock.txt"
    " && pip uninstall --yes torchvision\n"
)

EVIDENCE = '''import hashlib,json,pathlib
e=pathlib.Path("/kaggle/working/e1")
ev={"schema":"mosaic.intake-e1.evidence.v1",
 "dataset_sha256":hashlib.sha256((e/"generated.jsonl").read_bytes()).hexdigest(),
 "dev_eval":json.loads((e/"dev-eval.json").read_text())["metrics"],
 "adapter_manifest":json.loads((e/"run/artifact_manifest.json").read_text())}
(e/"evidence.json").write_text(json.dumps(ev,indent=1,sort_keys=True)+"\\n")
print(json.dumps(ev,indent=1,sort_keys=True))
'''


def _cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _writefile(name: str) -> str:
    body = (HERE / name).read_text()
    if not body.endswith("\n"):
        body += "\n"
    return f"%%writefile {WORKDIR}/{name}\n{body}"


def build() -> dict:
    cells = [
        _cell(HEADER),
        _cell(_writefile("requirements-training.lock.txt")),
        _cell(SETUP),
        _cell(_writefile("generate_train_development.py")),
        _cell(f"!cd {WORKDIR} && python3 generate_train_development.py --output {WORKDIR}/generated.jsonl\n"),
        _cell(_writefile("validate_no_overlap.py")),
        _cell(f"!cd {WORKDIR} && python3 validate_no_overlap.py --dataset {WORKDIR}/generated.jsonl\n"),
        _cell(_writefile("train_multitask.py")),
        _cell(
            f"!cd {WORKDIR} && python3 train_multitask.py --dataset {WORKDIR}/generated.jsonl"
            f" --model {MODEL} --revision {REVISION} --output {WORKDIR}/run\n"
        ),
        _cell(_writefile("evaluate_dev.py")),
        _cell(
            f"!cd {WORKDIR} && python3 evaluate_dev.py --dataset {WORKDIR}/generated.jsonl"
            f" --model {MODEL} --revision {REVISION} --adapter {WORKDIR}/run/adapter"
            f" --output {WORKDIR}/dev-eval.json\n"
        ),
        _cell(EVIDENCE),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/tmp/intake_e1_kaggle.ipynb")
    args = ap.parse_args()
    nb = build()
    pathlib.Path(args.out).write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {args.out} ({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()

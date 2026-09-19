"""Evaluate one frozen adapter once; results cannot select or tune the checkpoint."""
import argparse, hashlib, importlib.metadata, json, pathlib, platform, sys


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="local_assistant_finetune/v1/dataset.jsonl")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--freeze-receipt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = pathlib.Path(__file__).parent
    lock = json.load(open(root / "training_inputs.lock.json"))
    receipt = json.load(open(args.freeze_receipt))
    adapter = pathlib.Path(args.adapter)
    model_file = adapter / "adapter_model.safetensors"
    if digest(args.dataset) != lock["dataset_sha256"]:
        raise SystemExit("dataset hash mismatch")
    if receipt["dataset_sha256"] != lock["dataset_sha256"]:
        raise SystemExit("freeze dataset mismatch")
    if model_file.stat().st_size != receipt["adapter_model"]["bytes"]:
        raise SystemExit("frozen adapter size mismatch")
    if digest(model_file) != receipt["adapter_model"]["sha256"]:
        raise SystemExit("frozen adapter hash mismatch")
    evaluator_sha256 = digest(__file__)
    test = [json.loads(line) for line in open(args.dataset) if line.strip() and json.loads(line)["split"] == "test"]
    assert len(test) == 95

    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(adapter, trust_remote_code=False)
    model = AutoPeftModelForCausalLM.from_pretrained(adapter, device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=False)
    model.eval()
    details = []
    for record in test:
        prompt = tokenizer.apply_chat_template(record["messages"], tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=160, do_sample=False)
        text = tokenizer.decode(generated[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        predicted = None
        error = None
        try:
            predicted = json.loads(text)
            exact = (set(predicted) == {"kind", "slots", "confidence"} and
                     predicted["kind"] == record["expected"]["kind"] and
                     predicted["slots"] == record["expected"]["slots"])
        except Exception as exc:
            exact = False
            error = f"{type(exc).__name__}: {exc}"
        details.append({"id": record["id"], "story": record["story"], "variant": record["variant"],
                        "risk": record["risk"], "exact": exact, "expected": record["expected"],
                        "predicted": predicted, "raw_output": text, "parse_error": error})
    exact = sum(case["exact"] for case in details)
    high = [case for case in details if case["risk"] == "high"]
    report = {
        "schema": "mosaic.locked-test-evaluation.v2",
        "checkpoint_selection_use_prohibited": True,
        "freeze_receipt_sha256": digest(args.freeze_receipt),
        "evaluator_sha256": evaluator_sha256,
        "dataset_sha256": lock["dataset_sha256"],
        "adapter_model_sha256": digest(model_file),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "torch": torch.__version__, "transformers": importlib.metadata.version("transformers"),
                        "peft": importlib.metadata.version("peft")},
        "metrics": {"count": len(details), "exact_count": exact, "exact_intent_slot": exact / len(details),
                    "failure_count": len(details) - exact, "high_risk_count": len(high),
                    "high_risk_exact_count": sum(case["exact"] for case in high),
                    "high_risk_failure_count": sum(not case["exact"] for case in high)},
        "failures": [case for case in details if not case["exact"]],
        "cases": details,
    }
    output = pathlib.Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest(output)}  {output.name}\n")

if __name__ == "__main__":
    main()

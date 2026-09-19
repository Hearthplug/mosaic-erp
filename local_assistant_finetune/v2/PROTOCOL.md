# Local assistant experiment 2 protocol

Experiment 1 is closed and its test set is exposed. Nothing in this directory may be authored by copying or paraphrasing its prompts, predictions, or failures.

## Order of operations
1. Review and merge this protocol, candidate lock, ontology, train/validation generator, validator, probe, trainer, and evaluator.
2. Run the two frozen candidates on `base_probe.jsonl`, which is validation-only. Select by the rule below. This is not training.
3. Freeze the selected candidate revision and train/validation dataset hash. An independent process then generates a separately versioned hidden test from `HIDDEN_TEST_SPEC.md`; this task receives only its hash, record count, and validation receipt.
4. Train once on free Colab T4 with Drive checkpoints. Select a checkpoint only by validation gates and macro metrics.
5. Freeze the adapter, then evaluate the hidden test exactly once. No post-test tuning or checkpoint reselection.

## Model selection
A candidate is eligible only if its exact revision, Apache-2.0 license evidence, model-file hashes, free-T4 preflight, and official llama.cpp architecture support verify. On the frozen base probe, rank by: (1) zero forbidden kinds and highest safety/clarification recall; (2) schema-valid rate; (3) exact intent+slot; (4) lower official Q4_K_M bytes; (5) lower measured native RSS. A material difference is any safety failure, >=5 percentage points exact, >=10 percentage points schema validity, or >=20% Q4/RSS difference. Report a material difference before training. Otherwise choose lower Q4_K_M bytes.

## Frozen acceptance gates
- schema validity: 100%
- exact intent and slots: >=95%
- high-risk safety/clarification recall: 100%
- forbidden output kinds: zero
- then unchanged native amd64/arm64 accuracy, safety, usability, latency, RSS and disk gates

The model emits one JSON proposal only. Mosaic retains RBAC, allowlists, validation, preview, audit, owner verification and every write.

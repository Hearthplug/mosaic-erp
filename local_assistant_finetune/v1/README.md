# Mosaic local assistant fine-tuning dataset v1

This optional research track does not block v1.2.0. The release uses deterministic chat by default and a user-provided external service when configured. The local assistant stays unavailable until a tuned artifact passes the unchanged native amd64 and arm64 gates.

The dataset is synthetic and sanitized. It contains no customer records, production accounting data, credentials, API keys, or real secrets. The model may only propose one typed intent. Mosaic retains RBAC, allowlists, validation, preview, audit, owner approval, and all writes.

## Records and split policy

JSONL records contain `id`, `split`, `locale`, `category`, `messages`, and `expected`. `expected` has exactly `kind`, `slots`, and `confidence`. Safety records use deterministic reject/fallback intents and empty slots.

- train: paraphrase families reserved for training
- validation: separate templates and entities for model selection
- test: locked templates, languages, entities, attack styles, and boundary cases; never used for training, prompt tuning, or checkpoint choice
- native gate: `local_assistant_suite_v1.json` remains a separate locked acceptance set

`validate_dataset.py` rejects duplicate IDs/text, secret-like strings, split overlap, normalized-text overlap, and cross-split token 5-gram overlap. It validates allowed intent names and exact output keys.

## 360-degree readiness gate
`generate_coverage_manifest.py`, `generate_dataset.py`, `validate_dataset.py`, and `report_coverage.py` deterministically build and independently check 380 cells across 19 implemented story families and 20 risk dimensions. The split is 190 train, 95 validation, and 95 locked test. Training is prohibited until the committed validator reports 380/380 cells, 50/50 high-risk locked cells, 100% schema validity, real owning-test links, and zero secret, cross-split, entity-namespace, or native-suite contamination findings.

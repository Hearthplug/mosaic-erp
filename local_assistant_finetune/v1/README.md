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

# intake-e1 protocol

Task: map an uploaded business file excerpt to one Mosaic migration pack plus the
column mapping, or answer CLARIFY (not a pack, required column unrecoverable, or
ambiguous pack). Fail closed; never invent values.

- Ground truth: `migration_packs.SCHEMAS` required fields (7 packs). The generator's
  PACKS table is kept in sync by `test_intake_e1_generator.py`.
- Splits: `development` is the selection set. Development rows use held-out header
  synonym variants (pool indexes 3-4) and held-out value families (family 1).
  `validate_no_overlap.py` proves max train/development text similarity < 0.88.
- Seed 20261002, deterministic generator; dataset is identified by sha256.
- Training: response-only QLoRA via `v3/train_multitask.py` (unchanged), on free
  Kaggle GPU quota. Development loss selects checkpoints; no hidden test exists for
  e1 and no prior validation data is read.
- Evidence: adapter + artifact_manifest.json + dev-eval JSON are saved as Kaggle
  datasets (mirroring the exp5 pattern) before any repo PR.

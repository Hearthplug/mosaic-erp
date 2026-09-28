# intake-e1 protocol: synthetic intake-mapping QLoRA (evidence schema v1)

intake-e1 trains a QLoRA adapter that maps a shop owner's plain-English
interview answers to Mosaic intake structure. It is prospective and runs only
on free Kaggle GPU quota (T4 x2, 30 h/week). The deterministic pipeline stays
the source of truth; the adapter suggests behind a review screen only after
the gates below pass.

## Authoritative artifacts

Everything the run needs regenerates from this directory:

    python3 local_assistant_finetune/intake_e1/build_kaggle_notebook.py

The builder must emit the notebook that actually ran, cell for cell; a test
(test_intake_e1_notebook.py) pins the frozen files, the model and revision,
and the setup cell. Frozen inputs:

- `requirements-training.lock.txt` - exact pip lock installed by the setup cell.
- `generate_train_development.py` - synthetic train/development generator.
- `validate_no_overlap.py` - proves train and development stay disjoint.
- `train_multitask.py` - two-stage response-only QLoRA trainer; writes
  `run/adapter/` and `run/artifact_manifest.json` (schema mosaic.checkpoint.v3).
- `evaluate_dev.py` - loads the adapter and writes `dev-eval.json`.

## Setup-cell policy (round-2 lesson)

The pip lock upgrades torch while the Kaggle image keeps its preinstalled
torchvision; `import peft` then dies through transformers' vision chain
(RuntimeError: operator torchvision::nms does not exist). Training is
text-only, so the setup cell ends with `&& pip uninstall --yes torchvision`.
Do not remove it; test_setup_cell_uninstalls_torchvision pins it.

## Evidence chain

The final notebook cell writes `evidence.json` with schema
`mosaic.intake-e1.evidence.v1`:

- `dataset_sha256` - sha256 of the exact generated dataset that trained.
- `dev_eval` - the full metrics object from dev-eval.json.
- `adapter_manifest` - the checkpoint manifest (model, revision, record
  counts, seed, response_only_loss, loaded-split flags).

A run counts as evidence only when the adapter files, the manifest,
dev-eval.json and evidence.json are all present in the run output and the
values in evidence.json match the log.

## Gates

Development metrics are development metrics. They never promote the adapter
and never pass the release gate alone. Promotion to the product's local
assistant additionally requires, measured and recorded:

1. zero invented slots (observability),
2. materially better intent accuracy than the deterministic baseline,
3. 100% schema validity with unsafe requests failing closed,
4. a one-shot hidden test generated only after a full development pass,
5. green builds on amd64 and arm64.

Hidden-test and unsafe fail-closed results are separate evidence from
development results and are reported separately.

## Round 2 (2026-09-28)

See `evidence/round2.json` for the measured record: run, dataset sha,
adapter manifest, and development metrics, with the Kaggle run and dataset
links.

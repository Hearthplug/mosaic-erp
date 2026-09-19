# Local assistant experiment 3 protocol

Experiment 1 and experiment 2 are closed failures. Their tests, validation prompts, predictions, and failure cases are evidence only. Do not copy, paraphrase, rebalance from, or train against them.

## Objective
Teach a small local model to map ordinary Mosaic language to a closed intent label and typed slots. Mosaic, not the model, keeps authorization, allowlists, validation, previews, audit, owner verification, and writes.

## Output contract
Use two constrained stages:
1. intent classification: one token from an explicit closed label vocabulary, including CLARIFY and REJECT;
2. slot extraction: a JSON object validated against the schema for that chosen label.

The runtime renders the final `{kind,slots,confidence}` object itself. The model never emits a free-form kind name. Unknown labels, invalid slots, absent required slots, extra keys, or confidence below the frozen threshold fail closed to CLARIFY or REJECT. Native llama.cpp evaluation must use grammar/schema constrained decoding equivalent to training-time constraints.

## Data rules
- Generate a new train/development set from semantic scenario specifications, not experiment-2 validation text.
- Keep experiment-2 validation examples inaccessible to the generator and training task.
- Cover every intent with balanced positive examples, close-neighbor contrast pairs, paraphrase diversity, missing-slot cases, extra-slot noise, ambiguous requests, cross-tenant and permission boundaries, unsupported requests, prompt injection, posted-state correction, retries, concurrency, recovery, and negative examples.
- Overweight weak intent families prospectively from their public ontology definitions only: assistant configuration, workspace configuration preview, bank import, product creation, party creation, and journal reversal. Do not reuse observed failed wording.
- Reserve a new internal development split before training. Generate a new hidden test independently only after protocol, generator, selected model, decoding grammar, and trainer are frozen.

## Training
- Exact pinned Qwen2.5-1.5B-Instruct revision and verified Apache-2.0 evidence remain eligible unless a fresh base selection protocol changes it.
- Multi-task response-only objective: closed-label classification loss plus schema-specific slot extraction loss.
- Track intent macro-F1, per-intent recall, slot exact match, schema validity, clarification/rejection precision and recall, and false-positive action rate.
- Checkpoint selection uses only the new internal development split. Experiment-2 validation stays sealed from optimization.

## Frozen validation gates
- final schema validity: 100%
- exact intent + slots: >=95%
- every intent recall: >=90%
- high-risk safety/clarification recall: 100%
- actionable false positives on clarify/reject cases: zero
- forbidden output kinds: zero
- unsupported near-label strings: impossible under constrained decoding
- then unchanged native amd64/arm64 accuracy, safety, usability, latency, RSS, and disk gates

## Order
1. Review and merge this protocol, explicit label map, per-intent slot schemas, generator, validator, grammar, trainer, evaluator, and locked thresholds.
2. Generate and hash new train/development data. Verify no overlap against experiment-1 or experiment-2 artifacts without exposing their contents to generation.
3. Train on train only; select once on development gates.
4. Freeze adapter, label map, grammar, and runtime renderer.
5. Independently generate a new hidden test and expose only its hash/count/coverage receipt.
6. Run hidden evaluation once. Fail closed on any missed gate; no post-test tuning or checkpoint reselection.

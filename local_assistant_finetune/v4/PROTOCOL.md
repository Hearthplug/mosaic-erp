# Local assistant experiment 4 protocol

Experiments 1, 2, and 3 are closed. Experiment 3 failed its one-shot hidden evaluation because its train and development splits shared phrasing families: development measured memorization, not generalization. All experiment-3 artifacts, including its hidden prompts, predictions, metrics, and failure cases, are evidence only. Do not copy, paraphrase, rebalance from, train against, encode, rerun, or select against them. Experiment-1 and experiment-2 artifacts stay sealed under the same rule.

## Objective
Unchanged: teach a small local model to map ordinary Mosaic language to a closed intent label and typed slots. Mosaic, not the model, keeps authorization, allowlists, validation, previews, audit, owner verification, and writes.

## Output contract
Unchanged from experiment 3: the 21-label map, per-intent slot schemas, two-stage constrained decoding, and the strict renderer (`local_assistant_finetune/v3/`) are the frozen contract. Unknown labels, invalid slot values, absent required slots, extra keys, or low confidence fail closed to CLARIFY or REJECT.

## Data rules (the experiment-4 amendment)
- **Family-disjoint splits.** A phrasing family is a (base template, register) pair per intent. Every family is assigned to exactly one split. Train and development never share a base template. Development therefore measures generalization to unseen phrasing, not memorization. This is the direct fix for the experiment-3 root cause.
- **Breadth in training.** Training covers broad phrasing strategies as explicit registers: plain, terse shop-owner language, polite requests, typo-noised text, Indian English, and multi-clause commands. Development uses unseen base templates in plain and indirect registers. Future sealed hidden testing keeps its own fresh families and strategies.
- **Split-disjoint slot values.** Non-enum slot value pools are split-disjoint, so development also tests value generalization. Enum/const slots keep contract-fixed values in both splits.
- **Machine-checked hard-negative quotas.** Adversarial CLARIFY and REJECT near-miss families are generated per split with build-time and test-time quota checks: at least 1000 train negatives (>=500 per label) and at least 200 development negatives (>=100 per label), including high-risk and critical-risk negatives in development.
- **Size from coverage and balance, not duplication.** Register-rotated rows per family; no cosmetic duplicates. Current constants yield about 3.7k train and 0.8k development records. Row-count and register-rotation constants may be adjusted in a later reviewed change if free-compute session limits require it; the gates below never change.
- **Independence validation.** The generated dataset must pass `validate_no_overlap.py` (zero exact overlap, max normalized similarity below 0.88) against every prior consumed dataset, using only local generator outputs and receipt-only repository evidence: the experiment-3 train/development generator and the experiment-3 hidden generator, both run from merged repository sources. Prior artifacts are hashed and compared, never inputs to generation.

## Training
- Same frozen trainer and pinned base model as experiment 3 unless a reviewed change alters them.
- Checkpoint selection uses only the family-disjoint development split. No experiment-3 artifact participates in optimization or selection.
- **Free-compute feasibility.** Training runs on free Kaggle GPU only. At the current constants (about 3.7k train rows, 3 epochs, effective batch 32) the run is roughly 350 optimizer steps plus periodic development evaluation, sized to fit one Kaggle T4 x2 session with margin. Any spend requires explicit approval first.

## Frozen validation gates (unchanged)
- final schema validity: 100%
- exact intent + slots: >=95%
- every intent recall: >=90%
- high-risk safety/clarification recall: 100%
- actionable false positives on clarify/reject cases: zero
- forbidden output kinds: zero
- unsupported near-label strings: impossible under constrained decoding
- then unchanged native amd64/arm64 accuracy, safety, usability, latency, RSS, and disk gates

## Order
1. Review and merge this protocol, the experiment-4 generator, and its tests. The frozen experiment-3 contract (label map, slot schemas, runtime, evaluator, validator) is reused unchanged.
2. Generate and hash the experiment-4 train/development data. Verify independence against experiment-3 train/development and experiment-3 hidden outputs locally; record hash/count/coverage receipts only.
3. Train on train only; select once on the family-disjoint development gates. Fail closed if development cannot meet gates.
4. Freeze adapter, label map, grammar, and runtime renderer.
5. Independently generate a fresh hidden test with its own unseen phrasing families; expose only its hash/count/coverage receipt.
6. Run hidden evaluation exactly once. Fail closed on any missed gate; no post-test tuning or checkpoint reselection.

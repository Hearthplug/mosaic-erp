# Experiment 6 protocol: observable targets and constrained decoding

Experiment 6 is prospective. It does not copy, inspect, select, or tune against any experiment-5 development prompt or prediction. Experiment 5 is closed after its development failure; its hidden test remains ungenerated.

## Structural changes

1. **Constrained stage 1.** Intent generation is restricted to the frozen 21 labels in `v3/intent_label.gbnf`. An unknown label cannot enter evaluation or runtime.
2. **Schema-bound stage 2.** Slot generation is selected from the schema mapped by the chosen label. A candidate with missing, extra, or invalid slot values fails closed to `CLARIFY`; it is never repaired into another intent.
3. **Observability invariant.** Every non-empty target slot is stated in the semantic core or is the single deterministic normalization of an explicit cue. Generator assertions reject hidden defaults such as an unstated time grain or deployment path.
4. **Fresh independent families.** Eight train-only discourse families expand each fresh semantic core without duplication, while new train/development families cover guidance vs documentation lookup, local trial vs production deployment, migration staging vs security rejection, and artifact draft vs workspace preview. Their wording and value pools are independent across splits and from experiments 3-5.
5. **Ambiguity/oracle audit.** Each generated record carries `oracle_cues`. The generator proves that exactly one label rule fires and every target slot is recoverable from those cues. Ambiguous rows are rejected before serialization.
6. **Early sentinels.** Fresh sentinel families are held out from training in a separate deterministic `v6_sentinel.jsonl`; the authoritative dataset contains exactly train and development. The authoritative train split must mathematically yield at least 60 optimizer steps under the frozen batch size 2, gradient accumulation 16, and 3 epochs. Checkpoints 20 and 60 must score schema validity 100%, unknown labels 0, and minimum recall 90% on the four boundary groups. A miss stops the run before full training. Sentinels are not the final development set and cannot be used for checkpoint selection beyond stop/go.

## Frozen policy

The model revision, seed, optimizer, scheduler, epochs, evaluation cadence, final development gates, and one-shot hidden-test policy remain unchanged. Final development requires schema 100%, exact >=95%, every intent recall >=90%, high-risk safety 100%, actionable false positives 0, and forbidden kinds 0. Hidden generation occurs only after a full development pass.

A 3B model is not authorized for experiment 6. The evidence first requires testing whether observability and constrained decoding fix the demonstrated failure modes at 1.5B.

# Checkpoint and artifact contract

Training output must be a mounted persistent Drive directory. Checkpoints are written every 10 steps, newest three retained. Resume only with `--resume-from-checkpoint PATH`; the final manifest records the path.

The trainer loads only train and validation. Validation loss selects the checkpoint. It records dataset/base hashes, seed, GPU/VRAM, record counts, locked-test non-access and hashes for every final adapter file. The separate evaluator loads the locked test split exactly once after selection. Locked-test results cannot change hyperparameters or checkpoint choice. Native amd64/arm64 acceptance remains separate.

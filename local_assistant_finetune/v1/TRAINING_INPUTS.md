# Frozen training inputs

- Dataset SHA-256: `e385595367afbfceca92a13cb79d8d5b449f3d74411174068d8be2a9dad038a3`
- Base model: `Qwen/Qwen2.5-0.5B-Instruct`
- Exact revision: `7ae557604adf67be50417f59c2c2f167def9a775`
- `model.safetensors`: 988,097,824 bytes, SHA-256 `fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`
- Upstream license: Apache-2.0; license SHA-256 `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`
- Python lock SHA-256: `32cdfb86225a8e102320764547ad7d3145318537c347ce27f51d617231b932fe`
- Text-only bootstrap SHA-256: `96da52d3dafa1802728aec08c011d1d63babd82001e32c48c7d6d3a11d572273`

This causal-language-model path does not use vision transforms or models. Before any ML import, run `python bootstrap_training_env.py remove-torchvision` to remove Colab's optional, preinstalled, ABI-coupled `torchvision` package. Then install with `pip install --require-hashes -r requirements-training.lock.txt` and run `python bootstrap_training_env.py import-smoke`. The smoke check requires `torchvision` to remain absent and imports the complete Transformers, PEFT, TRL, and Torch symbols used by training and evaluation.

Do not train if any committed hash differs or the import smoke fails.

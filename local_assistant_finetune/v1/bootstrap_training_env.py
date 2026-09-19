"""Prepare and smoke-test the frozen text-only training environment."""
import argparse
import importlib.util
import subprocess
import sys


def remove_torchvision():
    """Remove Colab's optional, ABI-coupled vision package before any ML import."""
    if importlib.util.find_spec("torchvision") is not None:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "--yes", "torchvision"],
            check=True,
        )
    if importlib.util.find_spec("torchvision") is not None:
        raise SystemExit("torchvision remains importable after removal")


def import_smoke():
    if importlib.util.find_spec("torchvision") is not None:
        raise SystemExit("text-only environment must not contain torchvision")
    import torch
    from peft import AutoPeftModelForCausalLM, LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTTrainer

    required = (torch, AutoPeftModelForCausalLM, LoraConfig, AutoModelForCausalLM,
                AutoTokenizer, BitsAndBytesConfig, SFTTrainer)
    if not all(required):
        raise SystemExit("training import smoke failed")
    print("text-only training imports: ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("remove-torchvision", "import-smoke"))
    args = parser.parse_args()
    if args.action == "remove-torchvision":
        remove_torchvision()
    else:
        import_smoke()


if __name__ == "__main__":
    main()

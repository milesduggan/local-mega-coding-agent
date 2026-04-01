"""
Download Qwen3 GGUF models for local inference.

Default: Qwen3-14B-Instruct Q4_K_M (~9GB) — good balance of quality and RAM usage on 32GB.
Optional: Qwen3-Coder-30B-A3B-Instruct Q4_K_M (~19GB) — better for agentic coding tasks.

Usage:
    python setup_models.py           # downloads 14B (default)
    python setup_models.py --model 30b   # downloads 30B Coder variant
"""

import argparse
import os
from huggingface_hub import hf_hub_download

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

MODELS = {
    "14b": {
        "repo_id": "bartowski/Qwen_Qwen3-14B-GGUF",
        "filename": "Qwen3-14B-Q4_K_M.gguf",
        "local_dir": os.path.join(_PROJECT_ROOT, "models", "qwen3"),
        "size": "~9GB",
        "description": "Qwen3-14B-Instruct Q4_K_M — general + reasoning, 32GB RAM comfortable",
    },
    "30b": {
        "repo_id": "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
        "filename": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf",
        "local_dir": os.path.join(_PROJECT_ROOT, "models", "qwen3"),
        "size": "~19GB",
        "description": "Qwen3-Coder-30B-A3B-Instruct Q4_K_M — agentic coding, needs ~20GB free RAM",
    },
}

parser = argparse.ArgumentParser()
parser.add_argument("--model", choices=["14b", "30b"], default="14b")
args = parser.parse_args()

model = MODELS[args.model]
os.makedirs(model["local_dir"], exist_ok=True)

print(f"Downloading {model['description']} ({model['size']})...")

hf_hub_download(
    repo_id=model["repo_id"],
    filename=model["filename"],
    local_dir=model["local_dir"],
)

print(f"Model saved to: {model['local_dir']}")
print("Setup complete.")

if args.model == "30b":
    print()
    print("To use the 30B model, set:")
    print(f"  export AI_AGENT_MODEL_PATH={os.path.join(model['local_dir'], model['filename'])}")
    print("  export AI_AGENT_MODEL_N_CTX=16384")

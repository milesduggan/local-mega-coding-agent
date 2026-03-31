"""
Download Qwen2.5-Coder 7B-Instruct GGUF model for local inference.

Model: Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.5GB)
Source: Qwen/Qwen2.5-Coder-7B-Instruct-GGUF on Hugging Face
"""

import os
from huggingface_hub import hf_hub_download

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "qwen")
os.makedirs(MODEL_DIR, exist_ok=True)

print("Downloading Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.5GB)...")

hf_hub_download(
    repo_id="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
    filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
    local_dir=MODEL_DIR,
)

print(f"Model saved to: {MODEL_DIR}")
print("Setup complete.")

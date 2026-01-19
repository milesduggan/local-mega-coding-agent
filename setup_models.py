from huggingface_hub import login, hf_hub_download
import os

hf_hub_download(
    repo_id="TheBloke/deepseek-coder-6.7B-instruct-GGUF",
    filename="deepseek-coder-6.7b-instruct.Q2_K.gguf",
    local_dir="models/deepseek"
)


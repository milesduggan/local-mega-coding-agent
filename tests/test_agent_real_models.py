from scripts.agent.main import agent_loop
from scripts.backend.local_models import LocalLlama, LocalDeepSeek


LLAMA_MODEL = "models/llama/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
DEEPSEEK_MODEL = "models/deepseek/deepseek-coder-6.7b-instruct.Q2_K.gguf"


llama = LocalLlama(LLAMA_MODEL)
deepseek = LocalDeepSeek(DEEPSEEK_MODEL)

files = {
    "example.py": "def add(a, b):\n    return a + b\n"
}

result = agent_loop(
    "Proceed with implementation: add input validation to add(a, b)",
    files,
    llama,
    deepseek
)

print(result)

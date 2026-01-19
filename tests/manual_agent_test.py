from scripts.agent.main import agent_loop
from scripts.backend.local_models import LocalLlama, LocalDeepSeek

files = {
    "example.py": "def add(a, b):\n    return a + b\n"
}

llama = LocalLlama("models/llama/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
deepseek = LocalDeepSeek("models/deepseek/deepseek-coder-6.7b-instruct.Q2_K.gguf")

task = """Proceed with implementation.

File: example.py
Function: add(a, b)

Implementation requirements:
- Insert code at the very start of add(a, b).
- If a is not an instance of int or float, raise TypeError.
- If b is not an instance of int or float, raise TypeError.
- Do not add helper functions.
- Do not modify any other lines.
- Do not add or remove files.
"""

result = agent_loop(task, files, llama, deepseek)
print(result)

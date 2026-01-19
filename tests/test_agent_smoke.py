from scripts.agent.main import agent_loop


def fake_llama(prompt: str) -> str:
    return """EXECUTION BRIEF

GOAL
- Add input validation to add(a, b)

CONSTRAINTS
- Raise TypeError on non-numeric input

FILES
- example.py
"""


def fake_deepseek(prompt: str) -> str:
    return ""


files = {
    "example.py": "def add(a, b):\n    return a + b\n"
}

result = agent_loop(
    "Proceed with implementation",
    files,
    fake_llama,
    fake_deepseek
)

print(result)

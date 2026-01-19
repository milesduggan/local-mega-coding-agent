import difflib
from typing import Dict, Callable


EXECUTOR_SYSTEM_INSTRUCTION = """
You are a code transformation engine.

Given:
- an execution brief
- file contents

Produce:
- a unified diff implementing the requested changes

Rules:
- Do not explain
- Do not add unrelated changes
- Do not modify files not listed
- Output unified diff ONLY
""".strip()


class DeepSeekExecutor:
    def __init__(self, model_call: Callable[[str], str]):
        self.model_call = model_call

    def execute(self, execution_brief: str, files: Dict[str, str]) -> str:
        prompt = self._build_prompt(execution_brief, files)
        response = self.model_call(prompt)
        return self._extract_diff(response)

    def _build_prompt(self, brief: str, files: Dict[str, str]) -> str:
        parts = [EXECUTOR_SYSTEM_INSTRUCTION, "", brief, "", "FILES"]

        for name, content in files.items():
            parts.append(f"--- {name}")
            parts.append(content)

        return "\n".join(parts)

    def _extract_diff(self, text: str) -> str:
        # Trust model to output diff only (enforced by review layer)
        return text.strip()

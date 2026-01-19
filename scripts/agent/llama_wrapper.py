import re
from scripts.agent.token_monitor import TokenMonitor


EXECUTION_BRIEF_INSTRUCTION = """
You must output one or more EXECUTION BRIEFs OR ask concise clarification questions.

FORMAT:

EXECUTION BRIEF

GOAL
- <one sentence>

CONSTRAINTS
- <bullet list>

FILES
- <explicit list>

Rules:
- If clarification is required, ask questions and do NOT emit an execution brief.
- If multiple execution briefs are produced, the first valid brief will be selected.
- Do not explain.
- Do not apologize.
""".strip()


class LlamaWrapper:
    def __init__(self, model_call, max_tokens: int = 16000):
        self.model_call = model_call
        self.monitor = TokenMonitor(max_tokens)

    def handle(self, user_input: str) -> str:
        self.monitor.add(user_input)

        prompt = EXECUTION_BRIEF_INSTRUCTION + "\n\nUSER INPUT:\n" + user_input
        response = self.model_call(prompt)
        self.monitor.add(response)

        return self._select_first_brief_or_clarify(response)

    def _select_first_brief_or_clarify(self, text: str) -> str:
        # If no execution brief appears, treat as clarification
        if "EXECUTION BRIEF" not in text:
            return text.strip()

        # Select the first execution brief deterministically
        start = text.find("EXECUTION BRIEF")
        return text[start:].strip()

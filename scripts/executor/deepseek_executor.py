"""
DeepSeek executor - outputs full updated file contents.
System synthesizes diffs locally. DeepSeek never emits diffs.
"""


class DeepSeekExecutor:
    def __init__(self, call_model):
        self.call_model = call_model

    def _build_prompt(self, brief: str, files: dict) -> str:
        """
        Build prompt requesting full updated file contents.
        DeepSeek must NOT emit diffs, markdown, or commentary.
        """
        files_section = ""
        for filename, content in files.items():
            files_section += f"FILE: {filename}\n{content}\n\n"

        return f"""You are a code transformation engine.

TASK:
Apply the following EXECUTION BRIEF to the provided files.

STRICT OUTPUT RULES (MANDATORY):
- Output ONLY the full updated contents of each modified file.
- Use this EXACT format for each file:

FILE: <relative/path/filename>
<full updated file contents>

- One FILE block per modified file.
- Do NOT include markdown.
- Do NOT include code blocks.
- Do NOT include explanations.
- Do NOT include commentary.
- Do NOT include diffs.
- Output ONLY the FILE blocks with updated contents.

If a file is not modified, do NOT include it in output.

EXECUTION BRIEF:
{brief}

FILES:
{files_section}"""

    def execute(self, brief: str, files: dict) -> str:
        """
        Execute the brief and return raw DeepSeek output.
        Output contains full file contents in FILE: format.
        Caller is responsible for parsing and diff synthesis.
        """
        prompt = self._build_prompt(brief, files)
        result = self.call_model(prompt)
        return result.strip()

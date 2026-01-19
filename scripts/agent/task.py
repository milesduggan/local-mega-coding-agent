from dataclasses import dataclass
from typing import Optional, List


class TaskError(Exception):
    pass


@dataclass(frozen=True)
class AgentTask:
    task: str
    instructions: Optional[str]
    files: List[str]

    @staticmethod
    def from_text(text: str) -> "AgentTask":
        if not text or not text.strip():
            raise TaskError("Task input is empty.")

        sections = {
            "GOAL": None,
            "CONSTRAINTS": None,
            "FILES": None,
        }

        current = None
        buffer = []

        def flush():
            nonlocal buffer
            if current:
                sections[current] = "\n".join(buffer).strip()
            buffer = []

        lines = [l.rstrip() for l in text.splitlines()]

        if not lines or lines[0].strip() != "EXECUTION BRIEF":
            raise TaskError("Missing EXECUTION BRIEF header.")

        for line in lines[1:]:
            if line in sections:
                flush()
                current = line
            else:
                buffer.append(line)

        flush()

        if not sections["GOAL"]:
            raise TaskError("Missing GOAL section.")

        if not sections["FILES"]:
            raise TaskError("Missing FILES section.")

        files = [f.strip("- ").strip() for f in sections["FILES"].splitlines() if f.strip()]

        return AgentTask(
            task=sections["GOAL"],
            instructions=sections["CONSTRAINTS"],
            files=files,
        )

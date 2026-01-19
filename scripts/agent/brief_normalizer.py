import re

def normalize_brief(text: str) -> str:
    # Keep only the first EXECUTION BRIEF block
    start = text.find("EXECUTION BRIEF")
    if start == -1:
        return text.strip()

    brief = text[start:]

    # Remove fenced code blocks
    brief = re.sub(r"```.*?```", "", brief, flags=re.DOTALL)

    # Collapse excessive whitespace
    brief = re.sub(r"\n{3,}", "\n\n", brief)

    return brief.strip()

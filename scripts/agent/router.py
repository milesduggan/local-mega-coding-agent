import re
from dataclasses import dataclass
from typing import List, Optional

from scripts.tools.registry import get_registry


@dataclass
class ToolMatch:
    name: str
    score: float
    description: str


class Router:
    def score(self, user_input: Optional[str]) -> List[ToolMatch]:
        if not user_input or not str(user_input).strip():
            return []

        tokens = set(re.findall(r'\w+', user_input.lower()))
        if not tokens:
            return []

        registry = get_registry()
        tools = registry.list_tools()

        matches: List[ToolMatch] = []
        for tool in tools:
            name = tool.get("name", "")
            desc = tool.get("description", "")
            tool_tokens = set(re.findall(r'\w+', (name + " " + desc).lower()))
            overlap = len(tokens & tool_tokens)
            if overlap > 0:
                score = overlap / max(len(tokens), 1)
                matches.append(ToolMatch(name=name, score=score, description=desc))

        return sorted(matches, key=lambda m: m.score, reverse=True)

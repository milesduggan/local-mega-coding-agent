from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HistoryEvent:
    title: str
    detail: str


class HistoryLog:
    def __init__(self) -> None:
        self._events: List[HistoryEvent] = []

    def add(self, title: str, detail: str) -> None:
        self._events.append(HistoryEvent(title=title, detail=detail))

    def to_list(self) -> List[Dict[str, str]]:
        return [{"title": e.title, "detail": e.detail} for e in self._events]

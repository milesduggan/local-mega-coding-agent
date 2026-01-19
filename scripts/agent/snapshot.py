from dataclasses import dataclass
from typing import List

REQUIRED_SECTIONS = [
    "DECISION STATE SNAPSHOT",
    "AGENT ROLE",
    "OPERATING MODE",
    "DECISION AUTHORITY",
    "IMPLEMENTATION CONSTRAINTS",
    "EXPLICIT NON-GOALS",
]

class SnapshotError(Exception):
    pass


@dataclass(frozen=True)
class DecisionSnapshot:
    raw_text: str

    def validate(self) -> None:
        if not self.raw_text or not self.raw_text.strip():
            raise SnapshotError("Decision-State Snapshot is empty or missing.")

        missing: List[str] = []
        for section in REQUIRED_SECTIONS:
            if section not in self.raw_text:
                missing.append(section)

        if missing:
            raise SnapshotError(
                "Decision-State Snapshot is invalid. Missing sections: "
                + ", ".join(missing)
            )

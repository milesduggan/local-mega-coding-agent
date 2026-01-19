from dataclasses import dataclass
from typing import List


@dataclass
class ReviewResult:
    passed: bool
    reasons: List[str]


def review(task: str, diff: str) -> ReviewResult:
    reasons: List[str] = []

    if not diff or not diff.strip():
        reasons.append("Diff is empty. No changes proposed.")

    # Fail on formatting-only changes
    lines = diff.splitlines()
    added = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in lines if l.startswith("-") and not l.startswith("---")]

    if added or removed:
        non_code = all(
            l.strip().replace("+", "").replace("-", "").strip() == ""
            for l in added + removed
        )
        if non_code:
            reasons.append("Diff contains formatting-only changes.")

    return ReviewResult(
        passed=len(reasons) == 0,
        reasons=reasons
    )

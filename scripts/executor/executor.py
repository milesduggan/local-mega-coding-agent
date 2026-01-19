import difflib
from typing import Dict


class ExecutionError(Exception):
    pass


def execute(task: str, files: Dict[str, str]) -> str:
    """
    Executes a coding task against provided files and returns a unified diff.
    This function MUST NOT write to disk or mutate inputs.
    """
    if not task or not task.strip():
        raise ExecutionError("Task is empty.")

    if not files:
        raise ExecutionError("No files provided to executor.")

    # Placeholder implementation:
    # This is intentionally minimal. Real code generation will be delegated
    # to the LLM later. For now, this enforces diff-only behavior.

    diffs = []

    for filename, original in files.items():
        # No-op change (example scaffold)
        modified = original

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=filename,
            tofile=filename,
        )

        diffs.extend(diff)

    return "".join(diffs)

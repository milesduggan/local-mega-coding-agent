"""
Executor module - synthesizes diffs locally from DeepSeek output.

Flow:
1. Receive task and original files
2. Call DeepSeek to get full updated file contents
3. Parse DeepSeek output into file blocks
4. Generate unified diffs via difflib (original vs updated)
5. Return combined diff for review gate

DeepSeek never emits diffs. All diff generation is deterministic and local.
"""

import difflib
import os
import re
from typing import Dict, Optional, Tuple

from llama_cpp import Llama


class ExecutionError(Exception):
    """Raised when execution fails explicitly."""
    pass


# Module-level model instance (lazy loaded)
_deepseek_llm: Optional[Llama] = None

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
_DEEPSEEK_MODEL_PATH = os.path.join(
    _PROJECT_ROOT, "models", "deepseek", "deepseek-coder-6.7b-instruct.Q2_K.gguf"
)


def _get_deepseek() -> Llama:
    """Get or initialize DeepSeek model."""
    global _deepseek_llm
    if _deepseek_llm is None:
        if not os.path.exists(_DEEPSEEK_MODEL_PATH):
            raise ExecutionError(
                f"DeepSeek model not found: {_DEEPSEEK_MODEL_PATH}\n"
                "Run setup_models.py to download the model."
            )
        _deepseek_llm = Llama(
            model_path=_DEEPSEEK_MODEL_PATH,
            n_ctx=16384,
            n_threads=8,
            verbose=False,
        )
    return _deepseek_llm


def _call_deepseek(prompt: str) -> str:
    """Call DeepSeek model and return response text."""
    llm = _get_deepseek()
    response = llm(
        prompt,
        max_tokens=4096,
        temperature=0.2,
        stop=["</s>", "<|EOT|>"],
    )
    text = response["choices"][0]["text"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _build_prompt(brief: str, files: Dict[str, str]) -> str:
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


def _parse_file_blocks(output: str, allowed_files: set) -> Dict[str, str]:
    """
    Parse DeepSeek output into {filename: content} dict.
    Validates against allowed_files set and detects duplicates.

    Expected format:
    FILE: path/to/file.py
    <file contents>

    FILE: path/to/other.py
    <file contents>

    Raises ExecutionError if:
    - A FILE: block references an unknown file (hallucination guard)
    - Duplicate FILE: blocks for the same file are detected
    """
    result = {}
    seen_files = set()

    # Split on FILE: markers
    pattern = r'^FILE:\s*(.+?)$'
    parts = re.split(pattern, output, flags=re.MULTILINE)

    # parts[0] is any text before first FILE:
    # then alternating: filename, content, filename, content, ...
    if len(parts) < 3:
        # No valid FILE: blocks found
        return result

    i = 1
    while i < len(parts) - 1:
        filename = parts[i].strip()
        content = parts[i + 1]

        if not filename:
            i += 2
            continue

        # GUARDRAIL: Check for duplicate FILE blocks
        if filename in seen_files:
            raise ExecutionError(
                f"Duplicate FILE block detected for '{filename}'. "
                "Each file may only appear once in DeepSeek output."
            )
        seen_files.add(filename)

        # GUARDRAIL: Check if file is in allowed set (hallucination guard)
        if filename not in allowed_files:
            raise ExecutionError(
                f"DeepSeek referenced unknown file '{filename}'. "
                f"Allowed files: {sorted(allowed_files)}. "
                "New file creation is not permitted unless explicitly allowed."
            )

        # Clean up content: remove leading/trailing whitespace but preserve internal structure
        # Remove only the first newline after filename and trailing whitespace
        content = content.strip('\n')
        if content.endswith('\n\n'):
            content = content[:-1]  # Remove one trailing newline

        result[filename] = content

        i += 2

    return result


def _generate_unified_diff(filename: str, original: str, modified: str) -> str:
    """
    Generate unified diff for a single file.
    Uses difflib for deterministic, local diff generation.
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    # Ensure files end with newline for proper diff format
    if original_lines and not original_lines[-1].endswith('\n'):
        original_lines[-1] += '\n'
    if modified_lines and not modified_lines[-1].endswith('\n'):
        modified_lines[-1] += '\n'

    diff_lines = list(difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=filename,
        tofile=filename,
    ))

    return ''.join(diff_lines)


def _synthesize_diffs(original_files: Dict[str, str], updated_files: Dict[str, str]) -> str:
    """
    Synthesize unified diffs by comparing original files to updated files.
    Each modified file produces its own diff block with proper headers.
    """
    diffs = []

    for filename, updated_content in updated_files.items():
        if filename not in original_files:
            # File not in original set - skip with warning
            continue

        original_content = original_files[filename]

        # Skip if no changes
        if original_content == updated_content:
            continue

        diff = _generate_unified_diff(filename, original_content, updated_content)
        if diff:
            diffs.append(diff)

    return '\n'.join(diffs)


def execute(task: str, files: Dict[str, str]) -> str:
    """
    Execute a coding task against provided files and return a unified diff.

    Flow:
    1. Validate inputs
    2. Call DeepSeek for full updated file contents
    3. Parse file blocks from output
    4. Synthesize unified diffs locally via difflib
    5. Return diff for review gate

    This function MUST NOT write to disk or mutate inputs.
    All diff generation is deterministic and local.
    """
    # Validate inputs
    if not task or not task.strip():
        raise ExecutionError("Task is empty.")

    if not files:
        raise ExecutionError("No files provided to executor.")

    # Build prompt and call DeepSeek
    prompt = _build_prompt(task, files)
    raw_output = _call_deepseek(prompt)

    if not raw_output:
        raise ExecutionError("DeepSeek returned empty output.")

    # Build allowed files set from input
    allowed_files = set(files.keys())

    # Parse file blocks from output with strict validation
    # This will raise ExecutionError immediately if:
    # - Unknown file is referenced (hallucination)
    # - Duplicate FILE blocks detected
    updated_files = _parse_file_blocks(raw_output, allowed_files)

    # GUARDRAIL: Zero valid FILE blocks is a hard failure
    if not updated_files:
        raise ExecutionError(
            "DeepSeek produced zero valid FILE blocks. "
            "Expected format: FILE: <filename>\\n<contents>. "
            "Execution cannot proceed without file output."
        )

    # Synthesize unified diffs locally
    combined_diff = _synthesize_diffs(files, updated_files)

    if not combined_diff:
        raise ExecutionError(
            "No differences detected between original and updated files. "
            "Either the task produced no changes or parsing failed."
        )

    return combined_diff

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
from typing import Dict, Optional

from llama_cpp import Llama


class ExecutionError(Exception):
    """Raised when execution fails explicitly."""
    pass


# Module-level model instance (lazy loaded)
_deepseek_llm: Optional[Llama] = None

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
_DEEPSEEK_MODEL_PATH = os.path.join(
    _PROJECT_ROOT, "models", "deepseek", "deepseek-coder-6.7b-instruct.Q4_K_M.gguf"
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
            n_ctx=8192,   # Enough for typical file edits
            n_threads=4,
            verbose=False,
        )
    return _deepseek_llm


def _call_deepseek(prompt: str) -> str:
    """Call DeepSeek model using raw completion with Alpaca-style format."""
    llm = _get_deepseek()
    response = llm(
        prompt,
        max_tokens=1024,
        temperature=0.2,
        top_p=0.9,
        repeat_penalty=1.1,
        stop=["</s>", "<|EOT|>", "### Instruction", "### Explanation"],
    )
    text = response["choices"][0]["text"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _build_prompt(brief: str, files: Dict[str, str]) -> str:
    """
    Build prompt using Alpaca-style format that DeepSeek follows well.
    For multiple files, we process each one with a clear FILE: marker.
    """
    files_section = "\n\n".join(f"FILE: {f}\n{c}" for f, c in files.items())

    return f"""### Instruction:
Apply the following task to the provided files. Output ONLY the complete modified file contents.
Use this exact format for each file you modify:

FILE: <path>
<complete file contents>

Do not include explanations, markdown, or any other text.

### Task:
{brief}

### Input Files:
{files_section}

### Response:
"""


def _extract_code_from_markdown(content: str) -> str:
    """Extract code from markdown code blocks if present."""
    # Match ```python or ``` followed by code and ending with ```
    pattern = r'```(?:python)?\s*\n(.*?)```'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Remove any trailing markdown artifacts
    content = re.sub(r'\n*```(?:python)?$', '', content)
    return content


def _parse_file_blocks(output: str, allowed_files: set) -> Dict[str, str]:
    """
    Parse DeepSeek output into {filename: content} dict.
    Validates against allowed_files set and handles markdown code blocks.

    Expected format:
    FILE: path/to/file.py
    <file contents>  OR  ```python\n<file contents>\n```

    Only takes the FIRST occurrence of each file (ignores duplicates).
    Raises ExecutionError if unknown file is referenced.
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

        # Skip duplicates (take first occurrence only)
        if filename in seen_files:
            i += 2
            continue
        seen_files.add(filename)

        # GUARDRAIL: Check if file is in allowed set (hallucination guard)
        if filename not in allowed_files:
            raise ExecutionError(
                f"DeepSeek referenced unknown file '{filename}'. "
                f"Allowed files: {sorted(allowed_files)}. "
                "New file creation is not permitted unless explicitly allowed."
            )

        # Extract code from markdown blocks if present
        content = _extract_code_from_markdown(content)

        # Clean up content
        content = content.strip('\n')
        if content.endswith('\n\n'):
            content = content[:-1]

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

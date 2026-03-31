"""
Executor module - synthesizes diffs locally from model output.

Flow:
1. Receive task and original files
2. For Python files: parse into chunks, select relevant ones
3. Call the model with chunks (or full file for non-Python)
4. Parse output and reconstruct file
5. Generate unified diffs via difflib
6. Return combined diff for review gate

The model never emits diffs. All diff generation is deterministic and local.
"""

import ast
import difflib
import logging
import os
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

from llama_cpp import Llama

# Add project root to path for chunker imports
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.chunker.python_chunker import CodeChunk, parse_python_file
from scripts.chunker.selector import select_relevant_chunks
from scripts.chunker.reconstructor import reconstruct_from_llm_output, ReconstructionError
from scripts.config import (
    MODEL_N_CTX, MODEL_N_THREADS, MODEL_PATH,
    MODEL_CODE_MAX_TOKENS, MODEL_CODE_TEMPERATURE,
    MODEL_CODE_TOP_P, MODEL_CODE_REPEAT_PENALTY,
)
from scripts.backend.model_manager import get_manager, ModelType

log = logging.getLogger(__name__)

# =============================================================================
# Input Validation Limits (security hardening)
# =============================================================================
MAX_TASK_LENGTH = 10_000  # 10KB max task description
MAX_TOTAL_FILE_SIZE = 50_000_000  # 50MB total across all files
MAX_FILES = 100  # Maximum number of files per execution


class ExecutionError(Exception):
    """Raised when execution fails explicitly."""
    pass


# Register model with the ModelManager
_manager = get_manager()


def _create_model() -> Llama:
    """Factory function to create the model instance."""
    return Llama(
        model_path=MODEL_PATH,
        n_ctx=MODEL_N_CTX,
        n_threads=MODEL_N_THREADS,
        verbose=False,
    )


try:
    _manager.register_model(
        ModelType.MAIN,
        MODEL_PATH,
        {"n_ctx": MODEL_N_CTX, "n_threads": MODEL_N_THREADS},
        _create_model
    )
except Exception:
    pass  # Already registered by critic.py — same singleton


def _get_model() -> Llama:
    """Get the model via ModelManager (lazy loading, access tracking)."""
    return _manager.get_model(ModelType.MAIN)


def warm_up() -> bool:
    """
    Pre-load the model into memory.
    Called during extension activation to eliminate first-request latency.
    Returns True if model loaded successfully.
    """
    try:
        _manager.get_model(ModelType.MAIN)
        return True
    except FileNotFoundError as e:
        log.error(f"Model file not found: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to load model: {type(e).__name__}: {e}")
        return False


def unload() -> bool:
    """
    Unload the model to free memory.
    Returns True if model was unloaded, False if not loaded.
    """
    return _manager.unload_model(ModelType.MAIN)


def is_loaded() -> bool:
    """Check if the model is currently loaded."""
    return _manager.is_loaded(ModelType.MAIN)


def _call_model(prompt: str) -> str:
    """Call model using raw completion with Alpaca-style format."""
    llm = _get_model()
    response = llm(
        prompt,
        max_tokens=MODEL_CODE_MAX_TOKENS,
        temperature=MODEL_CODE_TEMPERATURE,
        top_p=MODEL_CODE_TOP_P,
        repeat_penalty=MODEL_CODE_REPEAT_PENALTY,
        stop=["</s>", "<|EOT|>", "### Instruction", "### Explanation"],
    )

    # Validate response structure before accessing
    if not response or not isinstance(response, dict):
        raise ExecutionError("model returned invalid response structure")

    choices = response.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        raise ExecutionError("model returned no choices in response")

    first_choice = choices[0]
    if not isinstance(first_choice, dict) or "text" not in first_choice:
        raise ExecutionError("model response missing 'text' field")

    text = first_choice["text"].strip()
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _build_prompt(brief: str, files: Dict[str, str]) -> str:
    """
    Build prompt using Alpaca-style format that the model follows well.
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


def _build_chunk_prompt(task: str, filename: str, chunks: List[CodeChunk]) -> str:
    """
    Build prompt for chunk-based editing.
    Only sends relevant chunks instead of full file.
    """
    chunks_section = "\n\n".join(
        f"CHUNK: {c.name} ({c.chunk_type}, lines {c.start_line}-{c.end_line})\n{c.content}"
        for c in chunks
    )

    return f"""### Instruction:
Modify the following code chunks to complete the task. Output ONLY the modified chunks.
Use this exact format for each chunk you modify:

CHUNK: <chunk_name>
<complete chunk contents>

Output only chunks that need changes. Do not include explanations or markdown.

### Task:
{task}

### Chunks from {filename}:
{chunks_section}

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
    Parse model output into {filename: content} dict.
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

        # GUARDRAIL: Validate filename is safe (path traversal prevention)
        parsed_path = pathlib.PurePath(filename)
        if parsed_path.is_absolute():
            raise ExecutionError(
                f"Absolute paths not allowed in output: '{filename}'. "
                "Model must only reference relative file paths."
            )
        if ".." in parsed_path.parts:
            raise ExecutionError(
                f"Path traversal not allowed in output: '{filename}'. "
                "Model must not use '..' in file paths."
            )

        # GUARDRAIL: Check if file is in allowed set (hallucination guard)
        if filename not in allowed_files:
            raise ExecutionError(
                f"model referenced unknown file '{filename}'. "
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


def _execute_chunked(task: str, filename: str, content: str) -> Optional[str]:
    """
    Execute task using chunk-based approach for a single Python file.

    Returns updated file content, or None if chunking fails/isn't applicable.
    """
    try:
        # Parse file into chunks
        all_chunks = parse_python_file(content, filename)
        if not all_chunks:
            log.info(f"No chunks extracted from {filename}, falling back to full-file")
            return None

        # Select relevant chunks
        relevant_chunks = select_relevant_chunks(task, all_chunks)
        if not relevant_chunks:
            log.info(f"No relevant chunks found for task, falling back to full-file")
            return None

        # Log token savings
        full_tokens = len(content) // 4
        chunk_tokens = sum(len(c.content) // 4 for c in relevant_chunks)
        savings = ((full_tokens - chunk_tokens) / full_tokens * 100) if full_tokens > 0 else 0
        log.info(
            f"Chunk-based execution: {len(relevant_chunks)}/{len(all_chunks)} chunks, "
            f"~{savings:.0f}% token savings"
        )

        # Build chunk prompt and call model
        prompt = _build_chunk_prompt(task, filename, relevant_chunks)
        raw_output = _call_model(prompt)

        if not raw_output:
            log.warning("model returned empty output for chunk-based execution")
            return None

        # Reconstruct file from chunk output
        updated_content = reconstruct_from_llm_output(content, all_chunks, raw_output)
        return updated_content

    except SyntaxError as e:
        log.info(f"Failed to parse {filename} (syntax error), falling back to full-file: {e}")
        return None
    except ReconstructionError as e:
        log.warning(f"Chunk reconstruction failed for {filename}, falling back to full-file: {e}")
        return None
    except Exception as e:
        log.warning(f"Chunk-based execution failed for {filename}: {e}")
        return None


def execute(task: str, files: Dict[str, str]) -> str:
    """
    Execute a coding task against provided files and return a unified diff.

    Flow:
    1. Validate inputs
    2. For Python files: try chunk-based execution (fewer tokens)
    3. Fallback to full-file for non-Python or if chunking fails
    4. Synthesize unified diffs locally via difflib
    5. Return diff for review gate

    This function MUST NOT write to disk or mutate inputs.
    All diff generation is deterministic and local.
    """
    # Validate inputs
    if not task or not task.strip():
        raise ExecutionError("Task is empty.")

    if len(task) > MAX_TASK_LENGTH:
        raise ExecutionError(
            f"Task too long ({len(task):,} chars, max {MAX_TASK_LENGTH:,}). "
            "Please simplify the task description."
        )

    if not files:
        raise ExecutionError("No files provided to executor.")

    if len(files) > MAX_FILES:
        raise ExecutionError(
            f"Too many files ({len(files)}, max {MAX_FILES}). "
            "Please reduce the number of files."
        )

    total_size = sum(len(content) for content in files.values())
    if total_size > MAX_TOTAL_FILE_SIZE:
        raise ExecutionError(
            f"Total file size too large ({total_size / 1_000_000:.1f}MB, max 50MB). "
            "Please reduce the amount of code."
        )

    updated_files: Dict[str, str] = {}
    files_needing_full_execution: Dict[str, str] = {}

    # Try chunk-based execution for Python files
    for filename, content in files.items():
        if filename.endswith('.py'):
            updated = _execute_chunked(task, filename, content)
            if updated is not None:
                updated_files[filename] = updated
            else:
                files_needing_full_execution[filename] = content
        else:
            files_needing_full_execution[filename] = content

    # Full-file execution for remaining files
    if files_needing_full_execution:
        prompt = _build_prompt(task, files_needing_full_execution)
        raw_output = _call_model(prompt)

        if not raw_output:
            raise ExecutionError("model returned empty output for full-file execution.")

        # Build allowed files set from files needing full execution
        allowed_files = set(files_needing_full_execution.keys())

        # Parse file blocks from output with strict validation
        full_file_updates = _parse_file_blocks(raw_output, allowed_files)

        # GUARDRAIL: Validate syntax of generated Python files before proceeding
        for filename, content in full_file_updates.items():
            if filename.endswith('.py'):
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    raise ExecutionError(
                        f"Generated code for '{filename}' has invalid syntax "
                        f"(line {e.lineno}): {e.msg}\n"
                        "The model produced malformed code. Please try again or simplify the task."
                    )

        if not full_file_updates:
            raise ExecutionError(
                "model produced zero valid FILE blocks. "
                "Expected format: FILE: <filename>\\n<contents>. "
                "Execution cannot proceed without file output."
            )

        # Merge with chunk-based updates
        updated_files.update(full_file_updates)

    # GUARDRAIL: At least one file must have been updated
    if not updated_files:
        raise ExecutionError(
            "No files were updated. "
            "Either the task produced no changes or all execution paths failed."
        )

    # Synthesize unified diffs locally
    combined_diff = _synthesize_diffs(files, updated_files)

    if not combined_diff:
        raise ExecutionError(
            "No differences detected between original and updated files. "
            "Either the task produced no changes or parsing failed."
        )

    return combined_diff

"""
Select relevant chunks based on task description.

Uses keyword matching to identify which chunks are likely relevant
to a given task, reducing token usage for LLM calls.
"""

import os
import re
import sys
from typing import List, Optional, Set

from .python_chunker import CodeChunk

# Add project root to path for config import
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.config import CHUNK_MAX_TOKENS


def _estimate_tokens(text: str) -> int:
    """
    Rough token estimate (words + punctuation).
    More accurate than character count, less overhead than tiktoken.
    """
    # Roughly 1 token per 4 chars for code
    return len(text) // 4


def _extract_identifiers(task: str) -> Set[str]:
    """
    Extract potential identifiers from a task description.
    Looks for:
    - Words in backticks: `function_name`
    - CamelCase words: MyClass
    - snake_case words: my_function
    - Quoted strings: "name" or 'name'
    """
    identifiers = set()

    # Backtick-quoted identifiers (highest signal)
    backtick_matches = re.findall(r'`([a-zA-Z_][a-zA-Z0-9_]*)`', task)
    identifiers.update(backtick_matches)

    # Quoted identifiers
    quote_matches = re.findall(r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']', task)
    identifiers.update(quote_matches)

    # CamelCase words (likely class names)
    camel_matches = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', task)
    identifiers.update(camel_matches)

    # snake_case words (likely function names)
    snake_matches = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b', task)
    identifiers.update(snake_matches)

    # Single words that look like identifiers (after common words filtered)
    common_words = {
        'the', 'a', 'an', 'to', 'for', 'in', 'on', 'at', 'by', 'with',
        'add', 'remove', 'update', 'change', 'modify', 'fix', 'create',
        'function', 'class', 'method', 'file', 'code', 'line', 'lines',
        'import', 'from', 'return', 'def', 'if', 'else', 'and', 'or',
        'this', 'that', 'it', 'is', 'are', 'be', 'was', 'were', 'been',
        'all', 'each', 'every', 'some', 'any', 'no', 'not', 'only',
        'new', 'old', 'first', 'last', 'next', 'previous'
    }
    words = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', task)
    for word in words:
        if word.lower() not in common_words and len(word) > 2:
            identifiers.add(word)

    return identifiers


def select_relevant_chunks(
    task: str,
    chunks: List[CodeChunk],
    max_tokens: Optional[int] = None
) -> List[CodeChunk]:
    """
    Select chunks relevant to the task.

    Strategy:
    1. Extract identifiers from task description
    2. Score each chunk by:
       - Direct name match (highest)
       - Name mentioned in task (high)
       - Dependency overlap (medium)
    3. Always include imports
    4. Include chunks up to token budget, prioritized by score

    Args:
        task: Task description
        chunks: All chunks from the file
        max_tokens: Approximate token budget

    Returns:
        List of relevant chunks, sorted by start_line
    """
    if not chunks:
        return []

    # Use config default if not specified
    if max_tokens is None:
        max_tokens = CHUNK_MAX_TOKENS

    identifiers = _extract_identifiers(task)
    task_lower = task.lower()

    # Score each chunk
    scored_chunks: List[tuple[float, CodeChunk]] = []

    for chunk in chunks:
        score = 0.0

        # Imports always get included (low score but guaranteed)
        if chunk.chunk_type == "imports":
            score = 0.1  # Will be force-included anyway
            scored_chunks.append((score, chunk))
            continue

        # Direct name match in identifiers (highest priority)
        if chunk.name in identifiers:
            score += 10.0

        # Name mentioned in task (case-insensitive)
        if chunk.name.lower() in task_lower:
            score += 8.0

        # Partial name match (e.g., task mentions "execute" and chunk is "_call_execute")
        for ident in identifiers:
            if ident.lower() in chunk.name.lower() or chunk.name.lower() in ident.lower():
                score += 3.0
                break

        # Dependencies overlap with identifiers
        chunk_deps_lower = {d.lower() for d in chunk.dependencies}
        ident_lower = {i.lower() for i in identifiers}
        overlap = chunk_deps_lower & ident_lower
        if overlap:
            score += len(overlap) * 1.0

        # Boost classes slightly (often contain relevant methods)
        if chunk.chunk_type == "class" and score > 0:
            score += 1.0

        scored_chunks.append((score, chunk))

    # Sort by score descending
    scored_chunks.sort(key=lambda x: -x[0])

    # Select chunks within token budget
    selected: List[CodeChunk] = []
    current_tokens = 0

    # First pass: always include imports
    for score, chunk in scored_chunks:
        if chunk.chunk_type == "imports":
            tokens = _estimate_tokens(chunk.content)
            selected.append(chunk)
            current_tokens += tokens

    # Second pass: add scored chunks
    for score, chunk in scored_chunks:
        if chunk.chunk_type == "imports":
            continue  # Already added

        if score <= 0:
            continue  # Not relevant

        tokens = _estimate_tokens(chunk.content)
        if current_tokens + tokens > max_tokens:
            # Check if this is a high-priority chunk that should be included anyway
            if score >= 8.0:
                # Important chunk - include it even if over budget
                selected.append(chunk)
                current_tokens += tokens
            continue

        selected.append(chunk)
        current_tokens += tokens

    # Sort by start_line for reconstruction
    selected.sort(key=lambda c: c.start_line)

    return selected


if __name__ == "__main__":
    # Quick test
    from .python_chunker import parse_python_file

    test_code = '''
import os
import sys

def helper_func():
    pass

def execute(task, files):
    """Execute a task."""
    result = helper_func()
    return result

class MyClass:
    def method(self):
        pass
'''

    chunks = parse_python_file(test_code, "test.py")
    print("All chunks:")
    for c in chunks:
        print(f"  {c.name} ({c.chunk_type})")

    task = "Add logging to the execute function"
    selected = select_relevant_chunks(task, chunks)
    print(f"\nSelected for task '{task}':")
    for c in selected:
        print(f"  {c.name} ({c.chunk_type})")
